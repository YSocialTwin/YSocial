#!/usr/bin/env bash
# Run the tests of YSocial and of every plugin repository under external/, and write a report that tells
# what to fix.
#
#   scripts/dev/run_all_tests.sh                 # CI selection of each repository, current Python
#   scripts/dev/run_all_tests.sh --full          # also the tests CI leaves out (ray, differential, ...)
#   scripts/dev/run_all_tests.sh -r YForum,YDating
#   scripts/dev/run_all_tests.sh --venv --install   # one virtualenv per repository, requirements installed
#   scripts/dev/run_all_tests.sh -- -k llm       # arguments after -- go to every pytest run
#
# Report (test-reports/<date-time>/, test-reports/latest points to it):
#   report.md      overview, failures grouped by cause, missing modules, skip reasons, slowest tests, static checks
#   summary.json   the same, machine readable
#   logs/ junit/   one log and one JUnit file per repository (YSocial is split in batches)
#
# The script never stops at the first failure; its exit status is 1 when something failed.
# Works with the bash 3.2 of macOS.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_BASE="$ROOT/test-reports"
OUT=""
ONLY=""
FULL=0
USE_VENV=0
INSTALL=0
CHECKS=1
BATCHES=4
TIMEOUT=300
PYTHON_BIN="${PYTHON:-python3}"
VENV_ROOT="${YSOCIAL_TEST_VENVS:-$HOME/.cache/ysocial-test-venvs}"
EXTRA_ARGS=()

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -r|--repos) ONLY="$2"; shift 2 ;;
    -o|--out) OUT="$2"; shift 2 ;;
    --full) FULL=1; shift ;;
    --venv) USE_VENV=1; shift ;;
    --install) INSTALL=1; USE_VENV=1; shift ;;
    --no-checks) CHECKS=0; shift ;;
    --batches) BATCHES="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    --list) LIST=1; shift ;;
    -h|--help) usage 0 ;;
    --) shift; EXTRA_ARGS=("$@"); break ;;
    *) echo "unknown option: $1" >&2; usage 2 ;;
  esac
done

# name | directory (relative to the root) | test paths | CI marker expression | extra marker expression with --full
# | requirement files / pip arguments for --install (space separated; "-e ." installs the repository)
SPECS=(
  "YSocial|.|y_web/tests|||requirements.txt"
  "YSocial-plugin-registry|.|plugin-registry/tests|||requirements.txt"
  "YForum|external/YForum|tests|unit or integration||-r requirements-dev.txt"
  "YDating|external/YDating|YDating/tests|not integration and not llm|not llm|-r requirements-dev.txt"
  "YInstantMessaging|external/YInstantMessaging|tests|not llm and not pg|not llm|-r requirements.txt"
  "YSimulator|external/YSimulator|YSimulator/tests|||-r requirements.txt -r requirements-dev.txt"
  "YPhotoSharing|external/YPhotoSharing|tests|||-r requirements.txt"
  "YClient|external/YClient|tests|||-r requirements_client.txt"
  "YClientReddit|external/YClientReddit|tests|||-r requirements_client.txt"
  "YServer|external/YServer|tests|||-r requirements_server.txt"
  "YServerReddit|external/YServerReddit|tests|||-r requirements_server.txt"
  "YFederation|external/YFederation|tests|||-e ."
  "y_agents_plugins|external/y_agents_plugins|tests|||-e . -r requirements.txt"
  "y_memory_subsystem|external/y_memory_subsystem|tests|||-e ."
  "reactive_agents|.|external/reactive_agents/tests|||requirements.txt"
  "frontend_adds-on|external/frontend_adds-on|tests|||-r requirements.txt"
  "ScenarioDesign|external/ScenarioDesign|tests|||-r requirements.txt"
  "TrainingModules|external/TrainingModules|tests|||-r requirements.txt"
)

