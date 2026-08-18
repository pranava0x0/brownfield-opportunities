"""Refresh dashboard data from one or more connectors.

    python refresh.py --list-sources
    python refresh.py --source superfund-npl                  # default source
    python refresh.py --source superfund-npl --limit 200
    python refresh.py --source superfund-npl --no-cache
    python refresh.py --source superfund-npl --dry-run        # cache only
    python refresh.py --source superfund-npl --fetch-only     # cache, skip write
    python refresh.py --all                                   # run every connector + combined sites.json

To add a new source: drop a module in `connectors/`, register it in
`connectors/__init__.py`. See `connectors/superfund_npl.py` for the pattern.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import connectors
from connectors.base import Connector, prefer_ipv4
from diff import diff_payloads, load_payload, render_markdown, short_summary
from schema import Payload

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache"
OUTPUT_DIR = ROOT / "docs" / "data"
DEFAULT_OUTPUT = OUTPUT_DIR / "sites.json"
CHANGES_PATH = ROOT / "data" / "changes.md"

# Slug whose fetch_records output goes into the canonical sites.json when run
# alone. With `--all`, the combined sites.json is rewritten from per-source files.
CANONICAL_SLUG = "superfund-npl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("refresh")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list-sources", action="store_true", help="Print registered connectors and exit.")
    p.add_argument("--source", choices=connectors.names(), default=CANONICAL_SLUG,
                   help=f"Which connector to run (default: {CANONICAL_SLUG}).")
    p.add_argument("--all", action="store_true",
                   help="Run all connectors. Writes per-source files + combined sites.json.")
    p.add_argument("--no-cache", action="store_true", help="Ignore cache; force fresh fetch.")
    p.add_argument("--dry-run", action="store_true", help="Use only cached responses.")
    p.add_argument("--fetch-only", action="store_true", help="Fetch + cache; skip JSON write.")
    p.add_argument("--output", type=Path, default=None,
                   help="Override output path. Default: docs/data/<slug>.json (sites.json for canonical / combined).")
    p.add_argument("--pretty", action="store_true",
                   help="Pretty-print JSON (default is minified — saves ~30%% on uncompressed size).")
    p.add_argument("--combined", action="store_true",
                   help="With --all: also write a combined sites.json with every program's records (~2 MB gzipped). Default off — frontend lazy-loads.")
    p.add_argument("--allow-ipv6", action="store_true",
                   help="Don't pin DNS to IPv4. Default is to pin, because "
                        "every EPA host resolves AAAA-first and a blackholed "
                        "v6 path costs a full 60s timeout per request before "
                        "urllib3 falls back (see connectors.base.prefer_ipv4).")
    p.add_argument("--missing-only", action="store_true",
                   help="Enrichment connectors only: skip sites already in the existing "
                        "docs/data/<slug>.json and merge new records with what's on disk. "
                        "Useful for resuming partial backfills (epa-superfund-docs, epa-echo, "
                        "ai-summary) without re-fetching covered sites. Ignored by producer "
                        "connectors (superfund-npl, epa-acres, dod-fuds, dod-brac).")

    # Each connector contributes its own flags. We register them all so help text
    # surfaces every option; non-applicable ones are simply ignored at runtime.
    for cls in connectors.REGISTRY.values():
        cls.add_cli_args(p)
    return p


def _resolve_output_path(slug: str, override: Path | None) -> Path:
    if override is not None:
        return override
    if slug == CANONICAL_SLUG:
        return DEFAULT_OUTPUT
    return OUTPUT_DIR / f"{slug}.json"


def assert_unique_ids(slug: str, records: list[dict]) -> None:
    """Fail loud if a connector emits the same `id` twice.

    `schema.py` validates each record in isolation; nothing validated the
    record *set*. That gap let `dod-fuds` ship a byte-identical duplicate of
    `FUDS-H09PT0002` — inflating every universal enrichment file to 46,760
    rows over a 46,759-id universe and drawing two stacked map markers.
    Found 2026-08-09 by `scripts/validate_data.py`.

    The check is O(n) on data we already hold, so it runs unconditionally for
    every connector rather than being something each one remembers to do.
    """
    seen: set[str] = set()
    dupes: dict[str, int] = {}
    for rec in records:
        sid = rec.get("id")
        if sid in seen:
            dupes[sid] = dupes.get(sid, 1) + 1
        seen.add(sid)
    if dupes:
        listed = ", ".join(f"{k} x{v}" for k, v in sorted(dupes.items())[:10])
        more = f" (+{len(dupes) - 10} more)" if len(dupes) > 10 else ""
        raise ValueError(
            f"[{slug}] duplicate ids in output: {listed}{more}. "
            f"{len(records)} records, {len(seen)} unique. Deduplicate in the "
            f"connector's fetch_records() before returning."
        )


def _serialize_payload(payload: Payload, pretty: bool) -> str:
    """Serialize, dropping fields that are None.

    `exclude_none=True` is critical at the ACRES scale — without it every
    record carries ~5 explicit `null` placeholder fields that bloat the file
    by 30–40% before gzip.
    """
    if pretty:
        return payload.model_dump_json(indent=2, exclude_none=True)
    # Minified: drop indentation + trailing whitespace.
    return payload.model_dump_json(exclude_none=True)


def _run_one(
    slug: str,
    args: argparse.Namespace,
    use_cache: bool,
    output_override: Path | None = None,
) -> tuple[int, list[dict[str, Any]] | None, str | None]:
    """Run one connector. Returns (returncode, records, source_label)."""
    cls = connectors.get(slug)
    inst: Connector = cls(cache_dir=CACHE_DIR)
    log.info("=== %s ===", slug)

    records = inst.fetch_records(args, use_cache=use_cache)
    if args.fetch_only:
        log.info("--fetch-only: skipping output write (%d records)", len(records))
        return 0, records, inst.source_label
    if not records:
        # The canonical Superfund file going empty would be a real outage —
        # abort so we don't corrupt the deployed dashboard. For enrichment
        # connectors a sparse run is normal (small --docs-limit, partial
        # coverage); write an empty payload so the file exists and the
        # frontend's lazy-load 404 path doesn't trigger.
        if slug == CANONICAL_SLUG:
            log.error("[%s] no records normalized; aborting", slug)
            return 1, None, inst.source_label
        log.warning("[%s] no records normalized; writing empty payload", slug)

    out_path = _resolve_output_path(slug, output_override or args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Snapshot prior payload before overwrite — used for diff log.
    # In --all mode the combined writer owns changes.md; per-source runs skip it.
    is_canonical_solo = slug == CANONICAL_SLUG and output_override is None
    prior = load_payload(out_path) if is_canonical_solo else None

    assert_unique_ids(slug, records)

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = Payload(
        generated_at=generated_at,
        source=inst.source_label,
        source_url=inst.source_url,
        limit=getattr(args, "limit", None),
        count=len(records),
        sites=records,
    )
    out_path.write_text(_serialize_payload(payload, pretty=args.pretty))
    log.info("wrote      %s (%d sites, %d bytes)",
             out_path, len(records), out_path.stat().st_size)

    if is_canonical_solo:
        diff = diff_payloads(prior, json.loads(out_path.read_text()))
        CHANGES_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHANGES_PATH.write_text(render_markdown(diff, generated_at))
        log.info("diff       %s — %s", CHANGES_PATH, short_summary(diff))

    return 0, records, inst.source_label


def _write_combined(
    by_slug: dict[str, tuple[list[dict[str, Any]], str, str]],
    pretty: bool,
) -> Path:
    """Write the merged sites.json containing every program's records.

    Sort: keep acreage-bearing records first (Superfund stays at the top of
    the table by default), then no-acreage by name.
    """
    all_records: list[dict[str, Any]] = []
    sources: list[str] = []
    source_urls: list[str] = []
    program_counts: Counter[str] = Counter()
    for slug, (records, source_label, source_url) in by_slug.items():
        all_records.extend(records)
        sources.append(source_label)
        source_urls.append(source_url)
        for r in records:
            program_counts[r.get("program") or slug] += 1

    all_records.sort(
        key=lambda r: (
            r.get("acreage") is None,
            -(r.get("acreage") or 0),
            (r.get("name") or "").lower(),
        )
    )

    # Ids must be unique ACROSS programs too — that's the whole point of the
    # `ACRES-` / `FUDS-` / `BRAC-` namespacing.
    assert_unique_ids("combined", all_records)

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = Payload(
        generated_at=generated_at,
        source=" + ".join(sources),
        source_url=source_urls[0] if source_urls else "",
        count=len(all_records),
        sites=all_records,
        programs=dict(program_counts),
    )
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    prior = load_payload(DEFAULT_OUTPUT)
    DEFAULT_OUTPUT.write_text(_serialize_payload(payload, pretty=pretty))
    log.info("wrote      %s (%d sites, %d bytes) [combined]",
             DEFAULT_OUTPUT, len(all_records), DEFAULT_OUTPUT.stat().st_size)

    diff = diff_payloads(prior, json.loads(DEFAULT_OUTPUT.read_text()))
    CHANGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHANGES_PATH.write_text(render_markdown(diff, generated_at))
    log.info("diff       %s — %s", CHANGES_PATH, short_summary(diff))

    return DEFAULT_OUTPUT


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # Pin before any connector opens a socket.
    prefer_ipv4(enabled=not args.allow_ipv6)

    if args.list_sources:
        for name in connectors.names():
            cls = connectors.get(name)
            print(f"  {name:20s}  {cls.source_label}")
        return 0

    use_cache = not args.no_cache
    if args.dry_run:
        if not any(CACHE_DIR.glob("*.json")):
            log.error("dry-run: no cached responses found in %s", CACHE_DIR)
            return 2

    if args.all:
        # Each connector writes its own per-source file. The canonical
        # sites.json stays Superfund-only for fast first paint (~170 KB
        # gzipped); the frontend lazy-loads other programs on demand.
        # `--combined` opts into one merged sites.json (~2 MB gzipped) for
        # users who want everything in a single fetch.
        rc = 0
        results: dict[str, tuple[list[dict[str, Any]], str, str]] = {}
        # Sort by run_order so enrichment connectors (which read other
        # connectors' per-source JSONs) run after their producers.
        ordered_slugs = sorted(
            connectors.names(),
            key=lambda s: (connectors.get(s).run_order, s),
        )
        for slug in ordered_slugs:
            cls = connectors.get(slug)
            per_source_path = OUTPUT_DIR / f"{slug}.json"
            try:
                sub_rc, records, label = _run_one(
                    slug, args, use_cache=use_cache,
                    output_override=per_source_path,
                )
            except Exception:
                # Per-connector fault isolation. `--all` walks ~20 connectors
                # over half a dozen federal hosts; a single transient network
                # error (Overpass 504, ECHO ReadTimeout, ArcGIS connection
                # reset) used to propagate out of `_run_one` and kill every
                # connector still queued behind it. That is what broke the
                # scheduled refresh 13 runs running from 2026-05-25.
                #
                # We log the full traceback (never swallow — see CLAUDE.md
                # "fail loud") and keep the run's exit code nonzero, so CI
                # still reports the failure; we just stop letting one host's
                # bad minute cost us every downstream connector too.
                log.exception(
                    "[%s] connector raised — isolating and continuing with "
                    "the remaining sources", slug,
                )
                rc = 1
                continue
            rc = sub_rc or rc
            if records is not None and label is not None:
                results[slug] = (records, label, cls.source_url)
        if not results or args.fetch_only:
            return rc
        # Mirror the canonical Superfund file → sites.json for fast first paint.
        canonical_src = OUTPUT_DIR / f"{CANONICAL_SLUG}.json"
        if canonical_src.exists():
            DEFAULT_OUTPUT.write_text(canonical_src.read_text())
            log.info("mirrored   %s → %s (canonical fast-path)",
                     canonical_src.name, DEFAULT_OUTPUT.name)
        if getattr(args, "combined", False):
            _write_combined(results, pretty=args.pretty)
        return rc

    rc, _, _ = _run_one(args.source, args, use_cache=use_cache)
    return rc


if __name__ == "__main__":
    sys.exit(main())
