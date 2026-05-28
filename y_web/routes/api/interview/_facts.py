from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, desc, func, or_

from y_web import db
from y_web.src.models import (
    AdminInterviewMessage,
    Exps,
    Interests,
    Post,
    Reactions,
    ReplyInboxState,
    User_interest,
    User_mgmt,
)

from ._helpers import _coerce_experiment_user_id, _truncate_middle
from ._memory import (
    _INTERVIEW_QUERY_TERM_ALIASES,
    _INTERVIEW_TERM_STOPWORDS,
    _INTERVIEW_WEAK_QUERY_TERMS,
    _experiment_sqlite_db_path,
)


def _extract_query_terms(admin_text: str, *, max_terms: int = 8) -> List[str]:
    """
    Heuristic keyword extraction from the admin's message.

    Intentionally simple and deterministic: helps retrieve evidence without an extra LLM call.
    """
    text = (admin_text or "").strip()
    if not text:
        return []

    # Prefer explicit @mentions.
    mentions = re.findall(r"@([A-Za-z0-9_]{2,32})", text)
    terms: List[str] = []
    for m in mentions:
        t = m.strip()
        if t:
            terms.append(t)

    # Extract "interesting" tokens: 3+ chars, alpha-numeric.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_'-]{2,}", text)
    for tok in tokens:
        t = tok.strip().strip("'\"").lower()
        if not t or t in _INTERVIEW_TERM_STOPWORDS:
            continue
        if t.isdigit() or len(t) < 3:
            continue
        terms.append(t)

    # Deduplicate while preserving order.
    seen = set()
    base_terms: List[str] = []
    for t in terms:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        base_terms.append(t)
        if len(base_terms) >= max_terms:
            break

    # Expand lightweight aliases to improve lexical fallback recall.
    out: List[str] = list(base_terms)
    for t in base_terms:
        alias_candidates = (
            _INTERVIEW_QUERY_TERM_ALIASES.get(str(t).strip().lower()) or []
        )
        for alias in alias_candidates:
            alias_clean = str(alias or "").strip().lower()
            if not alias_clean or alias_clean in seen:
                continue
            seen.add(alias_clean)
            out.append(alias_clean)
            if len(out) >= max_terms:
                break
        if len(out) >= max_terms:
            break
    return out[:max_terms]


def _extract_query_ids(admin_text: str) -> Dict[str, List[int]]:
    text = (admin_text or "").strip()
    if not text:
        return {"thread_ids": [], "post_ids": [], "comment_ids": []}

    def _ints_from(pattern: str) -> List[int]:
        vals: List[int] = []
        for m in re.findall(pattern, text, flags=re.IGNORECASE):
            try:
                v = int(str(m).strip())
            except Exception:
                continue
            if v > 0:
                vals.append(v)
        # Deduplicate, preserve order.
        seen = set()
        out: List[int] = []
        for v in vals:
            if v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out

    thread_ids = _ints_from(r"\bthread(?:_root_id)?\s*(?:=|:)?\s*#?(\d+)\b")
    post_ids = _ints_from(r"\bpost(?:_id)?\s*(?:=|:)?\s*#?(\d+)\b")
    comment_ids = _ints_from(r"\bcomment(?:_id)?\s*(?:=|:)?\s*#?(\d+)\b")
    return {
        "thread_ids": thread_ids[:8],
        "post_ids": post_ids[:8],
        "comment_ids": comment_ids[:8],
    }


def _evaluate_query_hit_text(text: str, terms: List[str]) -> Dict[str, Any]:
    text_l = str(text or "").lower()
    term_list = [str(t or "").strip().lower() for t in (terms or [])]
    term_list = [t for t in term_list if len(t) >= 3]
    matched_terms: List[str] = []
    for t in term_list:
        if t in text_l:
            matched_terms.append(t)
    matched_terms = list(dict.fromkeys(matched_terms))
    informative_terms = [
        t for t in matched_terms if t not in _INTERVIEW_WEAK_QUERY_TERMS
    ]
    score = (2 * len(informative_terms)) + len(matched_terms)
    return {
        "matched_terms": matched_terms,
        "informative_terms": informative_terms,
        "term_matches": len(matched_terms),
        "informative_matches": len(informative_terms),
        "score": int(score),
    }


def _build_contextual_admin_query_text(
    session_id: int,
    latest_admin_text: str,
    *,
    max_admin_msgs: int = 3,
    max_chars: int = 900,
) -> str:
    """
    Build a retrieval query that preserves references across follow-up turns.

    Example: "but what was his original comment?" should carry prior @mention context.
    """
    latest = (latest_admin_text or "").strip()
    chunks: List[str] = []
    if latest:
        chunks.append(latest)

    try:
        rows = (
            AdminInterviewMessage.query.filter_by(
                session_id=int(session_id), role="admin"
            )
            .order_by(AdminInterviewMessage.id.desc())
            .limit(max(1, int(max_admin_msgs) + 1))
            .all()
        )
    except Exception:
        rows = []

    # Keep only previous admin turns (exclude latest if duplicated).
    prev_texts: List[str] = []
    for m in rows:
        txt = (getattr(m, "content", "") or "").strip()
        if not txt:
            continue
        if latest and txt == latest:
            continue
        prev_texts.append(txt)
        if len(prev_texts) >= max(1, int(max_admin_msgs)):
            break

    for txt in reversed(prev_texts):
        chunks.append(txt)

    merged = "\n".join([c for c in chunks if c]).strip()
    if not merged:
        return latest
    if len(merged) <= int(max_chars):
        return merged
    return merged[-int(max_chars) :].strip()


def _get_reaction_counts_for_posts(post_ids: List[int]) -> Dict[int, Dict[str, int]]:
    if not post_ids:
        return {}
    ids = [int(x) for x in post_ids if x is not None]
    if not ids:
        return {}

    # Default to 0/0 for requested ids.
    counts: Dict[int, Dict[str, int]] = {
        int(pid): {"likes": 0, "dislikes": 0} for pid in ids
    }

    try:
        q = (
            db.session.query(
                Reactions.post_id.label("post_id"),
                func.sum(case((Reactions.type == "like", 1), else_=0)).label("likes"),
                func.sum(case((Reactions.type == "dislike", 1), else_=0)).label(
                    "dislikes"
                ),
            )
            .filter(Reactions.post_id.in_(ids))
            .group_by(Reactions.post_id)
        )
        for row in q.all():
            pid = int(getattr(row, "post_id", 0) or 0)
            if pid <= 0:
                continue
            counts[pid] = {
                "likes": int(getattr(row, "likes", 0) or 0),
                "dislikes": int(getattr(row, "dislikes", 0) or 0),
            }
    except Exception:
        # Best-effort only; fall back to zeros.
        pass

    return counts


