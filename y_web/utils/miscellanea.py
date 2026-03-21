"""
Backward-compatibility shim for y_web.utils.miscellanea.

The canonical location is now y_web.src.system.miscellanea.
All existing from y_web.utils.miscellanea import X call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.system.miscellanea instead.
"""

from y_web.src.system.miscellanea import *  # noqa: F401,F403
