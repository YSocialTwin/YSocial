"""
Backward-compatibility shim for y_web.recsys_support.

The canonical location is now ``y_web.src.recsys``.
All existing ``from y_web.recsys_support import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.recsys`` instead.
"""

from y_web.src.recsys import *  # noqa: F401,F403
