"""AI-generated plain-English site summary (Claude Haiku).

Federal databases ship structured fields — name, status, acreage, infra
proximity, document lists, enforcement counters. Even with everything in
front of them, a buyer still has to mentally synthesize "is this site
worth a closer look?". This connector hands that synthesis off to Claude
Haiku and writes a 3-paragraph plain-English narrative per site:

  ¶1 — What the site is (program, status, scale, location).
  ¶2 — Reuse signals (infrastructure proximity, document trail, ownership).
  ¶3 — Material risks (enforcement, contamination, completeness gaps).

The summary is **cached by content-hash of the input fields**: re-running
this connector with no upstream data changes is a no-op. Only sites whose
structured fields actually changed get re-billed. Combined with the small
Haiku model, full coverage of the policy-relevant universe (~1,900 Final +
Deleted Superfund sites) costs cents.

Output shape (per site): `{id, summary, summary_meta: {model, hash, generated_at}}`.

CLI:
    export ANTHROPIC_API_KEY=sk-ant-...
    python refresh.py --source ai-summary                    # default 100 sites/run
    python refresh.py --source ai-summary --ai-limit 500
    python refresh.py --source ai-summary --dry-run          # cache-only, no API key needed

`--dry-run` and `--fetch-only` work without an API key (per CLAUDE.md AI
cost-optimization principles).

References:
- Claude Haiku 4.5 model id: `claude-haiku-4-5-20251001` (cheapest current Claude tier).
- Anthropic SDK docs: https://docs.anthropic.com/en/api/messages
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

from connectors.base import Connector

log = logging.getLogger("connector.ai_summary")

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_LIMIT = 100
DEFAULT_MAX_TOKENS = 600

# Sites that don't carry the inputs we need for a meaningful summary aren't
# worth a paid call. We require at least a name and (program OR state).
SYSTEM_PROMPT = """You are a brownfield real-estate analyst writing for property buyers and developers evaluating contaminated-land opportunities.

Given the structured fields for a single federal contaminated site, write exactly three short paragraphs (40–70 words each) in plain English:

1. **What it is.** Identify the program, current regulatory status, scale (acreage), and location. Be specific — name the city/state and the program in human terms ("a Final-NPL Superfund site in Tacoma, WA").
2. **Reuse signals.** Highlight infrastructure proximity (transmission, rail, highway in miles; water/wastewater service area), the data-center reuse flag if present, document trail completeness (RODs, Five Year Reviews), and ownership clarity. If a relevant signal is missing, name it as a gap.
3. **Material risks.** Surface open enforcement actions, recent violations, large 5-year penalty totals, contamination scope cues from the name, or structural data gaps that would block a transaction. If genuinely no risks are visible, say "No material risks visible from federal data — direct due diligence required."

