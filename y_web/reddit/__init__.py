"""Legacy shim — canonical implementations are in y_web.src.forum."""
from __future__ import annotations

from y_web.src.forum import (  # noqa: F401
    apply_vote,
    base_hot_score,
    build_user_feed_posts,
    create_comment_reddit,
    create_post_reddit,
    fetch_feed_page,
    fetch_thread,
    rank_posts_longtail,
    serialize_feed_posts,
)
