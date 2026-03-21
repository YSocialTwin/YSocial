"""
Backward-compatibility shim for y_web.recsys_support.content_recsys.

The canonical location is now ``y_web.src.recsys.content_recsys``.
All existing ``from y_web.recsys_support.content_recsys import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.recsys.content_recsys`` instead.
"""

from y_web.src.recsys.content_recsys import *  # noqa: F401,F403
