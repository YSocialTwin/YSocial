"""
Backward-compatibility shim for y_web.utils.experiment_access.

The canonical location is now ``y_web.src.experiment.access``.
All existing ``from y_web.utils.experiment_access import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.experiment.access`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.experiment_access is deprecated; use y_web.src.experiment.access instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.experiment.access import *  # noqa: F401,F403
