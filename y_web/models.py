"""
Backward-compatibility shim for y_web.models.

The canonical location of all ORM model classes is now ``y_web.src.models``.
This module re-exports every class so that existing ``from y_web.models import
SomeModel`` imports continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.models`` (or its sub-modules
    ``y_web.src.models.experiment``, ``y_web.src.models.admin``,
    ``y_web.src.models.config``) instead.
"""

# Import sub-modules first so that SQLAlchemy registers every mapper before
# any caller accesses db.Model.metadata.
import y_web.src.models.admin  # noqa: F401
import y_web.src.models.config  # noqa: F401
import y_web.src.models.experiment  # noqa: F401

from y_web.src.models import *  # noqa: F401,F403
