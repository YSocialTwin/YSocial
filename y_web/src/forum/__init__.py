from __future__ import annotations

from y_web.src.commons.service import (  # noqa: F401
    build_user_feed_posts,
    fetch_feed_page,
    fetch_thread,
    serialize_feed_posts,
)
from y_web.src.forum.actions import (  # noqa: F401
    _calculate_vote_tallies,
    apply_vote,
    create_comment_reddit,
    create_post_reddit,
)
from y_web.src.commons.hot_rank import (  # noqa: F401
    RankedPost,
    base_hot_score,
    longtail_boost,
    rank_posts_longtail,
    stable_uniform_0_1,
)

# --- YForum (Ray runtime of the forum) integration in YSocial ---
#
# A forum experiment on the HPC path runs YForum with its own database; the schema is the one of the forum, so the
# pages of YSocial read it without a translation. The experiment switches of ``/admin/experiment_details`` are mapped
# onto the keys YForum reads (``experiment_config``).


def is_forum_hpc_experiment(experiment) -> bool:
    """A forum experiment that runs on YForum (HPC) rather than on the Flask pair (Standard)."""
    return (
        getattr(experiment, "platform_type", None) == "forum"
        and getattr(experiment, "simulator_type", None) == "HPC"
    )


from .validation import forum_hpc_installed  # noqa: E402,F401
