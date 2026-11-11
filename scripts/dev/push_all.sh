#!/usr/bin/env bash
# Push YSocial and every repository under external/ with one command, or only a chosen subset.
#
#   scripts/dev/push_all.sh                       # push every repository that has commits to push
#   scripts/dev/push_all.sh -n                    # dry run: show what would be pushed (git push --dry-run)
#   scripts/dev/push_all.sh -s                    # status only: branch, upstream, ahead/behind, uncommitted files
#   scripts/dev/push_all.sh -r YClient,YDating    # only these repositories (comma separated, case insensitive)
#   scripts/dev/push_all.sh -x YForum,YServer     # every repository except these
#   scripts/dev/push_all.sh -i                    # choose from a numbered list
#   scripts/dev/push_all.sh -y                    # do not ask for confirmation
#   scripts/dev/push_all.sh -l                    # list the repositories and exit
#   scripts/dev/push_all.sh --tags                # also push tags
#   scripts/dev/push_all.sh --no-fetch            # do not contact the remotes to refresh ahead/behind (status only)
#
# Names: YSocial (this repository, also accepted as "root" or ".") and the folder names under external/.
# Order: the repositories under external/ first, YSocial last, so that its plugin pointers never run ahead of the plugins.
# What it does for each repository:
#   - pushes the current branch to its upstream; a branch without upstream is published with "git push -u origin <branch>"
#   - skips a detached HEAD, a repository with nothing to push, and a diverged branch (pull or rebase it first)
#   - never forces: there is no --force option on purpose
#   - reports uncommitted changes (they are not pushed) and keeps going after a failure
# Exit status: 1 when a push failed or a repository is diverged, otherwise 0.
# Works with the bash 3.2 of macOS.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ONLY=""
EXCLUDE=""
DRY=0
STATUS_ONLY=0
YES=0
LIST=0
INTERACTIVE=0
TAGS=0
FETCH=1

usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -r|--repos) [ $# -ge 2 ] || usage 2; ONLY="$2"; shift 2 ;;
    -x|--exclude) [ $# -ge 2 ] || usage 2; EXCLUDE="$2"; shift 2 ;;
    -n|--dry-run) DRY=1; shift ;;
    -s|--status) STATUS_ONLY=1; shift ;;
    -y|--yes) YES=1; shift ;;
    -l|--list) LIST=1; shift ;;
    -i|--interactive) INTERACTIVE=1; shift ;;
    --tags) TAGS=1; shift ;;
    --no-fetch) FETCH=0; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 2 ;;
  esac
done

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
else
  RED=""; GREEN=""; YELLOW=""; DIM=""; BOLD=""; OFF=""
