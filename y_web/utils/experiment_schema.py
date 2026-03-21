"""
Backward-compatibility shim for y_web.utils.experiment_schema.

The canonical location is now ``y_web.src.experiment.schema``.
All existing ``from y_web.utils.experiment_schema import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.experiment.schema`` instead.
"""

from y_web.src.experiment.schema import *  # noqa: F401,F403
