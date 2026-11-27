#!/usr/bin/env bash
# Runs merge_repo.sh for every repository of a phase of the manifest, stopping at the first failure.
#
#   scripts/release/merge_phase.sh A [options of merge_repo.sh]
# Phases: A extensions, B YSimulator, C platforms, E plugin registry (before the core), D core. See the release document.
# Options are passed through (--execute, --push, --squash). A --test option applies to every repository of the phase.
set -u
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
phase="${1:?phase (A|B|C|D|E) required}"; shift
manifest_rows "$phase" | cut -f2 | while read -r dir; do
  "$RELEASE_DIR/merge_repo.sh" "$dir" "$@" || { echo "stopped at $dir"; exit 1; }
done