# static checks that CI runs (label | directory | command)
CHECK_SPECS=(
  "YSocial i18n catalogs|.|$PYTHON_BIN scripts/i18n/catalogs.py check"
  "YSocial i18n unmarked strings|.|$PYTHON_BIN scripts/i18n/scan_unmarked.py --check"
  "YSocial i18n glossary|.|$PYTHON_BIN scripts/i18n/check_glossary.py"
  "YSocial i18n coverage|.|$PYTHON_BIN scripts/i18n/coverage_report.py --min 98"
  "YSocial prompt hashes|.|$PYTHON_BIN scripts/prompts/snapshot_hashes.py --check"
  "YSocial prompt packs|.|$PYTHON_BIN scripts/prompts/validate_pack.py"
  "YForum flake8|external/YForum|$PYTHON_BIN -m flake8 YForum run_server.py run_client.py run_offline_gateway.py --count --select=E9,F63,F7,F82 --show-source --statistics"
  "YForum black|external/YForum|$PYTHON_BIN -m black --check YForum tests scripts run_server.py run_client.py run_offline_gateway.py"
  "YForum isort|external/YForum|$PYTHON_BIN -m isort --check-only YForum tests scripts run_server.py run_client.py run_offline_gateway.py"
)

if [ "${LIST:-0}" = 1 ]; then
  for s in "${SPECS[@]}"; do IFS='|' read -r name dir _ <<<"$s"; printf '%-26s %s\n' "$name" "$dir"; done
  exit 0
fi

[ -n "$OUT" ] || OUT="$OUT_BASE/$STAMP"
mkdir -p "$OUT/logs" "$OUT/junit" "$OUT/checks"
ln -sfn "$OUT" "$OUT_BASE/latest" 2>/dev/null || true
ROOT_REL_OUT="$OUT"

wanted() {  # is repository $1 selected?
  [ -z "$ONLY" ] && return 0
  case ",$ONLY," in *",$1,"*) return 0 ;; esac
  case "$1" in YSocial-*) case ",$ONLY," in *",YSocial,"*) return 0 ;; esac ;; esac
  return 1
}

python_for() {  # interpreter for repository $1 (creates the virtualenv with --venv)
  local name="$1"
  if [ "$USE_VENV" = 1 ]; then
    local base="${name%%-plugin-registry}"
    local venv="$VENV_ROOT/$base"
    if [ ! -x "$venv/bin/python" ]; then
      mkdir -p "$VENV_ROOT"
      "$PYTHON_BIN" -m venv "$venv" >>"$OUT/logs/_venv.log" 2>&1 || { echo "$PYTHON_BIN"; return; }
    fi
    echo "$venv/bin/python"
  else
    echo "$PYTHON_BIN"
  fi
}

install_for() {  # pip install the requirements of a repository into its virtualenv
  local name="$1" dir="$2" reqs="$3" py="$4"
  [ "$INSTALL" = 1 ] || return 0
  case "$name" in YSocial-plugin-registry) return 0 ;; esac
  echo "   installing requirements ($reqs)"
  ( cd "$ROOT/$dir" && "$py" -m pip install -q --upgrade pip pytest pytest-timeout >>"$OUT/logs/_install-$name.log" 2>&1
    # shellcheck disable=SC2086
    "$py" -m pip install -q $reqs >>"$OUT/logs/_install-$name.log" 2>&1 ) \
    || echo "   !! some requirements failed to install, see logs/_install-$name.log"
}

split_batches() {  # print the test files under $1 split in $2 batches, one batch per line (space separated)
  ( cd "$ROOT" && find "$1" -name 'test_*.py' | sort ) | awk -v n="$2" '
    { b[(NR-1)%n] = b[(NR-1)%n] " " $0 }
    END { for (i = 0; i < n; i++) if (b[i] != "") print b[i] }'
}

