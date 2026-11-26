#!/usr/bin/env bash
# Install YSocial from nothing and check that it works (plan, phase 6, point 2).
#
# It clones the core and every repository into an empty folder, builds a new virtual environment, installs the
# requirements, runs the smoke checks of fresh_install_check.py (start, sign in, admin pages, one experiment per
# platform and runtime) and then the suites that exercise the contracts and the extensions on that clean install.
# The first failing step stops the script with a status other than zero; the report goes to $WORK/report.md.
#
#   scripts/dev/fresh_install_check.sh                         # clone from the local checkout, branches below
#   SOURCE_BASE=https://github.com/YSocialTwin scripts/dev/fresh_install_check.sh   # clone from GitHub
#   BRANCHES=main scripts/dev/fresh_install_check.sh           # one branch for every repository
#   WORK=/tmp/fresh PYTHON=python3.12 scripts/dev/fresh_install_check.sh
#   WITH_YCREATOR=1 scripts/dev/fresh_install_check.sh         # also install YCreator (phase 7)
#   VENV=/path/to/venv scripts/dev/fresh_install_check.sh      # reuse a virtual environment (skips the install)
#
# Nothing is pushed and no existing checkout is changed: every clone is new.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${WORK:-$(mktemp -d /tmp/ysocial_fresh.XXXXXX)}"
PYTHON="${PYTHON:-python3}"
SOURCE_BASE="${SOURCE_BASE:-}"
BRANCHES="${BRANCHES:-}"
REPORT="$WORK/report.md"
CHECKOUT="$WORK/YSocial"

# repository  branch on the way to release (used when BRANCHES is empty); the core is first
DEFAULT_BRANCHES="
YSocial:pre-merge-phase5
ScenarioDesign:pre-merge-phase5
TrainingModules:pre-merge-phase5
frontend_adds-on:pre-merge-phase5
reactive_agents:pre-merge-phase5
YServer:pre-merge-phase4
YServerReddit:pre-merge-phase4
YSimulator:pre-merge-phase4
YForum:pre-merge-phase4
YPhotoSharing:pre-merge-phase3
YInstantMessaging:pre-merge-phase3
YDating:pre-merge-hardening
YFederation:platform-decoupling
YClient:main
YClientReddit:main
y_agents_plugins:main
y_memory_subsystem:main
"
if [ "${WITH_YCREATOR:-0}" = "1" ]; then DEFAULT_BRANCHES="$DEFAULT_BRANCHES
YCreator:pre-merge-hardening"; fi

mkdir -p "$WORK"
: > "$REPORT"
echo "# Fresh install check" >> "$REPORT"
echo "" >> "$REPORT"
echo "Folder: $WORK  -  Python: $($PYTHON --version 2>&1)  -  $(date -u +%FT%TZ)" >> "$REPORT"
echo "" >> "$REPORT"

fail() {
  echo "FAILED: $1" | tee -a "$REPORT"
  echo "Report: $REPORT"
  exit 1
}

run() {  # run <title> <command...>: log the command's output and stop at the first failure
  local title="$1"; shift
  echo "== $title"
  local log="$WORK/$(echo "$title" | tr -c 'A-Za-z0-9' '_').log"
  if "$@" >"$log" 2>&1; then
    echo "- ok: $title" >> "$REPORT"
  else
    tail -n 25 "$log"
    echo "- FAILED: $title (log: $log)" >> "$REPORT"
    fail "$title"
  fi
}

branch_of() {  # branch_of <repository>
  if [ -n "$BRANCHES" ]; then echo "$BRANCHES"; return; fi
  echo "$DEFAULT_BRANCHES" | awk -F: -v r="$1" '$1 == r {print $2}'
}

source_of() {  # source_of <repository>
  if [ -n "$SOURCE_BASE" ]; then echo "$SOURCE_BASE/$1"; return; fi
  if [ "$1" = "YSocial" ]; then echo "$HERE"; else echo "$HERE/external/$1"; fi
}

clone_one() {
  local repo="$1" branch dest
  branch="$(branch_of "$repo")"
  if [ "$repo" = "YSocial" ]; then dest="$CHECKOUT"; else dest="$CHECKOUT/external/$repo"; fi
  mkdir -p "$(dirname "$dest")"
  local source; source="$(source_of "$repo")"
  case "$source" in /*) source="file://$source" ;; esac  # a shallow clone: only the tip of the branch is needed
  git clone -q --depth 1 --branch "$branch" --single-branch "$source" "$dest" || return 1
  echo "$repo $branch $(git -C "$dest" rev-parse --short HEAD)" >> "$WORK/clones.txt"
}

echo "## Clone" >> "$REPORT"
: > "$WORK/clones.txt"
run "clone YSocial" clone_one YSocial
for repo in $(echo "$DEFAULT_BRANCHES" | awk -F: 'NF == 2 && $1 != "YSocial" {print $1}'); do
  run "clone $repo" clone_one "$repo"
done
{ echo ""; echo '```'; cat "$WORK/clones.txt"; echo '```'; echo ""; } >> "$REPORT"

echo "## Install" >> "$REPORT"
if [ -n "${VENV:-}" ]; then
  VENV_PY="$VENV/bin/python"
  echo "- reused environment: $VENV" >> "$REPORT"
else
  run "virtual environment" "$PYTHON" -m venv "$WORK/venv"
  VENV_PY="$WORK/venv/bin/python"
  run "requirements" "$VENV_PY" -m pip install -q -r "$CHECKOUT/requirements.txt" -r "$CHECKOUT/requirements/test.txt"
fi

export YSOCIAL_HOME="$CHECKOUT"
export PYTHONPATH="$CHECKOUT:$CHECKOUT/external"
export TMPDIR="${TMPDIR:-/tmp}"

echo "## Start and use" >> "$REPORT"
run "smoke checks" "$VENV_PY" "$CHECKOUT/scripts/dev/fresh_install_check.py" "$WORK/smoke.json"
echo "" >> "$REPORT"
"$VENV_PY" - "$WORK/smoke.json" >> "$REPORT" <<'PY'
import json, sys
for item in json.load(open(sys.argv[1])):
    print(f"- {'ok' if item['ok'] else 'FAILED'}: {item['step']}" + (f" ({item['detail']})" if item.get('detail') else ""))
PY

echo "## Contracts and extensions on the clean install" >> "$REPORT"
cd "$CHECKOUT" || fail "no checkout"
run "contracts of the platforms and of the extensions" "$VENV_PY" -m pytest -q -p no:cacheprovider \
  y_web/tests/test_sdk_contract.py y_web/tests/test_sdk_extensions_contract.py y_web/tests/test_decoupling_gate.py \
  y_web/tests/test_platform_discovery.py
run "Scenario Design suite" "$VENV_PY" -m pytest -q -p no:cacheprovider external/ScenarioDesign/tests
run "Training Modules bundle, export and import" "$VENV_PY" -m pytest -q -p no:cacheprovider \
  external/TrainingModules/tests/test_bundle.py external/TrainingModules/tests/test_runs.py
run "frontend add-ons suite" "$VENV_PY" -m pytest -q -p no:cacheprovider external/frontend_adds-on/tests
run "reactive agents suite" "$VENV_PY" -m pytest -q -p no:cacheprovider external/reactive_agents/tests

echo "" >> "$REPORT"
echo "Everything passed." >> "$REPORT"
echo "Report: $REPORT"
