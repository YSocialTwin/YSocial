"""
Backward-compatibility shim for y_web.utils.article_extractor.

The canonical location is now ``y_web.src.content.article_extractor``.

.. deprecated::
    Import directly from ``y_web.src.content.article_extractor`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.article_extractor is deprecated; use y_web.src.content.article_extractor instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.content.article_extractor import *  # noqa: F401,F403
