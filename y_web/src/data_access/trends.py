"""
Trending-content data-access helpers.

Provides functions for retrieving currently trending hashtags, emotions,
topics, and a user's top hashtags based on recent simulation activity.
"""

from sqlalchemy import desc
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.src.models import (
    Emotions,
    Hashtags,
    Interests,
    Post,
    Post_emotions,
    Post_hashtags,
    Post_topics,
    Rounds,
)


def _compute_last_round(last_round_obj):
    """Compute the absolute round number from a Rounds ORM object.

    Args:
        last_round_obj: Rounds instance or None

    Returns:
        Integer round number (day * 24 + hour), or 0 if None
    """
    if last_round_obj is None:
        return 0
    return last_round_obj.day * 24 + last_round_obj.hour


def get_trending_emotions(limit=10, window=120):
    """Get the trending emotions.

    Args:
        limit: Maximum number of emotions to return (default: 10)
        window: Number of rounds to look back (default: 120)

    Returns:
        List of dicts with keys ``emotion``, ``count``, ``id``
    """
    last_round_obj = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round = _compute_last_round(last_round_obj)

    em = (
        db.session.query(
            Emotions.id,
            Emotions.emotion,
            func.count(Post_emotions.emotion_id).label("count"),
        )
        .join(Post_emotions, Post_emotions.emotion_id == Emotions.id)
        .join(Post, Post.id == Post_emotions.post_id)
        .filter(Post.round >= last_round - window)
        .group_by(Emotions.id, Emotions.emotion)
        .order_by(desc("count"))
        .limit(limit)
    ).all()

    return [{"emotion": e[1], "count": e[2], "id": e[0]} for e in em]


def get_trending_hashtags(limit=10, window=120):
    """Get the trending hashtags.

    Args:
        limit: Maximum number of hashtags to return (default: 10)
        window: Number of rounds to look back (default: 120)

    Returns:
        List of dicts with keys ``hashtag``, ``count``, ``id``
    """
    last_round_obj = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round = _compute_last_round(last_round_obj)

    ht = (
        db.session.query(
            Hashtags.id,
            Hashtags.hashtag,
            func.count(Post_hashtags.hashtag_id).label("count"),
        )
        .join(Post_hashtags, Post_hashtags.hashtag_id == Hashtags.id)
        .join(Post, Post.id == Post_hashtags.post_id)
        .filter(Post.round >= last_round - window)
        .group_by(Hashtags.id, Hashtags.hashtag)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    return [{"hashtag": h[1], "count": h[2], "id": h[0]} for h in ht]


def get_trending_topics(limit=10, window=120):
    """
    Get currently trending topics based on recent post activity.

    Args:
        limit: Maximum number of topics to return (default: 10)
        window: Number of rounds to look back for trend calculation (default: 120)

    Returns:
        List of dicts with keys ``id``, ``topic``, ``count``
    """
    last_round_obj = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round = _compute_last_round(last_round_obj)

    tp = (
        db.session.query(
            Interests.iid,
            Interests.interest,
            func.count(Post_topics.topic_id).label("count"),
        )
        .join(Post_topics, Post_topics.topic_id == Interests.iid)
        .join(Post, Post.id == Post_topics.post_id)
        .filter(Post.round >= last_round - window)
        .group_by(Interests.iid, Interests.interest)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    return [{"id": t[0], "topic": t[1], "count": t[2]} for t in tp]


def get_top_user_hashtags(user_id, limit=10):
    """
    Get most frequently used hashtags by a user.

    Args:
        user_id: ID of the user to get hashtags for
        limit: Maximum number of hashtags to return (default: 10)

    Returns:
        List of dicts with keys ``id``, ``hashtag``, ``count``
    """
    ht = (
        Post.query.filter_by(user_id=user_id)
        .join(Post_hashtags, Post.id == Post_hashtags.post_id)
        .join(Hashtags, Post_hashtags.hashtag_id == Hashtags.id)
        .with_entities(
            Hashtags.id,
            Hashtags.hashtag,
            func.count(Post_hashtags.hashtag_id).label("count"),
        )
        .group_by(Hashtags.id, Hashtags.hashtag)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    return [{"id": h[0], "hashtag": h[1], "count": h[2]} for h in ht]
