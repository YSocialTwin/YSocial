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
#   MIX=core-top|platforms-top ONLY_SMOKE=1 ...                # cross-compatibility: the new core with the old
#                                                              # repositories (main), or the new ones with the old core
#   WITH_YCREATOR=1 scripts/dev/fresh_install_check.sh         # also install YCreator (phase 7)
#   VENV=/path/to/venv scripts/dev/fresh_install_check.sh      # reuse a virtual environment (skips the install)
#   RESUME=1 WORK=<same folder> ...                            # skip the steps that already passed in that folder
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
YCreator:pre-merge-phase7"; fi

mkdir -p "$WORK"
: > "$REPORT"
echo "# Fresh install check" >> "$REPORT"
echo "" >> "$REPORT"
echo "Folder: $WORK  -  $(date -u +%FT%TZ)" >> "$REPORT"
echo "" >> "$REPORT"

fail() {
  echo "FAILED: $1" | tee -a "$REPORT"
  echo "Report: $REPORT"
  exit 1
}

run() {  # run <title> <command...>: log the command's output and stop at the first failure
  local title="$1"; shift
  echo "== $title"
  local key; key="$(echo "$title" | tr -c 'A-Za-z0-9' '_')"
  local log="$WORK/$key.log"
  if [ "${RESUME:-0}" = "1" ] && [ -f "$WORK/.done_$key" ]; then echo "- ok (earlier run): $title" >> "$REPORT"; return 0; fi
  if "$@" >"$log" 2>&1; then
    touch "$WORK/.done_$key"
    echo "- ok: $title" >> "$REPORT"
  else
    tail -n 25 "$log"
    echo "- FAILED: $title (log: $log)" >> "$REPORT"
    fail "$title"
  fi
}

branch_of() {  # branch_of <repository>
  if [ -n "$BRANCHES" ]; then echo "$BRANCHES"; return; fi
  case "${MIX:-}" in
    core-top) if [ "$1" = "YSocial" ]; then echo "pre-merge-phase5"; else echo "main"; fi; return ;;
    platforms-top) if [ "$1" = "YSocial" ]; then echo "main"; else echo "$DEFAULT_BRANCHES" | awk -F: -v r="$1" '$1 == r {print $2}'; fi; return ;;
  esac
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
  if [ -d "$dest/.git" ]; then echo "$repo $branch $(git -C "$dest" rev-parse --short HEAD) (already there)" >> "$WORK/clones.txt"; return 0; fi
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

echo "Python: $("$VENV_PY" --version 2>&1)" >> "$REPORT"

export YSOCIAL_HOME="$CHECKOUT"
export PYTHONPATH="$CHECKOUT:$CHECKOUT/external"
export TMPDIR="${TMPDIR:-/tmp}"

echo "## Start and use" >> "$REPORT"
run "smoke checks" env FRESH_ROOT="$CHECKOUT" "$VENV_PY" "$HERE/scripts/dev/fresh_install_check.py" "$WORK/smoke.json"
echo "" >> "$REPORT"
"$VENV_PY" - "$WORK/smoke.json" >> "$REPORT" <<'PY'
import json, sys
for item in json.load(open(sys.argv[1])):
    print(f"- {'ok' if item['ok'] else 'FAILED'}: {item['step']}" + (f" ({item['detail']})" if item.get('detail') else ""))
PY

if [ "${ONLY_SMOKE:-0}" = "1" ]; then echo "" >> "$REPORT"; echo "Smoke checks passed (ONLY_SMOKE)." >> "$REPORT"; echo "Report: $REPORT"; exit 0; fi

echo "## Contracts and extensions on the clean install" >> "$REPORT"
cd "$CHECKOUT" || fail "no checkout"
# The suites below create experiments of every platform. A repository still classified as private is only offered
# once GitHub reports it public (an anonymous request the app makes by itself, and cannot make offline), so the
# check records that answer for them: it assumes the repositories are public, which is what the visibility
# decision of the release is about (docs/release-4.1-report.md). ASSUME_PUBLIC=0 leaves the state alone.
if [ "${ASSUME_PUBLIC:-1}" = "1" ]; then
  run "assume the private repositories are public" "$VENV_PY" - <<'PY'
import json, time
from pathlib import Path
from y_web.src.external_runtime.registry import supported_repos
state = {key: {"checked_at": time.time(), "public": True} for key, spec in supported_repos().items() if spec.is_private}
Path("external/repo_visibility.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
PY
  echo "- assumed public: private repositories (see the smoke step above for what a plain install shows)" >> "$REPORT"
fi
run "contracts of the platforms and of the extensions" "$VENV_PY" -m pytest -q -p no:cacheprovider \
  y_web/tests/test_sdk_contract.py y_web/tests/test_sdk_extensions_contract.py y_web/tests/test_decoupling_gate.py \
  y_web/tests/test_platform_discovery.py
run "Scenario Design suite" "$VENV_PY" -m pytest -q -p no:cacheprovider external/ScenarioDesign/tests
run "Training Modules bundle, export and import" "$VENV_PY" -m pytest -q -p no:cacheprovider \
  external/TrainingModules/tests/test_bundle.py external/TrainingModules/tests/test_runs.py
run "frontend add-ons suite" env PYTHONPATH="$CHECKOUT/external/frontend_adds-on:$PYTHONPATH" "$VENV_PY" -m pytest -q -p no:cacheprovider external/frontend_adds-on/tests
run "reactive agents suite" env PYTHONPATH="$CHECKOUT/external/reactive_agents:$PYTHONPATH" "$VENV_PY" -m pytest -q -p no:cacheprovider external/reactive_agents/tests

echo "" >> "$REPORT"
echo "Everything passed." >> "$REPORT"
echo "Report: $REPORT"
