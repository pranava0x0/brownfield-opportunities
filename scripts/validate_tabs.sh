#!/usr/bin/env bash
# One entry point for the tab-validation pipeline. Code does everything it can;
# the three model steps are printed as instructions because they run as agents.
#
#   scripts/validate_tabs.sh deterministic     tab-sites -> audit_tabs -> parcels -> queue (no model)
#   scripts/validate_tabs.sh adjudicate        quote-check, decide, list disputes, publish (no model)
#   scripts/validate_tabs.sh uat               click depth + load performance, 3 viewports (no model)
#
# Agent steps in between (max 2 concurrent unless .claude/agent-cap says otherwise):
#   Haiku    one agent per batches/batch-NN.json, prompt scripts/local_records_prompts/researcher.md
#   Sonnet   one agent per research/batch-NN.json, prompt scripts/local_records_prompts/verifier.md
#   Opus     one agent over disputes.json (if any), prompt scripts/local_records_prompts/adjudicator.md
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
case "${1:-}" in
  deterministic)
    $PY scripts/tab_sites.py --top "${TOP:-10}"
    # A MISMATCH is a finding to read, not a reason to skip the later steps.
    $PY scripts/audit_tabs.py --only coverage seismic flow poprings state --out data/validation/audit-offline.json || echo "audit (offline checks): findings above"
    $PY scripts/audit_tabs.py --only lines citations --out data/validation/audit-network.json || echo "audit (network checks): findings above"
    $PY scripts/check_links_browser.py || echo "browser link check: dead links above"
    $PY scripts/local_records.py queue --per-screen "${PER_SCREEN:-5}" --batch-size 4
    $PY scripts/local_records.py parcels
    echo; echo "Next: run Haiku researchers on data/validation/local-records/batches/*.json (not yet in research/)," \
         "then Sonnet verifiers on research/*.json, then: scripts/validate_tabs.sh adjudicate"
    ;;
  adjudicate)
    $PY scripts/local_records.py adjudicate
    if [ -s data/validation/local-records/disputes.json ] && [ "$($PY -c "import json;print(len(json.load(open('data/validation/local-records/disputes.json'))))")" != "0" ]; then
      echo "Disputes exist: run the Opus adjudicator (scripts/local_records_prompts/adjudicator.md), then re-run with APPLY=1"
    fi
    if [ "${APPLY:-}" = "1" ]; then $PY scripts/local_records.py apply-opus; fi
    $PY scripts/local_records.py publish
    $PY scripts/local_records.py report
    ;;
  uat)
    $PY scripts/uat_depth.py
    ;;
  *) sed -n 2,13p "$0"; exit 2 ;;
esac
