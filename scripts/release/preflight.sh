#!/usr/bin/env bash
# Checks to run before the first merge. Changes nothing except the state folder (release-state/).
#
#   scripts/release/preflight.sh                # repositories, branches, tags, core checks (a few minutes)
#   scripts/release/preflight.sh --quick        # repositories, branches and tags only
#   scripts/release/preflight.sh --tests        # also the full core test suite (one pytest process, long)
#
# Needs a Python with the core requirements: RELEASE_PY=/path/to/python scripts/release/preflight.sh
# Writes release-state/main_hashes.txt (the hash of main of every repository): that is the rollback point.
# Exit status 1 when something failed.
set -u
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
QUICK=0; TESTS=0
for a in "$@"; do case "$a" in --quick) QUICK=1 ;; --tests) TESTS=1 ;; *) echo "unknown option $a"; exit 2 ;; esac; done
mkdir -p "$STATE_DIR"; : > "$STATE_DIR/main_hashes.txt"

echo "== repositories, branches and tags"
for row in $(manifest_rows | tr '\t' '|'); do
  IFS='|' read -r phase dir branch tag mode <<< "$row"
  path="$(repo_path "$dir")"; name="$(repo_name "$dir")"
  if [ ! -e "$path/.git" ]; then bad "$name: not a git repository ($path)"; continue; fi
  git_in "$path" rev-parse --verify -q "refs/heads/$branch" >/dev/null || { bad "$name: branch $branch does not exist"; continue; }
  git_in "$path" rev-parse --verify -q refs/heads/main >/dev/null || { bad "$name: no local main"; continue; }
  # a file-mode change that is not a content change does not count (mounted folders flip the execute bit)
  dirty="$(git_in "$path" -c core.fileMode=false status --porcelain | wc -l | tr -d ' ')"
  [ "$dirty" = "0" ] && ok "$name: clean, $branch -> main ($(git_in "$path" rev-list --count main.."$branch") commits)" || bad "$name: $dirty uncommitted change(s)"
  if [ "$mode" = "ff" ]; then
    git_in "$path" merge-base --is-ancestor main "$branch" && ok "$name: main is an ancestor of $branch (fast-forward possible)" || bad "$name: not a fast-forward"
  else
    git_in "$path" merge-tree "$(git_in "$path" merge-base main "$branch")" main "$branch" 2>/dev/null | grep -q '^<<<<<<<' && bad "$name: merging $branch into main conflicts" || ok "$name: no textual conflict with main"
  fi
  if [ "$tag" != "-" ]; then
    git_in "$path" rev-parse -q --verify "refs/tags/$tag" >/dev/null && bad "$name: tag $tag already exists" || ok "$name: tag $tag is free"
  fi
  echo "$name $(git_in "$path" rev-parse main)" >> "$STATE_DIR/main_hashes.txt"
done
echo "  main hashes recorded in $STATE_DIR/main_hashes.txt"

echo "== versions"
if [ -f "$CORE/VERSION" ]; then v="$(tr -d '[:space:]' < "$CORE/VERSION")"; [ "$v" = "4.1.0" ] && ok "core VERSION is $v" || bad "core VERSION is $v, expected 4.1.0"; fi
for f in external/YDating/meta/info.json external/YInstantMessaging/meta/info.json; do
  # dev0 is fine for a -rc tag; it must go before a final v0.1.0
  grep -q 'dev0' "$CORE/$f" && ! grep -qP '\tv0\.1\.0-rc' "$CORE/scripts/release/manifest.tsv" && warn "$f still says dev0 (run scripts/release/drop_dev_suffix.sh before tagging v0.1.0)"
done

if [ "$QUICK" = "0" ]; then
  echo "== core checks ($PY)"
  cd "$CORE" || exit 1
  run() { local label="$1"; shift; if "$@" > "$STATE_DIR/last.log" 2>&1; then ok "$label"; else bad "$label (see $STATE_DIR/last.log)"; tail -5 "$STATE_DIR/last.log"; fi; }
  run "English prompt hashes" "$PY" scripts/prompts/snapshot_hashes.py --check
  run "prompt packs" "$PY" scripts/prompts/validate_pack.py
  run "i18n catalogs" "$PY" scripts/i18n/catalogs.py check
  run "production imports" "$PY" scripts/dev/check_production_imports.py
  run "built-in plugin list matches its recorded hash" "$PY" scripts/packaging/sync_builtin_plugins.py --verify
  run "decoupling gate and canary platform" "$PY" -m pytest -q -p no:cacheprovider y_web/tests/test_decoupling_gate.py y_web/tests/test_canary_platform.py y_web/tests/test_platform_baseline.py
  if [ "$TESTS" = "1" ]; then run "full core test suite" "$PY" -m pytest y_web/tests/ -q -p no:cacheprovider --timeout=300; fi
fi
echo; [ "$FAILED" = "0" ] && echo "preflight: OK" || { echo "preflight: $FAILED problem(s)"; exit 1; }
