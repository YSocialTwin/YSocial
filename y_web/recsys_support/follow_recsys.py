"""
Follower recommendation system algorithms.

Implements user and page recommendation strategies for suggesting new accounts
to follow based on network structure, shared interests, and user preferences.
"""

import numpy as np
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.models import (
    Admin_users,
    Agent,
    Follow,
    Page,
    User_mgmt,
)


def get_suggested_users(user_id, pages=False):
    """
    Get follow recommendations for a user.

    Suggests accounts to follow based on the user's recommendation system
    preference, optionally filtering for pages or regular users.

    Args:
        user_id: ID of user to get recommendations for, or "all" for none
        pages: If True, return only page accounts; if False, only regular users

    Returns:
        List of dictionaries with keys: 'username', 'id', 'profile_pic'
    """

    if user_id == "all":
        return []

    user = User_mgmt.query.filter_by(id=int(user_id)).first()

    users = __follow_suggestions(user.frecsys_type, user.id, 5, 1.5)
    if len(users) == 0:
        users = __follow_suggestions("", user.id, 5, 1.5)

    if not pages:
        res = [
            {"username": user.username, "id": user.id, "profile_pic": ""}
            for user in users
            if user.is_page != 1 and int(user_id) != user.id
        ]
    else:
        res = [
            {"username": user.username, "id": user.id, "profile_pic": ""}
            for user in users
            if user.is_page == 1 and int(user_id) != user.id
        ]
        if len(res) == 0:
            # get random Users with is_page = 1 that user_id is not following
            pages = (
                User_mgmt.query.filter_by(is_page=1).order_by(func.random()).limit(5)
            )

            for page in pages:
                # check if user_id is following the page
                if (
                    Follow.query.filter_by(user_id=user_id, follower_id=page.id).first()
                    is None
                ):
                    res.append(
                        {"username": page.username, "id": page.id, "profile_pic": ""}
                    )

    for user in res:
        if User_mgmt.query.filter_by(id=user["id"]).first().is_page == 1:
            pg = Page.query.filter_by(name=user["username"]).first()
            if pg is not None:
                user["profile_pic"] = pg.logo
        else:
            try:
                ag = Agent.query.filter_by(name=user["username"]).first()
                user["profile_pic"] = (
                    ag.profile_pic
                    if ag is not None and ag.profile_pic is not None
                    else Admin_users.query.filter_by(username=user["username"])
                    .first()
                    .profile_pic
                )
            except:
                user["profile_pic"] = ""

    return res


def __follow_suggestions(rectype, user_id, n_neighbors, leaning_biased):
    """Get follow suggestions for a user based on the follow recommender system.

    Args:
        rectype:
        user_id:
        n_neighbors:
        leaning_biased:

    Returns:
    """

    res = {}
    if rectype == "PreferentialAttachment":
        # get random nodes ordered by degree
        followers = (
            (
                db.session.query(
                    Follow, func.count(Follow.user_id).label("total")
                ).filter(Follow.action == "follow")
            )
            .group_by(Follow.follower_id)
            .order_by(func.count(Follow.user_id).desc())
        ).limit(n_neighbors)

        for follower in followers:
            res[follower[0].follower_id] = int(follower[1])

        # normalize pa to probabilities
        total_degree = sum(res.values())
        res = {k: v / total_degree for k, v in res.items()}

    if rectype == "CommonNeighbors":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        for target, neighbors in candidates.items():
            res[target] = len(neighbors & first_order_followers)

        total = sum(res.values())
        # normalize cn to probabilities
        res = {k: v / total for k, v in res.items() if v > 0}

    if rectype == "Jaccard":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        for candidate in candidates:
            res[candidate] = len(first_order_followers & candidates[candidate]) / len(
                first_order_followers | candidates[candidate]
            )

        total = sum(res.values())
        res = {k: v / total for k, v in res.items() if v > 0}

    elif rectype == "AdamicAdar":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        res = {}
        for target, neighbors in candidates.items():
            res[target] = neighbors & first_order_followers

        for target in res:
            res[target] = sum(
                [
                    1 / np.log(len(Follow.query.filter_by(user_id=neighbor).all()))
                    for neighbor in res[target]
                ]
            )

        total = sum([v for v in res.values() if v != np.inf])
        res = {k: v / total for k, v in res.items() if v > 0 and v != np.inf}

    else:
        # get random users
        users = User_mgmt.query.order_by(func.random()).limit(n_neighbors)

        for user in users:
            res[user.id] = 1 / n_neighbors

    l_source = User_mgmt.query.filter_by(id=user_id).first().leaning
    leanings = __get_users_leanings(res.keys())
    for user in res:
        if leanings[user] == l_source:
            res[user] = res[user] * leaning_biased

    res = [k for k, v in res.items() if v > 0]
    users = [User_mgmt.query.filter_by(id=user).first() for user in res]
    if len(users) > n_neighbors:
        users = users[:n_neighbors]
    return users


def __get_two_hops_neighbors(node_id):
    """Get the two hops neighbors of a user.

    Args:
        node_id: the user id

    Returns:
        the two hops neighbors"""
    # (node_id, direct_neighbors)
    first_order_followers = set(
        [
            f.follower_id
            for f in Follow.query.filter_by(user_id=node_id, action="follow")
        ]
    )
    # (direct_neighbors, second_order_followers)
    second_order_followers = Follow.query.filter(
        Follow.user_id.in_(first_order_followers), Follow.action == "follow"
    )
    # (second_order_followers, third_order_followers)
    third_order_followers = Follow.query.filter(
        Follow.user_id.in_([f.follower_id for f in second_order_followers]),
        Follow.action == "follow",
    )

    candidate_to_follower = {}
    for node in third_order_followers:
        if node.user_id not in candidate_to_follower:
            candidate_to_follower[node.user_id] = set()
        candidate_to_follower[node.user_id].add(node.follower_id)

    return first_order_followers, candidate_to_follower


def __get_users_leanings(agents):
    """Get the political leaning of a list of users.

    Args:
        agents: the list of users

    Returns:
        the political leaning of the users"""
    leanings = {}
    for agent in agents:
        leanings[agent] = User_mgmt.query.filter_by(id=agent).first().leaning
    return leanings
