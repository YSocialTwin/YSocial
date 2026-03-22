"""
Backward-compatibility shim for y_web.telemetry.usage_data.

The canonical location is now ``y_web.src.telemetry.usage_data``.
All existing ``from y_web.src.telemetry.usage_data import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.telemetry.usage_data`` instead.
"""

from y_web.src.telemetry.usage_data import *  # noqa: F401,F403
