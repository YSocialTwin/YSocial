#!/usr/bin/env bash
# Merges the release branch of one repository into main and tags it, as the manifest says.
#
#   scripts/release/merge_repo.sh <directory> [options]      # <directory> as in manifest.tsv ("." = the core)
#     (no option)   dry run: prints what it would do
#     --execute     do it on the LOCAL repository: merge into main, run --test, tag
#     --push        with --execute: also push main and the tag (never forces)
#     --squash      squash instead of a merge commit (the whole release must use the same choice)
#     --test CMD    command run in the repository after the merge and before the tag; if it fails the merge is undone
#
# It refuses to run when the repository has uncommitted changes, when the tag exists, or when main is behind its
# remote. Rollback point: release-state/main_hashes.txt (written by preflight.sh).
set -u
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
dir="${1:?directory required}"; shift
EXEC=0; PUSH=0; SQUASH=0; TESTCMD=""
while [ $# -gt 0 ]; do case "$1" in
  --execute) EXEC=1 ;; --push) PUSH=1 ;; --squash) SQUASH=1 ;; --test) shift; TESTCMD="${1:-}" ;;
  *) echo "unknown option $1"; exit 2 ;; esac; shift; done
row="$(manifest_rows | awk -F'\t' -v d="$dir" '$2 == d')"
[ -n "$row" ] || { echo "$dir is not in the manifest"; exit 2; }
branch="$(echo "$row" | cut -f3)"; tag="$(echo "$row" | cut -f4)"; mode="$(echo "$row" | cut -f5)"
path="$(repo_path "$dir")"; name="$(repo_name "$dir")"
run() { if [ "$EXEC" = "1" ]; then echo "+ $*"; "$@"; else echo "[dry run] $*"; fi; }

[ -z "$(git_in "$path" -c core.fileMode=false status --porcelain)" ] || { echo "$name: uncommitted changes"; exit 1; }
git_in "$path" rev-parse -q --verify "refs/heads/$branch" >/dev/null || { echo "$name: no branch $branch"; exit 1; }
[ "$tag" = "-" ] || { git_in "$path" rev-parse -q --verify "refs/tags/$tag" >/dev/null && { echo "$name: tag $tag exists"; exit 1; }; }
if [ "$EXEC" = "1" ] && git_in "$path" remote get-url origin >/dev/null 2>&1; then
  git_in "$path" fetch -q origin main || { echo "$name: cannot fetch origin"; exit 1; }
  behind="$(git_in "$path" rev-list --count main..origin/main)"
  [ "$behind" = "0" ] || { echo "$name: main is $behind commit(s) behind origin/main: update it first (git pull --ff-only on main)"; exit 1; }
fi

echo "== $name: $branch -> main${tag:+, tag $tag}"
run git_in "$path" checkout -q main
before="$(git_in "$path" rev-parse main)"
if [ "$mode" = "ff" ]; then
  run git_in "$path" merge --ff-only "$branch"
elif [ "$SQUASH" = "1" ]; then
  run git_in "$path" merge --squash "$branch"
  run git_in "$path" commit -q -m "$name: $branch"
else
  run git_in "$path" merge --no-ff -q "$branch" -m "Merge $branch into main"
fi
if [ "$EXEC" = "1" ] && [ -n "$TESTCMD" ]; then
  echo "+ test: $TESTCMD"
  if ! (cd "$path" && bash -c "$TESTCMD"); then
    echo "$name: the test failed, undoing the merge (main back to ${before:0:8})"
    git_in "$path" reset -q --hard "$before"; exit 1
  fi
fi
[ "$tag" = "-" ] || run git_in "$path" tag -a "$tag" -m "$name $tag"
if [ "$PUSH" = "1" ]; then
  run git_in "$path" push origin main
  [ "$tag" = "-" ] || run git_in "$path" push origin "$tag"
fi
[ "$EXEC" = "1" ] && echo "$name: done (main ${before:0:8} -> $(git_in "$path" rev-parse --short main))"
exit 0
