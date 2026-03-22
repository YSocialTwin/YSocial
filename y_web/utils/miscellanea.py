"""
Backward-compatibility shim for y_web.utils.miscellanea.

The canonical location is now y_web.src.system.miscellanea.
All existing from y_web.src.system.miscellanea import X call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.system.miscellanea instead.
"""
import warnings

warnings.warn(
    "y_web.utils.miscellanea is deprecated; use y_web.src.system.miscellanea instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.system.miscellanea import *  # noqa: F401,F403
