#!/usr/bin/env python3
"""Validate and merge per-site research dossiers into docs/data/site-research.json.

The daily research routine writes one JSON file per researched site (a
`schema.SiteResearch` object) and merges it with this script. It is the only
writer of the data file, so every entry passes the same checks:

  * the entry validates against `schema.SiteResearch` (extra fields rejected,
    every development and the summary carry at least one https citation);
  * the id exists in a shipped program inventory (Superfund, ACRES, FUDS, BRAC);
  * no date is in the future, and `next_review` falls after `researched_at`.

Merging is append-only: a replaced summary moves into `history`, and
developments are unioned (deduplicated by kind, date and source URL).

Usage:
  python3 scripts/site_research.py context <SITE_ID>     # shipped fields to verify
  python3 scripts/site_research.py add entry.json [...]   # validate + merge
  python3 scripts/site_research.py validate               # check the whole file
  python3 scripts/site_research.py due [--limit N]        # entries past next_review
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schema import SiteResearch, SiteResearchPayload  # noqa: E402

log = logging.getLogger("site_research")

DATA_DIR = ROOT / "docs" / "data"
OUTPUT = DATA_DIR / "site-research.json"
PROGRAM_FILES = ("superfund-npl.json", "epa-acres.json", "dod-fuds.json", "dod-brac.json")
# Enrichment files whose fields help a researcher check what the site shows.
CONTEXT_FILES = ("infra-proximity.json", "parcel-owner.json", "epa-echo.json",
                 "epa-superfund-docs.json", "ai-summary.json", "coord-quality.json")
HISTORY_LIMIT = 12
SOURCE_LABEL = "Per-site research: cited news, permits, filings and field checks"


class ResearchError(ValueError):
    """An entry that must not be merged."""


def _today() -> dt.date:
    return dt.date.today()


def _parse_day(value: str) -> dt.date:
    """Accept YYYY-MM or YYYY-MM-DD; a month resolves to its first day."""
    return dt.date.fromisoformat(value if len(value) == 10 else value + "-01")


def load_corpus(data_dir: Path = DATA_DIR) -> dict[str, dict[str, Any]]:
    corpus: dict[str, dict[str, Any]] = {}
    for name in PROGRAM_FILES:
        path = data_dir / name
        if not path.exists():
            raise FileNotFoundError(f"program inventory missing: {path}")
        for rec in json.loads(path.read_text()).get("sites", []):
            corpus[rec["id"]] = rec
    return corpus


def load_payload(path: Path = OUTPUT) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "generated_at": "", "source": SOURCE_LABEL, "count": 0, "sites": []}
    return json.loads(path.read_text())


def check_entry(entry: dict[str, Any], corpus_ids: Iterable[str], today: dt.date) -> SiteResearch:
    """Schema-validate one entry and apply the checks the schema cannot express."""
    try:
        model = SiteResearch.model_validate(entry)
    except Exception as exc:
        raise ResearchError(f"{entry.get('id', '?')}: schema: {exc}") from exc
    if model.id not in set(corpus_ids):
        raise ResearchError(f"{model.id}: not a shipped site id (Superfund/ACRES/FUDS/BRAC)")
    researched = _parse_day(model.researched_at)
    dates: list[tuple[str, str]] = [("researched_at", model.researched_at),
                                    ("search_window_start", model.search_window_start)]
    for i, src in enumerate(model.summary_sources):
        dates.append((f"summary_sources[{i}].accessed", src.accessed))
        if src.published:
            dates.append((f"summary_sources[{i}].published", src.published))
    for i, item in enumerate(model.items):
        dates.append((f"items[{i}].date", item.date))
        for j, src in enumerate(item.sources):
            dates.append((f"items[{i}].sources[{j}].accessed", src.accessed))
            if src.published:
                dates.append((f"items[{i}].sources[{j}].published", src.published))
    for label, value in dates:
        if _parse_day(value) > today:
            raise ResearchError(f"{model.id}: {label}={value} is in the future")
    if _parse_day(model.search_window_start) > researched:
        raise ResearchError(f"{model.id}: search_window_start is after researched_at")
    if _parse_day(model.next_review) <= researched:
        raise ResearchError(f"{model.id}: next_review must fall after researched_at")
    if not model.items and not model.no_new_developments:
        raise ResearchError(f"{model.id}: no developments listed; set no_new_developments=true "
                            "when the search window was searched and nothing was found")
    return model


def _item_key(item: dict[str, Any]) -> tuple[str, str, str]:
    first_url = item["sources"][0]["url"] if item.get("sources") else ""
    return (item["kind"], item["date"], first_url.rstrip("/"))


def merge(existing: dict[str, Any] | None, new: SiteResearch) -> dict[str, Any]:
    """Return the merged dossier; never drops a prior summary or development."""
    merged = new.model_dump(exclude_none=True)
    if not existing:
        return merged
    history = list(existing.get("history") or [])
    if existing.get("summary") and existing["summary"] != merged["summary"]:
        history.insert(0, {"researched_at": existing["researched_at"], "summary": existing["summary"]})
    merged["history"] = (history + [h for h in merged.get("history", []) if h not in history])[:HISTORY_LIMIT]
    seen = {_item_key(i) for i in merged.get("items", [])}
    for old in existing.get("items") or []:
        if _item_key(old) not in seen:
            merged.setdefault("items", []).append(old)
            seen.add(_item_key(old))
    merged["items"] = sorted(merged.get("items", []), key=lambda i: i["date"], reverse=True)
    return merged


def write_payload(sites: list[dict[str, Any]], path: Path = OUTPUT) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE_LABEL,
        "count": len(sites),
        "sites": sorted(sites, key=lambda s: s["id"]),
    }
    SiteResearchPayload.model_validate(payload)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    return payload


def add_entries(entries: list[dict[str, Any]], *, path: Path = OUTPUT, data_dir: Path = DATA_DIR,
                today: dt.date | None = None) -> dict[str, Any]:
    today = today or _today()
    corpus_ids = load_corpus(data_dir).keys()
    models = [check_entry(e, corpus_ids, today) for e in entries]  # all-or-nothing
    by_id = {s["id"]: s for s in load_payload(path).get("sites", [])}
    for model in models:
        by_id[model.id] = merge(by_id.get(model.id), model)
    return write_payload(list(by_id.values()), path)


def validate_file(path: Path = OUTPUT, data_dir: Path = DATA_DIR, today: dt.date | None = None) -> int:
    today = today or _today()
    payload = load_payload(path)
    SiteResearchPayload.model_validate(payload)
    corpus_ids = load_corpus(data_dir).keys()
    for entry in payload["sites"]:
        check_entry(entry, corpus_ids, today)
    if payload["count"] != len(payload["sites"]):
        raise ResearchError("count does not match the number of sites")
    ids = [s["id"] for s in payload["sites"]]
    if len(ids) != len(set(ids)):
        raise ResearchError("duplicate site ids")
    return len(ids)


def site_context(site_id: str, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    """The shipped record plus the enrichment fields a visitor sees for it."""
    corpus = load_corpus(data_dir)
    if site_id not in corpus:
        raise ResearchError(f"{site_id}: not a shipped site id")
    context = {"record": corpus[site_id], "enrichment": {}}
    for name in CONTEXT_FILES:
        path = data_dir / name
        if not path.exists():
            continue
        for rec in json.loads(path.read_text()).get("sites", []):
            if rec.get("id") == site_id or rec.get("epa_id") == site_id:
                context["enrichment"][name] = rec
                break
    existing = {s["id"]: s for s in load_payload(data_dir / OUTPUT.name).get("sites", [])}
    if site_id in existing:
        context["prior_research"] = existing[site_id]
    return context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ctx = sub.add_parser("context", help="print shipped fields for one site")
    p_ctx.add_argument("site_id")
    p_add = sub.add_parser("add", help="validate and merge entry files")
    p_add.add_argument("files", nargs="+", type=Path)
    sub.add_parser("validate", help="validate the whole data file")
    p_due = sub.add_parser("due", help="list dossiers past their next_review date")
    p_due.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        if args.cmd == "context":
            print(json.dumps(site_context(args.site_id), indent=1, ensure_ascii=False))
        elif args.cmd == "add":
            entries: list[dict[str, Any]] = []
            for f in args.files:
                loaded = json.loads(f.read_text())
                entries.extend(loaded if isinstance(loaded, list) else [loaded])
            payload = add_entries(entries)
            log.info("merged %d entr%s; site-research.json now holds %d site%s",
                     len(entries), "y" if len(entries) == 1 else "ies", payload["count"],
                     "" if payload["count"] == 1 else "s")
        elif args.cmd == "validate":
            log.info("site-research.json OK: %d sites", validate_file())
        elif args.cmd == "due":
            today = _today().isoformat()
            due = [s for s in load_payload().get("sites", []) if s["next_review"] <= today]
            for s in sorted(due, key=lambda s: s["next_review"])[: args.limit]:
                print(f"{s['next_review']}  {s['id']}  {s['name']}")
    except (ResearchError, FileNotFoundError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
