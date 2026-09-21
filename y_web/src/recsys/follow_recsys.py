"""
Follower recommendation system algorithms.

Implements user and page recommendation strategies for suggesting new accounts
to follow based on network structure, shared interests, and user preferences.
"""

import math
import random as _random

import numpy as np
from sqlalchemy import select
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.src.models import (
    Admin_users,
    Agent,
    Follow,
    Page,
    Post,
    Post_topics,
    Reactions,
    User_interest,
    User_mgmt,
)


def get_suggested_users(username, pages=False):
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

    if username == "all":
        return []

    user = db.session.scalars(select(User_mgmt).filter_by(username=username)).first()
    user_id = user.id

    users = __follow_suggestions(user.frecsys_type, user.id, 5, 1.5)
    if len(users) == 0:
        users = __follow_suggestions("", user.id, 5, 1.5)

    if not pages:
        res = [
            {"username": user.username, "id": user.id, "profile_pic": ""}
            for user in users
            if user.is_page != 1 and user_id != user.id
        ]
    else:
        res = [
            {"username": user.username, "id": user.id, "profile_pic": ""}
            for user in users
            if user.is_page == 1 and user_id != user.id
        ]
        if len(res) == 0:
            # get random Users with is_page = 1 that user_id is not following
            pages = (
                User_mgmt.query.filter_by(is_page=1).order_by(func.random()).limit(5)
            )

            for page in pages:
                # check if user_id is following the page
                if (
                    db.session.scalars(
                        select(Follow).filter_by(user_id=user_id, follower_id=page.id)
                    ).first()
                    is None
                ):
                    res.append(
                        {"username": page.username, "id": page.id, "profile_pic": ""}
                    )

    for user in res:
        if (
            db.session.scalars(select(User_mgmt).filter_by(id=user["id"]))
            .first()
            .is_page
            == 1
        ):
            pg = db.session.scalars(
                select(Page).filter_by(name=user["username"])
            ).first()
            if pg is not None:
                user["profile_pic"] = pg.logo
        else:
            try:
                ag = db.session.scalars(
                    select(Agent).filter_by(name=user["username"])
                ).first()
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


# ---------------------------------------------------------------------------
# Big Five cosine-similarity helpers (used by CosineSimilarity mode)
# ---------------------------------------------------------------------------


def _big5_vec(u):
    """Return a 5-dim float vector from User_mgmt Big Five columns."""
    try:
        return [float(v or 0) for v in (u.oe, u.co, u.ex, u.ag, u.ne)]
    except (TypeError, ValueError):
        return [0.0] * 5


def _cosine(a, b):
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ---------------------------------------------------------------------------
# Core recommendation dispatcher
# ---------------------------------------------------------------------------


