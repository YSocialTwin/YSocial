"""
Backward-compatibility shim for y_web.utils.experiment_schedule_monitor.

The canonical location is now ``y_web.src.experiment.schedule_monitor``.
All existing ``from y_web.utils.experiment_schedule_monitor import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.experiment.schedule_monitor`` instead.
"""

from y_web.src.experiment.schedule_monitor import *  # noqa: F401,F403
