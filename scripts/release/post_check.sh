#!/usr/bin/env bash
# What to verify after the merges and the tags. Reads only (it fetches the remotes), changes nothing.
#
#   scripts/release/post_check.sh            # local state: main contains the branch, tags exist, versions agree
#   scripts/release/post_check.sh --remote   # also: the remote has main and the tag at the same commit
#   scripts/release/post_check.sh --fresh    # also: the clean-install check with everything on main (long)
set -u
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
REMOTE=0; FRESH=0
for a in "$@"; do case "$a" in --remote) REMOTE=1 ;; --fresh) FRESH=1 ;; *) echo "unknown option $a"; exit 2 ;; esac; done
for row in $(manifest_rows | tr '\t' '|'); do
  IFS='|' read -r phase dir branch tag mode <<< "$row"
  path="$(repo_path "$dir")"; name="$(repo_name "$dir")"
  git_in "$path" merge-base --is-ancestor "$branch" main && ok "$name: main contains $branch" || bad "$name: main does not contain $branch"
  if [ "$tag" != "-" ]; then
    git_in "$path" rev-parse -q --verify "refs/tags/$tag" >/dev/null || { bad "$name: tag $tag missing"; continue; }
    [ "$(git_in "$path" rev-parse "$tag^{commit}")" = "$(git_in "$path" rev-parse main)" ] && ok "$name: $tag is on main" || warn "$name: $tag is not the tip of main"
  fi
  if [ "$REMOTE" = "1" ]; then
    git_in "$path" fetch -q origin main --tags 2>/dev/null
    [ "$(git_in "$path" rev-parse main)" = "$(git_in "$path" rev-parse origin/main)" ] && ok "$name: origin/main equals main" || bad "$name: origin/main differs from main"
    [ "$tag" = "-" ] || { git_in "$path" ls-remote --tags origin "$tag" | grep -q "$tag" && ok "$name: tag $tag is on the remote" || bad "$name: tag $tag is not on the remote"; }
  fi
done
echo "== core"
cd "$CORE" || exit 1
v="$(tr -d '[:space:]' < VERSION)"; [ "$v" = "4.1.0" ] && ok "VERSION $v" || bad "VERSION $v"
"$PY" scripts/packaging/sync_builtin_plugins.py --verify >/dev/null 2>&1 && ok "built-in copy matches its hash" || bad "built-in copy edited by hand"
"$PY" scripts/packaging/sync_builtin_plugins.py --check-latest >/dev/null 2>&1 && ok "built-in copy equals the registry main (release gate)" || bad "built-in copy differs from the registry main (sync it)"
if [ "$FRESH" = "1" ]; then
  echo "== clean install on main (long)"
  sed -e 's/:\(pre-merge-[a-z0-9]*\|decouple-zero\|platform-decoupling\)/:main/' -e "s#^HERE=.*#HERE=$CORE#" \
      scripts/dev/fresh_install_check.sh > "$STATE_DIR/fresh_on_main.sh"
  WITH_YCREATOR=1 WORK="${WORK:-/tmp/ysocial_fresh_main}" bash "$STATE_DIR/fresh_on_main.sh" && ok "clean install" || bad "clean install (see its report.md)"
fi
echo; [ "$FAILED" = "0" ] && echo "post_check: OK" || { echo "post_check: $FAILED problem(s)"; exit 1; }