fi

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# every repository: "name|path" (external/ first, YSocial last)
NAMES=()
PATHS=()
for d in "$ROOT"/external/*/; do
  d="${d%/}"
  [ -e "$d/.git" ] || continue
  NAMES+=("$(basename "$d")")
  PATHS+=("$d")
done
NAMES+=("YSocial")
PATHS+=("$ROOT")
TOTAL=${#NAMES[@]}

in_csv() { # in_csv <csv> <name> : is <name> in the comma separated list (case insensitive, root aliases)
  local csv="$1" name item
  name="$(lower "$2")"
  local IFS=','
  for item in $csv; do
    item="$(lower "$(printf '%s' "$item" | tr -d ' ')")"
    case "$item" in root|.|ysocial-root) item="ysocial" ;; esac
    [ "$item" = "$name" ] && return 0
  done
  return 1
}

check_names() { # refuse names that match no repository
  local csv="$1" item found i
  local IFS=','
  for item in $csv; do
    item="$(printf '%s' "$item" | tr -d ' ')"
    [ -z "$item" ] && continue
    found=0
    for ((i = 0; i < TOTAL; i++)); do
      in_csv "$item" "${NAMES[$i]}" && found=1
    done
    if [ "$found" -eq 0 ]; then
      echo "${RED}unknown repository: $item${OFF}  (use -l to list them)" >&2
      exit 2
    fi
  done
}

[ -n "$ONLY" ] && check_names "$ONLY"
[ -n "$EXCLUDE" ] && check_names "$EXCLUDE"

if [ "$LIST" -eq 1 ]; then
  for ((i = 0; i < TOTAL; i++)); do
    printf '%-20s %s\n' "${NAMES[$i]}" "${PATHS[$i]#$ROOT}"
  done
  exit 0
fi

# selection
SEL=()
for ((i = 0; i < TOTAL; i++)); do
  n="${NAMES[$i]}"
  if [ -n "$ONLY" ] && ! in_csv "$ONLY" "$n"; then continue; fi
  if [ -n "$EXCLUDE" ] && in_csv "$EXCLUDE" "$n"; then continue; fi
  SEL+=("$i")
done

if [ "$INTERACTIVE" -eq 1 ]; then
  echo "${BOLD}Repositories${OFF}"
  for ((k = 0; k < ${#SEL[@]}; k++)); do
    printf '  %2d) %s\n' $((k + 1)) "${NAMES[${SEL[$k]}]}"
  done
  printf 'Numbers or names to push (space or comma separated, "all" for every one): '
  read -r answer || exit 1
  answer="$(printf '%s' "$answer" | tr ',' ' ')"
  if [ "$(lower "$answer")" != "all" ]; then
    CHOSEN=()
    for tok in $answer; do
      picked=""
      case "$tok" in
        ''|*[!0-9]*)
          for ((k = 0; k < ${#SEL[@]}; k++)); do
            in_csv "$tok" "${NAMES[${SEL[$k]}]}" && picked="${SEL[$k]}"
          done ;;
        *) [ "$tok" -ge 1 ] && [ "$tok" -le ${#SEL[@]} ] && picked="${SEL[$((tok - 1))]}" ;;
      esac
      if [ -z "$picked" ]; then echo "${RED}not in the list: $tok${OFF}" >&2; exit 2; fi
      CHOSEN+=("$picked")
    done
    SEL=()
    for c in ${CHOSEN[@]+"${CHOSEN[@]}"}; do SEL+=("$c"); done
  fi
fi

if [ ${#SEL[@]} -eq 0 ]; then echo "no repository selected" >&2; exit 2; fi

# state of each selected repository
ACTION=()   # push | publish | skip | diverged
NOTE=()
for ((k = 0; k < ${#SEL[@]}; k++)); do
  i="${SEL[$k]}"; p="${PATHS[$i]}"
  branch="$(git -C "$p" symbolic-ref --short -q HEAD || true)"
  if [ "$FETCH" -eq 1 ] && [ -n "$branch" ]; then
    git -C "$p" fetch --quiet 2>/dev/null || echo "${YELLOW}${NAMES[$i]}: fetch failed, ahead/behind may be stale${OFF}" >&2
  fi
  dirty="$(git -C "$p" status --porcelain --untracked-files=no | wc -l | tr -d ' ')"
  if [ -z "$branch" ]; then
    ACTION[$k]="skip"; NOTE[$k]="detached HEAD"
  else
    up="$(git -C "$p" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
    if [ -z "$up" ]; then
      if git -C "$p" remote | grep -qx origin; then
        ACTION[$k]="publish"; NOTE[$k]="$branch has no upstream: git push -u origin $branch"
      else
        ACTION[$k]="skip"; NOTE[$k]="$branch has no upstream and there is no remote named origin"
      fi
    else
      counts="$(git -C "$p" rev-list --left-right --count "HEAD...$up" 2>/dev/null || echo "0 0")"
      ahead="${counts%%[[:space:]]*}"; behind="${counts##*[[:space:]]}"
      if [ "$ahead" -gt 0 ] && [ "$behind" -gt 0 ]; then
        ACTION[$k]="diverged"; NOTE[$k]="$branch -> $up: $ahead ahead, $behind behind (pull or rebase first)"
      elif [ "$ahead" -gt 0 ]; then
        ACTION[$k]="push"; NOTE[$k]="$branch -> $up: $ahead commit(s) to push"
      elif [ "$behind" -gt 0 ]; then
        ACTION[$k]="skip"; NOTE[$k]="$branch -> $up: nothing to push ($behind behind)"
      else
        ACTION[$k]="skip"; NOTE[$k]="$branch -> $up: up to date"
      fi
    fi
  fi
  if [ "$dirty" -gt 0 ]; then NOTE[$k]="${NOTE[$k]}; $dirty uncommitted file(s) not pushed"; fi
done

echo "${BOLD}Plan${OFF}"
for ((k = 0; k < ${#SEL[@]}; k++)); do
  i="${SEL[$k]}"
  case "${ACTION[$k]}" in
    push|publish) mark="${GREEN}push    ${OFF}" ;;
    diverged)     mark="${RED}diverged${OFF}" ;;
    *)            mark="${DIM}skip    ${OFF}" ;;
  esac
  printf '  %s %-20s %s\n' "$mark" "${NAMES[$i]}" "${NOTE[$k]}"
done

[ "$STATUS_ONLY" -eq 1 ] && exit 0

TODO=0
for ((k = 0; k < ${#SEL[@]}; k++)); do
  case "${ACTION[$k]}" in push|publish) TODO=$((TODO + 1)) ;; esac
done
if [ "$TODO" -eq 0 ]; then
  echo "Nothing to push."
  for a in ${ACTION[@]+"${ACTION[@]}"}; do [ "$a" = "diverged" ] && exit 1; done
  exit 0
fi

if [ "$DRY" -eq 0 ] && [ "$YES" -eq 0 ]; then
  printf 'Push %d repositor%s? [y/N] ' "$TODO" "$([ "$TODO" -eq 1 ] && echo y || echo ies)"
  read -r reply || exit 1
  case "$reply" in y|Y|yes|YES) ;; *) echo "aborted"; exit 1 ;; esac
fi

FAILED=0
PUSHED=0
for ((k = 0; k < ${#SEL[@]}; k++)); do
  i="${SEL[$k]}"; p="${PATHS[$i]}"; n="${NAMES[$i]}"
  case "${ACTION[$k]}" in
    push|publish) ;;
    diverged) FAILED=$((FAILED + 1)); continue ;;
    *) continue ;;
  esac
  args=(push)
  [ "$DRY" -eq 1 ] && args+=(--dry-run)
  [ "$TAGS" -eq 1 ] && args+=(--tags)
  if [ "${ACTION[$k]}" = "publish" ]; then
    args+=(-u origin "$(git -C "$p" symbolic-ref --short HEAD)")
  fi
  echo; echo "${BOLD}== $n${OFF}  ${DIM}git ${args[*]}${OFF}"
  if git -C "$p" "${args[@]}"; then
    PUSHED=$((PUSHED + 1))
  else
    echo "${RED}$n: push failed${OFF}" >&2
    FAILED=$((FAILED + 1))
  fi
done

echo
if [ "$DRY" -eq 1 ]; then verb="would be pushed (dry run)"; else verb="pushed"; fi
echo "${BOLD}Done:${OFF} $PUSHED $verb, $FAILED failed or diverged."
[ "$FAILED" -eq 0 ]