def __follow_suggestions(rectype, user_id, n_neighbors, leaning_biased):
    """Get follow suggestions for a user based on the follow recommender system.

    Args:
        rectype:        Algorithm name string
        user_id:        Requesting user's ID
        n_neighbors:    How many candidates to return
        leaning_biased: Multiplier applied to same-leaning candidates

    Returns:
        List of User_mgmt ORM objects
    """

    res = {}

    # -----------------------------------------------------------------------
    # Existing Standard modes
    # -----------------------------------------------------------------------

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
            res[follower[0].follower_id] = follower[1]

        # normalize pa to probabilities
        total_degree = sum(res.values())
        if total_degree:
            res = {k: v / total_degree for k, v in res.items()}

    if rectype == "CommonNeighbors":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        for target, neighbors in candidates.items():
            res[target] = len(neighbors & first_order_followers)

        total = sum(res.values())
        # normalize cn to probabilities
        res = {k: v / total for k, v in res.items() if v > 0} if total else {}

    if rectype == "Jaccard":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        for candidate in candidates:
            union = first_order_followers | candidates[candidate]
            if union:
                res[candidate] = len(
                    first_order_followers & candidates[candidate]
                ) / len(union)

        total = sum(res.values())
        res = {k: v / total for k, v in res.items() if v > 0} if total else {}

    if rectype == "AdamicAdar":
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        scores = {}
        for target, neighbors in candidates.items():
            scores[target] = neighbors & first_order_followers

        for target in scores:
            s = 0.0
            for neighbor in scores[target]:
                deg = len(
                    db.session.scalars(select(Follow).filter_by(user_id=neighbor)).all()
                )
                if deg > 1:
                    s += 1 / np.log(deg)
            res[target] = s

        total = sum(v for v in res.values() if v != np.inf)
        res = (
            {k: v / total for k, v in res.items() if v > 0 and v != np.inf}
            if total
            else {}
        )

    # -----------------------------------------------------------------------
    # HPC-only modes
    # -----------------------------------------------------------------------

    if rectype == "Activity":
        # Recommend high-activity users (by post count) not yet followed
        already_followed = set(
            f.follower_id
            for f in db.session.scalars(
                select(Follow).filter_by(user_id=user_id, action="follow")
            ).all()
        )
        rows = (
            db.session.query(Post.user_id, func.count(Post.id).label("cnt"))
            .group_by(Post.user_id)
            .order_by(func.count(Post.id).desc())
            .limit(n_neighbors * 4)
            .all()
        )
        rank = 1
        for uid, cnt in rows:
            if uid != user_id and uid not in already_followed:
                res[uid] = cnt / rank
                rank += 1
                if len(res) >= n_neighbors * 2:
                    break
        total = sum(res.values())
        if total:
            res = {k: v / total for k, v in res.items()}

    if rectype == "CoEngagement":
        # Recommend users who reacted to the same posts as the target user
        my_post_ids = set(
            r.post_id
            for r in db.session.scalars(
                select(Reactions).filter_by(user_id=user_id)
            ).all()
        )
        if my_post_ids:
            co_reactors = db.session.scalars(
                select(Reactions).filter(
                    Reactions.post_id.in_(my_post_ids),
                    Reactions.user_id != user_id,
                )
            ).all()
            already_followed = set(
                f.follower_id
                for f in db.session.scalars(
                    select(Follow).filter_by(user_id=user_id, action="follow")
                ).all()
            )
            for r in co_reactors:
                if r.user_id not in already_followed:
                    res[r.user_id] = res.get(r.user_id, 0) + 1
            total = sum(res.values())
            if total:
                res = {k: v / total for k, v in res.items()}

    if rectype == "CosineSimilarity":
        # Recommend users with similar Big Five personality profiles
        me = db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first()
        if me is not None:
            my_vec = _big5_vec(me)
            already_followed = set(
                f.follower_id
                for f in db.session.scalars(
                    select(Follow).filter_by(user_id=user_id, action="follow")
                ).all()
            )
            all_users = db.session.scalars(select(User_mgmt)).all()
            for u in all_users:
                if u.id == user_id or u.id in already_followed:
                    continue
                sim = _cosine(my_vec, _big5_vec(u))
                if sim > 0:
                    res[u.id] = sim
            total = sum(res.values())
            if total:
                res = {k: v / total for k, v in res.items()}

    if rectype == "RandomWalkRestart":
        # Personalized PageRank / random walk with restart on the follow graph
        alpha = 0.15  # restart probability
        steps = 200  # number of walk steps

        # Build adjacency: adj[uid] = list of follower_ids they follow
        all_follows = db.session.scalars(
            select(Follow).filter_by(action="follow")
        ).all()
        adj = {}
        for f in all_follows:
            adj.setdefault(f.user_id, []).append(f.follower_id)

        already_followed = set(
            f.follower_id
            for f in db.session.scalars(
                select(Follow).filter_by(user_id=user_id, action="follow")
            ).all()
        )

        current = user_id
        visit_count = {}
        for _ in range(steps):
            if _random.random() < alpha or current not in adj or not adj[current]:
                current = user_id
            else:
                current = _random.choice(adj[current])
            if current != user_id:
                visit_count[current] = visit_count.get(current, 0) + 1

        for uid, cnt in visit_count.items():
            if uid not in already_followed:
                res[uid] = cnt

        total = sum(res.values())
        if total:
            res = {k: v / total for k, v in res.items()}

    if rectype == "ReactionsOnContent":
        # Recommend users who reacted to posts tagged with the target user's interests
        my_interest_ids = set(
            ui.interest_id
            for ui in db.session.scalars(
                select(User_interest).filter_by(user_id=user_id)
            ).all()
        )
        if my_interest_ids:
            # posts with those topics
            topic_post_ids = set(
                pt.post_id
                for pt in db.session.scalars(
                    select(Post_topics).filter(
                        Post_topics.topic_id.in_(my_interest_ids)
                    )
                ).all()
            )
            already_followed = set(
                f.follower_id
                for f in db.session.scalars(
                    select(Follow).filter_by(user_id=user_id, action="follow")
                ).all()
            )
            if topic_post_ids:
                reactors = db.session.scalars(
                    select(Reactions).filter(
                        Reactions.post_id.in_(topic_post_ids),
                        Reactions.user_id != user_id,
                    )
                ).all()
                for r in reactors:
                    if r.user_id not in already_followed:
                        res[r.user_id] = res.get(r.user_id, 0) + 1
                total = sum(res.values())
                if total:
                    res = {k: v / total for k, v in res.items()}

    if rectype == "ResourceAllocation":
        # Resource Allocation index: 1/degree instead of 1/log(degree)
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)

        scores = {}
        for target, neighbors in candidates.items():
            scores[target] = neighbors & first_order_followers

        for target in scores:
            s = 0.0
            for neighbor in scores[target]:
                deg = len(
                    db.session.scalars(select(Follow).filter_by(user_id=neighbor)).all()
                )
                if deg > 0:
                    s += 1.0 / deg
            res[target] = s

        total = sum(res.values())
        if total:
            res = {k: v / total for k, v in res.items() if v > 0}

    if rectype == "TwoHopEgoSampling":
        # Uniformly sample from the 2-hop ego network excluding already-followed
        first_order_followers, candidates = __get_two_hops_neighbors(user_id)
        already_followed = first_order_followers | {user_id}
        pool = [uid for uid in candidates if uid not in already_followed]
        if pool:
            sampled = _random.sample(pool, min(n_neighbors * 2, len(pool)))
            for uid in sampled:
                res[uid] = 1.0 / len(sampled)

    # -----------------------------------------------------------------------
    # Random fallback (no mode matched or result is empty)
    # -----------------------------------------------------------------------

    if not res:
        users = User_mgmt.query.order_by(func.random()).limit(n_neighbors)
        for user in users:
            res[user.id] = 1 / n_neighbors

    # -----------------------------------------------------------------------
    # Apply leaning bias and resolve to User_mgmt objects
    # -----------------------------------------------------------------------

    l_source = (
        db.session.scalars(select(User_mgmt).filter_by(id=user_id)).first().leaning
    )
    leanings = __get_users_leanings(res.keys())
    for user in res:
        if leanings[user] == l_source:
            res[user] = res[user] * leaning_biased

    res = [k for k, v in res.items() if v > 0]
    users = [
        db.session.scalars(select(User_mgmt).filter_by(id=user)).first() for user in res
    ]
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
        leanings[agent] = (
            db.session.scalars(select(User_mgmt).filter_by(id=agent)).first().leaning
        )
    return leanings
