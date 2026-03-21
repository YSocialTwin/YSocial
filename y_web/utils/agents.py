"""
Backward-compatibility shim for y_web.utils.agents.

The canonical location is now ``y_web.src.agents.population``.
All existing ``from y_web.utils.agents import X`` call sites
continue to work without modification.

.. deprecated::
    Import directly from ``y_web.src.agents.population`` instead.
"""

from y_web.src.agents.population import *  # noqa: F401,F403
# Re-export private helpers that are accessed by name in tests/internal code
from y_web.src.agents.population import (  # noqa: F401
    _generate_unique_name,
    _normalize_generated_username,
)
