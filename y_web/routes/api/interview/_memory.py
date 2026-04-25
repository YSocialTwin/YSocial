from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import current_app
from sqlalchemy import desc, func

from y_web import db
from y_web.src.content.avatars import resolve_forum_profile_pic
from y_web.src.models import (
    Admin_users,
    Agent,
    Exps,
    Interests,
    Page,
    Rounds,
    User_interest,
    User_mgmt,
)
from y_web.src.system.path_utils import get_writable_path

from ._blueprint import (
    _INTERVIEW_MEMORY_DEFAULT_QUERY,
    _MEMORY_MODE_LEGACY,
    _MEMORY_MODE_LEGACY_FALLBACK,
    _MEMORY_MODE_SEMANTIC,
)
from ._helpers import (
    _INTERVIEW_MEMORY_EVENTS_TIMEOUTS,
    _INTERVIEW_MEMORY_SEARCH_TIMEOUTS,
    _coerce_experiment_user_id,
    _get_experiment_uid_from_db_name,
    _normalize_memory_mode,
    _truncate_middle,
)
from ._server import (
    _get_latest_experiment_runtime,
    _post_server_json,
    _post_server_json_with_retries,
)


def _resolve_interview_profile_pic(user: User_mgmt, exp: Exps) -> str:
    if not user or not exp:
        return ""
    if str(getattr(exp, "platform_type", "") or "") == "forum":
        return resolve_forum_profile_pic(user, int(getattr(exp, "idexp", 0) or 0))

    username = str(getattr(user, "username", "") or "").strip()
    if not username:
        return ""

    if bool(getattr(user, "is_page", False)):
        page = Page.query.filter_by(name=username).first()
        return getattr(page, "logo", "") if page else ""

    agent = Agent.query.filter_by(name=username).first()
    if agent and getattr(agent, "profile_pic", None):
        return agent.profile_pic

    admin = Admin_users.query.filter_by(username=username).first()
    if admin and getattr(admin, "profile_pic", None):
        return admin.profile_pic
    return ""


def _iter_run_ids_from_server_log(
    exp: Exps,
    *,
    agent_user_id: Optional[int] = None,
    max_bytes: int = 2_000_000,
    max_candidates: int = 12,
) -> List[str]:
    uid = _get_experiment_uid_from_db_name(getattr(exp, "db_name", "") or "")
    if not uid:
        return []

    log_path = get_writable_path(
        os.path.join("y_web", "experiments", uid, "_server.log")
    )
    if not os.path.exists(log_path):
        return []

    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            read_size = min(size, int(max_bytes))
            if read_size <= 0:
                return []
            f.seek(-read_size, os.SEEK_END)
            buf = f.read(read_size)
    except Exception:
        return []

    text = buf.decode("utf-8", errors="ignore")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: List[str] = []
    seen = set()
    for ln in reversed(lines):
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if obj.get("message") != "agent_decision":
            continue
        if agent_user_id is not None:
            try:
                if str(_coerce_experiment_user_id(obj.get("agent_user_id"))) != str(
                    _coerce_experiment_user_id(agent_user_id)
                ):
                    continue
            except Exception:
                continue
        run_id = obj.get("run_id")
        if not isinstance(run_id, str):
            continue
        rid = run_id.strip()
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append(rid)
        if len(out) >= max(1, int(max_candidates)):
            break
    return out


def _probe_run_memory_coverage(
    exp: Exps,
    *,
    run_id: str,
    agent_user_id: int,
    query_text: str = _INTERVIEW_MEMORY_DEFAULT_QUERY,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "run_id": str(run_id or "").strip(),
        "candidate_count": 0,
        "returned_k": 0,
        "ready": 0,
        "degraded_mode": True,
        "ok": False,
    }
    rid = out["run_id"]
    if not rid:
        return out
    try:
        res = _post_server_json_with_retries(
            exp,
            "/memory/search",
            {
                "run_id": rid,
                "agent_user_id": _coerce_experiment_user_id(agent_user_id),
                "query_text": str(query_text or _INTERVIEW_MEMORY_DEFAULT_QUERY),
                "types": ["event", "reflection", "summary"],
                "k": 2,
                "max_chars": 400,
            },
            timeouts_s=(1.6, 2.2),
            require_status_200=True,
        )
    except Exception:
        return out

    if not isinstance(res, dict):
        return out
    rm = res.get("retrieval_meta")
    if not isinstance(rm, dict):
        rm = {}
    emb = rm.get("embedding_status_summary")
    if not isinstance(emb, dict):
        emb = {}
    try:
        out["candidate_count"] = int(rm.get("candidate_count") or 0)
    except Exception:
        out["candidate_count"] = 0
    try:
        out["returned_k"] = int(rm.get("returned_k") or 0)
    except Exception:
        out["returned_k"] = 0
    try:
        out["ready"] = int(emb.get("ready") or 0)
    except Exception:
        out["ready"] = 0
    out["degraded_mode"] = bool(rm.get("degraded_mode", True))
    out["ok"] = True
    return out