run_pytest() {  # label dir py markers paths...
  local label="$1" dir="$2" py="$3" markers="$4"; shift 4
  local args=(-q -ra --tb=short -p no:cacheprovider -o junit_family=xunit2 "--junitxml=$OUT/junit/$label.xml")
  if "$py" -c 'import pytest_timeout' >/dev/null 2>&1; then args+=("--timeout=$TIMEOUT"); fi
  [ -n "$markers" ] && args+=(-m "$markers")
  local start end rc
  start=$(date +%s)
  ( cd "$ROOT/$dir" && "$py" -m pytest "${args[@]}" "$@" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} ) >"$OUT/logs/$label.log" 2>&1
  rc=$?
  end=$(date +%s)
  printf '%s\t%s\t%s\n' "$label" "$rc" "$((end-start))" >>"$OUT/runs.tsv"
  return $rc
}

: >"$OUT/runs.tsv"
: >"$OUT/notrun.tsv"
echo "Report: $OUT"
echo "Python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))   mode: $([ "$FULL" = 1 ] && echo full || echo 'CI selection')"
echo

for spec in "${SPECS[@]}"; do
  IFS='|' read -r name dir paths ci_markers full_markers reqs <<<"$spec"
  wanted "$name" || continue
  if [ ! -d "$ROOT/$dir" ] || { [ "$dir" != "." ] && [ ! -d "$ROOT/$dir/${paths%% *}" ] && [ ! -d "$ROOT/$dir/$(dirname "${paths%% *}")" ]; }; then
    printf '%s\tnot checked out (%s)\n' "$name" "$dir" >>"$OUT/notrun.tsv"; echo "-- $name: not checked out, skipped"; continue
  fi
  if [ ! -d "$ROOT/$dir/${paths%% *}" ]; then
    printf '%s\tno test directory (%s)\n' "$name" "$paths" >>"$OUT/notrun.tsv"; echo "-- $name: no tests, skipped"; continue
  fi
  py="$(python_for "$name")"
  if ! "$py" -m pytest --version >/dev/null 2>&1; then
    printf '%s\tpytest is not installed for %s\n' "$name" "$py" >>"$OUT/notrun.tsv"; echo "-- $name: pytest missing for $py, skipped"; continue
  fi
  install_for "$name" "$dir" "$reqs" "$py"
  markers="$ci_markers"; [ "$FULL" = 1 ] && markers="$full_markers"
  echo "== $name  ($dir/$paths${markers:+  -m \"$markers\"})"
  if [ "$name" = "YSocial" ]; then
    i=0
    while IFS= read -r files; do
      i=$((i+1))
      # shellcheck disable=SC2086
      run_pytest "YSocial__b$i" "$dir" "$py" "$markers" $files
      printf '   batch %s: exit %s\n' "$i" "$?"
    done < <(split_batches "$paths" "$BATCHES")
  else
    # shellcheck disable=SC2086
    run_pytest "$name" "$dir" "$py" "$markers" $paths
    printf '   exit %s\n' "$?"
  fi
done

if [ "$CHECKS" = 1 ]; then
  : >"$OUT/checks.tsv"
  echo; echo "== static checks"
  for spec in "${CHECK_SPECS[@]}"; do
    IFS='|' read -r label dir cmd <<<"$spec"
    case "$label" in
      YSocial*) wanted YSocial || continue ;;
      YForum*) wanted YForum || continue ;;
    esac
    [ -d "$ROOT/$dir" ] || continue
    log="$OUT/checks/$(echo "$label" | tr ' /' '__').log"
    ( cd "$ROOT/$dir" && eval "$cmd" ) >"$log" 2>&1
    rc=$?
    printf '%s\t%s\t%s\n' "$label" "$rc" "$log" >>"$OUT/checks.tsv"
    printf '   %-34s %s\n' "$label" "$([ $rc = 0 ] && echo ok || echo "FAILED ($rc)")"
  done
fi

