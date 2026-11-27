#!/usr/bin/env bash
# Deletes the release branches once everything is verified. Dry run unless --execute. Only deletes a branch that
# main already contains (git branch -d, never -D); with --remote also deletes it on origin.
#
#   scripts/release/cleanup_branches.sh                       # shows what would be deleted
#   scripts/release/cleanup_branches.sh --execute [--remote]
set -u
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
EXEC=0; REMOTE=0
for a in "$@"; do case "$a" in --execute) EXEC=1 ;; --remote) REMOTE=1 ;; *) echo "unknown option $a"; exit 2 ;; esac; done
for row in $(manifest_rows | tr '\t' '|'); do
  IFS='|' read -r phase dir branch tag mode <<< "$row"
  path="$(repo_path "$dir")"; name="$(repo_name "$dir")"
  git_in "$path" rev-parse -q --verify "refs/heads/$branch" >/dev/null || continue
  if ! git_in "$path" merge-base --is-ancestor "$branch" main; then warn "$name: main does not contain $branch, kept"; continue; fi
  if [ "$EXEC" = "1" ]; then
    [ "$(git_in "$path" branch --show-current)" = "$branch" ] && git_in "$path" checkout -q main
    git_in "$path" branch -d "$branch" >/dev/null && ok "$name: deleted $branch"
    [ "$REMOTE" = "1" ] && git_in "$path" push -q origin --delete "$branch" 2>/dev/null && ok "$name: deleted origin/$branch"
  else
    echo "[dry run] $name: would delete $branch$([ "$REMOTE" = 1 ] && echo " and origin/$branch")"
  fi
done