Rules:
- Three paragraphs. No headers, no bullets, no bold.
- Cite numbers with units ("0.4 miles to transmission", "$1.2M in 5-year penalties").
- Do not invent facts. If a field is absent, treat it as absent — never speculate.
- Neutral, dispassionate tone. No marketing language.
"""


def _fingerprint(site: dict[str, Any]) -> str:
    """Deterministic hash of the input fields the model sees.

    Used as the cache key — if any field below changes, we re-bill; if nothing
    changes, we serve the cached summary. Picks only fields that actually
    influence the narrative; ignores internal/display-only fields like
    `lat_real`, `_inset`, `city_raw` so cosmetic tweaks don't invalidate.
    """
    relevant = {
        k: site.get(k)
        for k in (
            "id", "program", "name", "state", "city", "county",
            "acreage", "npl_status", "npl_status_code",
            "federal_facility", "current_owner", "current_owner_source",
            "near_electric_transmission", "near_water_supply", "near_wastewater",
            "near_railroad", "near_highway", "pop_density",
            "transmission_mi", "rail_mi", "highway_mi",
            "data_center_reuse_candidate",
            "eligibility", "fuds_status", "component",
        )
    }
    # Document and enforcement summaries — fingerprint only the headline
    # counters so a date-sort tweak in document ordering doesn't invalidate.
    docs = site.get("documents") or []
    relevant["doc_count"] = len(docs)
    relevant["doc_categories"] = sorted({d.get("category") for d in docs if d.get("category")})
    enf = site.get("enforcement") or {}
    for k in (
        "inspections_5yr", "formal_actions_5yr", "informal_actions_5yr",
        "penalties_5yr_usd", "current_compliance", "last_violation_date",
    ):
        if k in enf:
            relevant[f"enf_{k}"] = enf[k]

    canonical = json.dumps(relevant, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_user_prompt(site: dict[str, Any]) -> str:
    """Compose the per-site user message — a structured field dump.

    Kept as labeled key:value lines (not raw JSON) so the model treats it
    as facts rather than a programmatic schema and writes more naturally.
    Empty fields are omitted to avoid the model hallucinating around them.
    """
    lines = [f"Site: {site.get('name') or '(unnamed)'}"]
    program_label = {
        "superfund": "EPA Superfund (NPL)",
        "brownfield": "EPA Brownfield (ACRES)",
        "fuds": "DOD Formerly Used Defense Site (FUDS)",
        "brac": "DOD Base Realignment & Closure (BRAC)",
    }.get(site.get("program"), site.get("program") or "—")
    lines.append(f"Program: {program_label}")

    loc_parts = [site.get("city"), site.get("county"), site.get("state")]
    loc = ", ".join(p for p in loc_parts if p)
    if loc:
        lines.append(f"Location: {loc}")

    if site.get("acreage") is not None:
        lines.append(f"Acreage: {site['acreage']:.1f} acres")
    if site.get("npl_status"):
        lines.append(f"NPL status: {site['npl_status']}")
    if site.get("federal_facility"):
        lines.append(f"Federal facility: {site['federal_facility']}")
    if site.get("eligibility"):
        lines.append(f"FUDS eligibility: {site['eligibility']}")
    if site.get("fuds_status"):
        lines.append(f"FUDS property status: {site['fuds_status']}")
    if site.get("component"):
        lines.append(f"Military component: {site['component']}")
    if site.get("current_owner"):
        src = site.get("current_owner_source") or "source"
        lines.append(f"Current owner: {site['current_owner']} (per {src})")

    # Universal infra distances (from infra-proximity connector).
    infra_bits = []
    if site.get("transmission_mi") is not None:
        infra_bits.append(f"transmission {site['transmission_mi']:.1f} mi")
    if site.get("rail_mi") is not None:
        infra_bits.append(f"rail {site['rail_mi']:.1f} mi")
    if site.get("highway_mi") is not None:
        infra_bits.append(f"highway {site['highway_mi']:.1f} mi")
    if infra_bits:
        lines.append("Nearest infrastructure: " + ", ".join(infra_bits))

    # EPA RE-Powering qualitative buckets (Superfund-only).
    qual = []
    if site.get("near_electric_transmission"):
        qual.append(f"power={site['near_electric_transmission']}")
    if site.get("near_water_supply"):
        qual.append(f"water={site['near_water_supply']}")
    if site.get("near_wastewater"):
        qual.append(f"wastewater={site['near_wastewater']}")
    if site.get("pop_density"):
        qual.append(f"density={site['pop_density']}")
    if qual:
        lines.append("EPA RE-Powering profile: " + "; ".join(qual))

    if site.get("data_center_reuse_candidate") is True:
        lines.append("Data-center reuse candidate: YES (≥50 ac + power + water)")
    elif site.get("data_center_reuse_candidate") is False:
        lines.append("Data-center reuse candidate: NO")

    docs = site.get("documents") or []
    if docs:
        cats = sorted({d.get("category") for d in docs if d.get("category")})
        lines.append(f"Federal documents on file: {len(docs)} ({', '.join(cats) or 'mixed'})")
        # Surface up to 3 most recent doc titles for context.
        sample = [d.get("title") for d in docs[:3] if d.get("title")]
        if sample:
            lines.append("Recent documents: " + " | ".join(sample[:3]))

    enf = site.get("enforcement") or {}
    if enf:
        bits = []
        if enf.get("inspections_5yr") is not None:
            bits.append(f"{enf['inspections_5yr']} inspections (5yr)")
        if enf.get("formal_actions_5yr") is not None:
            bits.append(f"{enf['formal_actions_5yr']} formal actions (5yr)")
        if enf.get("penalties_5yr_usd") is not None:
            bits.append(f"${enf['penalties_5yr_usd']:,.0f} in penalties (5yr)")
        if enf.get("current_compliance"):
            bits.append(f"compliance: {enf['current_compliance']}")
        if enf.get("last_violation_date"):
            bits.append(f"last violation {enf['last_violation_date']}")
        if bits:
            lines.append("Enforcement (EPA ECHO): " + "; ".join(bits))

    return "\n".join(lines)


class AiSummary(Connector):
    slug = "ai-summary"
    source_label = "AI-generated site summaries (Claude Haiku)"
    source_url = "https://www.anthropic.com/claude/haiku"

    # Reads docs/data/superfund-npl.json + enrichment files. Run after every
    # other producer + enrichment so the summary reflects the latest state.
    run_order = 400

    @classmethod
    def add_cli_args(cls, p: argparse.ArgumentParser) -> None:
        existing = {a.dest for a in p._actions}
        if "limit" not in existing:
            p.add_argument(
                "--limit",
                type=int,
                default=None,
                help="Cap the number of records (default: unlimited).",
            )
        p.add_argument(
            "--ai-limit",
            type=int,
            default=DEFAULT_LIMIT,
            help=f"Max sites to summarize per run (default: {DEFAULT_LIMIT}). "
                 "Cache makes incremental coverage cheap.",
        )
        p.add_argument(
            "--ai-skip",
            type=int,
            default=0,
            help="Skip the first N sites — for resumable batch coverage.",
        )
        p.add_argument(
            "--ai-status",
            default="F,D",
            help="Comma-separated NPL status codes to summarize (default: F,D — "
                 "Final + Deleted; the policy-relevant universe). "
                 "Use 'all' to ignore status.",
        )
        p.add_argument(
            "--ai-model",
            default=DEFAULT_MODEL,
            help=f"Anthropic model ID (default: {DEFAULT_MODEL}).",
        )
        p.add_argument(
            "--ai-max-tokens",
            type=int,
            default=DEFAULT_MAX_TOKENS,
            help=f"Per-summary max output tokens (default: {DEFAULT_MAX_TOKENS}).",
        )

    def fetch_records(
        self, args: argparse.Namespace, use_cache: bool
    ) -> list[dict[str, Any]]:
        sites = self._load_enriched_sites()
        if not sites:
            log.error(
                "no Superfund sites loaded — run --source superfund-npl first"
            )
            return []

        status_filter = self._parse_status_filter(getattr(args, "ai_status", "F,D"))
        if status_filter is not None:
            sites = [s for s in sites if s.get("npl_status_code") in status_filter]
            log.info("status filter %s: %d eligible sites",
                     sorted(status_filter), len(sites))

        sites.sort(
            key=lambda s: (
                s.get("acreage") is None,
                -(s.get("acreage") or 0),
                (s.get("name") or "").lower(),
            )
        )
        skip = max(0, getattr(args, "ai_skip", 0) or 0)
        take = getattr(args, "ai_limit", DEFAULT_LIMIT) or 0
        target_sites = sites[skip: skip + take] if take else sites[skip:]
        log.info("summarizing %d sites (skip=%d, take=%d)",
                 len(target_sites), skip, take or -1)

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        # `--dry-run` / `--fetch-only` should work without an API key — they
        # only consume cached responses or skip the write entirely.
        is_no_network = getattr(args, "dry_run", False)
        if not api_key and not is_no_network:
            log.error(
                "ANTHROPIC_API_KEY not set — required for ai-summary "
                "(use --dry-run for cache-only re-builds)"
            )
            return []

        model = getattr(args, "ai_model", DEFAULT_MODEL)
        max_tokens = getattr(args, "ai_max_tokens", DEFAULT_MAX_TOKENS)

        records: list[dict[str, Any]] = []
        cache_hits = 0
        cache_misses = 0
        skipped_no_input = 0

        for i, site in enumerate(target_sites, 1):
            sid = site.get("id")
            if not sid or not site.get("name"):
                skipped_no_input += 1
                continue
            fp = _fingerprint(site)
            cached = self._read_cached_summary(sid, fp)
            if cached is not None:
                cache_hits += 1
                records.append({
                    "id": sid,
                    "program": site.get("program") or "superfund",
                    "summary": cached["summary"],
                    "summary_meta": cached["summary_meta"],
                })
                continue
            if not api_key:
                # Cache miss but no API key — skip rather than abort.
                continue
            try:
                summary_text = self._call_anthropic(
                    site=site, api_key=api_key,
                    model=model, max_tokens=max_tokens,
                )
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else None
                # 429 / 5xx are transient — log and continue. We don't
                # exponential-backoff per-site; the next run will retry.
                if code in (408, 429, 500, 502, 503, 504):
                    log.warning("[%s] Anthropic HTTP %s — skipping", sid, code)
                    continue
                raise
            cache_misses += 1
            meta = {
                "model": model,
                "hash": fp,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._write_cached_summary(sid, fp, summary_text, meta)
            records.append({
                "id": sid,
                "program": site.get("program") or "superfund",
                "summary": summary_text,
                "summary_meta": meta,
            })
            log.info("[%d/%d] %s → %d chars",
                     i, len(target_sites), sid, len(summary_text))

        log.info(
            "summarized %d sites — %d cache hits, %d misses, %d skipped",
            len(records), cache_hits, cache_misses, skipped_no_input,
        )
        if getattr(args, "limit", None):
            records = records[: args.limit]
        return records

    # ----- helpers -----

    def _load_enriched_sites(self) -> list[dict[str, Any]]:
        """Load Superfund sites and merge in available enrichment files.

        We can't rely on `sites.json` (which is just the canonical Superfund
        mirror); we explicitly merge the enrichment JSONs by id so the
        summary reflects every signal we have on disk. Missing enrichment
        files are silently skipped.
        """
        data_dir = Path(__file__).resolve().parent.parent / "docs" / "data"
        sf_path = data_dir / "superfund-npl.json"
        if not sf_path.exists():
            return []
        sites = json.loads(sf_path.read_text()).get("sites", [])
        by_id = {s.get("id"): s for s in sites if s.get("id")}

        # Merge in known enrichment files so the prompt sees infra distances,
        # documents, and ECHO data the same way the frontend does.
        for fname, fields in (
            ("epa-redev.json", None),  # merge all fields
            ("infra-proximity.json", ("transmission_mi", "rail_mi", "highway_mi")),
            ("epa-superfund-docs.json", ("documents",)),
            ("epa-echo.json", ("enforcement",)),
        ):
            path = data_dir / fname
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as e:
                log.warning("failed to read %s: %s — skipping", fname, e)
                continue
            for rec in payload.get("sites") or []:
                rid = rec.get("id") or rec.get("epa_id")
                target = by_id.get(rid)
                if not target:
                    continue
                if fields is None:
                    for k, v in rec.items():
                        if k in ("id", "program", "epa_id"):
                            continue
                        if v is not None and target.get(k) is None:
                            target[k] = v
                else:
                    for k in fields:
                        if rec.get(k) is not None and target.get(k) is None:
                            target[k] = rec[k]
        return sites

    @staticmethod
    def _parse_status_filter(raw: str | None) -> set[str] | None:
        if not raw or raw.lower() == "all":
            return None
        return {s.strip() for s in raw.split(",") if s.strip()}

    def _summary_cache_path(self, site_id: str, fp: str) -> Path:
        # Distinct prefix from the http cache so they don't collide.
        return self.cache_dir / f"{self.slug}_summary_{site_id}_{fp}.json"

    def _read_cached_summary(self, site_id: str, fp: str) -> dict[str, Any] | None:
        path = self._summary_cache_path(site_id, fp)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cached_summary(
        self,
        site_id: str,
        fp: str,
        summary_text: str,
        meta: dict[str, Any],
    ) -> None:
        path = self._summary_cache_path(site_id, fp)
        path.write_text(json.dumps({
            "summary": summary_text,
            "summary_meta": meta,
        }))

    def _call_anthropic(
        self,
        site: dict[str, Any],
        api_key: str,
        model: str,
        max_tokens: int,
    ) -> str:
        """One Messages API call. Returns the assistant's text response."""
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": build_user_prompt(site)},
            ],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        # Mirror the base class's pacing. Anthropic's rate limits are well above
        # 1 req/s for Haiku, but we want to be respectful and predictable.
        time.sleep(0.5)
        resp = requests.post(
            ANTHROPIC_MESSAGES_URL,
            data=json.dumps(body),
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        # `content` is a list of content blocks — concatenate all text blocks.
        parts = []
        for block in data.get("content") or []:
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
        return "\n".join(parts).strip()
