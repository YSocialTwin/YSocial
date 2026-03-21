"""
Backward-compatibility shim for y_web.utils.experiment_helpers.

The canonical location is now ``y_web.src.experiment.helpers``.
All existing ``from y_web.utils.experiment_helpers import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.experiment.helpers`` instead.
"""

from y_web.src.experiment.helpers import *  # noqa: F401,F403
