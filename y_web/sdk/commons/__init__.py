"""The code every feed-based platform shares: opaque ids, ordering, hot ranking and the feed/thread services.

Each submodule *is* the core module (same object), so ``from y_web.sdk.commons.service import fetch_feed_page`` reads what
the core reads and a test that replaces a function of the core is seen by the platform.
"""

from y_web.sdk.commons import hot_rank, ids, ordering, service  # noqa: F401

__all__ = ["hot_rank", "ids", "ordering", "service"]
