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


def get_mutual_friends(user_a, user_b, limit=10):
    """Get the mutual friends between two users.

    Args:
        user_a: ID of the first user
        user_b: ID of the second user
        limit: Maximum number of results (default: 10)

    Returns:
        List of dicts with keys ``id``, ``username``, ``profile_pic``
    """
    friends_a = Follow.query.filter_by(user_id=user_a, action="follow").distinct()
    friends_b = Follow.query.filter_by(user_id=user_b, action="follow").distinct()

    mutual_friends = []
    for f_a in friends_a:
        for f_b in friends_b:
            if f_a.follower_id == f_b.follower_id:
                mutual_friends.append(f_a.follower_id)

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

    number_followees = (
        db.session.query(Follow.follower_id)
        .filter(Follow.user_id == user_id, Follow.follower_id != user_id)
        .group_by(Follow.follower_id)
        .having(func.count(Follow.follower_id) % 2 == 1)
        .count()
    )

    number_followers = (
        db.session.query(Follow.user_id)
        .filter(Follow.follower_id == user_id, Follow.user_id != user_id)
        .group_by(Follow.user_id)
        .having(func.count(Follow.user_id) % 2 == 1)
        .count()
    )

    followee_list = []
    followers_list = []

    if (number_followers - page * limit < -limit) and (
        number_followees - page * limit < -limit
    ):
        return get_user_friends(user_id, limit=limit, page=page - 1)

    if page * limit <= number_followees + limit:
        followee_query = (
            db.session.query(Follow.follower_id, User_mgmt.username, User_mgmt.id)
            .filter(Follow.user_id == user_id, Follow.follower_id != user_id)
            .join(User_mgmt, Follow.follower_id == User_mgmt.id)
            .group_by(Follow.follower_id, User_mgmt.username, User_mgmt.id)
            .having(func.count(Follow.follower_id) % 2 == 1)
            .paginate(page=page, per_page=limit, error_out=False)
        )

        for f in followee_query.items:
            uid_f = f.id
            followee_list.append(
                {
                    "id": uid_f,
                    "username": f.username,
                    "number_reactions": Reactions.query.filter_by(
                        user_id=uid_f
                    ).count(),
                    "number_followers": (
                        db.session.query(Follow.user_id)
                        .filter(Follow.follower_id == uid_f, Follow.user_id != uid_f)
                        .group_by(Follow.user_id)
                        .having(func.count(Follow.user_id) % 2 == 1)
                        .count()
                    ),
                    "number_followees": (
                        db.session.query(Follow.follower_id)
                        .filter(Follow.user_id == uid_f, Follow.follower_id != uid_f)
                        .group_by(Follow.follower_id)
                        .having(func.count(Follow.follower_id) % 2 == 1)
                        .count()
                    ),
                }
            )

    if page * limit <= number_followers + limit:
        followers_query = (
            db.session.query(Follow.user_id, User_mgmt.username, User_mgmt.id)
            .filter(Follow.follower_id == user_id, Follow.user_id != user_id)
            .join(User_mgmt, Follow.user_id == User_mgmt.id)
            .group_by(Follow.user_id, User_mgmt.username, User_mgmt.id)
            .having(func.count(Follow.user_id) % 2 == 1)
            .paginate(page=page, per_page=limit, error_out=False)
        )

        for f in followers_query.items:
            uid_f = f.id
            followers_list.append(
                {
                    "id": uid_f,
                    "username": f.username,
                    "number_reactions": Reactions.query.filter_by(
                        user_id=uid_f
                    ).count(),
                    "number_followers": (
                        db.session.query(Follow.user_id)
                        .filter(Follow.follower_id == uid_f, Follow.user_id != uid_f)
                        .group_by(Follow.user_id)
                        .having(func.count(Follow.user_id) % 2 == 1)
                        .count()
                    ),
                    "number_followees": (
                        db.session.query(Follow.follower_id)
                        .filter(Follow.user_id == uid_f, Follow.follower_id != uid_f)
                        .group_by(Follow.follower_id)
                        .having(func.count(Follow.follower_id) % 2 == 1)
                        .count()
                    ),
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
