#!/usr/bin/env bash
# Runs another release script from a temporary copy of scripts/release. Use it whenever the script switches the
# core to main (phase D): the release scripts exist only on the release branch and would vanish under their own feet.
#
#   scripts/release/run_from_copy.sh merge_phase.sh D --execute
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CORE="$(cd "$HERE/../.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/ysocial-release.XXXXXX")"
cp -R "$HERE/." "$TMP/"
script="${1:?script name required}"; shift
export STATE_DIR="${STATE_DIR:-$CORE/release-state}"
bash "$TMP/$script" "$@"; rc=$?
rm -rf "$TMP"; exit $rc
