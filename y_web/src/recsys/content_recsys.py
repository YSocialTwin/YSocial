"""
Content recommendation system algorithms.

Implements various content recommendation strategies for personalizing
the social media feed including reverse chronological, popularity-based,
follower-based, interest-based, and collaborative filtering approaches.
"""

import logging
import math

from sqlalchemy import bindparam, desc, or_, text
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


logger = logging.getLogger(__name__)


class PersonalizedFeedRankingError(RuntimeError):
    """Raised when Personalized Feed data exists but cannot be ranked."""


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
        # db row stored as filter_bubble_v1 → compact = filterbubblev1
        "filterbubblev1":   "FilterBubble",
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


def _declared_topic_ids(uid):
    """Return profile-selected topic IDs, when the preference table exists.

    ``user_topic_interest`` is intentionally queried as text: standard
    experiments use integer topic IDs while HPC experiments commonly use
    UUIDs.  Older databases do not have this table, so absence is treated as
    no declared preferences rather than as a ranking error.
    """
    try:
        engine = db.engines.get("db_exp")
        if engine is None:
            return []
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT topic_id, interest_level FROM user_topic_interest "
                    "WHERE CAST(user_id AS TEXT) = :uid"
                ),
                {"uid": str(uid)},
            ).all()
    except Exception:
        return []
    return [
        str(row[0])
        for row in rows
        if row[0] is not None and float(row[1] or 0.0) > 0.0
    ]


def _user_interest_topic_ids(uid):
    """Combine declared profile topics with legacy behavioral interests."""
    declared = _declared_topic_ids(uid)
    try:
        legacy = db.session.scalars(
            sa_select(User_interest.interest_id).filter_by(user_id=uid)
        ).all()
    except Exception:
        legacy = []
    return list(dict.fromkeys([*declared, *(str(value) for value in legacy)]))


def _post_ids_for_topic_ids(topic_ids):
    """Resolve topic IDs to post IDs across integer and UUID experiments."""
    if not topic_ids:
        return []
    try:
        engine = db.engines.get("db_exp")
        if engine is None:
            return []
        statement = text(
            "SELECT DISTINCT post_id FROM post_topics "
            "WHERE CAST(topic_id AS TEXT) IN :topic_ids"
        ).bindparams(bindparam("topic_ids", expanding=True))
        with engine.connect() as connection:
            rows = connection.execute(statement, {"topic_ids": topic_ids}).all()
    except Exception:
        return []
    return [row[0] for row in rows if row[0] is not None]


def _users_with_declared_topics(topic_ids, exclude_uid=None):
    """Find users sharing at least one declared topic with the target user."""
    if not topic_ids:
        return []
    try:
        engine = db.engines.get("db_exp")
        if engine is None:
            return []
        statement = text(
            "SELECT DISTINCT user_id FROM user_topic_interest "
            "WHERE CAST(topic_id AS TEXT) IN :topic_ids"
        ).bindparams(bindparam("topic_ids", expanding=True))
        with engine.connect() as connection:
            rows = connection.execute(statement, {"topic_ids": topic_ids}).all()
    except Exception:
        rows = []
    values = [row[0] for row in rows if row[0] is not None]
    if exclude_uid is not None:
        values = [value for value in values if str(value) != str(exclude_uid)]
    return values


