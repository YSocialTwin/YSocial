#!/usr/bin/env bash
# Turns 0.1.0.dev0 into 0.1.0 in YDating, YInstantMessaging and YFederation (on their release branch) and commits it.
# Run it before merging those repositories (all three are released as v0.1.0).
#
#   scripts/release/drop_dev_suffix.sh            # show what would change
#   scripts/release/drop_dev_suffix.sh --execute  # change and commit on the current branch of each repository
#
# The commit is made with the git identity set in the environment, with the Claude trailers.
set -u
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
TRAILERS="Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Gr2XS4TNFgny4x3U8ubQWw"
EXEC=0; [ "${1:-}" = "--execute" ] && EXEC=1
for spec in "external/YDating:decouple-zero:meta/info.json YDating/__init__.py" "external/YInstantMessaging:decouple-zero:meta/info.json yinstantmessaging/version.py" "external/YFederation:platform-decoupling:pyproject.toml meta/info.json ysocial_federation/__init__.py"; do
  dir="${spec%%:*}"; rest="${spec#*:}"; want="${rest%%:*}"; files="${rest#*:}"; path="$(repo_path "$dir")"; name="$(repo_name "$dir")"
  branch="$(git_in "$path" branch --show-current)"
  [ "$branch" = "$want" ] || { bad "$name: on $branch, expected $want"; continue; }
  hits="$(cd "$path" && grep -ln '0\.1\.0\.dev0' $files 2>/dev/null)"
  [ -z "$hits" ] && { ok "$name: no dev0 left"; continue; }
  echo "$name: $(echo $hits | tr '\n' ' ')"
  if [ "$EXEC" = "1" ]; then
    (cd "$path" && for f in $hits; do sed -i.bak 's/0\.1\.0\.dev0/0.1.0/g' "$f" && rm -f "$f.bak"; done && git add $hits && git commit -q -m "Versione 0.1.0 (senza dev0)" -m "$TRAILERS" && ok "$name: committed $(git rev-parse --short HEAD)")
  fi
done
[ "$FAILED" = "0" ]
