#!/usr/bin/env bash
# Run the tests of YSocial with only some of the runtime repositories installed, to show that the platforms
# do not depend on each other (plan, phase F9.5).
#
# The runtime repositories of the microblogging and forum platforms are
#   YServer / YServerReddit  - the Standard runtime (Flask pair, with YClient / YClientReddit)
#   YSimulator / YForum      - the HPC runtime (Ray)
# Each one carries the pages, library and templates it needs, so every combination has to work: a test that
# reads a repository is skipped (or not collected) where that repository is absent, and nothing else may fail.
#
#   scripts/dev/run_install_matrix.sh                  # every combination below
#   scripts/dev/run_install_matrix.sh hpc-only none    # only these
#   MATRIX_SELECT='platform|forum' scripts/dev/run_install_matrix.sh   # tests whose file name matches (regex)
#   PYTHON=.venv/bin/python scripts/dev/run_install_matrix.sh
#
# A combination hides the repositories it leaves out by moving them to external/.install_matrix_hidden/ and puts
# them back when it ends (also on Ctrl-C), so run it on a checkout where nothing else is using external/.
# Exit status: 1 when a combination has failures.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXTERNAL="$ROOT/external"
HIDDEN="$EXTERNAL/.install_matrix_hidden"
PYTHON="${PYTHON:-python3}"
SELECT="${MATRIX_SELECT:-}"
RUNTIMES="YServer YServerReddit YSimulator YForum"

# name: repositories that are left out
combo_hidden() {
  case "$1" in
    all) echo "" ;;
    standard-only) echo "YSimulator YForum" ;;
    hpc-only) echo "YServer YServerReddit" ;;
    microblogging-only) echo "YServerReddit YForum" ;;
    forum-only) echo "YServer YSimulator" ;;
    no-yserver) echo "YServer" ;;
    no-yserverreddit) echo "YServerReddit" ;;
    no-ysimulator) echo "YSimulator" ;;
    no-yforum) echo "YForum" ;;
    none) echo "$RUNTIMES" ;;
    *) return 1 ;;
  esac
}
ALL_COMBOS="all standard-only hpc-only microblogging-only forum-only no-yserver no-yserverreddit no-ysimulator no-yforum none"

restore() {
  if [ -d "$HIDDEN" ]; then
    for dir in "$HIDDEN"/*; do
      [ -d "$dir" ] || continue
      name="$(basename "$dir")"
      [ -e "$EXTERNAL/$name" ] || mv "$dir" "$EXTERNAL/$name"
    done
    rmdir "$HIDDEN" 2>/dev/null || true
  fi
  # the application rewrites it when it starts
  git -C "$ROOT" checkout -- external/plugins.json 2>/dev/null || true
}
trap restore EXIT INT TERM

hide() {
  mkdir -p "$HIDDEN"
  for name in $1; do
    if [ -d "$EXTERNAL/$name" ]; then
      mv "$EXTERNAL/$name" "$HIDDEN/$name"
    fi
  done
}

# test files to run: the ones whose repositories are installed (what conftest.py would not collect is left out)
select_files() {
  (cd "$ROOT" && SELECT="$SELECT" "$PYTHON" - <<'PY'
import glob, os, re, sys
sys.path.insert(0, os.getcwd())
from y_web.tests import _platform_alias as alias

alias.install()
absent = set(alias.absent_tests())
select = os.environ.get("SELECT")
for path in sorted(glob.glob("y_web/tests/test_*.py")):
    name = os.path.basename(path)
    if name in absent or (select and not re.search(select, name)):
        continue
    print(path)
PY
  ) 2>/dev/null
}

COMBOS="${*:-$ALL_COMBOS}"
STATUS=0
SUMMARY=""
for combo in $COMBOS; do
  if ! hidden="$(combo_hidden "$combo")"; then
    echo "unknown combination: $combo (known: $ALL_COMBOS)" >&2
    exit 2
  fi
  restore
  hide "$hidden"
  echo "=== $combo (left out: ${hidden:-nothing}) ==="
  files="$(select_files)"
  if [ -z "$files" ]; then
    result="no test selected"
  else
    out="$(cd "$ROOT" && PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m pytest -p no:cacheprovider -q --tb=short $files 2>&1)"
    echo "$out" | grep -E "^(FAILED|ERROR)" | sed 's/ - .*//'
    result="$(echo "$out" | tail -1)"
    if echo "$out" | grep -qE "^(FAILED|ERROR)| failed| error"; then
      STATUS=1
    fi
  fi
  echo "$result"
  SUMMARY="$SUMMARY
$(printf '%-20s %s' "$combo" "$result")"
done
restore
echo
echo "=== summary ==="
echo "$SUMMARY" | sed '/^$/d'
exit $STATUS
