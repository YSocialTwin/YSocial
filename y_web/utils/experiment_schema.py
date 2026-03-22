"""
Backward-compatibility shim for y_web.utils.experiment_schema.

The canonical location is now ``y_web.src.experiment.schema``.
All existing ``from y_web.src.experiment.schema import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.experiment.schema`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.experiment_schema is deprecated; use y_web.src.experiment.schema instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.experiment.schema import *  # noqa: F401,F403
