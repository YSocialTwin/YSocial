"""
Backward-compatibility shim for y_web.utils.check_blog.

The canonical location is now y_web.src.system.check_blog.
All existing from y_web.utils.check_blog import X call sites
continue to work without modification.

.. deprecated::
    Import directly from y_web.src.system.check_blog instead.
"""
import warnings

warnings.warn(
    "y_web.utils.check_blog is deprecated; use y_web.src.system.check_blog instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.system.check_blog import *  # noqa: F401,F403
