"""
Backward-compatibility shim for y_web.utils.log_sync_scheduler.

The canonical location is now y_web.src.hpc.log_sync_scheduler.
All existing ``from y_web.src.hpc.log_sync_scheduler import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.hpc.log_sync_scheduler instead.
"""
import warnings

warnings.warn(
    "y_web.utils.log_sync_scheduler is deprecated; use y_web.src.hpc.log_sync_scheduler instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.hpc.log_sync_scheduler import *  # noqa: F401,F403
from y_web.src.hpc.log_sync_scheduler import (  # noqa: F401
    _scheduler,
    _scheduler_lock,
)