def _detect_run_id_from_server_log(
    exp: Exps,
    *,
    agent_user_id: Optional[int] = None,
    probe_memory_coverage: bool = True,
) -> Dict[str, Any]:
    """
    Best-effort run_id discovery from recent logs, preferring runs with memory coverage
    for the selected agent.
    """
    run_ids = _iter_run_ids_from_server_log(exp, agent_user_id=agent_user_id)
    if not run_ids:
        # Fallback: no agent-filtered runs, try global.
        run_ids = _iter_run_ids_from_server_log(exp, agent_user_id=None)
    if not run_ids:
        return {
            "run_id": None,
            "source": "none",
            "selected_reason": "no_run_in_logs",
            "candidates_checked": [],
        }

    candidates_checked: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None
    for rid in run_ids[:6]:
        if agent_user_id is None or not probe_memory_coverage:
            best = {"run_id": rid}
            break
        cov = _probe_run_memory_coverage(
            exp, run_id=rid, agent_user_id=_coerce_experiment_user_id(agent_user_id)
        )
        candidates_checked.append(cov)
        if (
            int(cov.get("returned_k") or 0) > 0
            or int(cov.get("candidate_count") or 0) > 0
        ):
            best = {"run_id": rid, "coverage": cov}
            break

    if best is None:
        best = {"run_id": run_ids[0]}
        return {
            "run_id": str(best["run_id"]),
            "source": "log_scan_latest",
            "selected_reason": "latest_run_no_memory_coverage_signal",
            "candidates_checked": candidates_checked,
        }

    return {
        "run_id": str(best["run_id"]),
        "source": "log_scan_ranked" if probe_memory_coverage else "log_scan_latest",
        "selected_reason": (
            "memory_coverage_positive"
            if best.get("coverage")
            else (
                "latest_agent_run"
                if probe_memory_coverage
                else "latest_agent_run_unprobed"
            )
        ),
        "candidates_checked": candidates_checked,
    }


def _experiment_sqlite_db_path(exp: Exps) -> Optional[Any]:
    from pathlib import Path

    db_uri_main = str(current_app.config.get("SQLALCHEMY_DATABASE_URI", "") or "")
    if db_uri_main.startswith("postgresql"):
        return None
    db_name = str(getattr(exp, "db_name", "") or "").strip()
    if not db_name:
        return None
    return Path(get_writable_path(os.path.join("y_web", db_name)))


