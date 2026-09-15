"""
Content recommendation system algorithms.

Implements various content recommendation strategies for personalizing
the social media feed including reverse chronological, popularity-based,
follower-based, interest-based, and collaborative filtering approaches.
"""

from sqlalchemy import desc, or_
from sqlalchemy import select as sa_select
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.src.models import (
    Follow,
    Post,
    Post_topics,
    Reactions,
    Rounds,
    User_interest,
    User_mgmt,
)


def _normalize_content_recsys_mode(mode):
    """Normalize UI/backend content-rec sys aliases to canonical mode names."""
    raw = str(mode or "").strip()
    if not raw:
        return "Random"

    compact = raw.replace("_", "").replace("-", "").replace(" ", "").strip().lower()
    mode_aliases = {
        # ── existing ──────────────────────────────────────────────────────
        "reversechrono":                    "ReverseChrono",
        "rc":                               "ReverseChrono",
        "reversechronopopularity":          "ReverseChronoPopularity",
        "rcp":                              "ReverseChronoPopularity",
        "reversechronofollowers":           "ReverseChronoFollowers",
        "rcf":                              "ReverseChronoFollowers",
        "reversechronofollowerspopularity": "ReverseChronoFollowersPopularity",
        "fp":                               "ReverseChronoFollowersPopularity",
        "contentrecsys":                    "Random",
        "default":                          "Random",
        "random":                           "Random",
        # ── Standard (HPC,Standard) ───────────────────────────────────────
        "reversechronocomments":            "ReverseChronoComments",
        "rcc":                              "ReverseChronoComments",
        "commoninterests":                  "CommonInterests",
        "ci":                               "CommonInterests",
        "commonuserinterests":              "CommonUserInterests",
        "cui":                              "CommonUserInterests",
        "similarusersreactions":            "SimilarUsersReactions",
        "sir":                              "SimilarUsersReactions",
        "similarusersposts":                "SimilarUsersPosts",
        "sip":                              "SimilarUsersPosts",
        # ── HPC-only ──────────────────────────────────────────────────────
        "collaborativeuseruser":            "CollaborativeUserUser",
        "cuu":                              "CollaborativeUserUser",
        "collaborativeitemitem":            "CollaborativeItemItem",
        "cii":                              "CollaborativeItemItem",
        "contentbasedfeatures":             "ContentBasedFeatures",
        "cbf":                              "ContentBasedFeatures",
        "contentbasedvector":               "ContentBasedVector",
        "cbv":                              "ContentBasedVector",
        "hybridlinearranker":               "HybridLinearRanker",
        "hlr":                              "HybridLinearRanker",
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


def _root_post_filter():
    return or_(Post.comment_to.is_(None), Post.comment_to == -1)


def _reverse_chrono_fallback(uid, page, per_page):
    """ReverseChrono query used as a secondary fill slot in split-feed modes."""
    q = Post.query.filter(Post.user_id != uid, _root_post_filter())
    return _order_query_by_simulation_time(q)


def get_suggested_posts(uid, mode, page=1, per_page=10, follower_ratio=0.6):
    """
    Get recommended posts for a user based on specified algorithm.

    Supports multiple recommendation strategies including chronological feeds,
    popularity-based ranking, follower-focused content, interest-based filtering,
    collaborative filtering, and random sampling.

    Args:
        uid: User ID to get recommendations for, or "all" for global feed
        mode: Recommendation algorithm name (canonical or alias)
        page: Page number for pagination
        per_page: Number of posts per page
        follower_ratio: Ratio of primary-slot posts for split-feed modes

    Returns:
        Tuple of (posts, additional_posts) where posts is paginated query result
        and additional_posts may contain supplementary content
    """

    mode = _normalize_content_recsys_mode(mode)

    if uid == "all":
        posts_query = db.session.query(Post).filter(_root_post_filter())
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return posts, None

    # ── Existing Standard modes ──────────────────────────────────────────

    if mode == "ReverseChrono":
        posts_query = db.session.query(Post).filter(
            Post.user_id != uid, _root_post_filter()
        )
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=per_page, error_out=False
        )
        additional_posts = None

    elif mode == "ReverseChronoPopularity":
        posts_query = db.session.query(Post).filter(
            Post.user_id != uid, _root_post_filter()
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
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        posts_query = Post.query.filter(
            Post.user_id.in_(follower_ids), _root_post_filter()
        )
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=int(per_page * follower_ratio), error_out=False
        )
        additional_query = Post.query.filter(Post.user_id != uid, _root_post_filter())
        additional_posts = _order_query_by_simulation_time(additional_query).paginate(
            page=page,
            per_page=int(per_page * (1 - follower_ratio)),
            error_out=False,
        )

    elif mode == "ReverseChronoFollowersPopularity":
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        posts_query = db.session.query(Post).filter(
            Post.user_id.in_(follower_ids), _root_post_filter()
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
        additional_query = Post.query.filter(Post.user_id != uid, _root_post_filter())
        additional_posts = _order_query_by_simulation_time(additional_query).paginate(
            page=page,
            per_page=int(per_page * (1 - follower_ratio)),
            error_out=False,
        )

    # ── New Standard (HPC,Standard) modes ───────────────────────────────

    elif mode == "ReverseChronoComments":
        # Posts ordered by comment count desc, then reverse chrono.
        # A "comment" is any post whose comment_to == parent post id.
        comment_counts = (
            db.session.query(
                Post.comment_to.label("post_id"),
                func.count(Post.id).label("n_comments"),
            )
            .filter(Post.comment_to != -1, Post.comment_to.isnot(None))
            .group_by(Post.comment_to)
            .subquery()
        )
        posts_query = (
            db.session.query(Post)
            .outerjoin(comment_counts, Post.id == comment_counts.c.post_id)
            .outerjoin(Rounds, Post.round == Rounds.id)
            .filter(Post.user_id != uid, _root_post_filter())
            .order_by(
                desc(func.coalesce(comment_counts.c.n_comments, 0)),
                desc(func.coalesce(Rounds.day, -1)),
                desc(func.coalesce(Rounds.hour, -1)),
                desc(Post.id),
            )
        )
        posts = posts_query.paginate(page=page, per_page=per_page, error_out=False)
        additional_posts = None

    elif mode == "CommonInterests":
        # Posts tagged with topics the user is interested in.
        interest_ids = db.session.scalars(
            sa_select(User_interest.interest_id).filter_by(user_id=uid)
        ).all()

        if interest_ids:
            matching_post_ids = db.session.scalars(
                sa_select(Post_topics.post_id)
                .where(Post_topics.topic_id.in_(interest_ids))
                .distinct()
            ).all()
            posts_query = Post.query.filter(
                Post.id.in_(matching_post_ids),
                Post.user_id != uid,
                _root_post_filter(),
            )
            posts = _order_query_by_simulation_time(posts_query).paginate(
                page=page, per_page=per_page, error_out=False
            )
        else:
            posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page, per_page=per_page, error_out=False
            )
        additional_posts = None

    elif mode == "CommonUserInterests":
        # Posts from users who share at least one interest with the target user.
        # Primary slot: posts from interest-similar users; secondary: global RC.
        interest_ids = db.session.scalars(
            sa_select(User_interest.interest_id).filter_by(user_id=uid)
        ).all()

        if interest_ids:
            similar_user_ids = db.session.scalars(
                sa_select(User_interest.user_id)
                .where(
                    User_interest.interest_id.in_(interest_ids),
                    User_interest.user_id != uid,
                )
                .distinct()
            ).all()
            posts_query = Post.query.filter(
                Post.user_id.in_(similar_user_ids), _root_post_filter()
            )
            posts = _order_query_by_simulation_time(posts_query).paginate(
                page=page, per_page=int(per_page * follower_ratio), error_out=False
            )
            additional_posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page,
                per_page=int(per_page * (1 - follower_ratio)),
                error_out=False,
            )
        else:
            posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page, per_page=per_page, error_out=False
            )
            additional_posts = None

    elif mode == "SimilarUsersReactions":
        # Posts liked by users who share the same political leaning.
        # Primary slot: liked posts from leaning-matched users; secondary: global RC.
        target = db.session.get(User_mgmt, uid)
        target_leaning = target.leaning if target else None

        similar_user_ids = db.session.scalars(
            sa_select(User_mgmt.id).where(
                User_mgmt.leaning == target_leaning, User_mgmt.id != uid
            )
        ).all()

        if similar_user_ids:
            liked_post_ids = db.session.scalars(
                sa_select(Reactions.post_id)
                .where(Reactions.user_id.in_(similar_user_ids))
                .distinct()
            ).all()
            posts_query = Post.query.filter(
                Post.id.in_(liked_post_ids),
                Post.user_id != uid,
                _root_post_filter(),
            )
            posts = _order_query_by_simulation_time(posts_query).paginate(
                page=page, per_page=int(per_page * follower_ratio), error_out=False
            )
            additional_posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page,
                per_page=int(per_page * (1 - follower_ratio)),
                error_out=False,
            )
        else:
            posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page, per_page=per_page, error_out=False
            )
            additional_posts = None

    elif mode == "SimilarUsersPosts":
        # Posts authored by users who share the same political leaning (demographic proxy).
        # Primary slot: posts from leaning-matched users; secondary: global RC.
        target = db.session.get(User_mgmt, uid)
        target_leaning = target.leaning if target else None

        similar_user_ids = db.session.scalars(
            sa_select(User_mgmt.id).where(
                User_mgmt.leaning == target_leaning, User_mgmt.id != uid
            )
        ).all()

        posts_query = Post.query.filter(
            Post.user_id.in_(similar_user_ids), _root_post_filter()
        )
        posts = _order_query_by_simulation_time(posts_query).paginate(
            page=page, per_page=int(per_page * follower_ratio), error_out=False
        )
        additional_posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
            page=page,
            per_page=int(per_page * (1 - follower_ratio)),
            error_out=False,
        )

    # ── HPC-only modes (YWeb implementation — admin-gated to HPC experiments) ─

    elif mode == "CollaborativeUserUser":
        # Find users who liked the same posts as the target user, then recommend
        # other posts those users liked (that the target hasn't seen).
        user_liked_ids = db.session.scalars(
            sa_select(Reactions.post_id).filter_by(user_id=uid).distinct()
        ).all()

        if user_liked_ids:
            similar_user_ids = db.session.scalars(
                sa_select(Reactions.user_id)
                .where(
                    Reactions.post_id.in_(user_liked_ids),
                    Reactions.user_id != uid,
                )
                .distinct()
            ).all()
            candidates = db.session.scalars(
                sa_select(Reactions.post_id)
                .where(
                    Reactions.user_id.in_(similar_user_ids),
                    Reactions.post_id.notin_(user_liked_ids),
                )
                .distinct()
            ).all()
            posts_query = Post.query.filter(
                Post.id.in_(candidates),
                Post.user_id != uid,
                _root_post_filter(),
            )
            posts = _order_query_by_simulation_time(posts_query).paginate(
                page=page, per_page=per_page, error_out=False
            )
        else:
            posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page, per_page=per_page, error_out=False
            )
        additional_posts = None

    elif mode == "CollaborativeItemItem":
        # Posts co-liked with posts the user already liked (item-item CF via
        # shared engagement: other items that co-likers also engaged with).
        user_liked_ids = db.session.scalars(
            sa_select(Reactions.post_id).filter_by(user_id=uid).distinct()
        ).all()

        if user_liked_ids:
            co_likers = db.session.scalars(
                sa_select(Reactions.user_id)
                .where(
                    Reactions.post_id.in_(user_liked_ids),
                    Reactions.user_id != uid,
                )
                .distinct()
            ).all()
            similar_items = db.session.scalars(
                sa_select(Reactions.post_id)
                .where(
                    Reactions.user_id.in_(co_likers),
                    Reactions.post_id.notin_(user_liked_ids),
                )
                .distinct()
            ).all()
            posts_query = Post.query.filter(
                Post.id.in_(similar_items),
                Post.user_id != uid,
                _root_post_filter(),
            )
            posts = _order_query_by_simulation_time(posts_query).paginate(
                page=page, per_page=per_page, error_out=False
            )
        else:
            posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page, per_page=per_page, error_out=False
            )
        additional_posts = None

    elif mode == "ContentBasedFeatures":
        # Posts tagged with topics matching the user's declared interests,
        # secondarily ranked by reaction count (popularity within the topic set).
        # Differentiates from CommonInterests by the secondary popularity sort.
        interest_ids = db.session.scalars(
            sa_select(User_interest.interest_id).filter_by(user_id=uid)
        ).all()

        if interest_ids:
            matching_post_ids = db.session.scalars(
                sa_select(Post_topics.post_id)
                .where(Post_topics.topic_id.in_(interest_ids))
                .distinct()
            ).all()
            posts_query = (
                Post.query.filter(
                    Post.id.in_(matching_post_ids),
                    Post.user_id != uid,
                    _root_post_filter(),
                )
                .outerjoin(Rounds, Post.round == Rounds.id)
                .order_by(
                    desc(func.coalesce(Rounds.day, -1)),
                    desc(func.coalesce(Rounds.hour, -1)),
                    desc(Post.reaction_count),
                    desc(Post.id),
                )
            )
            posts = posts_query.paginate(page=page, per_page=per_page, error_out=False)
        else:
            posts = _reverse_chrono_fallback(uid, page, per_page).paginate(
                page=page, per_page=per_page, error_out=False
            )
        additional_posts = None

    else:
        # Random / unrecognised mode — ContentRecSys default
        posts = (
            Post.query.filter(Post.user_id != uid, _root_post_filter())
            .order_by(func.random())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    return posts, additional_posts
