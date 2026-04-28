"""Refresh dashboard data from one or more connectors.

    python refresh.py --list-sources
    python refresh.py --source superfund-npl                  # default source
    python refresh.py --source superfund-npl --limit 200
    python refresh.py --source superfund-npl --no-cache
    python refresh.py --source superfund-npl --dry-run        # cache only
    python refresh.py --source superfund-npl --fetch-only     # cache, skip write
    python refresh.py --all                                   # run every connector

To add a new source: drop a module in `connectors/`, register it in
`connectors/__init__.py`. See `connectors/superfund_npl.py` for the pattern.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import connectors
from connectors.base import Connector
from diff import diff_payloads, load_payload, render_markdown, short_summary
from schema import Payload

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache"
OUTPUT_DIR = ROOT / "docs" / "data"
DEFAULT_OUTPUT = OUTPUT_DIR / "sites.json"
CHANGES_PATH = ROOT / "data" / "changes.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("refresh")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list-sources", action="store_true", help="Print registered connectors and exit.")
    p.add_argument("--source", choices=connectors.names(), default="superfund-npl",
                   help="Which connector to run (default: superfund-npl).")
    p.add_argument("--all", action="store_true", help="Run all connectors. Each writes its own file.")
    p.add_argument("--no-cache", action="store_true", help="Ignore cache; force fresh fetch.")
    p.add_argument("--dry-run", action="store_true", help="Use only cached responses.")
    p.add_argument("--fetch-only", action="store_true", help="Fetch + cache; skip JSON write.")
    p.add_argument("--output", type=Path, default=None,
                   help="Output JSON path. Default: docs/data/<slug>.json (or sites.json for the legacy single-source case).")

    # Each connector contributes its own flags. We register them all so help text
    # surfaces every option; non-applicable ones are simply ignored at runtime.
    for cls in connectors.REGISTRY.values():
        cls.add_cli_args(p)
    return p


def _resolve_output_path(slug: str, override: Path | None) -> Path:
    if override is not None:
        return override
    # Legacy single-source case keeps writing to sites.json so the frontend
    # doesn't break; future multi-source runs use slug-named files.
    if slug == "superfund-npl":
        return DEFAULT_OUTPUT
    return OUTPUT_DIR / f"{slug}.json"


def _run_one(slug: str, args: argparse.Namespace, use_cache: bool) -> int:
    cls = connectors.get(slug)
    inst: Connector = cls(cache_dir=CACHE_DIR)
    log.info("=== %s ===", slug)

    records = inst.fetch_records(args, use_cache=use_cache)
    if args.fetch_only:
        log.info("--fetch-only: skipping output write (%d records)", len(records))
        return 0
    if not records:
        log.error("[%s] no records normalized; aborting", slug)
        return 1

    out_path = _resolve_output_path(slug, args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Snapshot prior payload before overwrite — used for diff log.
    prior = load_payload(out_path)

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = Payload(
        generated_at=generated_at,
        source=inst.source_label,
        source_url=inst.source_url,
        limit=getattr(args, "limit", None),
        count=len(records),
        sites=records,  # validated by Pydantic
    )
    out_path.write_text(payload.model_dump_json(indent=2))
    log.info("wrote      %s (%d sites)", out_path, len(records))

    # Only write a changes.md for the canonical superfund-npl output.
    if slug == "superfund-npl":
        diff = diff_payloads(prior, json.loads(out_path.read_text()))
        CHANGES_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHANGES_PATH.write_text(render_markdown(diff, generated_at))
        log.info("diff       %s — %s", CHANGES_PATH, short_summary(diff))

    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

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

    targets = connectors.names() if args.all else [args.source]
    rc = 0
    for slug in targets:
        rc = _run_one(slug, args, use_cache=use_cache) or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
