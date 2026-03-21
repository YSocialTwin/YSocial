"""
Backward-compatibility shim for y_web.utils.desktop_file_handler.

The canonical location is now y_web.src.system.desktop_file_handler.
All existing from y_web.utils.desktop_file_handler import X call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.system.desktop_file_handler instead.
"""

from y_web.src.system.desktop_file_handler import *  # noqa: F401,F403
