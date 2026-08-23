#!/usr/bin/env bash
# Pre-PR gate — run before opening or updating any PR on this repo.
#
# Encodes the guards that the 2026-08-23 coal-repowering PR shipped red on,
# so the next PR can't repeat them without noticing. Two lenses:
#   1. Code/architecture: unit suite, provenance registry drift, the
#      first-paint DOM budget, refresh-date drift, mobile tab-strip overflow.
#   2. Data/domain: offline corpus validation incl. overlay Pydantic schemas,
#      curated-row provenance (source_url + verified_at), and coal-catalog
#      coherence (derived flags, valuation recompute, join distances).
#
# Usage:
#   bash scripts/pr_gate.sh          # full gate (unit + validators + guard e2e)
#   bash scripts/pr_gate.sh --fast   # skip the browser-based e2e guards
#
# The full e2e suite still runs in CI; this is the fast local gate (~2-4 min).
set -uo pipefail
cd "$(dirname "$0")/.."

FAST=0
[ "${1:-}" = "--fast" ] && FAST=1

fail=0
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
run()  { "$@" || fail=1; }

step "1/4 unit tests (includes provenance-registry drift guard)"
run python3 -m pytest tests/ -q --ignore=tests/e2e -p no:cacheprovider

step "2/4 offline data validation (schema, joins, provenance, coherence)"
run python3 scripts/validate_data.py --fail-on FAIL

step "3/4 curated-citation liveness (coal + federal overlays; network, best-effort)"
python3 - <<'EOF' || echo "  (liveness check skipped/failed — network optional, verify before ship)"
import json, sys, urllib.request
from pathlib import Path
bad = 0
seen = set()
for fname, key, field in [
    ("coal-conversions.json", "assets", "source_url"),
    ("federal-clean-energy.json", "sites", "solicitation_url"),
]:
    payload = json.loads((Path("docs/data") / fname).read_text())
    for rec in payload.get(key, []):
        url = rec.get(field)
        if not url or url in seen:
            continue
        seen.add(url)
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "brownfield-pr-gate"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status >= 400:
                    raise Exception(f"HTTP {r.status}")
        except Exception as e:
            # GET fallback — some hosts reject HEAD.
            try:
                with urllib.request.urlopen(url, timeout=10) as r:
                    if r.status >= 400:
                        raise Exception(f"HTTP {r.status}")
            except Exception as e2:
                bad += 1
                print(f"  DEAD CITATION {fname}: {url} ({e2})")
print(f"  checked {len(seen)} unique citation URLs, {bad} dead")
sys.exit(1 if bad else 0)
EOF
[ $? -ne 0 ] && fail=1

if [ "$FAST" -eq 1 ]; then
  step "4/4 e2e guards — SKIPPED (--fast)"
else
  step "4/4 e2e guards (DOM budget, refresh date, coal tab, mobile overflow)"
  run python3 -m pytest -q -p no:cacheprovider \
    tests/e2e/test_smoke.py::test_dom_size_under_5k_nodes \
    tests/e2e/test_smoke.py::test_refresh_date_reflects_freshest_data_file \
    tests/e2e/test_coal_repowering.py
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "PR GATE: FAILED — fix before opening/updating the PR."
  exit 1
fi
echo "PR GATE: PASSED."
