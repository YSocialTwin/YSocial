#!/usr/bin/env bash
# Turns 0.1.0.dev0 into 0.1.0 in YDating and YInstantMessaging (on their release branch) and commits it.
# Run it before merging those two repositories, and only if you decided to release them as v0.1.0.
#
#   scripts/release/drop_dev_suffix.sh            # show what would change
#   scripts/release/drop_dev_suffix.sh --execute  # change and commit on the current branch of each repository
#
# The commit is made with your own git identity (no trailer added).
set -u
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
EXEC=0; [ "${1:-}" = "--execute" ] && EXEC=1
for spec in "external/YDating:meta/info.json YDating/__init__.py" "external/YInstantMessaging:meta/info.json yinstantmessaging/version.py"; do
  dir="${spec%%:*}"; files="${spec#*:}"; path="$(repo_path "$dir")"; name="$(repo_name "$dir")"
  branch="$(git_in "$path" branch --show-current)"
  [ "$branch" = "decouple-zero" ] || { bad "$name: on $branch, expected decouple-zero"; continue; }
  hits="$(cd "$path" && grep -ln '0\.1\.0\.dev0' $files 2>/dev/null)"
  [ -z "$hits" ] && { ok "$name: no dev0 left"; continue; }
  echo "$name: $(echo $hits | tr '\n' ' ')"
  if [ "$EXEC" = "1" ]; then
    (cd "$path" && for f in $hits; do sed -i.bak 's/0\.1\.0\.dev0/0.1.0/g' "$f" && rm -f "$f.bak"; done && git add $hits && git commit -q -m "Versione 0.1.0 (senza dev0)" && ok "$name: committed $(git rev-parse --short HEAD)")
  fi
done
[ "$FAILED" = "0" ]