def _post_to_fact(
    p: Post,
    counts: Dict[int, Dict[str, int]],
    comment_context: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if p is None:
        return {}
    pid = int(getattr(p, "id", 0) or 0)
    c = counts.get(pid) or {}
    text = getattr(p, "tweet", "") or ""
    out = {
        "post_id": pid,
        "thread_root_id": int(getattr(p, "thread_id", 0) or 0) or None,
        "comment_to": (
            int(getattr(p, "comment_to", -1) or -1)
            if getattr(p, "comment_to", None) is not None
            else None
        ),
        "round": int(getattr(p, "round", 0) or 0) or None,
        "reaction_count": int(getattr(p, "reaction_count", 0) or 0),
        "likes": int(c.get("likes", 0) or 0),
        "dislikes": int(c.get("dislikes", 0) or 0),
        "text": _truncate_middle(str(text), 240),
    }
    if isinstance(comment_context, dict):
        extra = comment_context.get(pid)
        if isinstance(extra, dict):
            out.update(extra)
    return out


def _build_facts_snapshot_sqlite(
    *,
    exp: Exps,
    agent_user_id: str,
    admin_text: str,
    top_posts_limit: int = 3,
    recent_comments_limit: int = 5,
    query_hits_limit: int = 5,
) -> Dict[str, Any]:
    db_path = _experiment_sqlite_db_path(exp)
    snap: Dict[str, Any] = {
        "agent_user_id": agent_user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if db_path is None or not db_path.exists():
        snap.update(
            {
                "query_terms": [],
                "query_id_filters": {
                    "thread_ids": [],
                    "post_ids": [],
                    "comment_ids": [],
                },
                "query_hit_evaluations": [],
                "query_hits_viable_count": 0,
                "top_posts": [],
                "recent_root_posts": [],
                "recent_comments": [],
                "replies_to_recent_comments": [],
                "replies_to_top_posts": [],
                "query_hits": [],
            }
        )
        return snap

    terms = _extract_query_terms(admin_text)
    query_ids = _extract_query_ids(admin_text)
    snap["query_terms"] = terms
    snap["query_id_filters"] = query_ids

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:

            def _fetch_posts(
                where_sql: str, params: Tuple[Any, ...], limit: int
            ) -> List[sqlite3.Row]:
                sql = f"""
                    select id, tweet, thread_id, comment_to, round, reaction_count, user_id
                    from post
                    where {where_sql}
                    order by reaction_count desc, id desc
                    limit ?
                """
                return conn.execute(sql, tuple(params) + (int(limit),)).fetchall()

            def _fetch_recent_posts(
                where_sql: str, params: Tuple[Any, ...], limit: int
            ) -> List[sqlite3.Row]:
                sql = f"""
                    select id, tweet, thread_id, comment_to, round, reaction_count, user_id
                    from post
                    where {where_sql}
                    order by id desc
                    limit ?
                """
                return conn.execute(sql, tuple(params) + (int(limit),)).fetchall()

            top_posts = _fetch_posts(
                "user_id = ? and coalesce(comment_to, '-1') = '-1'",
                (agent_user_id,),
                int(top_posts_limit),
            )
            recent_root_posts = _fetch_recent_posts(
                "user_id = ? and coalesce(comment_to, '-1') = '-1'",
                (agent_user_id,),
                max(int(top_posts_limit), 5),
            )
            recent_comments = _fetch_recent_posts(
                "user_id = ? and coalesce(comment_to, '-1') != '-1'",
                (agent_user_id,),
                int(recent_comments_limit),
            )

            all_posts = (
                list(top_posts) + list(recent_root_posts) + list(recent_comments)
            )

            query_hits_rows: List[sqlite3.Row] = []
            if terms:
                conds = []
                params: List[Any] = [agent_user_id]
                for term in terms[:8]:
                    conds.append("lower(tweet) like ?")
                    params.append(f"%{str(term).lower()}%")
                sql = f"""
                    select id, tweet, thread_id, comment_to, round, reaction_count, user_id
                    from post
                    where user_id = ? and ({' or '.join(conds)})
                    order by id desc
                    limit ?
                """
                query_hits_rows.extend(
                    conn.execute(
                        sql, tuple(params) + (max(int(query_hits_limit), 8),)
                    ).fetchall()
                )

            explicit_rows: List[sqlite3.Row] = []
            thread_ids = [
                str(x) for x in (query_ids.get("thread_ids") or []) if str(x).strip()
            ]
            post_ids = [
                str(x) for x in (query_ids.get("post_ids") or []) if str(x).strip()
            ]
            comment_ids = [
                str(x) for x in (query_ids.get("comment_ids") or []) if str(x).strip()
            ]
            explicit_conds = []
            explicit_params: List[Any] = [agent_user_id]
            if thread_ids:
                explicit_conds.append(
                    f"thread_id in ({','.join(['?']*len(thread_ids))})"
                )
                explicit_params.extend(thread_ids)
            if post_ids:
                explicit_conds.append(f"id in ({','.join(['?']*len(post_ids))})")
                explicit_params.extend(post_ids)
            if comment_ids:
                explicit_conds.append(
                    f"comment_to in ({','.join(['?']*len(comment_ids))})"
                )
                explicit_params.extend(comment_ids)
            if explicit_conds:
                sql = f"""
                    select id, tweet, thread_id, comment_to, round, reaction_count, user_id
                    from post
                    where user_id = ? and ({' or '.join(explicit_conds)})
                    order by id desc
                    limit ?
                """
                explicit_rows = conn.execute(
                    sql,
                    tuple(explicit_params) + (max(int(query_hits_limit), 8),),
                ).fetchall()

            merged_by_id: Dict[str, sqlite3.Row] = {}
            for row in list(explicit_rows) + list(query_hits_rows):
                rid = str(row["id"])
                if rid not in merged_by_id:
                    merged_by_id[rid] = row
            query_hits = list(merged_by_id.values())[: max(int(query_hits_limit), 8)]
            all_posts.extend(query_hits)

            post_ids_all = sorted(
                {str(row["id"]) for row in all_posts if row is not None}
            )
            reaction_counts: Dict[str, Dict[str, int]] = {
                pid: {"likes": 0, "dislikes": 0} for pid in post_ids_all
            }
            if post_ids_all:
                sql = f"""
                    select post_id,
                           sum(case when lower(type) in ('like','love','laugh') then 1 else 0 end) as likes,
                           sum(case when lower(type) in ('dislike','angry','sad') then 1 else 0 end) as dislikes
                    from reactions
                    where post_id in ({','.join(['?']*len(post_ids_all))})
                    group by post_id
                """
                for row in conn.execute(sql, tuple(post_ids_all)).fetchall():
                    reaction_counts[str(row["post_id"])] = {
                        "likes": int(row["likes"] or 0),
                        "dislikes": int(row["dislikes"] or 0),
                    }

            parent_ids = sorted(
                {
                    str(row["comment_to"])
                    for row in list(recent_comments) + list(query_hits)
                    if str(row["comment_to"] or "").strip() not in {"", "-1", "None"}
                }
            )
            thread_ids_for_context = sorted(
                {
                    str(row["thread_id"])
                    for row in list(recent_comments) + list(query_hits)
                    if str(row["thread_id"] or "").strip() not in {"", "0", "None"}
                }
            )

            parent_map: Dict[str, sqlite3.Row] = {}
            if parent_ids:
                sql = f"select id, tweet, user_id from post where id in ({','.join(['?']*len(parent_ids))})"
                for row in conn.execute(sql, tuple(parent_ids)).fetchall():
                    parent_map[str(row["id"])] = row

            op_map: Dict[str, sqlite3.Row] = {}
            if thread_ids_for_context:
                sql = f"select id, tweet, user_id from post where id in ({','.join(['?']*len(thread_ids_for_context))})"
                for row in conn.execute(sql, tuple(thread_ids_for_context)).fetchall():
                    op_map[str(row["id"])] = row

            user_ids = sorted(
                {
                    str(row["user_id"])
                    for row in list(parent_map.values()) + list(op_map.values())
                    if str(row["user_id"] or "").strip()
                }
            )
            usernames: Dict[str, str] = {}
            if user_ids:
                sql = f"select id, username from user_mgmt where id in ({','.join(['?']*len(user_ids))})"
                for row in conn.execute(sql, tuple(user_ids)).fetchall():
                    usernames[str(row["id"])] = str(row["username"] or "")

            def _row_to_fact(row: sqlite3.Row) -> Dict[str, Any]:
                pid = str(row["id"])
                parent_id = str(row["comment_to"] or "")
                thread_id = str(row["thread_id"] or "")
                parent_post = parent_map.get(parent_id)
                thread_post = op_map.get(thread_id)
                return {
                    "post_id": pid,
                    "thread_root_id": thread_id or None,
                    "comment_to": (
                        parent_id if parent_id and parent_id != "-1" else None
                    ),
                    "round": str(row["round"] or "") or None,
                    "reaction_count": int(row["reaction_count"] or 0),
                    "likes": int((reaction_counts.get(pid) or {}).get("likes", 0) or 0),
                    "dislikes": int(
                        (reaction_counts.get(pid) or {}).get("dislikes", 0) or 0
                    ),
                    "text": _truncate_middle(str(row["tweet"] or ""), 240),
                    "parent_post_id": (
                        parent_id if parent_id and parent_id != "-1" else None
                    ),
                    "parent_user_id": (
                        str(parent_post["user_id"]) if parent_post is not None else None
                    ),
                    "parent_username": (
                        usernames.get(str(parent_post["user_id"]))
                        if parent_post is not None
                        else None
                    ),
                    "parent_text": (
                        _truncate_middle(str(parent_post["tweet"] or ""), 220)
                        if parent_post is not None
                        else None
                    ),
                    "thread_op_post_id": thread_id or None,
                    "thread_op_user_id": (
                        str(thread_post["user_id"]) if thread_post is not None else None
                    ),
                    "thread_op_username": (
                        usernames.get(str(thread_post["user_id"]))
                        if thread_post is not None
                        else None
                    ),
                    "thread_op_text": (
                        _truncate_middle(str(thread_post["tweet"] or ""), 180)
                        if thread_post is not None
                        else None
                    ),
                }

            hit_eval_rows: List[Dict[str, Any]] = []
            for row in query_hits:
                ev = _evaluate_query_hit_text(str(row["tweet"] or ""), terms)
                hit_eval_rows.append(
                    {
                        "post_id": str(row["id"]),
                        "thread_root_id": str(row["thread_id"] or "") or None,
                        "score": int(ev.get("score") or 0),
                        "term_matches": int(ev.get("term_matches") or 0),
                        "informative_matches": int(ev.get("informative_matches") or 0),
                        "matched_terms": ev.get("matched_terms") or [],
                        "informative_terms": ev.get("informative_terms") or [],
                    }
                )
            hit_eval_rows.sort(
                key=lambda r: (
                    int(r.get("informative_matches") or 0),
                    int(r.get("score") or 0),
                ),
                reverse=True,
            )

            snap["query_hit_evaluations"] = hit_eval_rows[:8]
            snap["query_hits_viable_count"] = sum(
                1
                for row in hit_eval_rows
                if int(row.get("informative_matches") or 0) > 0
            )
            snap["top_posts"] = [_row_to_fact(row) for row in top_posts]
            snap["recent_root_posts"] = [_row_to_fact(row) for row in recent_root_posts]
            snap["recent_comments"] = [_row_to_fact(row) for row in recent_comments]
            snap["replies_to_recent_comments"] = []
            snap["replies_to_top_posts"] = []
            snap["query_hits"] = [_row_to_fact(row) for row in query_hits]
        finally:
            conn.close()
    except Exception:
        snap["query_hit_evaluations"] = []
        snap["query_hits_viable_count"] = 0
        snap["top_posts"] = []
        snap["recent_root_posts"] = []
        snap["recent_comments"] = []
        snap["replies_to_recent_comments"] = []
        snap["replies_to_top_posts"] = []
        snap["query_hits"] = []
    return snap


def _build_facts_snapshot(
    *,
    exp: Optional[Exps] = None,
    agent_user_id: Any,
    admin_text: str,
    top_posts_limit: int = 3,
    recent_comments_limit: int = 5,
    query_hits_limit: int = 5,
) -> Dict[str, Any]:
    """
    Deterministic evidence extracted from the experiment DB (db_exp bind).

    Purpose: reduce hallucination in interviews by giving the model a short list
    of concrete things it actually posted/commented on, plus query-matched hits.
    """
    normalized_agent_user_id = _coerce_experiment_user_id(agent_user_id)
    if isinstance(normalized_agent_user_id, str) and exp is not None:
        return _build_facts_snapshot_sqlite(
            exp=exp,
            agent_user_id=normalized_agent_user_id,
            admin_text=admin_text,
            top_posts_limit=top_posts_limit,
            recent_comments_limit=recent_comments_limit,
            query_hits_limit=query_hits_limit,
        )
    snap: Dict[str, Any] = {
        "agent_user_id": normalized_agent_user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    def _collect_seen_replies(parent_posts: List[Post]) -> List[Dict[str, Any]]:
        parent_list = [p for p in (parent_posts or []) if p is not None]
        parent_ids = [int(getattr(p, "id", 0) or 0) for p in parent_list]
        parent_ids = [pid for pid in parent_ids if pid > 0]
        if not parent_ids:
            return []

        parent_map = {
            int(getattr(p, "id")): p for p in parent_list if getattr(p, "id", None)
        }

        # Reading signal: replies up to this cursor were seen in notifications inbox.
        last_seen_reply_id = 0
        try:
            st = ReplyInboxState.query.filter_by(
                user_id=normalized_agent_user_id
            ).first()
            if st is not None:
                last_seen_reply_id = int(getattr(st, "last_seen_reply_id", 0) or 0)
        except Exception:
            last_seen_reply_id = 0

        total_counts: Dict[int, int] = {}
        try:
            q_total = (
                Post.query.with_entities(
                    Post.comment_to.label("comment_to"),
                    func.count(Post.id).label("cnt"),
                )
                .filter(Post.comment_to.in_(parent_ids))
                .filter(Post.user_id != normalized_agent_user_id)
                .group_by(Post.comment_to)
            )
            for row in q_total.all():
                pid = int(getattr(row, "comment_to", 0) or 0)
                if pid > 0:
                    total_counts[pid] = int(getattr(row, "cnt", 0) or 0)
        except Exception:
            total_counts = {}

        try:
            reply_posts = (
                Post.query.filter(Post.comment_to.in_(parent_ids))
                .filter(Post.user_id != normalized_agent_user_id)
                .order_by(desc(Post.id))
                .limit(120)
                .all()
            )
        except Exception:
            reply_posts = []

        reply_ids = [
            int(getattr(rp, "id", 0) or 0)
            for rp in reply_posts
            if int(getattr(rp, "id", 0) or 0) > 0
        ]
        reacted_ids: set[int] = set()
        direct_reply_ids: set[int] = set()

        if reply_ids:
            try:
                reacted_rows = (
                    Reactions.query.with_entities(Reactions.post_id)
                    .filter(Reactions.user_id == normalized_agent_user_id)
                    .filter(Reactions.post_id.in_(reply_ids))
                    .all()
                )
                reacted_ids = {
                    int(getattr(r, "post_id", 0) or 0)
                    for r in reacted_rows
                    if int(getattr(r, "post_id", 0) or 0) > 0
                }
            except Exception:
                reacted_ids = set()

            try:
                replied_rows = (
                    Post.query.with_entities(Post.comment_to)
                    .filter(Post.user_id == normalized_agent_user_id)
                    .filter(Post.comment_to.in_(reply_ids))
                    .all()
                )
                direct_reply_ids = {
                    int(getattr(r, "comment_to", 0) or 0)
                    for r in replied_rows
                    if int(getattr(r, "comment_to", 0) or 0) > 0
                }
            except Exception:
                direct_reply_ids = set()

        try:
            author_ids = sorted(
                {
                    _coerce_experiment_user_id(getattr(rp, "user_id", None))
                    for rp in reply_posts
                    if _coerce_experiment_user_id(getattr(rp, "user_id", None))
                    is not None
                },
                key=lambda value: str(value),
            )
            users = (
                User_mgmt.query.filter(User_mgmt.id.in_(author_ids)).all()
                if author_ids
                else []
            )
            author_name_by_id = {
                _coerce_experiment_user_id(u.id): getattr(u, "username", None)
                for u in users
                if u is not None
            }
        except Exception:
            author_name_by_id = {}

        seen_counts: Dict[int, int] = {pid: 0 for pid in parent_ids}
        seen_examples_map: Dict[int, List[Dict[str, Any]]] = {
            pid: [] for pid in parent_ids
        }
        seen_reply_ids_by_parent: Dict[int, set[int]] = {
            pid: set() for pid in parent_ids
        }

        for rp in reply_posts:
            rid = int(getattr(rp, "id", 0) or 0)
            parent_id = int(getattr(rp, "comment_to", -1) or -1)
            author_id = _coerce_experiment_user_id(getattr(rp, "user_id", None))
            if rid <= 0 or parent_id not in seen_examples_map:
                continue

            seen_via: List[str] = []
            if rid <= int(last_seen_reply_id):
                seen_via.append("read")
            if rid in reacted_ids:
                seen_via.append("voted")
            if rid in direct_reply_ids:
                seen_via.append("commented")
            if not seen_via:
                continue

            if rid not in seen_reply_ids_by_parent[parent_id]:
                seen_reply_ids_by_parent[parent_id].add(rid)
                seen_counts[parent_id] = int(seen_counts.get(parent_id, 0) or 0) + 1

            if len(seen_examples_map[parent_id]) >= 2:
                continue

            seen_examples_map[parent_id].append(
                {
                    "reply_post_id": rid,
                    "user_id": author_id,
                    "username": author_name_by_id.get(author_id),
                    "round": int(getattr(rp, "round", 0) or 0) or None,
                    "text": _truncate_middle(str(getattr(rp, "tweet", "") or ""), 200),
                    "seen_via": seen_via,
                }
            )

        out: List[Dict[str, Any]] = []
        for p in parent_list:
            pid = int(getattr(p, "id", 0) or 0)
            if pid <= 0:
                continue
            parent_post = parent_map.get(pid) or p
            out.append(
                {
                    "post_id": pid,
                    "thread_root_id": int(getattr(parent_post, "thread_id", 0) or 0)
                    or None,
                    "round": int(getattr(parent_post, "round", 0) or 0) or None,
                    "text": _truncate_middle(
                        str(getattr(parent_post, "tweet", "") or ""), 220
                    ),
                    "total_reply_count": int(total_counts.get(pid, 0) or 0),
                    "seen_reply_count": int(seen_counts.get(pid, 0) or 0),
                    "seen_reply_examples": seen_examples_map.get(pid) or [],
                }
            )
        return out

    # Root posts (threads started by the agent).
    try:
        q_top = (
            Post.query.filter(Post.user_id == normalized_agent_user_id)
            .filter(Post.comment_to == -1)
            .order_by(desc(Post.reaction_count), desc(Post.id))
            .limit(int(top_posts_limit))
        )
        top_posts = q_top.all()
    except Exception:
        top_posts = []

    # Most recent authored root posts (for "last post/tweet" questions).
    try:
        q_recent_roots = (
            Post.query.filter(Post.user_id == normalized_agent_user_id)
            .filter(Post.comment_to == -1)
            .order_by(desc(Post.id))
            .limit(max(int(top_posts_limit), 5))
        )
        recent_root_posts = q_recent_roots.all()
    except Exception:
        recent_root_posts = []

    # Recent comments.
    try:
        q_recent = (
            Post.query.filter(Post.user_id == normalized_agent_user_id)
            .filter(Post.comment_to != -1)
            .order_by(desc(Post.id))
            .limit(int(recent_comments_limit))
        )
        recent_comments = q_recent.all()
    except Exception:
        recent_comments = []

    replies_to_recent_comments: List[Dict[str, Any]] = []
    replies_to_top_posts: List[Dict[str, Any]] = []
    try:
        replies_to_recent_comments = _collect_seen_replies(recent_comments or [])
    except Exception:
        replies_to_recent_comments = []
    try:
        replies_to_top_posts = _collect_seen_replies(top_posts or [])
    except Exception:
        replies_to_top_posts = []

    # Query-conditioned hits in the agent's own text.
    terms = _extract_query_terms(admin_text)
    snap["query_terms"] = terms
    query_ids = _extract_query_ids(admin_text)
    snap["query_id_filters"] = query_ids
    query_hits = []
    if terms:
        try:
            conds = [
                Post.tweet.ilike(f"%{t}%")
                for t in terms[:8]
                if isinstance(t, str) and t.strip()
            ]
            if conds:
                q_hits = (
                    Post.query.filter(Post.user_id == normalized_agent_user_id)
                    .filter(or_(*conds))
                    .order_by(desc(Post.id))
                    .limit(int(query_hits_limit))
                )
                query_hits = q_hits.all()
        except Exception:
            query_hits = []

    # Explicit id-conditioned hits (e.g., "thread 79", "post_id=122").
    id_hits = []
    try:
        thread_ids = [int(x) for x in (query_ids.get("thread_ids") or []) if int(x) > 0]
        post_ids = [int(x) for x in (query_ids.get("post_ids") or []) if int(x) > 0]
        comment_ids = [
            int(x) for x in (query_ids.get("comment_ids") or []) if int(x) > 0
        ]
    except Exception:
        thread_ids, post_ids, comment_ids = [], [], []

    if thread_ids or post_ids or comment_ids:
        try:
            id_conds = []
            if thread_ids:
                id_conds.append(Post.thread_id.in_(thread_ids))
            if post_ids:
                id_conds.append(Post.id.in_(post_ids))
            if comment_ids:
                id_conds.append(Post.comment_to.in_(comment_ids))
            if id_conds:
                q_id_hits = (
                    Post.query.filter(Post.user_id == normalized_agent_user_id)
                    .filter(or_(*id_conds))
                    .order_by(desc(Post.id))
                    .limit(max(int(query_hits_limit), 8))
                )
                id_hits = q_id_hits.all()
        except Exception:
            id_hits = []

    # Merge explicit-id hits first, then lexical hits, dedup by post id.
    merged_hits: List[Post] = []
    seen_hit_ids = set()
    for p in (id_hits or []) + (query_hits or []):
        if p is None:
            continue
        pid = int(getattr(p, "id", 0) or 0)
        if pid <= 0 or pid in seen_hit_ids:
            continue
        seen_hit_ids.add(pid)
        merged_hits.append(p)
        if len(merged_hits) >= max(int(query_hits_limit), 8):
            break
    query_hits = merged_hits

    # Score lexical relevance so weak generic term matches do not override strict evidence mode.
    hit_eval_rows: List[Dict[str, Any]] = []
    hit_eval_by_pid: Dict[int, Dict[str, Any]] = {}
    for p in query_hits:
        if p is None:
            continue
        pid = int(getattr(p, "id", 0) or 0)
        if pid <= 0:
            continue
        ev = _evaluate_query_hit_text(str(getattr(p, "tweet", "") or ""), terms)
        row = {
            "post_id": pid,
            "thread_root_id": int(getattr(p, "thread_id", 0) or 0) or None,
            "score": int(ev.get("score") or 0),
            "term_matches": int(ev.get("term_matches") or 0),
            "informative_matches": int(ev.get("informative_matches") or 0),
            "matched_terms": ev.get("matched_terms") or [],
            "informative_terms": ev.get("informative_terms") or [],
        }
        hit_eval_rows.append(row)
        hit_eval_by_pid[pid] = row

    hit_eval_rows.sort(
        key=lambda r: (
            int(r.get("informative_matches") or 0),
            int(r.get("score") or 0),
            int(r.get("post_id") or 0),
        ),
        reverse=True,
    )
    if hit_eval_rows:
        pid_order = [
            int(r.get("post_id") or 0)
            for r in hit_eval_rows
            if int(r.get("post_id") or 0) > 0
        ]
        by_pid = {int(getattr(p, "id", 0) or 0): p for p in query_hits if p is not None}
        query_hits = [by_pid[pid] for pid in pid_order if pid in by_pid][
            : max(int(query_hits_limit), 8)
        ]
    query_hits_viable_count = sum(
        1 for r in hit_eval_rows if int(r.get("informative_matches") or 0) > 0
    )
    snap["query_hit_evaluations"] = hit_eval_rows[:8]
    snap["query_hits_viable_count"] = int(query_hits_viable_count)

    # Build explicit "who did I reply to?" context for comment rows so interview
    # answers can resolve OP/parent identity deterministically.
    comment_context: Dict[int, Dict[str, Any]] = {}
    try:
        comment_posts = []
        for p in recent_comments or []:
            if p is None:
                continue
            try:
                if int(getattr(p, "comment_to", -1) or -1) != -1:
                    comment_posts.append(p)
            except Exception:
                continue
        for p in query_hits or []:
            if p is None:
                continue
            try:
                if int(getattr(p, "comment_to", -1) or -1) != -1:
                    comment_posts.append(p)
            except Exception:
                continue

        comment_posts_by_id: Dict[int, Post] = {}
        for p in comment_posts:
            pid = int(getattr(p, "id", 0) or 0)
            if pid > 0 and pid not in comment_posts_by_id:
                comment_posts_by_id[pid] = p

        if comment_posts_by_id:
            parent_ids = sorted(
                {
                    int(getattr(p, "comment_to", -1) or -1)
                    for p in comment_posts_by_id.values()
                    if int(getattr(p, "comment_to", -1) or -1) > 0
                }
            )
            thread_root_ids = sorted(
                {
                    int(getattr(p, "thread_id", 0) or 0)
                    for p in comment_posts_by_id.values()
                    if int(getattr(p, "thread_id", 0) or 0) > 0
                }
            )

            parent_map: Dict[int, Post] = {}
            if parent_ids:
                parents = Post.query.filter(Post.id.in_(parent_ids)).all()
                parent_map = {
                    int(getattr(pp, "id", 0) or 0): pp
                    for pp in parents
                    if pp is not None
                }

            op_map: Dict[int, Post] = {}
            if thread_root_ids:
                ops = Post.query.filter(Post.id.in_(thread_root_ids)).all()
                op_map = {
                    int(getattr(op, "id", 0) or 0): op for op in ops if op is not None
                }

            user_ids = set()
            for pp in parent_map.values():
                try:
                    uid = _coerce_experiment_user_id(getattr(pp, "user_id", None))
                    if uid is not None:
                        user_ids.add(uid)
                except Exception:
                    continue
            for op in op_map.values():
                try:
                    uid = _coerce_experiment_user_id(getattr(op, "user_id", None))
                    if uid is not None:
                        user_ids.add(uid)
                except Exception:
                    continue

            username_by_id: Dict[Any, Optional[str]] = {}
            if user_ids:
                users = User_mgmt.query.filter(
                    User_mgmt.id.in_(sorted(user_ids, key=lambda value: str(value)))
                ).all()
                username_by_id = {
                    _coerce_experiment_user_id(u.id): getattr(u, "username", None)
                    for u in users
                    if u is not None
                }

            for pid, p in comment_posts_by_id.items():
                parent_id = int(getattr(p, "comment_to", -1) or -1)
                thread_root_id = int(getattr(p, "thread_id", 0) or 0)
                parent_post = parent_map.get(parent_id)
                thread_op_post = op_map.get(thread_root_id)

                parent_user_id = (
                    _coerce_experiment_user_id(getattr(parent_post, "user_id", None))
                    if parent_post is not None
                    else None
                )

                thread_op_user_id = (
                    _coerce_experiment_user_id(getattr(thread_op_post, "user_id", None))
                    if thread_op_post is not None
                    else None
                )

                comment_context[pid] = {
                    "parent_post_id": int(parent_id) if parent_id > 0 else None,
                    "parent_user_id": parent_user_id,
                    "parent_username": (
                        username_by_id.get(parent_user_id)
                        if parent_user_id is not None
                        else None
                    ),
                    "parent_text": (
                        _truncate_middle(
                            str(getattr(parent_post, "tweet", "") or ""), 220
                        )
                        if parent_post is not None
                        else None
                    ),
                    "thread_op_post_id": (
                        int(thread_root_id) if thread_root_id > 0 else None
                    ),
                    "thread_op_user_id": thread_op_user_id,
                    "thread_op_username": (
                        username_by_id.get(thread_op_user_id)
                        if thread_op_user_id is not None
                        else None
                    ),
                    "thread_op_text": (
                        _truncate_middle(
                            str(getattr(thread_op_post, "tweet", "") or ""), 180
                        )
                        if thread_op_post is not None
                        else None
                    ),
                }
    except Exception:
        comment_context = {}

    # Batch counts for all referenced posts.
    all_posts: List[Post] = []
    for lst in [top_posts, recent_root_posts, recent_comments, query_hits]:
        for p in lst:
            if p is not None:
                all_posts.append(p)
    post_ids = sorted(
        {
            int(getattr(p, "id", 0) or 0)
            for p in all_posts
            if getattr(p, "id", None) is not None
        }
    )
    counts = _get_reaction_counts_for_posts(post_ids)

    snap["top_posts"] = [
        _post_to_fact(p, counts, comment_context) for p in (top_posts or [])
    ]
    snap["recent_root_posts"] = [
        _post_to_fact(p, counts, comment_context) for p in (recent_root_posts or [])
    ]
    snap["recent_comments"] = [
        _post_to_fact(p, counts, comment_context) for p in (recent_comments or [])
    ]
    snap["replies_to_recent_comments"] = replies_to_recent_comments
    snap["replies_to_top_posts"] = replies_to_top_posts
    snap["query_hits"] = [
        _post_to_fact(p, counts, comment_context) for p in (query_hits or [])
    ]
    return snap


def _format_facts_pack(snapshot: Dict[str, Any], *, max_chars: int = 3500) -> str:
    if not isinstance(snapshot, dict):
        return ""
    parts: List[str] = []
    parts.append("FACTS PACK (ground truth from the experiment DB)")

    terms = snapshot.get("query_terms") or []
    if isinstance(terms, list) and terms:
        parts.append(
            "Query terms: " + ", ".join([str(t) for t in terms[:8] if str(t).strip()])
        )
    query_ids = snapshot.get("query_id_filters") or {}
    if isinstance(query_ids, dict):
        tids = query_ids.get("thread_ids") or []
        pids = query_ids.get("post_ids") or []
        cids = query_ids.get("comment_ids") or []
        if tids or pids or cids:
            parts.append(
                "Query ids: "
                f"thread_ids={tids if tids else []}, "
                f"post_ids={pids if pids else []}, "
                f"comment_ids={cids if cids else []}"
            )

    def _fmt_posts(label: str, posts: Any, *, limit: int):
        parts.append(f"\n{label}:")
        if not isinstance(posts, list) or not posts:
            parts.append("- (none)")
            return
        for p in posts[:limit]:
            if not isinstance(p, dict):
                continue
            pid = p.get("post_id")
            tr = p.get("thread_root_id")
            ct = p.get("comment_to")
            rd = p.get("round")
            likes = p.get("likes")
            dislikes = p.get("dislikes")
            rc = p.get("reaction_count")
            txt = (p.get("text") or "").strip()
            parent_username = p.get("parent_username")
            parent_user_id = p.get("parent_user_id")
            parent_post_id = p.get("parent_post_id")
            op_username = p.get("thread_op_username")
            op_user_id = p.get("thread_op_user_id")
            op_post_id = p.get("thread_op_post_id")
            parent_text = (p.get("parent_text") or "").strip()
            op_text = (p.get("thread_op_text") or "").strip()
            parts.append(
                f"- post_id={pid} thread_root_id={tr} comment_to={ct} round={rd} "
                f"likes={likes} dislikes={dislikes} reactions={rc}: {txt}"
            )
            if parent_post_id is not None or op_post_id is not None:
                parent_label = (
                    f"@{parent_username}"
                    if parent_username
                    else f"user_id={parent_user_id}"
                )
                op_label = f"@{op_username}" if op_username else f"user_id={op_user_id}"
                parts.append(
                    f"  reply_target: parent_post_id={parent_post_id} parent={parent_label} "
                    f"thread_op_post_id={op_post_id} thread_op={op_label}"
                )
                if parent_text:
                    parts.append(f"  parent_text: {parent_text}")
                elif op_text:
                    parts.append(f"  thread_op_text: {op_text}")

    _fmt_posts("Top threads you started", snapshot.get("top_posts"), limit=3)
    _fmt_posts("Recent posts you made", snapshot.get("recent_root_posts"), limit=5)
    _fmt_posts("Recent comments you made", snapshot.get("recent_comments"), limit=5)

    def _fmt_seen_replies(label: str, rows: Any, *, limit: int):
        parts.append(f"\n{label}:")
        if not isinstance(rows, list) or not rows:
            parts.append("- (none)")
            return
        for c in rows[:limit]:
            if not isinstance(c, dict):
                continue
            pid = c.get("post_id")
            tr = c.get("thread_root_id")
            rd = c.get("round")
            seen_rc = int(c.get("seen_reply_count") or 0)
            total_rc = int(c.get("total_reply_count") or 0)
            txt = (c.get("text") or "").strip()
            parts.append(
                f"- post_id={pid} thread_root_id={tr} round={rd} "
                f"seen_replies={seen_rc} total_replies={total_rc}: {txt}"
            )
            exs = c.get("seen_reply_examples")
            if isinstance(exs, list) and exs:
                for ex in exs[:2]:
                    if not isinstance(ex, dict):
                        continue
                    who = ex.get("username") or f"user_id={ex.get('user_id')}"
                    via = ex.get("seen_via") or []
                    via_s = (
                        ",".join([str(v) for v in via if str(v).strip()])
                        if isinstance(via, list)
                        else ""
                    )
                    parts.append(
                        f"  - by @{who} reply_post_id={ex.get('reply_post_id')} "
                        f"round={ex.get('round')} seen_via={via_s}: {ex.get('text')}"
                    )

    _fmt_seen_replies(
        "Replies you've seen to your top threads",
        snapshot.get("replies_to_top_posts"),
        limit=3,
    )
    _fmt_seen_replies(
        "Replies you've seen to your recent comments",
        snapshot.get("replies_to_recent_comments"),
        limit=5,
    )

    _fmt_posts(
        "Your posts/comments matching the admin's question",
        snapshot.get("query_hits"),
        limit=5,
    )

    out = "\n".join([p for p in parts if p is not None]).strip()
    if len(out) <= max_chars:
        return out
    return out[: max_chars - 3].rstrip() + "..."


def _build_evidence_guard(
    *,
    facts_snapshot: Dict[str, Any],
    memory_snapshot: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    facts = facts_snapshot if isinstance(facts_snapshot, dict) else {}
    mem = memory_snapshot if isinstance(memory_snapshot, dict) else {}

    query_hits = facts.get("query_hits")
    if not isinstance(query_hits, list):
        query_hits = []
    try:
        query_hits_viable_n = int(facts.get("query_hits_viable_count") or 0)
    except Exception:
        query_hits_viable_n = 0

    def _safe_len(key: str) -> int:
        v = facts.get(key)
        return len(v) if isinstance(v, list) else 0

    top_posts_n = _safe_len("top_posts")
    recent_comments_n = _safe_len("recent_comments")
    seen_replies_top_n = _safe_len("replies_to_top_posts")
    seen_replies_recent_n = _safe_len("replies_to_recent_comments")
    query_hits_n = len(query_hits)

    retrieval_meta = mem.get("retrieval_meta")
    if not isinstance(retrieval_meta, dict):
        retrieval_meta = {}

    try:
        memory_returned_k = int(retrieval_meta.get("returned_k") or 0)
    except Exception:
        memory_returned_k = 0
    memory_degraded = bool(retrieval_meta.get("degraded_mode", False))

    has_direct_activity_evidence = bool(top_posts_n > 0 or recent_comments_n > 0)
    strict_no_inference = bool(
        memory_degraded
        or (
            memory_returned_k <= 0
            and query_hits_viable_n <= 0
            and not has_direct_activity_evidence
        )
    )

    lines = ["EVIDENCE STATUS (for this answer):"]
    lines.append(
        f"- query_hits={query_hits_n}, query_hits_viable={query_hits_viable_n}, "
        f"top_posts={top_posts_n}, recent_comments={recent_comments_n}"
    )
    lines.append(
        f"- seen_replies_top={seen_replies_top_n}, seen_replies_recent={seen_replies_recent_n}"
    )
    lines.append(
        f"- memory_returned_k={memory_returned_k}, memory_degraded={memory_degraded}"
    )
    lines.append(f"- strict_no_inference={strict_no_inference}")
    if strict_no_inference:
        lines.append(
            '- For activity-specific questions, answer "can\'t confirm" unless exact evidence is present.'
        )
        lines.append(
            "- Do not introduce new movie/book titles, usernames, or thread narratives not in evidence."
        )

    meta = {
        "strict_no_inference": strict_no_inference,
        "query_hits": query_hits_n,
        "query_hits_viable": query_hits_viable_n,
        "has_direct_activity_evidence": has_direct_activity_evidence,
        "memory_returned_k": memory_returned_k,
        "memory_degraded_mode": memory_degraded,
    }
    return "\n".join(lines), meta


def _collect_known_record_ids(*objs: Any) -> List[int]:
    ids = set()

    def _walk(obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key.endswith("_id"):
                    try:
                        iv = int(v)
                    except Exception:
                        iv = None
                    if iv is not None and iv > 0:
                        ids.add(iv)
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for o in objs:
        _walk(o)

    return sorted(ids)


def _extract_semantic_candidates(
    *,
    facts_snapshot: Dict[str, Any],
    memory_snapshot: Dict[str, Any],
    max_candidates: int = 2,
) -> List[Dict[str, Any]]:
    facts = facts_snapshot if isinstance(facts_snapshot, dict) else {}
    memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}
    semantic_items = memory.get("semantic_items")
    if not isinstance(semantic_items, list) or not semantic_items:
        return []

    query_terms = []
    for t in facts.get("query_terms") or []:
        ts = str(t or "").strip().lower()
        if ts:
            query_terms.append(ts)

    rows: List[Dict[str, Any]] = []
    for it in semantic_items:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text_humanized") or it.get("text") or "").strip()
        if not text:
            continue
        text_l = text.lower()
        term_hits = 0
        if query_terms:
            term_hits = sum(1 for t in query_terms if len(t) >= 3 and t in text_l)
        try:
            score = float(it.get("score") or 0.0)
        except Exception:
            score = 0.0
        # Keep moderate+ similarity rows or explicit term-overlap rows.
        if term_hits <= 0 and score < 0.33:
            continue
        rows.append(
            {
                "score": score,
                "term_hits": term_hits,
                "round_id": it.get("round_id"),
                "thread_root_id": it.get("thread_root_id"),
                "target_post_id": it.get("target_post_id"),
                "text": _truncate_middle(text, 120),
            }
        )

    rows.sort(
        key=lambda r: (int(r.get("term_hits") or 0), float(r.get("score") or 0.0)),
        reverse=True,
    )
    return rows[: max(1, int(max_candidates))]


def _extract_facts_candidates(
    *, facts_snapshot: Dict[str, Any], max_candidates: int = 2
) -> List[Dict[str, Any]]:
    facts = facts_snapshot if isinstance(facts_snapshot, dict) else {}
    rows = facts.get("query_hits")
    try:
        viable_hits = int(facts.get("query_hits_viable_count") or 0)
    except Exception:
        viable_hits = 0
    if viable_hits <= 0:
        rows = facts.get("recent_root_posts")
    if not isinstance(rows, list) or not rows:
        rows = facts.get("recent_root_posts")
    if not isinstance(rows, list) or not rows:
        rows = facts.get("top_posts")
    if not isinstance(rows, list) or not rows:
        return []
    evals_raw = facts.get("query_hit_evaluations")
    evals_by_pid: Dict[int, Dict[str, Any]] = {}
    if isinstance(evals_raw, list):
        for e in evals_raw:
            if not isinstance(e, dict):
                continue
            try:
                pid = int(e.get("post_id") or 0)
            except Exception:
                pid = 0
            if pid > 0:
                evals_by_pid[pid] = e
    out = []
    for p in rows:
        if not isinstance(p, dict):
            continue
        try:
            pid = int(p.get("post_id") or 0)
        except Exception:
            pid = 0
        if pid <= 0:
            continue
        e = evals_by_pid.get(pid) or {}
        out.append(
            {
                "post_id": pid,
                "thread_root_id": p.get("thread_root_id"),
                "round": p.get("round"),
                "text": _truncate_middle(str(p.get("text") or "").strip(), 120),
                "informative_matches": int(e.get("informative_matches") or 0),
                "score": int(e.get("score") or 0),
            }
        )
    out.sort(
        key=lambda r: (
            int(r.get("informative_matches") or 0),
            int(r.get("score") or 0),
            int(r.get("post_id") or 0),
        ),
        reverse=True,
    )
    return out[: max(1, int(max_candidates))]


def _try_direct_recent_activity_reply(
    *, admin_text: str, facts_snapshot: Dict[str, Any]
) -> Optional[Tuple[str, Dict[str, Any]]]:
    text = (admin_text or "").strip()
    lowered = text.lower()
    if not lowered:
        return None

    if not any(
        token in lowered
        for token in [
            "last tweet",
            "recent tweet",
            "recent tweets",
            "last post",
            "recent post",
            "recent posts",
            "latest post",
            "latest tweet",
            "what did you post",
            "what was your last",
            "what were your recent",
        ]
    ):
        return None

    recent_posts = facts_snapshot.get("recent_root_posts")
    if not isinstance(recent_posts, list):
        recent_posts = []
    recent_posts = [row for row in recent_posts if isinstance(row, dict)]

    if recent_posts:
        if any(
            token in lowered
            for token in ["recent posts", "recent tweets", "what were your recent"]
        ):
            items = []
            for row in recent_posts[:3]:
                snippet = (row.get("text") or "").strip()
                if snippet:
                    items.append(f'- "{snippet}"')
            if items:
                return (
                    "My most recent posts were:\n"
                    + "\n".join(items)
                    + "\nDo you want me to expand on one of them?",
                    {
                        "direct_answer": True,
                        "reason": "recent_root_posts_plural",
                        "candidate_count": len(items),
                    },
                )

        latest = recent_posts[0]
        snippet = (latest.get("text") or "").strip()
        if snippet:
            return (
                f'My most recent post was: "{snippet}" Do you want the previous one too?',
                {
                    "direct_answer": True,
                    "reason": "recent_root_post_singular",
                    "post_id": latest.get("post_id"),
                },
            )

    recent_comments = facts_snapshot.get("recent_comments")
    if not isinstance(recent_comments, list):
        recent_comments = []
    recent_comments = [row for row in recent_comments if isinstance(row, dict)]
    if recent_comments:
        latest = recent_comments[0]
        snippet = (latest.get("text") or "").strip()
        if snippet:
            return (
                "I don't see a recent standalone post in my records, but my latest recorded comment was: "
                f'"{snippet}" Do you want me to look at my recent comments instead?',
                {
                    "direct_answer": True,
                    "reason": "recent_comment_fallback",
                    "post_id": latest.get("post_id"),
                },
            )

    return (
        "I don't see a recent post in my records right now. If you want, I can check my recent comments instead.",
        {"direct_answer": True, "reason": "no_recent_activity_records"},
    )


def _build_retrieval_trace(
    *,
    contextual_query_text: str,
    facts_snapshot: Dict[str, Any],
    memory_snapshot: Dict[str, Any],
    sanitize_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    facts = facts_snapshot if isinstance(facts_snapshot, dict) else {}
    memory = memory_snapshot if isinstance(memory_snapshot, dict) else {}
    retrieval_meta = memory.get("retrieval_meta")
    if not isinstance(retrieval_meta, dict):
        retrieval_meta = {}

    semantic_items = memory.get("semantic_items")
    if not isinstance(semantic_items, list):
        semantic_items = []
    semantic_top_k = []
    for it in semantic_items[:5]:
        if not isinstance(it, dict):
            continue
        try:
            score = float(it.get("score") or 0.0)
        except Exception:
            score = 0.0
        semantic_top_k.append(
            {
                "score": score,
                "item_type": it.get("item_type"),
                "round_id": it.get("round_id"),
                "thread_root_id": it.get("thread_root_id"),
                "target_post_id": it.get("target_post_id"),
                "text": _truncate_middle(
                    str(it.get("text_humanized") or it.get("text") or ""), 120
                ),
            }
        )

    semantic_candidates = _extract_semantic_candidates(
        facts_snapshot=facts,
        memory_snapshot=memory,
        max_candidates=3,
    )

    query_hits = facts.get("query_hits")
    query_hits_count = len(query_hits) if isinstance(query_hits, list) else 0
    try:
        query_hits_viable_count = int(facts.get("query_hits_viable_count") or 0)
    except Exception:
        query_hits_viable_count = 0
    if query_hits_viable_count > 0:
        selected_context_source = "facts_query_hits"
    elif semantic_candidates:
        selected_context_source = "semantic_candidates"
    elif semantic_top_k:
        selected_context_source = "semantic_items_topk"
    else:
        selected_context_source = "none"

    return {
        "contextual_query_text": str(contextual_query_text or "").strip(),
        "query_terms": facts.get("query_terms") or [],
        "query_id_filters": facts.get("query_id_filters") or {},
        "facts_query_hits_count": int(query_hits_count),
        "facts_query_hits_viable_count": int(query_hits_viable_count),
        "query_hit_evaluations": facts.get("query_hit_evaluations") or [],
        "memory_mode_used": memory.get("memory_mode_used"),
        "memory_retrieval_meta": retrieval_meta,
        "semantic_top_k": semantic_top_k,
        "semantic_candidates": semantic_candidates,
        "selected_context_source": selected_context_source,
        "sanitize_reason": (sanitize_meta or {}).get("reason"),
    }