# git state of every repository, for the report
: >"$OUT/git.tsv"
for spec in "${SPECS[@]}"; do
  IFS='|' read -r name dir _ <<<"$spec"
  case "$name" in YSocial-*) continue ;; reactive_agents) dir="external/reactive_agents" ;; esac
  [ -d "$ROOT/$dir/.git" ] || [ "$dir" = "." ] || continue
  printf '%s\t%s\t%s\t%s\n' "$name" \
    "$(git -C "$ROOT/$dir" branch --show-current 2>/dev/null)" \
    "$(git -C "$ROOT/$dir" rev-parse --short HEAD 2>/dev/null)" \
    "$(git -C "$ROOT/$dir" status --porcelain 2>/dev/null | grep -vc '^??')" >>"$OUT/git.tsv"
done
{
  echo "python	$($PYTHON_BIN --version 2>&1)"
  echo "pytest	$($PYTHON_BIN -m pytest --version 2>&1 | head -1)"
  echo "platform	$(uname -srm)"
  echo "mode	$([ "$FULL" = 1 ] && echo full || echo 'CI selection')"
  echo "venvs	$([ "$USE_VENV" = 1 ] && echo "$VENV_ROOT" || echo 'no (current interpreter)')"
  echo "date	$(date '+%Y-%m-%d %H:%M:%S')"
} >"$OUT/env.tsv"

# ---------------------------------------------------------------------------------------------- report
"$PYTHON_BIN" - "$OUT" <<'PYEOF'
import collections, csv, json, os, re, sys, xml.etree.ElementTree as ET

out = sys.argv[1]


def tsv(name):
    path = os.path.join(out, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [line.rstrip("\n").split("\t") for line in fh if line.strip()]


def repo_of(label):
    return label.split("__")[0]


def tail(path, n=25):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-n:]).rstrip()
    except OSError:
        return ""


def signature(text):
    text = (text or "").strip().splitlines()[0] if (text or "").strip() else "(no message)"
    text = re.sub(r"0x[0-9a-fA-F]+", "0x…", text)
    text = re.sub(r"(/[\w.\-@+ ]+){2,}", "<path>", text)
    text = re.sub(r"\b\d+\b", "N", text)
    return text[:170]


runs = {label: (int(rc), int(sec)) for label, rc, sec in tsv("runs.tsv")}
repos = collections.OrderedDict()
cases = []  # dicts: repo, id, status, message, location, time
for label in runs:
    repo = repo_of(label)
    r = repos.setdefault(repo, dict(passed=0, failed=0, errors=0, skipped=0, seconds=0, rc=[], logs=[], hasxml=False))
    r["rc"].append(runs[label][0])
    r["seconds"] += runs[label][1]
    r["logs"].append(os.path.join("logs", label + ".log"))
    xml = os.path.join(out, "junit", label + ".xml")
    if not os.path.exists(xml):
        continue
    try:
        root = ET.parse(xml).getroot()
    except ET.ParseError:
        continue
    r["hasxml"] = True
    for tc in root.iter("testcase"):
        ident = "%s::%s" % ((tc.get("classname") or "").replace(".", "/"), tc.get("name")) if tc.get("classname") else tc.get("name")
        entry = dict(repo=repo, id=ident, time=float(tc.get("time") or 0), status="passed", message="", location="")
        for kind in ("failure", "error", "skipped"):
            node = tc.find(kind)
            if node is not None:
                entry["status"] = {"failure": "failed", "error": "errors", "skipped": "skipped"}[kind]
                body = node.text or ""
                msg = node.get("message") or ""
                if kind == "skipped":
                    m = re.search(r"Skipped: (.*?)[\"')]*$", body.strip(), re.S)
                    msg = m.group(1) if m else (body.strip() or msg)
                else:
                    elines = [l[1:].strip() for l in body.splitlines() if l.startswith("E ")]
                    msg = (elines[-1] if elines else "") or msg or body.strip()
                entry["message"] = msg
                locs = re.findall(r"^(\S+\.py:\d+)", body, re.M)
                entry["location"] = locs[-1] if locs else ""
                break
        r[{"passed": "passed", "failed": "failed", "errors": "errors", "skipped": "skipped"}[entry["status"]]] += 1
        cases.append(entry)

