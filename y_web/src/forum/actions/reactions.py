from __future__ import annotations

from typing import Tuple

from sqlalchemy import func

from y_web import db
from y_web.src.models import Post, Post_Sentiment, Post_topics, Reactions
from y_web.src.forum.actions.posts import _ensure_experiment_context, _get_current_round


def _calculate_vote_tallies(post_id: int) -> Tuple[int, int]:
    """Calculate like and dislike counts for a post."""
    likes = (
        db.session.query(func.count(Reactions.id))
        .filter(Reactions.post_id == post_id, Reactions.type == "like")
        .scalar()
        or 0
    )
    dislikes = (
        db.session.query(func.count(Reactions.id))
        .filter(Reactions.post_id == post_id, Reactions.type == "dislike")
        .scalar()
        or 0
    )
    return int(likes), int(dislikes)


def apply_vote(user, post_id: int, action: str) -> Tuple[int, int]:
    """
    Apply a vote (like/dislike/neutral) to a post.

    Args:
        user: Current user object (from flask_login)
        post_id: ID of the post to vote on
        action: One of "like", "dislike", or "neutral"

    Returns:
        Tuple of (likes, dislikes) counts after the vote

    Raises:
        ValueError: If post not found or action invalid
        RuntimeError: If database operation fails
    """
    if action not in {"like", "dislike", "neutral"}:
        raise ValueError(f"Invalid action: {action}")

    # Ensure experiment database context is set up
    _ensure_experiment_context(user)

    post = Post.query.filter_by(id=post_id).first()
    if post is None:
        raise ValueError(f"Post {post_id} not found")

    round_id = _get_current_round()

    try:
        existing_reaction = (
            Reactions.query.filter_by(post_id=post_id, user_id=user.id)
            .order_by(Reactions.id.desc())
            .first()
        )

        if action == "neutral":
            if existing_reaction is not None:
                db.session.delete(existing_reaction)
                db.session.commit()
            likes, dislikes = _calculate_vote_tallies(post_id)
            post.reaction_count = likes + dislikes
            db.session.commit()
            return likes, dislikes

        if existing_reaction is None:
            reaction = Reactions(
                post_id=post_id,
                user_id=user.id,
                round=round_id,
                type=action,
            )
            db.session.add(reaction)
        else:
            existing_reaction.type = action
            existing_reaction.round = round_id

        db.session.commit()

        likes, dislikes = _calculate_vote_tallies(post_id)
        post.reaction_count = likes + dislikes
        db.session.commit()

        # Get sentiment parent for tracking
        sentiment_parent = ""
        post_sentiment_record = Post_Sentiment.query.filter_by(post_id=post_id).first()
        if post_sentiment_record is not None:
            compound = post_sentiment_record.compound
            if compound > 0.05:
                sentiment_parent = "pos"
            elif compound < -0.05:
                sentiment_parent = "neg"
            else:
                sentiment_parent = "neu"

        # Create reaction sentiment records for each topic
        post_topics_list = Post_topics.query.filter_by(post_id=post_id).all()
        for post_topic in post_topics_list:
            topic_id = post_topic.topic_id

            reaction_sentiment = Post_Sentiment(
                post_id=post_id,
                user_id=user.id,
                pos=0 if action == "dislike" else 1,
                neg=0 if action == "like" else 1,
                neu=0,
                compound=1 if action == "like" else -1,
                sentiment_parent=sentiment_parent,
                round=round_id,
                is_reaction=1,
                topic_id=topic_id,
            )
            db.session.add(reaction_sentiment)
            db.session.commit()

    except Exception as exc:
        db.session.rollback()
        raise RuntimeError(f"Database operation failed: {exc}")

    # Calculate and return vote tallies
    return _calculate_vote_tallies(post_id)
