# Source this before running project commands on this Mac:
#   source "/Users/pranava/Projects/Brownfield Opportunities/scripts/env.sh"
# /usr/bin/git and /usr/bin/python3 fail until the Xcode license is accepted,
# so use the Command Line Tools git and the project venv instead.
MAIN="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
export MAIN
export WT="$MAIN/.claude/worktrees/routine-site-research"
export G=/Library/Developer/CommandLineTools/usr/bin/git
export PY="$MAIN/.venv/bin/python"
export PATH="$HOME/.local/bin:$PATH"   # gh, node
