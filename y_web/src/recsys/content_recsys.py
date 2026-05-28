"""
Content recommendation system algorithms.

Implements various content recommendation strategies for personalizing
the social media feed including reverse chronological, popularity-based,
follower-based, and random sampling approaches.
"""

from sqlalchemy import desc
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.src.models import (
    Follow,
    Post,
    Rounds,
)


def _normalize_content_recsys_mode(mode):
    """Normalize UI/backend content-rec sys aliases to canonical mode names."""
    raw = str(mode or "").strip()
    if not raw:
        return "Random"

    compact = raw.replace("_", "").replace("-", "").replace(" ", "").strip().lower()
    mode_aliases = {
        "reversechrono": "ReverseChrono",
        "rc": "ReverseChrono",
        "reversechronopopularity": "ReverseChronoPopularity",
        "rcp": "ReverseChronoPopularity",
        "reversechronofollowers": "ReverseChronoFollowers",
        "rcf": "ReverseChronoFollowers",
        "reversechronofollowerspopularity": "ReverseChronoFollowersPopularity",
        "fp": "ReverseChronoFollowersPopularity",
        "contentrecsys": "Random",
        "default": "Random",
        "random": "Random",
    }
    return mode_aliases.get(compact, raw)


def _order_query_by_simulation_time(query):
    """
    Order feed items by simulation time, not by row IDs.

    Uses Rounds.day/hour as the primary sort key, with stable post-level
    tie-breakers to keep ordering deterministic.
    """
    return query.outerjoin(Rounds, Post.round == Rounds.id).order_by(
        desc(func.coalesce(Rounds.day, -1)),
        desc(func.coalesce(Rounds.hour, -1)),
        desc(Post.id),
    )


def get_suggested_posts(uid, mode, page=1, per_page=10, follower_ratio=0.6):
    """
    Get recommended posts for a user based on specified algorithm.

    Supports multiple recommendation strategies including chronological feeds,
    popularity-based ranking, follower-focused content, and random sampling.

    Args:
        uid: User ID to get recommendations for, or "all" for global feed
        mode: Recommendation algorithm - "ReverseChrono", "ReverseChronoPopularity",
              "ReverseChronoFollowers", or "Random"
        page: Page number for pagination
        per_page: Number of posts per page
        follower_ratio: Ratio of posts from followed users (for follower-based modes)

    Returns:
        Tuple of (posts, additional_posts) where posts is paginated query result
        and additional_posts may contain supplementary content
    """

    mode = _normalize_content_recsys_mode(mode)

    if uid == "all":
        # get posts in reverse chrono for all users
        posts_query = db.session.query(Post).filter_by(comment_to=-1)
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=per_page, error_out=False
        )
        additional_posts = None
        return posts, additional_posts

    if mode == "ReverseChrono":
        # get posts in reverse chronological order
        posts_query = db.session.query(Post).filter(
            Post.user_id != uid, Post.comment_to == -1
        )
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=per_page, error_out=False
        )
        additional_posts = None

    elif mode == "ReverseChronoPopularity":
        # get posts ordered by likes in reverse chronological order

        posts_query = db.session.query(Post).filter(
            Post.user_id != uid, Post.comment_to == -1
        )
        posts = (
            posts_query.outerjoin(Rounds, Post.round == Rounds.id)
            .order_by(
                desc(func.coalesce(Rounds.day, -1)),
                desc(func.coalesce(Rounds.hour, -1)),
                desc(Post.reaction_count),
                desc(Post.id),
            )
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    elif mode == "ReverseChronoFollowers":
        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers in reverse chronological order

        posts_query = Post.query.filter(
            Post.user_id.in_(follower_ids), Post.comment_to == -1
        )
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=int(per_page * follower_ratio), error_out=False
        )
        additional_query = Post.query.filter(Post.user_id != uid, Post.comment_to == -1)
        additional_posts = _order_query_by_simulation_time(additional_query).paginate(
            page=page,
            per_page=int(per_page * (1 - follower_ratio)),
            error_out=False,
        )

    elif mode == "ReverseChronoFollowersPopularity":
        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers ordered by likes and reverse chronologically
        posts_query = db.session.query(Post).filter(
            Post.user_id.in_(follower_ids), Post.comment_to == -1
        )
        posts = (
            posts_query.outerjoin(Rounds, Post.round == Rounds.id)
            .order_by(
                desc(func.coalesce(Rounds.day, -1)),
                desc(func.coalesce(Rounds.hour, -1)),
                desc(Post.reaction_count),
                desc(Post.id),
            )
            .paginate(
                page=page, per_page=int(per_page * follower_ratio), error_out=False
            )
        )
        additional_query = Post.query.filter(Post.user_id != uid, Post.comment_to == -1)
        additional_posts = _order_query_by_simulation_time(additional_query).paginate(
            page=page,
            per_page=int(per_page * (1 - follower_ratio)),
            error_out=False,
        )

    else:
        # get posts in random order
        posts = (
            Post.query.filter(Post.user_id != uid, Post.comment_to == -1)
            .order_by(func.random())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    return posts, additional_posts
