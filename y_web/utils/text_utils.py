"""
Backward-compatibility shim for y_web.utils.text_utils.

The canonical location is now ``y_web.src.content.text_utils``.

.. deprecated::
    Import directly from ``y_web.src.content.text_utils`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.text_utils is deprecated; use y_web.src.content.text_utils instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.content.text_utils import *  # noqa: F401,F403