def _detect_run_id_from_experiment_db(
    exp: Exps, *, agent_user_id: Optional[int] = None
) -> Dict[str, Any]:
    db_path = _experiment_sqlite_db_path(exp)
    if db_path is None or not db_path.exists():
        return {
            "run_id": None,
            "source": "none",
            "selected_reason": "no_sqlite_experiment_db",
            "candidates_checked": [],
        }

    queries: List[Any] = []
    if agent_user_id is not None:
        queries.extend(
            [
                (
                    "select run_id, count(*) as cnt from memory_items where agent_user_id=? and run_id is not null and trim(run_id) != '' group by run_id order by cnt desc, max(round_id) desc",
                    (_coerce_experiment_user_id(agent_user_id),),
                    "memory_items_by_agent",
                ),
                (
                    "select run_id, count(*) as cnt from memory_interaction_events where actor_user_id=? and run_id is not null and trim(run_id) != '' group by run_id order by cnt desc, max(round_id) desc",
                    (_coerce_experiment_user_id(agent_user_id),),
                    "memory_events_by_actor",
                ),
            ]
        )
    queries.extend(
        [
            (
                "select run_id, count(*) as cnt from memory_items where run_id is not null and trim(run_id) != '' group by run_id order by cnt desc, max(round_id) desc",
                (),
                "memory_items_global",
            ),
            (
                "select run_id, count(*) as cnt from memory_interaction_events where run_id is not null and trim(run_id) != '' group by run_id order by cnt desc, max(round_id) desc",
                (),
                "memory_events_global",
            ),
        ]
    )

    checked: List[Dict[str, Any]] = []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            for sql, params, source in queries:
                try:
                    rows = cur.execute(sql, params).fetchall()
                except Exception as exc:
                    checked.append({"source": source, "error": str(exc)})
                    continue
                if rows:
                    rid = str(rows[0][0] or "").strip()
                    checked.append(
                        {
                            "source": source,
                            "candidate_run_id": rid,
                            "candidate_count": int(rows[0][1] or 0),
                        }
                    )
                    if rid:
                        return {
                            "run_id": rid,
                            "source": source,
                            "selected_reason": "sqlite_memory_rows_present",
                            "candidates_checked": checked,
                        }
                else:
                    checked.append({"source": source, "candidate_count": 0})
        finally:
            conn.close()
    except Exception as exc:
        return {
            "run_id": None,
            "source": "none",
            "selected_reason": f"sqlite_probe_failed:{exc}",
            "candidates_checked": checked,
        }

    return {
        "run_id": None,
        "source": "none",
        "selected_reason": "no_memory_run_in_db",
        "candidates_checked": checked,
    }


def _get_current_round_id() -> int:
    try:
        rid = db.session.query(func.max(Rounds.id)).scalar()
        return int(rid or 0)
    except Exception:
        return 0


def _get_top_interests_for_user(
    user_id: Any, *, window_rounds: int = 50, limit: int = 10
) -> List[str]:
    cur = _get_current_round_id()
    base = max(0, cur - int(window_rounds))
    normalized_user_id = _coerce_experiment_user_id(user_id)

    try:
        q = (
            db.session.query(
                User_interest.interest_id,
                Interests.interest,
                func.count(User_interest.interest_id).label("cnt"),
            )
            .join(Interests, User_interest.interest_id == Interests.iid)
            .filter(
                User_interest.user_id == normalized_user_id,
                User_interest.round_id >= int(base),
                User_interest.round_id <= int(cur),
            )
            .group_by(User_interest.interest_id, Interests.interest)
            .order_by(desc(func.count(User_interest.interest_id)))
            .limit(int(limit))
        )
        return [row.interest for row in q.all() if getattr(row, "interest", None)]
    except Exception:
        return []


def _build_persona_snapshot(user: User_mgmt, interests: List[str], exp: Exps) -> str:
    vibe = (getattr(exp, "exp_descr", "") or "").strip()
    if not vibe and getattr(exp, "platform_type", "") == "forum":
        vibe = (
            "casual fun subreddit; stay on-topic; short replies; "
            "avoid unrelated politics/history unless the thread explicitly calls for it"
        )

    def _s(v: Any, default: str = "") -> str:
        if v is None:
            return default
        s = str(v).strip()
        return s if s else default

    interest_str = ", ".join([i for i in (interests or []) if str(i).strip()])
    if not interest_str:
        interest_str = "none"

    lines = [
        f"Name: {_s(getattr(user, 'username', ''), 'unknown')}",
        f"Age: {_s(getattr(user, 'age', ''), 'unknown')}",
        f"Gender: {_s(getattr(user, 'gender', ''), 'unknown')}",
        f"Nationality: {_s(getattr(user, 'nationality', ''), 'unknown')}",
        f"Profession: {_s(getattr(user, 'profession', ''), 'unknown')}",
        f"Education: {_s(getattr(user, 'education_level', ''), 'unknown')}",
        f"Political leaning: {_s(getattr(user, 'leaning', ''), 'neutral')}",
        f"Personality (Big Five): oe={_s(getattr(user, 'oe', ''), 'n/a')}, co={_s(getattr(user, 'co', ''), 'n/a')}, ex={_s(getattr(user, 'ex', ''), 'n/a')}, ag={_s(getattr(user, 'ag', ''), 'n/a')}, ne={_s(getattr(user, 'ne', ''), 'n/a')}",
        f"Interests: {interest_str}",
        f"Language: {_s(getattr(user, 'language', ''), 'en')}",
        f"Toxicity: {_s(getattr(user, 'toxicity', ''), 'no')}",
    ]
    if vibe:
        lines.append(f"Community vibe: {vibe}")

    return "\n".join(lines)


