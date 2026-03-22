"""
Backward-compatibility shim for y_web.utils.experiment_clock.

The canonical location is now ``y_web.src.experiment.clock``.
All existing ``from y_web.utils.experiment_clock import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.experiment.clock`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.experiment_clock is deprecated; use y_web.src.experiment.clock instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.experiment.clock import *  # noqa: F401,F403