notrun = {a: b for a, b, *_ in tsv("notrun.tsv")}
total = collections.Counter()
for r in repos.values():
    for k in ("passed", "failed", "errors", "skipped"):
        total[k] += r[k]


def state(r):
    if r["failed"] or r["errors"]:
        return "FAIL"
    if not r["hasxml"]:
        return "NO RESULT"
    if r["passed"] == 0 and r["skipped"] == 0:
        return "NO TESTS"
    return "ok"


bad = [c for c in cases if c["status"] in ("failed", "errors")]
clusters = collections.OrderedDict()
for c in bad:
    key = signature(c["message"])
    cl = clusters.setdefault(key, dict(count=0, repos=collections.Counter(), tests=[]))
    cl["count"] += 1
    cl["repos"][c["repo"]] += 1
    cl["tests"].append(c)
ordered = sorted(clusters.items(), key=lambda kv: -kv[1]["count"])

missing = collections.Counter()
for c in bad:
    m = re.search(r"No module named '([\w.\-]+)'", c["message"] or "")
    if m:
        missing[(m.group(1).split(".")[0], c["repo"])] += 1

skips = collections.OrderedDict()
for c in cases:
    if c["status"] == "skipped":
        reason = re.sub(r"^\S+\.py:\d+: ", "", signature(c["message"]))
        s = skips.setdefault(reason, dict(count=0, repos=collections.Counter()))
        s["count"] += 1
        s["repos"][c["repo"]] += 1

checks = [dict(label=l, rc=int(rc), log=os.path.relpath(p, out)) for l, rc, p in tsv("checks.tsv")]
env = {k: v for k, *v in tsv("env.tsv") for v in [" ".join(v)]}
git = tsv("git.tsv")

lines = []
w = lines.append
w("# Test report")
w("")
w("%s — %s — %s — %s" % (env.get("date", ""), env.get("python", ""), env.get("pytest", ""), env.get("platform", "")))
w("")
w("Mode: %s. Virtualenvs: %s." % (env.get("mode", ""), env.get("venvs", "")))
w("")
w("## Overview")
w("")
w("| Repository | Result | Passed | Failed | Errors | Skipped | Time (s) |")
w("|---|---|---:|---:|---:|---:|---:|")
for name, r in repos.items():
    w("| %s | %s | %d | %d | %d | %d | %d |" % (name, state(r), r["passed"], r["failed"], r["errors"], r["skipped"], r["seconds"]))
for name, why in notrun.items():
    w("| %s | NOT RUN: %s | | | | | |" % (name, why))
w("| **Total** | | **%d** | **%d** | **%d** | **%d** | |" % (total["passed"], total["failed"], total["errors"], total["skipped"]))
w("")
failing_checks = [c for c in checks if c["rc"] != 0]
w("Static checks: %d of %d failed." % (len(failing_checks), len(checks)) if checks else "Static checks: not run.")
w("")

w("## Problems to fix")
w("")
if not bad and not failing_checks and not any(state(r) in ("NO RESULT",) for r in repos.values()):
    w("Nothing failed.")
    w("")
for key, cl in ordered:
    repos_txt = ", ".join("%s (%d)" % kv for kv in cl["repos"].most_common())
    w("### %d× %s" % (cl["count"], key))
    w("")
    w("Repositories: %s." % repos_txt)
    w("")
    for c in cl["tests"][:8]:
        w("- `%s` — %s" % (c["id"], c["location"] or c["repo"]))
    if len(cl["tests"]) > 8:
        w("- … and %d more (see `summary.json`)" % (len(cl["tests"]) - 8))
    w("")