def _rank_feature_based_posts(uid, topic_ids, page, per_page, hybrid=False):
    """Rank topic-tagged posts deterministically for CBV/HLR modes.

    The project does not persist a universal embedding column, so the vector
    representation is the sparse topic vector.  HLR adds a bounded engagement
    component; both modes use the same stable simulation-time/ID tie breaker.
    """
    post_ids = _post_ids_for_topic_ids(topic_ids)
    if not post_ids:
        return _reverse_chrono_fallback(uid, page, per_page).paginate(
            page=page, per_page=per_page, error_out=False
        )

    topic_set = set(topic_ids)
    try:
        with db.engines["db_exp"].connect() as connection:
            topic_rows = connection.execute(
                text(
                    "SELECT post_id, topic_id FROM post_topics "
                    "WHERE CAST(post_id AS TEXT) IN :post_ids"
                ).bindparams(bindparam("post_ids", expanding=True)),
                {"post_ids": [str(value) for value in post_ids]},
            ).all()
    except Exception:
        topic_rows = []

    post_topics = {}
    for post_id, topic_id in topic_rows:
        post_topics.setdefault(str(post_id), set()).add(str(topic_id))

    candidates = Post.query.filter(
        Post.id.in_(post_ids), Post.user_id != uid, _root_post_filter()
    ).all()
    if not candidates:
        return _reverse_chrono_fallback(uid, page, per_page).paginate(
            page=page, per_page=per_page, error_out=False
        )

    max_reactions = max((int(post.reaction_count or 0) for post in candidates), default=0)

    def rank_key(post):
        overlap = len(post_topics.get(str(post.id), set()) & topic_set)
        engagement = (int(post.reaction_count or 0) / max_reactions) if max_reactions else 0.0
        score = float(overlap) + (0.35 * engagement if hybrid else 0.0)
        return (-score, -int(post.reaction_count or 0), str(post.id))

    candidates.sort(key=rank_key)
    start = max(0, (page - 1) * per_page)
    return _make_pagination(candidates[start:start + per_page], page, per_page, len(candidates))



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

    Reads user interests + opinions from the experiment DB and scores every
    non-owned root post. Identifiers are deliberately treated as opaque values:
    Standard experiments use integers, while HPC experiments use UUID strings.

    An empty mapping means a genuine cold start (no preferences or no tagged
    candidates). Operational/schema failures raise PersonalizedFeedRankingError
    so callers can log an observable fallback instead of disguising a defect as
    a cold start.

    Author opinion priority per (author, topic, post):
      1. agent_opinion row whose id_post = post.id (recorded at write time)
      2. author's most recent agent_opinion at/before the post's simulation time
      3. author's baseline opinion (tid = 0)
      4. neutral weight (w_op = 0.5) when no opinion record is available

    settings keys: filter_bubble_alpha, filter_bubble_beta, filter_bubble_gamma,
                   filter_bubble_wr, filter_bubble_wc, filter_bubble_ws
    """
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
                    text("SELECT topic_id, interest_level FROM user_topic_interest "
                         "WHERE CAST(user_id AS TEXT) = :uid"),
                    {"uid": uid_str},
                ).fetchall()
            }
            if not interests:
                return {}

            # 2. User opinions at onboarding (tid = 0)
            rows = conn.execute(
                text("SELECT topic_id, opinion FROM agent_opinion "
                     "WHERE CAST(agent_id AS TEXT) = :aid "
                     "AND CAST(tid AS TEXT) = '0'"),
                {"aid": uid_str},
            ).fetchall()
            user_opinions = {str(r[0]): float(r[1]) for r in rows}

            # 3. Post topics for non-owned root posts
            pt_rows = conn.execute(
                text("SELECT pt.post_id, pt.topic_id "
                     "FROM post_topics pt "
                     "JOIN post p ON p.id = pt.post_id "
                     "WHERE CAST(p.user_id AS TEXT) != :uid "
                     "  AND (p.comment_to IS NULL "
                     "       OR CAST(p.comment_to AS TEXT) = '-1')"),
                {"uid": uid_str},
            ).fetchall()
            post_topics_map = {}
            for pid, tid in pt_rows:
                post_topics_map.setdefault(str(pid), []).append(str(tid))
            if not post_topics_map:
                return {}

            # 4. Post metadata: author, raw round FK (for opinion lookup),
            #    round_val (day*24+hour, for recency), base engagement.
            meta_rows = conn.execute(
                text("SELECT p.id, p.user_id, p.reaction_count, p.round, r.day, r.hour "
                     "FROM post p LEFT JOIN rounds r ON r.id = p.round "
                     "WHERE CAST(p.user_id AS TEXT) != :uid "
                     "  AND (p.comment_to IS NULL "
                     "       OR CAST(p.comment_to AS TEXT) = '-1')"),
                {"uid": uid_str},
            ).fetchall()
            post_meta = {}
            native_post_ids = {}
            max_round_val = 0
            all_author_ids = set()
            for pid, author_id, reaction_count, round_id, day, hour in meta_rows:
                rv = int(day or 0) * 24 + int(hour or 0)
                if rv > max_round_val:
                    max_round_val = rv
                all_author_ids.add(str(author_id))
                pid_key = str(pid)
                native_post_ids[pid_key] = pid
                post_meta[pid_key] = {
                    "author_id":      str(author_id),
                    "reaction_count": int(reaction_count or 0),
                    "round_val":      rv,
                    "round_id":       str(round_id) if round_id is not None else "",
                }

            # 5a. Author opinions explicitly tied to a specific post (highest priority).
            #     Keyed as opinions_at_post[agent_id][post_id][topic_id].
            opinions_at_post = {}
            post_ids = list(native_post_ids.values())
            if post_ids:
                stmt = text(
                    "SELECT agent_id, id_post, topic_id, opinion "
                    "FROM agent_opinion WHERE id_post IN :post_ids"
                ).bindparams(bindparam("post_ids", expanding=True))
                for agent_id, id_post, topic_id, opinion in conn.execute(
                    stmt, {"post_ids": post_ids}
                ).fetchall():
                    (
                        opinions_at_post
                        .setdefault(str(agent_id), {})
                        .setdefault(str(id_post), {})
                    )[str(topic_id)] = float(opinion)

            # 5b. Author opinion history. Round IDs are not ordered: UUID HPC
            #     schemas require chronology to be resolved through rounds.
            #     Values are (simulation_hour, opinion), sorted ascending.
            opinion_history = {}
            baseline_author_opinions = {}
            if all_author_ids:
                author_ids = list(all_author_ids)
                baseline_stmt = text(
                    "SELECT agent_id, topic_id, opinion FROM agent_opinion "
                    "WHERE CAST(agent_id AS TEXT) IN :author_ids "
                    "AND CAST(tid AS TEXT) = '0'"
                ).bindparams(bindparam("author_ids", expanding=True))
                for agent_id, topic_id, opinion in conn.execute(
                    baseline_stmt, {"author_ids": author_ids}
                ).fetchall():
                    baseline_author_opinions.setdefault(str(agent_id), {})[
                        str(topic_id)
                    ] = float(opinion)

                history_stmt = text(
                    "SELECT ao.agent_id, ao.topic_id, ao.opinion, r.day, r.hour "
                    "FROM agent_opinion ao "
                    "JOIN rounds r ON r.id = ao.tid "
                    "WHERE CAST(ao.agent_id AS TEXT) IN :author_ids "
                    "AND CAST(ao.tid AS TEXT) != '0' "
                    "ORDER BY r.day ASC, r.hour ASC"
                ).bindparams(bindparam("author_ids", expanding=True))
                for agent_id, topic_id, opinion, day, hour in conn.execute(
                    history_stmt, {"author_ids": author_ids}
                ).fetchall():
                    simulation_hour = int(day or 0) * 24 + int(hour or 0)
                    (
                        opinion_history
                        .setdefault(str(agent_id), {})
                        .setdefault(str(topic_id), [])
                    ).append((simulation_hour, float(opinion)))

            comment_counts = {}
            share_counts = {}
            if gamma > 0:
                try:
                    cc_rows = conn.execute(
                        text("SELECT comment_to, COUNT(*) FROM post "
                             "WHERE comment_to IS NOT NULL "
                             "AND CAST(comment_to AS TEXT) != '-1' "
                             "GROUP BY comment_to")
                    ).fetchall()
                    comment_counts = {str(r[0]): int(r[1]) for r in cc_rows}
                    sc_rows = conn.execute(
                        text("SELECT shared_from, COUNT(*) FROM post "
                             "WHERE shared_from IS NOT NULL "
                             "AND CAST(shared_from AS TEXT) != '-1' "
                             "GROUP BY shared_from")
                    ).fetchall()
                    share_counts = {str(r[0]): int(r[1]) for r in sc_rows}
                except Exception as exc:
                    raise PersonalizedFeedRankingError(
                        "Unable to load Personalized Feed engagement data"
                    ) from exc

    except PersonalizedFeedRankingError:
        raise
    except Exception as exc:
        raise PersonalizedFeedRankingError(
            f"Unable to load Personalized Feed data for user {uid_str}"
        ) from exc

    def _latest_opinion_before(history_list, post_round_val):
        """Return the latest opinion at/before a post's simulation time."""
        eligible = [value for when, value in history_list if when <= post_round_val]
        return eligible[-1] if eligible else None

    # 6. Compute scores
    scored = []
    current_round_val = max_round_val

    for post_id_str, topic_ids in post_topics_map.items():
        meta = post_meta.get(post_id_str, {})
        author_id     = meta.get("author_id", "")
        post_round_val = meta.get("round_val", 0)
        thematic = 0.0

        for topic_id in topic_ids:
            w_int = interests.get(topic_id, 0.0)
            if w_int == 0.0:
                continue
            u_op = user_opinions.get(topic_id)

            # Priority 1: opinion explicitly recorded at post write time
            p_op = (
                opinions_at_post
                .get(author_id, {})
                .get(post_id_str, {})
                .get(topic_id)
            )
            # Priority 2: most recent opinion before (or at) post publication round
            if p_op is None:
                hist = opinion_history.get(author_id, {}).get(topic_id)
                if hist:
                    p_op = _latest_opinion_before(hist, post_round_val)
            if p_op is None:
                p_op = baseline_author_opinions.get(author_id, {}).get(topic_id)

            if u_op is not None and p_op is not None:
                w_op = math.exp(-alpha * (u_op - p_op) ** 2)
            elif u_op is None:
                w_op = 1.0
            else:
                w_op = 0.5  # author opinion unknown — neutral weight
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

        final_score = thematic * recency * engagement
        scored.append({
            "post_id": native_post_ids[post_id_str],
            "score": final_score,
            "round_val": meta.get("round_val", 0),
            "engagement": eng if gamma > 0 else meta.get("reaction_count", 0),
        })

    sort_mode = str(settings.get("filter_bubble_sort", "score") or "score").lower()
    if sort_mode == "recency":
        key = lambda item: (-item["round_val"], -item["score"], str(item["post_id"]))
    elif sort_mode == "engagement":
        key = lambda item: (-item["engagement"], -item["score"], str(item["post_id"]))
    else:  # score and hybrid both use the complete configured score
        key = lambda item: (-item["score"], -item["round_val"], str(item["post_id"]))

    # Dict insertion order is the ranking contract consumed by pagination.
    return {item["post_id"]: item["score"] for item in sorted(scored, key=key)}


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
        interest_ids = _user_interest_topic_ids(uid)

        if interest_ids:
            matching_post_ids = _post_ids_for_topic_ids(interest_ids)
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
        interest_ids = _user_interest_topic_ids(uid)

        if interest_ids:
            similar_user_ids = db.session.scalars(
                sa_select(User_interest.user_id)
                .where(
                    User_interest.interest_id.in_([value for value in interest_ids if value.isdigit()]),
                    User_interest.user_id != uid,
                )
                .distinct()
            ).all()
            similar_user_ids.extend(
                _users_with_declared_topics(interest_ids, exclude_uid=uid)
            )
            similar_user_ids = list(dict.fromkeys(similar_user_ids))
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
        interest_ids = _user_interest_topic_ids(uid)

        if interest_ids:
            matching_post_ids = _post_ids_for_topic_ids(interest_ids)
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

    elif mode == "ContentBasedVector":
        # Sparse topic-vector similarity.  This is deliberately deterministic
        # and remains useful for UUID-backed HPC experiments.
        posts = _rank_feature_based_posts(
            uid, _user_interest_topic_ids(uid), page, per_page, hybrid=False
        )
        additional_posts = None

    elif mode == "HybridLinearRanker":
        # Topic similarity plus a bounded engagement component.
        posts = _rank_feature_based_posts(
            uid, _user_interest_topic_ids(uid), page, per_page, hybrid=True
        )
        additional_posts = None

    elif mode == "FilterBubble":
        try:
            if exp_engine is None:
                raise PersonalizedFeedRankingError(
                    "No experiment engine is available for Personalized Feed"
                )
            bubble_scores = _filter_bubble_score(
                uid, exp_engine, fb_settings or {}
            )
        except PersonalizedFeedRankingError:
            logger.exception(
                "Personalized Feed ranking failed for user %s; using reverse chronology",
                uid,
            )
            bubble_scores = {}
        if not bubble_scores:
            # Availability fallback for either an observable ranking error or a
            # genuine cold start. _filter_bubble_score only returns {} for the
            # latter; failures are logged above.
            posts_query = db.session.query(Post).filter(
                Post.user_id != uid, _root_post_filter()
            )
            posts = _order_query_by_simulation_time(posts_query).paginate(
                page=page, per_page=per_page, error_out=False
            )
        else:
            # The scorer returns an insertion-ordered mapping whose order also
            # includes deterministic simulation-time tie breaking.
            ranked_ids = list(bubble_scores)
            unscored_ids = [
                r[0] for r in
                _order_query_by_simulation_time(
                    db.session.query(Post.id).filter(
                        Post.user_id != uid,
                        _root_post_filter(),
                        Post.id.notin_(ranked_ids),
                    )
                )
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
