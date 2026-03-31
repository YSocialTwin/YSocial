"""
User-centric data-access helpers.

Provides functions for retrieving a user's friends (followers/followees),
mutual friends with another user, and the user's most recent interests.
"""

from sqlalchemy import desc
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.src.data_access.trends import _compute_last_round
from y_web.src.models import (
    Admin_users,
    Agent,
    Follow,
    Interests,
    Page,
    Reactions,
    Rounds,
    User_interest,
    User_mgmt,
)


def _reduce_latest_follow_map(events, *, source_attr: str, target_attr: str):
    latest = {}
    for event in events or []:
        try:
            source_id = int(getattr(event, source_attr))
            target_id = int(getattr(event, target_attr))
            event_id = int(getattr(event, "id"))
        except Exception:
            continue
        current = latest.get((source_id, target_id))
        if current is None or event_id > current[0]:
            latest[(source_id, target_id)] = (
                event_id,
                str(getattr(event, "action", "") or "").strip().lower(),
            )
    return latest


def _active_follow_pairs():
    events = Follow.query.order_by(Follow.id.asc()).all()
    latest = _reduce_latest_follow_map(
        events, source_attr="user_id", target_attr="follower_id"
    )
    return {
        (user_id, follower_id)
        for (user_id, follower_id), (_event_id, action) in latest.items()
        if action == "follow" and user_id != follower_id
    }


def count_followees(user_id):
    active_pairs = _active_follow_pairs()
    return sum(1 for source_id, _target_id in active_pairs if source_id == int(user_id))


def count_followers(user_id):
    active_pairs = _active_follow_pairs()
    return sum(1 for _source_id, target_id in active_pairs if target_id == int(user_id))


def get_mutual_friends(user_a, user_b, limit=10):
    """Get the mutual friends between two users.

    Args:
        user_a: ID of the first user
        user_b: ID of the second user
        limit: Maximum number of results (default: 10)

    Returns:
        List of dicts with keys ``id``, ``username``, ``profile_pic``
    """
    active_pairs = _active_follow_pairs()
    friends_a = {target_id for source_id, target_id in active_pairs if source_id == int(user_a)}
    friends_b = {target_id for source_id, target_id in active_pairs if source_id == int(user_b)}
    mutual_friends = list(friends_a & friends_b)

    res = []
    added = {}
    for uid in mutual_friends[:limit]:
        user = User_mgmt.query.filter_by(id=uid).first()
        profile_pic = ""
        if user.is_page == 1:
            page = Page.query.filter_by(name=user.username).first()
            if page is not None:
                profile_pic = page.logo
        else:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = (
                ag.profile_pic
                if ag is not None and ag.profile_pic is not None
                else Admin_users.query.filter_by(username=user.username)
                .first()
                .profile_pic
            )

        if user.id not in added:
            res.append(
                {"id": user.id, "username": user.username, "profile_pic": profile_pic}
            )
            added[user.id] = None

    return res


def get_user_friends(user_id, limit=12, page=1):
    """Get the followers and followees of the user with pagination.

    Args:
        user_id: ID of the user
        limit: Items per page (default: 12)
        page: Current page number (default: 1)

    Returns:
        Tuple of (followers_list, followee_list, total_followers, total_followees)
    """
    if page < 1:
        page = 1

    active_pairs = _active_follow_pairs()
    followee_ids = sorted(
        [target_id for source_id, target_id in active_pairs if source_id == int(user_id)],
        reverse=True,
    )
    follower_ids = sorted(
        [source_id for source_id, target_id in active_pairs if target_id == int(user_id)],
        reverse=True,
    )

    number_followees = len(followee_ids)
    number_followers = len(follower_ids)

    followee_list = []
    followers_list = []

    if (number_followers - page * limit < -limit) and (
        number_followees - page * limit < -limit
    ):
        return get_user_friends(user_id, limit=limit, page=page - 1)

    start = max(0, (page - 1) * limit)
    end = start + limit

    if start < number_followees:
        for uid_f in followee_ids[start:end]:
            f = User_mgmt.query.filter_by(id=uid_f).first()
            if f is None:
                continue
            followee_list.append(
                {
                    "id": uid_f,
                    "username": f.username,
                    "number_reactions": Reactions.query.filter_by(
                        user_id=uid_f
                    ).count(),
                    "number_followers": count_followers(uid_f),
                    "number_followees": count_followees(uid_f),
                }
            )

    if start < number_followers:
        for uid_f in follower_ids[start:end]:
            f = User_mgmt.query.filter_by(id=uid_f).first()
            if f is None:
                continue
            followers_list.append(
                {
                    "id": uid_f,
                    "username": f.username,
                    "number_reactions": Reactions.query.filter_by(
                        user_id=uid_f
                    ).count(),
                    "number_followers": count_followers(uid_f),
                    "number_followees": count_followees(uid_f),
                }
            )

    return followers_list, followee_list, number_followers, number_followees


def get_user_recent_interests(user_id, limit=5):
    """
    Get user's most engaged interests from recent activity.

    Args:
        user_id: ID of the user to get interests for
        limit: Maximum number of interests to return (default: 5)

    Returns:
        List of tuples containing (interest_name, interest_id, engagement_count)
    """
    last_round = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round_id = _compute_last_round(last_round)

    interests = (
        db.session.query(
            Interests.interest,
            User_interest.interest_id,
            func.count(User_interest.interest_id).label("count"),
        )
        .join(User_interest, Interests.iid == User_interest.interest_id)
        .filter(
            User_interest.user_id == user_id,
            User_interest.round_id >= last_round_id - 36,
        )
        .group_by(Interests.interest, User_interest.interest_id)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )

    return [
        (interest, interest_id, count) for interest, interest_id, count in interests
    ]
