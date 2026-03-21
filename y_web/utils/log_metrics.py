"""
Backward-compatibility shim for y_web.utils.log_metrics.

The canonical locations are now:
- y_web.src.hpc.log_parser  — raw log parsing and shared helpers
- y_web.src.hpc.log_metrics — metric persistence and completion monitoring

All existing ``from y_web.utils.log_metrics import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.hpc.log_parser or
    y_web.src.hpc.log_metrics instead.
"""

from y_web.src.hpc.log_parser import *  # noqa: F401,F403
from y_web.src.hpc.log_parser import (  # noqa: F401
    _commit_with_retry,
    _ensure_session_clean,
)
from y_web.src.hpc.log_metrics import *  # noqa: F401,F403
