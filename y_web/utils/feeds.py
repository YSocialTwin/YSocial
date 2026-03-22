"""
Backward-compatibility shim for y_web.utils.feeds.

The canonical location is now ``y_web.src.content.feeds``.

.. deprecated::
    Import directly from ``y_web.src.content.feeds`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.feeds is deprecated; use y_web.src.content.feeds instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.content.feeds import *  # noqa: F401,F403
