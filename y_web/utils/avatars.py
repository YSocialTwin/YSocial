"""
Backward-compatibility shim for y_web.utils.avatars.

The canonical location is now ``y_web.src.content.avatars``.

.. deprecated::
    Import directly from ``y_web.src.content.avatars`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.avatars is deprecated; use y_web.src.content.avatars instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.content.avatars import *  # noqa: F401,F403
