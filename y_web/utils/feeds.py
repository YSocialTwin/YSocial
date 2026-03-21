"""
Backward-compatibility shim for y_web.utils.feeds.

The canonical location is now ``y_web.src.content.feeds``.

.. deprecated::
    Import directly from ``y_web.src.content.feeds`` instead.
"""

from y_web.src.content.feeds import *  # noqa: F401,F403
