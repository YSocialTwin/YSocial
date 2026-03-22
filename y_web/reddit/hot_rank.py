"""Legacy shim — canonical implementation is in y_web.src.forum.hot_rank."""
from __future__ import annotations

from y_web.src.forum.hot_rank import (  # noqa: F401
    RankedPost,
    base_hot_score,
    longtail_boost,
    rank_posts_longtail,
    stable_uniform_0_1,
)

