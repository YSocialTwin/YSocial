"""
y_web.src.recsys — recommendation system package.

Sub-modules
-----------
content_recsys — post/content recommendation algorithms
follow_recsys  — user/page follow recommendation algorithms

Re-exports the same top-level names as the old recsys_support package.
"""

from y_web.src.recsys.content_recsys import get_suggested_posts  # noqa: F401
from y_web.src.recsys.follow_recsys import get_suggested_users  # noqa: F401
