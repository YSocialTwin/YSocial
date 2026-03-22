"""
Backward-compatibility shim for y_web.utils.population_platform.

The canonical location is now ``y_web.src.agents.platform``.
All existing ``from y_web.utils.population_platform import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.agents.platform`` instead.
"""
import warnings

warnings.warn(
    "y_web.utils.population_platform is deprecated; use y_web.src.agents.platform instead.",
    DeprecationWarning,
    stacklevel=2,
)


from y_web.src.agents.platform import *  # noqa: F401,F403
