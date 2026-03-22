#!/usr/bin/env python3
"""Entry-point script for client subprocess execution."""

import os
import sys

# Ensure the repository root is on sys.path so the y_web package can be found
# when this script is invoked directly as a subprocess entry-point.
# y_web/src/simulation/client_runner.py → y_web/src/simulation → y_web/src → y_web → repo root
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from y_web.src.simulation.process_runner import run_client_main

if __name__ == "__main__":
    run_client_main()
