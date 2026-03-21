"""
Backward-compatibility shim for y_web.experiment_context.

The canonical location is now ``y_web.src.experiment.context``.
All existing ``from y_web.experiment_context import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.experiment.context`` instead.
"""

from y_web.src.experiment.context import *  # noqa: F401,F403
