"""Backward-compatibility shim for y_web.utils.execution_backend.

The canonical location is now ``y_web.src.simulation.execution_backend``.
"""

import warnings

warnings.warn(
    "y_web.utils.execution_backend is deprecated; use "
    "y_web.src.simulation.execution_backend instead.",
    DeprecationWarning,
    stacklevel=2,
)

from y_web.src.simulation.execution_backend import *  # noqa: F401,F403
from y_web.src.simulation.execution_backend import (  # noqa: F401
    backup_population_for_hpc_client,
    start_client,
    start_hpc_client,
    start_hpc_server,
    start_server,
    stop_hpc_client,
    stop_hpc_server,
    terminate_client,
    terminate_process_on_port,
    terminate_server_process,
)
