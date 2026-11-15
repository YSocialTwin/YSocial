"""The code every feed-based platform shares: opaque ids, ordering and the display time.

Each submodule *is* the core module (same object), so ``from y_web.sdk.commons.display_time import _format_display_time`` reads what
the core reads and a test that replaces a function of the core is seen by the platform.
"""

from y_web.sdk.commons import display_time, ids, ordering  # noqa: F401

__all__ = ["display_time", "ids", "ordering"]