if missing:
    w("## Missing Python modules")
    w("")
    w("Tests that failed to import a module are usually an environment problem, not a code problem.")
    w("")
    w("| Module | Repository | Tests affected |")
    w("|---|---|---:|")
    for (mod, repo), n in missing.most_common():
        w("| `%s` | %s | %d |" % (mod, repo, n))
    w("")

noresult = [n for n, r in repos.items() if state(r) in ("NO RESULT", "NO TESTS")]
if noresult:
    w("## Runs without results")
    w("")
    for n in noresult:
        w("**%s** — pytest exited with %s without writing results. Last lines of the log:" % (n, ",".join(map(str, repos[n]["rc"]))))
        w("")
        w("```")
        for lg in repos[n]["logs"]:
            w(tail(os.path.join(out, lg), 15))
        w("```")
        w("")

if failing_checks:
    w("## Failed static checks")
    w("")
    for c in failing_checks:
        w("**%s** (exit %d, `%s`):" % (c["label"], c["rc"], c["log"]))
        w("")
        w("```")
        w(tail(os.path.join(out, c["log"]), 12))
        w("```")
        w("")

if skips:
    w("## Skipped tests, by reason")
    w("")
    w("A large group of skips for a missing plugin or package means those tests are not protecting anything in this environment.")
    w("")
    w("| Skipped | Reason | Repositories |")
    w("|---:|---|---|")
    for reason, s in sorted(skips.items(), key=lambda kv: -kv[1]["count"])[:25]:
        w("| %d | %s | %s |" % (s["count"], reason.replace("|", "\\|"), ", ".join("%s (%d)" % kv for kv in s["repos"].most_common())))
    w("")

slow = sorted(cases, key=lambda c: -c["time"])[:15]
if slow and slow[0]["time"] > 0:
    w("## Slowest tests")
    w("")
    w("| Seconds | Repository | Test |")
    w("|---:|---|---|")
    for c in slow:
        w("| %.1f | %s | `%s` |" % (c["time"], c["repo"], c["id"]))
    w("")

if git:
    w("## Repositories")
    w("")
    w("| Repository | Branch | Commit | Modified tracked files |")
    w("|---|---|---|---:|")
    for name, branch, sha, dirty in git:
        w("| %s | %s | %s | %s |" % (name, branch, sha, dirty))
    w("")
w("Logs: `logs/<repository>.log`, JUnit: `junit/<repository>.xml`, checks: `checks/`.")
with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")

summary = dict(
    environment=env,
    totals=dict(total),
    repositories={n: dict(result=state(r), passed=r["passed"], failed=r["failed"], errors=r["errors"], skipped=r["skipped"], seconds=r["seconds"]) for n, r in repos.items()},
    not_run=notrun,
    clusters=[dict(signature=k, count=v["count"], repositories=dict(v["repos"]), tests=[dict(id=t["id"], repo=t["repo"], location=t["location"], message=(t["message"] or "")[:500]) for t in v["tests"]]) for k, v in ordered],
    missing_modules=[dict(module=m, repository=r, tests=n) for (m, r), n in missing.most_common()],
    failed_checks=[dict(label=c["label"], exit=c["rc"], log=c["log"]) for c in failing_checks],
)
with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2)

print()
print("%-26s %-10s %7s %7s %7s %7s" % ("repository", "result", "passed", "failed", "errors", "skipped"))
for name, r in repos.items():
    print("%-26s %-10s %7d %7d %7d %7d" % (name, state(r), r["passed"], r["failed"], r["errors"], r["skipped"]))
for name, why in notrun.items():
    print("%-26s NOT RUN: %s" % (name, why))
print()
print("failure groups: %d   failed static checks: %d" % (len(ordered), len(failing_checks)))
print("report: %s" % os.path.join(out, "report.md"))
sys.exit(1 if (bad or failing_checks or any(state(r) in ("FAIL", "NO RESULT") for r in repos.values())) else 0)
PYEOF
