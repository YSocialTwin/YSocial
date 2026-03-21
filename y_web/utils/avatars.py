"""
Backward-compatibility shim for y_web.utils.avatars.

The canonical location is now ``y_web.src.content.avatars``.

.. deprecated::
    Import directly from ``y_web.src.content.avatars`` instead.
"""

from y_web.src.content.avatars import *  # noqa: F401,F403
