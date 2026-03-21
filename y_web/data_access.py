"""
Backward-compatibility shim for y_web.data_access.

The canonical location of all data-access functions is now
``y_web.src.data_access``.  This module re-exports every public function so
that existing ``from y_web.data_access import some_function`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.data_access`` (or its sub-modules
    ``y_web.src.data_access.posts``, ``y_web.src.data_access.users``,
    ``y_web.src.data_access.trends``, ``y_web.src.data_access.profiles``)
    instead.
"""

# Import sub-modules first so all functions are registered before the
# star-import resolves the namespace.
import y_web.src.data_access.posts  # noqa: F401
import y_web.src.data_access.profiles  # noqa: F401
import y_web.src.data_access.trends  # noqa: F401
import y_web.src.data_access.users  # noqa: F401

from y_web.src.data_access import *  # noqa: F401,F403
