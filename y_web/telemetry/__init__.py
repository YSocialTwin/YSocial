"""
Backward-compatibility shim for y_web.telemetry.

The canonical location is now ``y_web.src.telemetry``.
All existing ``from y_web.src.telemetry import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.telemetry`` instead.
"""

from y_web.src.telemetry import *  # noqa: F401,F403
