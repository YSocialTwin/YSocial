"""
Backward-compatibility shim for y_web.utils.path_utils.

The canonical location is now y_web.src.system.path_utils.
All existing from y_web.src.system.path_utils import X call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.system.path_utils instead.
"""
import warnings

warnings.warn(
    "y_web.utils.path_utils is deprecated; use y_web.src.system.path_utils instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.system.path_utils import *  # noqa: F401,F403
