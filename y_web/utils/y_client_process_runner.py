#!/usr/bin/env python3
"""
Shim: y_client_process_runner — logic lives in y_web.src.simulation.process_runner.

This script is kept for backward compatibility. All imports and the main()
entry point delegate to the canonical location.
"""
import warnings

warnings.warn(
    "y_web.utils.y_client_process_runner is deprecated; use y_web.src.simulation.process_runner instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.simulation.process_runner import (  # noqa: F401
    _candidate_memory_package_dirs,
    _get_client_archetypes,
    _repair_legacy_agent_file,
    _resolve_client_package_dir,
    ensure_agents_have_archetype,
    get_users_per_hour,
    process_agent,
    run_client_main,
    run_simulation,
    sample_agents,
    start_client_process,
)


def main():
    """Backward-compatible entry point — delegates to run_client_main."""
    run_client_main()


if __name__ == "__main__":
    main()
