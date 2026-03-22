#!/usr/bin/env python3
"""
Shim: y_server_process_runner — logic lives in y_web.src.simulation.process_runner.

This script is kept for backward compatibility. All imports and the main()
entry point delegate to the canonical location.
"""

from y_web.src.simulation.process_runner import run_server_main  # noqa: F401


def main():
    """Backward-compatible entry point — delegates to run_server_main."""
    run_server_main()


if __name__ == "__main__":
    main()
