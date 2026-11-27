#!/usr/bin/env bash
# Shared helpers of the release scripts (sourced, not run). Works with the bash 3.2 of macOS.
RELEASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE="${CORE:-$(cd "$RELEASE_DIR/../.." && pwd)}"
MANIFEST="${MANIFEST:-$RELEASE_DIR/manifest.tsv}"
STATE_DIR="${STATE_DIR:-$CORE/release-state}"
PY="${RELEASE_PY:-python3}"
export PYTHONPATH="$CORE:$CORE/external${PYTHONPATH:+:$PYTHONPATH}"
export YSOCIAL_HOME="${YSOCIAL_HOME:-$CORE}"

ok()   { printf '  ok    %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; FAILED=$((FAILED + 1)); }
FAILED=0

# manifest_rows [phase]  ->  "phase<TAB>dir<TAB>branch<TAB>tag<TAB>mode" lines, comments skipped
manifest_rows() {
  grep -v '^#' "$MANIFEST" | grep -v '^[[:space:]]*$' | awk -F'\t' -v p="${1:-}" 'p == "" || $1 == p'
}
repo_path() { if [ "$1" = "." ]; then echo "$CORE"; else echo "$CORE/$1"; fi; }
repo_name() { if [ "$1" = "." ]; then echo YSocial; else basename "$1"; fi; }
git_in() { local d="$1"; shift; git -C "$d" "$@"; }
