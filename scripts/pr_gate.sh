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

step "3/4 curated-citation liveness (coal + federal + hanford overlays)"
# Exit codes: 0 = all resolve · 1 = at least one DEFINITIVE dead URL (gates)
# · 2 = network unreachable (warns, does not gate — but verify before ship).
python3 - <<'EOF'
import json, sys, time, urllib.error, urllib.request
from pathlib import Path
dead, unreachable = 0, 0
seen = set()
# House network ethics: >=1.5s between requests to any single host, and a
# throttling answer (429/403) is INCONCLUSIVE, never a dead citation — a
# rate-limited GEM wiki must not block every PR (Codex review round 2).
INCONCLUSIVE_HTTP = {403, 429}
last_hit: dict[str, float] = {}

def check(fname: str, url: str) -> None:
    global dead, unreachable
    if not url or url in seen:
        return
    seen.add(url)
    host = url.split("/", 3)[2]
    wait = last_hit.get(host, 0) + 1.5 - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    status = None
    for method in ("HEAD", "GET"):  # some hosts reject HEAD
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": "brownfield-pr-gate"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                status = r.status
            break
        except urllib.error.HTTPError as e:
            status = e.code  # definitive server answer
            if status in INCONCLUSIVE_HTTP:
                break        # don't hammer a throttling host with the GET retry
        except Exception:
            status = None    # network-level failure — inconclusive
    last_hit[host] = time.monotonic()
    if status is None or status in INCONCLUSIVE_HTTP:
        unreachable += 1
        print(f"  UNREACHABLE {fname}: {url}" + (f" (HTTP {status})" if status else ""))
    elif status >= 400:
        dead += 1
        print(f"  DEAD CITATION {fname}: {url} (HTTP {status})")

for fname, key, field in [
    ("coal-conversions.json", "assets", "source_url"),
    ("federal-clean-energy.json", "sites", "solicitation_url"),
    ("hanford-e2e.json", "parcels", "source_url"),
]:
    payload = json.loads((Path("docs/data") / fname).read_text())
    for rec in payload.get(key, []):
        check(fname, rec.get(field))

# facility_types is a top-level dict (not a list), one row per facility
# type rather than per parcel — the general "what this facility type needs"
# claims (water demand, licensing pathway, acreage threshold) added
# 2026-08-24, same provenance contract as everything else on the page.
hanford = json.loads((Path("docs/data") / "hanford-e2e.json").read_text())
for meta in hanford.get("facility_types", {}).values():
    check("hanford-e2e.json (facility_types)", meta.get("source_url"))

print(f"  checked {len(seen)} unique citation URLs: {dead} dead, {unreachable} unreachable/throttled")
sys.exit(1 if dead else (2 if unreachable else 0))
EOF
live_rc=$?
if [ "$live_rc" -eq 1 ]; then
  echo "  citation liveness: FAILED (dead URL — the v1 bug this step exists to catch)"
  fail=1
elif [ "$live_rc" -eq 2 ]; then
  echo "  citation liveness: WARN (network unreachable — verify manually before ship)"
elif [ "$live_rc" -ne 0 ]; then
  echo "  citation liveness: script error (rc=$live_rc)"
  fail=1
fi

if [ "$FAST" -eq 1 ]; then
  step "4/4 e2e guards — SKIPPED (--fast)"
else
  step "4/4 e2e guards (DOM budget, refresh date, coal tab, mobile overflow)"
  run python3 -m pytest -q -p no:cacheprovider -n 4 \
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
