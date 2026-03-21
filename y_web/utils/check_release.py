"""
Backward-compatibility shim for y_web.utils.check_release.

The canonical location is now y_web.src.system.check_release.
All existing from y_web.utils.check_release import X call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.system.check_release instead.
"""

from y_web.src.system.check_release import *  # noqa: F401,F403
