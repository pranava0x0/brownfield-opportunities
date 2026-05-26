#!/usr/bin/env bash
# Resumption helper for the brownfields-data-updates scheduled task.
# Run after either of the background refreshes (epa-echo / epa-superfund-docs) completes.
# Idempotent — safe to re-run.

set -euo pipefail
cd "$(dirname "$0")/.."

ECHO_RUNNING=$(pgrep -f "refresh.py --source epa-echo" || true)
DOCS_RUNNING=$(pgrep -f "refresh.py --source epa-superfund-docs" || true)

echo "==> Process status"
echo "    ECHO PID=${ECHO_RUNNING:-(done)}  DOCS PID=${DOCS_RUNNING:-(done)}"

echo "==> Coverage check"
python3 - <<'PYEOF'
import json
from pathlib import Path
def rows(d):
    if isinstance(d, list): return d
    for k in ('records','sites','data'):
        if k in d and isinstance(d[k], list): return d[k]
    for k,v in d.items():
        if isinstance(v, list): return v
    return []
sf = json.loads(Path('docs/data/superfund-npl.json').read_text())
fd = [s for s in rows(sf) if s.get('npl_status_code') in ('F','D')]
echo = rows(json.loads(Path('docs/data/epa-echo.json').read_text()))
docs = rows(json.loads(Path('docs/data/epa-superfund-docs.json').read_text()))
print(f'    F/D superfund = {len(fd)}')
print(f'    echo coverage = {len(echo)} / {len(fd)} ({100*len(echo)/len(fd):.1f}%)')
print(f'    docs coverage = {len(docs)} / {len(fd)} ({100*len(docs)/len(fd):.1f}%)')
PYEOF

if [[ -z "$ECHO_RUNNING" && -z "$DOCS_RUNNING" ]]; then
  echo "==> Both runs complete — full AI summary regen + stage all"
  python3 refresh.py --source ai-summary --ai-static --ai-status F,D --ai-limit 0
  git add docs/data/epa-echo.json docs/data/epa-superfund-docs.json docs/data/ai-summary.json
elif [[ -z "$ECHO_RUNNING" && -n "$DOCS_RUNNING" ]]; then
  echo "==> ECHO done, docs still running — partial stage (ECHO + AI regen)"
  echo "    AI regen incorporates whatever docs records are already on disk."
  python3 refresh.py --source ai-summary --ai-static --ai-status F,D --ai-limit 0
  git add docs/data/epa-echo.json docs/data/ai-summary.json
elif [[ -n "$ECHO_RUNNING" && -z "$DOCS_RUNNING" ]]; then
  echo "==> Docs done, ECHO still running — partial stage (docs + AI regen)"
  python3 refresh.py --source ai-summary --ai-static --ai-status F,D --ai-limit 0
  git add docs/data/epa-superfund-docs.json docs/data/ai-summary.json
else
  echo "==> Both still running — re-run when at least one completes"
  exit 1
fi

echo "==> Staged"
git status --short
echo
echo "Next: review and commit. Suggested message form:"
echo "  chore(data): refresh ECHO enforcement + AI summaries"
