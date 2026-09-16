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
        # ── Human-only ───────────────────────────────────────────────────────
        "filterbubble":     "FilterBubble",
        "fb":               "FilterBubble",
        "personalizedfeed": "FilterBubble",
        "pf":               "FilterBubble",
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



def _make_pagination(items, page, per_page, total):
    """Lightweight pagination wrapper compatible with Flask-SQLAlchemy Pagination."""
    class _Page:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = max(1, -(-total // per_page))
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1 if self.has_prev else None
            self.next_num = page + 1 if self.has_next else None

        def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
            last = 0
            for num in range(1, self.pages + 1):
                if (num <= left_edge or
                        self.page - left_current <= num <= self.page + right_current or
                        num > self.pages - right_edge):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num
    return _Page(items, page, per_page, total)


def _filter_bubble_score(uid, exp_engine, settings):
    """
    Return {post_id: score} for FilterBubble (Personalized Feed) mode.

    Reads user interests + opinions from the experiment SQLite DB and scores
    every non-owned root post. Returns {} when no onboarding data is found,
    triggering a silent reverse-chrono fallback in get_suggested_posts.

    settings keys: filter_bubble_alpha, filter_bubble_beta, filter_bubble_gamma,
                   filter_bubble_wr, filter_bubble_wc, filter_bubble_ws
    """
    import math
    from sqlalchemy import text as _text

    uid_str = str(uid)
    alpha = float(settings.get("filter_bubble_alpha", 2.0))
    beta  = float(settings.get("filter_bubble_beta",  0.0))
    gamma = float(settings.get("filter_bubble_gamma", 0.0))
    wr    = float(settings.get("filter_bubble_wr", 1.0))
    wc    = float(settings.get("filter_bubble_wc", 1.5))
    ws    = float(settings.get("filter_bubble_ws", 2.0))

    try:
        with exp_engine.connect() as conn:
            # 1. User interests
            interests = {
                str(r[0]): float(r[1])
                for r in conn.execute(
                    _text("SELECT topic_id, interest_level FROM user_topic_interest "
                          "WHERE user_id = :uid"),
                    {"uid": uid_str},
                ).fetchall()
            }
            if not interests:
                return {}

            # 2. User opinions at onboarding (tid = 0)
            user_opinions = {}
            for sentinel in ("'0'", "0"):
                try:
                    rows = conn.execute(
                        _text("SELECT topic_id, opinion FROM agent_opinion "
                              "WHERE agent_id = :aid AND tid = " + sentinel),
                        {"aid": uid_str},
                    ).fetchall()
                    if rows:
                        user_opinions = {str(r[0]): float(r[1]) for r in rows}
                        break
                except Exception:
                    pass

            # 3. Post topics for non-owned root posts
            pt_rows = conn.execute(
                _text("SELECT pt.post_id, pt.topic_id "
                      "FROM post_topics pt "
                      "JOIN post p ON p.id = pt.post_id "
                      "WHERE p.user_id != :uid "
                      "  AND (p.comment_to IS NULL OR p.comment_to = -1)"),
                {"uid": uid_str},
            ).fetchall()
            post_topics_map = {}
            for pid, tid in pt_rows:
                post_topics_map.setdefault(str(pid), []).append(str(tid))
            if not post_topics_map:
                return {}

            # 4. Author opinions at post-write time (priority 1)
            all_pids_str = ",".join(post_topics_map.keys())
            author_opinions_at_post = {}
            try:
                ao_rows = conn.execute(
                    _text("SELECT agent_id, id_post, topic_id, opinion "
                          "FROM agent_opinion "
                          "WHERE id_post IN (" + all_pids_str + ")"),
                ).fetchall()
                for agent_id, id_post, topic_id, opinion in ao_rows:
                    author_opinions_at_post[
                        (str(agent_id), str(id_post), str(topic_id))
                    ] = float(opinion)
            except Exception:
                pass

            # 5. Author latest opinions as fallback (priority 2)
            author_latest_opinions = {}
            try:
                al_rows = conn.execute(
                    _text("SELECT agent_id, topic_id, opinion "
                          "FROM agent_opinion "
                          "WHERE (agent_id, topic_id, id) IN ("
                          "  SELECT agent_id, topic_id, MAX(id) "
                          "  FROM agent_opinion GROUP BY agent_id, topic_id"
                          ")")
                ).fetchall()
                for agent_id, topic_id, opinion in al_rows:
                    author_latest_opinions[(str(agent_id), str(topic_id))] = float(opinion)
            except Exception:
                pass

            # 6. VADER sentiment — last-resort opinion proxy (priority 3)
            post_sentiments = {}
            try:
                sent_rows = conn.execute(
                    _text("SELECT post_id, topic_id, compound FROM post_sentiment "
                          "WHERE is_post = 1")
                ).fetchall()
                for pid, tid, compound in sent_rows:
                    post_sentiments[(str(pid), str(tid))] = (float(compound) + 1.0) / 2.0
            except Exception:
                pass

            # 7. Post metadata: author, round, base engagement
            meta_rows = conn.execute(
                _text("SELECT p.id, p.user_id, p.reaction_count, r.day, r.hour "
                      "FROM post p LEFT JOIN rounds r ON r.id = p.round "
                      "WHERE p.user_id != :uid "
                      "  AND (p.comment_to IS NULL OR p.comment_to = -1)"),
                {"uid": uid_str},
            ).fetchall()
            post_meta = {}
            max_round_val = 1
            for pid, author_id, reaction_count, day, hour in meta_rows:
                rv = (day or 0) * 24 + (hour or 0)
                if rv > max_round_val:
                    max_round_val = rv
                post_meta[str(pid)] = {
                    "author_id": str(author_id),
                    "reaction_count": int(reaction_count or 0),
                    "round_val": rv,
                }

            comment_counts = {}
            share_counts = {}
            if gamma > 0:
                try:
                    cc_rows = conn.execute(
                        _text("SELECT comment_to, COUNT(*) FROM post "
                              "WHERE comment_to IS NOT NULL AND comment_to != -1 "
                              "GROUP BY comment_to")
                    ).fetchall()
                    comment_counts = {str(r[0]): int(r[1]) for r in cc_rows}
                    sc_rows = conn.execute(
                        _text("SELECT shared_from, COUNT(*) FROM post "
                              "WHERE shared_from IS NOT NULL AND shared_from != -1 "
                              "GROUP BY shared_from")
                    ).fetchall()
                    share_counts = {str(r[0]): int(r[1]) for r in sc_rows}
                except Exception:
                    pass

    except Exception:
        return {}

    # 8. Compute scores
    scores = {}
    current_round_val = max_round_val

    for post_id_str, topic_ids in post_topics_map.items():
        meta = post_meta.get(post_id_str, {})
        author_id = meta.get("author_id", "")
        thematic = 0.0

        for topic_id in topic_ids:
            w_int = interests.get(topic_id, 0.0)
            if w_int == 0.0:
                continue
            u_op = user_opinions.get(topic_id)
            p_op = (
                author_opinions_at_post.get((author_id, post_id_str, topic_id))
                or author_latest_opinions.get((author_id, topic_id))
                or post_sentiments.get((post_id_str, topic_id))
            )
            if u_op is not None and p_op is not None:
                w_op = math.exp(-alpha * (u_op - p_op) ** 2)
            elif u_op is None:
                w_op = 1.0
            else:
                w_op = 0.5
            thematic += w_int * w_op

        if thematic == 0.0:
            continue

        age = max(0, current_round_val - meta.get("round_val", current_round_val))
        recency = math.exp(-beta * age) if beta > 0 else 1.0

        if gamma > 0:
            eng = (
                wr * meta.get("reaction_count", 0)
                + wc * comment_counts.get(post_id_str, 0)
                + ws * share_counts.get(post_id_str, 0)
            )
            engagement = 1.0 + gamma * math.log1p(eng)
        else:
            engagement = 1.0

        scores[int(post_id_str)] = thematic * recency * engagement

    return scores


def _update_filter_bubble_interests(user_id, post_id, interaction_type, exp_engine, lr=0.05):
    """
    Update user_topic_interest in the experiment DB after a user interaction.

    EMA update: interest_new = (1-lr)*interest_old + lr*delta
    Silently returns on any error so the original interaction is never blocked.
    """
    from sqlalchemy import text as _text

    DELTA = {"like": 1.0, "heart": 1.0, "share": 1.0,
             "comment": 0.8, "dislike": 0.0, "angry": 0.0}
    delta = DELTA.get(str(interaction_type).lower(), 0.5)
    uid_str = str(user_id)

    try:
        with exp_engine.connect() as conn:
            topic_rows = conn.execute(
                _text("SELECT topic_id FROM post_topics WHERE post_id = :pid"),
                {"pid": post_id},
            ).fetchall()
            if not topic_rows:
                return
            for (topic_id,) in topic_rows:
                tid_str = str(topic_id)
                existing = conn.execute(
                    _text("SELECT interest_level FROM user_topic_interest "
                          "WHERE user_id = :uid AND topic_id = :tid"),
                    {"uid": uid_str, "tid": tid_str},
                ).fetchone()
                if existing:
                    new_level = round(
                        max(0.0, min(1.0, (1.0 - lr) * float(existing[0]) + lr * delta)), 4
                    )
                    conn.execute(
                        _text("UPDATE user_topic_interest "
                              "SET interest_level = :lvl "
                              "WHERE user_id = :uid AND topic_id = :tid"),
                        {"lvl": new_level, "uid": uid_str, "tid": tid_str},
                    )
                else:
                    conn.execute(
                        _text("INSERT INTO user_topic_interest "
                              "(user_id, topic_id, interest_level) "
                              "VALUES (:uid, :tid, :lvl)"),
                        {"uid": uid_str, "tid": tid_str,
                         "lvl": round(lr * delta, 4)},
                    )
            conn.commit()
    except Exception:
        pass


def get_suggested_posts(uid, mode, page=1, per_page=10, follower_ratio=0.6,
                        exp_engine=None, fb_settings=None):
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

    elif mode == "FilterBubble":
        bubble_scores = (
            _filter_bubble_score(uid, exp_engine, fb_settings or {})
            if exp_engine is not None
            else {}
        )
        if not bubble_scores:
            # Silent fallback to reverse-chrono when no onboarding data
            posts_query = db.session.query(Post).filter(
                Post.user_id != uid, _root_post_filter()
            )
            posts = _order_query_by_simulation_time(posts_query).paginate(
                page=page, per_page=per_page, error_out=False
            )
        else:
            ranked_ids = sorted(bubble_scores, key=lambda k: -bubble_scores[k])
            unscored_ids = [
                r[0] for r in
                db.session.query(Post.id)
                .filter(Post.user_id != uid, _root_post_filter(),
                        Post.id.notin_(set(ranked_ids)))
                .order_by(desc(Post.id))
                .all()
            ]
            full_ranking = ranked_ids + unscored_ids
            start = (page - 1) * per_page
            page_ids = full_ranking[start: start + per_page]
            pos_map = {pid: i for i, pid in enumerate(page_ids)}
            fetched = (
                db.session.query(Post).filter(Post.id.in_(page_ids)).all()
                if page_ids else []
            )
            fetched.sort(key=lambda p: pos_map.get(p.id, 9999))
            total = len(full_ranking)
            # Wrap in a simple object compatible with Pagination duck-typing
            posts = _make_pagination(fetched, page, per_page, total)
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