def _default_memory_query(query_text: Optional[str]) -> str:
    q = (query_text or "").strip()
    return q if q else _INTERVIEW_MEMORY_DEFAULT_QUERY


def _extract_requested_memory_mode(raw_snapshot: Any) -> str:
    snap = raw_snapshot
    if isinstance(raw_snapshot, str):
        try:
            snap = json.loads(raw_snapshot or "{}")
        except Exception:
            snap = {}
    if not isinstance(snap, dict):
        snap = {}
    return _normalize_memory_mode(snap.get("memory_mode_requested"))


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    try:
        s = str(value).strip().lower()
    except Exception:
        return bool(default)
    if not s:
        return bool(default)
    return s in {"1", "true", "yes", "on", "y"}


def _interview_debug_enabled(payload: Optional[Dict[str, Any]] = None) -> bool:
    p = payload if isinstance(payload, dict) else {}
    if _as_bool(p.get("debug"), False):
        return True
    return _as_bool(os.environ.get("INTERVIEW_DEBUG_TRACE"), False)


def _build_memory_snapshot_legacy(
    exp: Exps, *, run_id: Optional[str], agent_user_id: int
) -> Dict[str, Any]:
    snap: Dict[str, Any] = {
        "run_id": run_id,
        "agent_user_id": _coerce_experiment_user_id(agent_user_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if not run_id:
        snap["error"] = "run_id_missing"
        return snap

    ctx = None
    events_payload = None
    try:
        ctx = _post_server_json(
            exp,
            "/memory/get_context",
            {
                "run_id": run_id,
                "agent_user_id": _coerce_experiment_user_id(agent_user_id),
            },
            timeout_s=3.0,
        )
    except Exception as exc:
        snap["error"] = f"context_fetch_failed: {exc}"

    try:
        events_payload = _post_server_json_with_retries(
            exp,
            "/memory/events_recent",
            {"run_id": run_id, "limit": 200},
            timeouts_s=_INTERVIEW_MEMORY_EVENTS_TIMEOUTS,
        )
    except Exception as exc:
        snap["error"] = f"events_fetch_failed: {exc}"

    if isinstance(ctx, dict):
        snap["community_digest"] = ctx.get("community_digest")

    events = []
    if isinstance(events_payload, dict):
        raw_events = events_payload.get("events")
        if isinstance(raw_events, list):
            events = [e for e in raw_events if isinstance(e, dict)]

    # Keep a small tail for debugging.
    snap["recent_events_tail"] = events[-50:]

    relevant = []
    for ev in events:
        try:
            actor = ev.get("actor_user_id")
            target = ev.get("target_user_id")
            if actor == agent_user_id or target == agent_user_id:
                relevant.append(ev)
        except Exception:
            continue

    # Agent-focused tail for grounding interview answers (avoid mixing in other users' events).
    snap["agent_events_tail"] = relevant[-30:]

    # Relationships: pick top counterpart user_ids by count, then recency.
    pair_counts: Dict[int, int] = {}
    pair_last_round: Dict[int, int] = {}
    for ev in relevant:
        other = None
        try:
            actor = ev.get("actor_user_id")
            target = ev.get("target_user_id")
            rid = int(ev.get("round_id") or 0)
            if actor == agent_user_id and target is not None:
                other = int(target)
            elif target == agent_user_id and actor is not None:
                other = int(actor)
        except Exception:
            other = None
        if other is None:
            continue
        pair_counts[other] = pair_counts.get(other, 0) + 1
        pair_last_round[other] = max(pair_last_round.get(other, 0), rid)

    other_ids = sorted(
        pair_counts.keys(),
        key=lambda oid: (pair_counts.get(oid, 0), pair_last_round.get(oid, 0)),
        reverse=True,
    )[:5]

    relationships = []
    for other_id in other_ids:
        other_username = None
        try:
            u = User_mgmt.query.get(int(other_id))
            other_username = getattr(u, "username", None) if u else None
        except Exception:
            other_username = None

        other_ctx = None
        try:
            other_ctx = _post_server_json(
                exp,
                "/memory/get_context",
                {
                    "run_id": run_id,
                    "agent_user_id": _coerce_experiment_user_id(agent_user_id),
                    "other_user_id": int(other_id),
                    "pair_limit": 8,
                },
                timeout_s=3.0,
            )
        except Exception:
            other_ctx = None

        relationships.append(
            {
                "other_user_id": int(other_id),
                "other_username": other_username,
                "social_card": (
                    other_ctx.get("social_card")
                    if isinstance(other_ctx, dict)
                    else None
                ),
                "recent_pair_events": (
                    other_ctx.get("recent_pair_events")
                    if isinstance(other_ctx, dict)
                    else None
                ),
            }
        )

    # Threads: pick recent distinct threads the agent interacted in.
    thread_ids: List[int] = []
    seen = set()
    for ev in reversed(relevant):
        tr = ev.get("thread_root_id")
        if tr is None:
            continue
        try:
            tr_i = int(tr)
        except Exception:
            continue
        if tr_i in seen:
            continue
        seen.add(tr_i)
        thread_ids.append(tr_i)
        if len(thread_ids) >= 3:
            break

    threads = []
    for thread_root_id in thread_ids:
        tctx = None
        try:
            tctx = _post_server_json(
                exp,
                "/memory/get_context",
                {
                    "run_id": run_id,
                    "agent_user_id": _coerce_experiment_user_id(agent_user_id),
                    "thread_root_id": int(thread_root_id),
                },
                timeout_s=3.0,
            )
        except Exception:
            tctx = None

        threads.append(
            {
                "thread_root_id": int(thread_root_id),
                "thread_card": (
                    tctx.get("thread_card") if isinstance(tctx, dict) else None
                ),
            }
        )

    snap["relationships"] = relationships
    snap["threads"] = threads
    return snap


def _build_memory_snapshot_semantic(
    exp: Exps,
    *,
    run_id: Optional[str],
    agent_user_id: int,
    query_text: Optional[str] = None,
    k: int = 12,
    max_chars: int = 1800,
    time_window_rounds: int = 250,
) -> Dict[str, Any]:
    snap: Dict[str, Any] = {
        "run_id": run_id,
        "agent_user_id": _coerce_experiment_user_id(agent_user_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "query_text": _default_memory_query(query_text),
        "relationships": [],
        "threads": [],
        "recent_events_tail": [],
        "agent_events_tail": [],
    }
    if not run_id:
        raise RuntimeError("run_id_missing")

    search_payload = {
        "run_id": run_id,
        "agent_user_id": _coerce_experiment_user_id(agent_user_id),
        "query_text": _default_memory_query(query_text),
        "types": ["event", "reflection", "summary"],
        "k": int(k),
        "max_chars": int(max_chars),
        "time_window_rounds": int(time_window_rounds),
        "include_evidence_tail": True,
    }
    search = _post_server_json_with_retries(
        exp,
        "/memory/search",
        search_payload,
        timeouts_s=_INTERVIEW_MEMORY_SEARCH_TIMEOUTS,
        require_status_200=True,
    )

    # Keep digest continuity in interview displays while moving retrieval to semantic search.
    try:
        ctx = _post_server_json(
            exp,
            "/memory/get_context",
            {
                "run_id": run_id,
                "agent_user_id": _coerce_experiment_user_id(agent_user_id),
            },
            timeout_s=3.0,
        )
    except Exception:
        ctx = None
    if isinstance(ctx, dict):
        snap["community_digest"] = ctx.get("community_digest")

    items = search.get("items")
    if not isinstance(items, list):
        items = []

    retrieval_meta = search.get("retrieval_meta")
    if not isinstance(retrieval_meta, dict):
        retrieval_meta = {}

    snap["memory_brief"] = str(search.get("memory_brief") or "").strip()
    snap["semantic_items"] = [it for it in items if isinstance(it, dict)]
    snap["retrieval_meta"] = retrieval_meta
    return snap


def _build_deferred_memory_snapshot(
    *,
    run_id: Optional[str],
    agent_user_id: int,
    memory_mode: Optional[str] = None,
    reason: str = "deferred_until_refresh",
) -> Dict[str, Any]:
    requested_mode = _normalize_memory_mode(memory_mode)
    return {
        "run_id": run_id,
        "agent_user_id": _coerce_experiment_user_id(agent_user_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "memory_mode_requested": requested_mode,
        "memory_mode_used": "",
        "load_state": "deferred",
        "deferred_reason": str(reason or "deferred_until_refresh"),
        "relationships": [],
        "threads": [],
        "recent_events_tail": [],
        "agent_events_tail": [],
    }


def _memory_snapshot_has_structured_content(snapshot: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(snapshot, dict):
        return False
    for key in (
        "semantic_items",
        "relationships",
        "threads",
        "agent_events_tail",
        "recent_events_tail",
        "retrieval_meta",
        "community_digest",
        "memory_brief",
    ):
        value = snapshot.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _build_memory_snapshot(
    exp: Exps,
    *,
    run_id: Optional[str],
    agent_user_id: int,
    memory_mode: Optional[str] = None,
    query_text: Optional[str] = None,
) -> Dict[str, Any]:
    requested_mode = _normalize_memory_mode(memory_mode)
    if requested_mode == _MEMORY_MODE_LEGACY:
        legacy = _build_memory_snapshot_legacy(
            exp, run_id=run_id, agent_user_id=agent_user_id
        )
        legacy["memory_mode_requested"] = requested_mode
        legacy["memory_mode_used"] = _MEMORY_MODE_LEGACY
        return legacy

    try:
        semantic = _build_memory_snapshot_semantic(
            exp,
            run_id=run_id,
            agent_user_id=agent_user_id,
            query_text=query_text,
        )
        semantic["memory_mode_requested"] = requested_mode
        semantic["memory_mode_used"] = _MEMORY_MODE_SEMANTIC
        return semantic
    except Exception as exc:
        legacy = _build_memory_snapshot_legacy(
            exp, run_id=run_id, agent_user_id=agent_user_id
        )
        legacy["memory_mode_requested"] = requested_mode
        legacy["memory_mode_used"] = _MEMORY_MODE_LEGACY_FALLBACK
        legacy["fallback_reason"] = str(exc)
        return legacy


def _format_memory_pack(snapshot: Dict[str, Any], *, max_chars: int = 4500) -> str:
    if not isinstance(snapshot, dict):
        return ""

    run_id = snapshot.get("run_id")
    memory_mode_used = str(snapshot.get("memory_mode_used") or "").strip().lower()
    parts: List[str] = []
    parts.append(f"MEMORY PACK (run_id={run_id})")
    if memory_mode_used:
        parts.append(f"mode={memory_mode_used}")

    digest = snapshot.get("community_digest") or {}
    if isinstance(digest, dict) and (digest.get("digest_text") or ""):
        parts.append("\nCOMMUNITY DIGEST:")
        parts.append(str(digest.get("digest_text") or "").strip())

    memory_brief = (snapshot.get("memory_brief") or "").strip()
    semantic_items = snapshot.get("semantic_items")
    if memory_brief:
        parts.append("\nMEMORY SEARCH BRIEF:")
        parts.append(memory_brief)

    retrieval_meta = snapshot.get("retrieval_meta")
    if not isinstance(retrieval_meta, dict):
        retrieval_meta = {}

    def _clean_username(raw: Any) -> str:
        try:
            out = str(raw or "").strip().lstrip("@")
        except Exception:
            out = ""
        return out

    if isinstance(semantic_items, list) and semantic_items:
        parts.append("\nTOP RETRIEVED MEMORIES:")
        for it in semantic_items[:10]:
            if not isinstance(it, dict):
                continue
            item_type = str(it.get("item_type") or "item").strip()
            round_id = it.get("round_id")
            score = it.get("score")
            try:
                score_s = f"{float(score):.2f}"
            except Exception:
                score_s = "?"
            text = _truncate_middle(
                str(it.get("text_humanized") or it.get("text") or "").strip(), 260
            )
            support_ids = it.get("supporting_event_ids")
            target_user_id = it.get("target_user_id")
            target_username = _clean_username(
                it.get("target_username") or it.get("other_username")
            )
            target_post_id = it.get("target_post_id")
            actor_user_id = it.get("actor_user_id")
            actor_username = _clean_username(it.get("actor_username"))
            actor_post_id = it.get("actor_post_id")
            thread_root_id = it.get("thread_root_id")
            id_bits = []
            if target_username:
                id_bits.append(f"target=@{target_username}")
            elif target_user_id is not None:
                id_bits.append(f"target_user_id={target_user_id}")
            if target_post_id is not None:
                id_bits.append(f"target_post_id={target_post_id}")
            if actor_username:
                id_bits.append(f"actor=@{actor_username}")
            elif actor_user_id is not None:
                id_bits.append(f"actor_user_id={actor_user_id}")
            if actor_post_id is not None:
                id_bits.append(f"actor_post_id={actor_post_id}")
            if thread_root_id is not None:
                id_bits.append(f"thread_root_id={thread_root_id}")
            ids_s = (" " + " ".join(id_bits)) if id_bits else ""
            if isinstance(support_ids, list) and support_ids:
                sid = ", ".join([str(x) for x in support_ids[:4]])
                parts.append(
                    f"- [{item_type}] round={round_id} score={score_s}{ids_s} supports={sid}: {text}"
                )
            else:
                parts.append(
                    f"- [{item_type}] round={round_id} score={score_s}{ids_s}: {text}"
                )

    if retrieval_meta:
        returned_k = retrieval_meta.get("returned_k")
        degraded_mode = retrieval_meta.get("degraded_mode")
        candidate_count = retrieval_meta.get("candidate_count")
        parts.append(
            "\nMEMORY RETRIEVAL META:\n"
            f"- candidate_count={candidate_count}, returned_k={returned_k}, degraded_mode={degraded_mode}"
        )
        try:
            returned_k_int = int(returned_k or 0)
        except Exception:
            returned_k_int = 0
        if bool(degraded_mode) or returned_k_int <= 0:
            parts.append(
                "- Reliability warning: memory retrieval is weak for this query."
            )
            parts.append(
                "- Do not infer specific prior interactions from memory alone."
            )

    # Keep legacy rendering for backward compatibility and semantic fallback mode.
    rels = snapshot.get("relationships")
    if isinstance(rels, list) and rels:
        parts.append("\nRELATIONSHIPS (top):")
        for r in rels[:5]:
            if not isinstance(r, dict):
                continue
            other_username = _clean_username(r.get("other_username"))
            if other_username:
                other = f"@{other_username}"
            else:
                other = f"user_id={r.get('other_user_id')}"
            sc = r.get("social_card") or {}
            if isinstance(sc, dict):
                vals = []
                for k in [
                    "affinity",
                    "conflict",
                    "humor",
                    "trust",
                    "last_relation_label",
                ]:
                    if k in sc and sc.get(k) is not None:
                        vals.append(f"{k}={sc.get(k)}")
                summary = (sc.get("summary_text") or "").strip()
                parts.append(f"- {other}: " + (", ".join(vals) if vals else ""))
                if summary:
                    parts.append(f"  summary: {summary}")
                ev_tail = sc.get("evidence_tail")
                if ev_tail:
                    try:
                        if isinstance(ev_tail, str):
                            ev_tail_str = ev_tail.strip()
                        else:
                            ev_tail_str = json.dumps(ev_tail)
                    except Exception:
                        ev_tail_str = str(ev_tail)
                    ev_tail_str = (ev_tail_str or "").strip()
                    if ev_tail_str:
                        parts.append(f"  evidence_tail: {ev_tail_str[:600]}")
            evs = r.get("recent_pair_events")
            if isinstance(evs, list) and evs:
                parts.append("  recent interactions:")
                for ev in evs[-5:]:
                    if not isinstance(ev, dict):
                        continue
                    actor_uname = _clean_username(ev.get("actor_username"))
                    target_uname = _clean_username(ev.get("target_username"))
                    if actor_uname or target_uname:
                        actor_target = f" actor=@{actor_uname or 'user'} target=@{target_uname or 'user'}"
                    else:
                        actor_target = ""
                    parts.append(
                        f"  - round {ev.get('round_id')}: {ev.get('event_type')} "
                        f"relation={ev.get('relation_label')} tone={ev.get('tone_label')}{actor_target} "
                        f"thread_root_id={ev.get('thread_root_id')} target_post_id={ev.get('target_post_id')} "
                        f"claim={ev.get('salient_claim')}"
                    )

    threads = snapshot.get("threads")
    if isinstance(threads, list) and threads:
        parts.append("\nRECENT THREADS:")
        for t in threads[:3]:
            if not isinstance(t, dict):
                continue
            tid = t.get("thread_root_id")
            tc = t.get("thread_card") or {}
            if not isinstance(tc, dict):
                tc = {}
            gist = (tc.get("gist_text") or "").strip()
            my_role = (tc.get("my_role") or "").strip()
            participants_top = tc.get("participants_top")
            entry_points = tc.get("entry_points")
            last_seen_round_id = tc.get("last_seen_round_id")

            try:
                if isinstance(participants_top, str):
                    participants_top_str = participants_top.strip()
                else:
                    participants_top_str = (
                        json.dumps(participants_top)
                        if participants_top is not None
                        else ""
                    )
            except Exception:
                participants_top_str = str(participants_top or "")

            try:
                if isinstance(entry_points, str):
                    entry_points_str = entry_points.strip()
                else:
                    entry_points_str = (
                        json.dumps(entry_points) if entry_points is not None else ""
                    )
            except Exception:
                entry_points_str = str(entry_points or "")

            parts.append(f"- thread_root_id={tid}: {gist}")
            if my_role:
                parts.append(f"  my_role: {my_role}")
            if participants_top_str.strip():
                parts.append(
                    f"  participants_top: {participants_top_str.strip()[:400]}"
                )
            if entry_points_str.strip():
                parts.append(f"  entry_points: {entry_points_str.strip()[:200]}")
            if last_seen_round_id is not None:
                parts.append(f"  last_seen_round_id: {last_seen_round_id}")

    ev_tail = snapshot.get("agent_events_tail")
    if isinstance(ev_tail, list) and ev_tail:
        parts.append("\nRECENT EVENTS (agent-related tail):")
        for ev in ev_tail[-15:]:
            if not isinstance(ev, dict):
                continue
            claim = (ev.get("salient_claim") or "").strip()
            if claim and len(claim) > 160:
                claim = claim[:157].rstrip() + "..."
            parts.append(
                f"- r{ev.get('round_id')}: {ev.get('event_type')} "
                f"relation={ev.get('relation_label')} tone={ev.get('tone_label')} "
                f"thread_root_id={ev.get('thread_root_id')} target_post_id={ev.get('target_post_id')} "
                f"claim={claim}"
            )

    out = "\n".join([p for p in parts if p is not None])
    out = out.strip()
    if len(out) <= max_chars:
        return out
    return out[: max_chars - 3].rstrip() + "..."


_INTERVIEW_TERM_STOPWORDS = {
    "a",
    "about",
    "after",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "comment",
    "commented",
    "comments",
    "did",
    "do",
    "does",
    "for",
    "from",
    "have",
    "hi",
    "i",
    "in",
    "is",
    "it",
    "like",
    "make",
    "made",
    "me",
    "my",
    "more",
    "no",
    "not",
    "of",
    "on",
    "or",
    "post",
    "posted",
    "posts",
    "recently",
    "reply",
    "replied",
    "replies",
    "remember",
    "the",
    "their",
    "thread",
    "threads",
    "to",
    "upvote",
    "upvoted",
    "upvotes",
    "what",
    "was",
    "who",
    "which",
    "with",
    "one",
    "tell",
    "you",
    "your",
    "yourself",
    "yes",
}

_INTERVIEW_QUERY_TERM_ALIASES: Dict[str, List[str]] = {
    # Common shorthand that often misses direct lexical matching in posts.
    "dnd": ["d&d", "dungeons and dragons", "dungeons", "dragons", "tabletop"],
    "d&d": ["dungeons and dragons", "dnd", "tabletop"],
}

_INTERVIEW_WEAK_QUERY_TERMS = {
    "new",
    "last",
    "latest",
    "lately",
    "latetly",
    "recent",
    "recently",
    "help",
    "girl",
    "guy",
    "post",
    "posted",
    "tweet",
    "tweets",
    "comment",
    "commented",
    "thread",
    "threads",
    "out",
}
