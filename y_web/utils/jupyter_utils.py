"""
Backward-compatibility shim for y_web.utils.jupyter_utils.

The canonical location is now y_web.src.system.jupyter_utils.
All existing from y_web.utils.jupyter_utils import X call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.system.jupyter_utils instead.
"""

from y_web.src.system.jupyter_utils import *  # noqa: F401,F403
