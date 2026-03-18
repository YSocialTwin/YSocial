from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import case, desc, func, or_

from y_web import db
from y_web.models import (
    Admin_users,
    AdminInterviewMessage,
    AdminInterviewSession,
    Client,
    Exps,
    Interests,
    Post,
    Reactions,
    ReplyInboxState,
    Rounds,
    User_interest,
    User_mgmt,
)
from y_web.utils.path_utils import get_writable_path

api_interview = Blueprint("api_interview", __name__, url_prefix="/api/interview")
_Y_WEB_DIR = Path(__file__).resolve().parents[1]

_MEMORY_MODE_LEGACY = "legacy"
_MEMORY_MODE_SEMANTIC = "semantic"
_MEMORY_MODE_LEGACY_FALLBACK = "legacy_fallback"
_INTERVIEW_MEMORY_MODE_DEFAULT = (
    os.environ.get("INTERVIEW_MEMORY_MODE_DEFAULT", _MEMORY_MODE_SEMANTIC)
    .strip()
    .lower()
)
if _INTERVIEW_MEMORY_MODE_DEFAULT not in {_MEMORY_MODE_LEGACY, _MEMORY_MODE_SEMANTIC}:
    _INTERVIEW_MEMORY_MODE_DEFAULT = _MEMORY_MODE_SEMANTIC
_INTERVIEW_MEMORY_DEFAULT_QUERY = "Most important recent memories, relationships, norms, and ongoing threads for this agent."


def _get_experiment_uid_from_db_name(db_name: str) -> Optional[str]:
    """Extract the experiment UID from SQLite/PostgreSQL experiment db names."""
    if not db_name:
        return None
    if db_name.startswith("experiments_"):
        return db_name.replace("experiments_", "")
    if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
        parts = re.split(r"[/\\\\]", db_name)
        if len(parts) >= 2:
            return parts[1]
    return None


def _parse_timeout_series(
    raw: Optional[str], default: Tuple[float, ...]
) -> Tuple[float, ...]:
    values: List[float] = []
    for part in str(raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            value = float(token)
        except Exception:
            continue
        if value > 0:
            values.append(value)
    return tuple(values) if values else default


_INTERVIEW_MEMORY_EVENTS_TIMEOUTS = _parse_timeout_series(
    os.environ.get("INTERVIEW_MEMORY_EVENTS_TIMEOUTS"),
    (6.0, 12.0, 20.0),
)
_INTERVIEW_MEMORY_SEARCH_TIMEOUTS = _parse_timeout_series(
    os.environ.get("INTERVIEW_MEMORY_SEARCH_TIMEOUTS"),
    (7.0, 15.0, 25.0),
)


def _json_success(data=None, meta=None, status=200):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def _json_error(message: str, status: int = 400, *, code: Optional[str] = None):
    payload = {"success": False, "error": message}
    if code:
        payload["code"] = code
    return jsonify(payload), status


def _require_privileged() -> Optional[Admin_users]:
    username = (getattr(current_user, "username", "") or "").strip()
    if not username:
        return None
    admin_user = Admin_users.query.filter_by(username=username).first()
    if not admin_user or admin_user.role not in {"admin", "researcher"}:
        return None
    return admin_user


def _normalize_llm_base_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"http://{url}"
    if not url.endswith("/v1"):
        url = url.rstrip("/") + "/v1"
    return url


def _safe_json_loads(text: str) -> Optional[dict]:
    try:
        return json.loads(text or "")
    except Exception:
        return None


def _server_base_url(exp: Exps) -> str:
    host = (getattr(exp, "server", "") or "").strip() or "127.0.0.1"
    port = int(getattr(exp, "port", 0) or 0)
    if host.startswith(("http://", "https://")):
        return host.rstrip("/")
    return f"http://{host}:{port}"


def _post_server_json(exp: Exps, path: str, payload: dict, *, timeout_s: float = 4.0):
    base = _server_base_url(exp)
    url = f"{base}{path}"
    resp = requests.post(url, json=payload, timeout=timeout_s)
    return _safe_json_loads(resp.text)


def _post_server_json_with_retries(
    exp: Exps,
    path: str,
    payload: dict,
    *,
    timeouts_s: Tuple[float, ...],
    require_status_200: bool = False,
) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    attempts = max(1, len(timeouts_s))
    for timeout_s in timeouts_s[:attempts]:
        try:
            out = _post_server_json(exp, path, payload, timeout_s=float(timeout_s))
        except Exception as exc:
            last_err = exc
            continue

        if not isinstance(out, dict):
            last_err = RuntimeError(f"{path} invalid response")
            continue

        if require_status_200 and int(out.get("status") or 0) != 200:
            last_err = RuntimeError(f"{path} status={out.get('status')}")
            continue

        return out

    if last_err is not None:
        raise RuntimeError(f"{path} failed after {attempts} attempts: {last_err}")
    raise RuntimeError(f"{path} failed after {attempts} attempts")


def _build_change_db_path_for_exp(exp: Exps) -> str:
    """
    Build payload path expected by YServer /change_db endpoint.

    Mirrors the existing server boot logic so interview mode uses the same DB binding rules.
    """
    db_uri_main = str(current_app.config.get("SQLALCHEMY_DATABASE_URI", "") or "")
    db_type = "postgresql" if db_uri_main.startswith("postgresql") else "sqlite"

    y_web_dir = get_writable_path(os.path.join("y_web"))
    if db_type == "sqlite":
        full_path = os.path.join(y_web_dir, str(getattr(exp, "db_name", "") or ""))
        if len(full_path) > 2 and full_path[1] == ":":
            if len(full_path) > 3 and full_path[2] in ("/", "\\"):
                return full_path[3:].replace("\\", "/")
            return full_path[2:].replace("\\", "/")
        return full_path[1:].replace("\\", "/")

    old_db_name = db_uri_main.split("/")[-1]
    return db_uri_main.replace(
        old_db_name, str(getattr(exp, "db_name", "") or "").strip()
    )


def _ensure_experiment_server_db_binding(exp: Exps) -> Dict[str, Any]:
    """
    Best-effort /change_db call so memory/search is scoped to the selected experiment DB.
    """
    out = {"ok": False, "change_db_url": "", "path": "", "error": ""}
    try:
        path_payload = _build_change_db_path_for_exp(exp)
    except Exception as exc:
        out["error"] = f"build_path_failed:{exc}"
        return out
    out["path"] = path_payload

    base = _server_base_url(exp)
    url = f"{base}/change_db"
    out["change_db_url"] = url
    try:
        resp = requests.post(url, json={"path": path_payload}, timeout=4.0)
        txt = resp.text or ""
        if resp.status_code == 200 and ("status" in txt):
            out["ok"] = True
            return out
        out["error"] = f"status={resp.status_code}"
        return out
    except Exception as exc:
        out["error"] = str(exc)
        return out


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
                if int(obj.get("agent_user_id")) != int(agent_user_id):
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
                "agent_user_id": int(agent_user_id),
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
            exp, run_id=rid, agent_user_id=int(agent_user_id)
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


def _get_current_round_id() -> int:
    try:
        rid = db.session.query(func.max(Rounds.id)).scalar()
        return int(rid or 0)
    except Exception:
        return 0


def _get_top_interests_for_user(
    user_id: int, *, window_rounds: int = 50, limit: int = 10
) -> List[str]:
    cur = _get_current_round_id()
    base = max(0, cur - int(window_rounds))

    try:
        q = (
            db.session.query(
                User_interest.interest_id,
                Interests.interest,
                func.count(User_interest.interest_id).label("cnt"),
            )
            .join(Interests, User_interest.interest_id == Interests.iid)
            .filter(
                User_interest.user_id == int(user_id),
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


def _normalize_memory_mode(mode: Optional[str]) -> str:
    val = str(mode or "").strip().lower()
    if val in {_MEMORY_MODE_LEGACY, _MEMORY_MODE_SEMANTIC}:
        return val
    return _INTERVIEW_MEMORY_MODE_DEFAULT


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
        "agent_user_id": int(agent_user_id),
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
            {"run_id": run_id, "agent_user_id": int(agent_user_id)},
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
                    "agent_user_id": int(agent_user_id),
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
                    "agent_user_id": int(agent_user_id),
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
        "agent_user_id": int(agent_user_id),
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
        "agent_user_id": int(agent_user_id),
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
            {"run_id": run_id, "agent_user_id": int(agent_user_id)},
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
        "agent_user_id": int(agent_user_id),
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
    "comment",
    "commented",
    "thread",
    "threads",
    "out",
}


def _truncate_middle(text: str, max_len: int) -> str:
    s = (text or "").strip()
    if max_len <= 0:
        return ""
    if len(s) <= max_len:
        return s
    keep = max_len - 3
    left = max(0, keep // 2)
    right = max(0, keep - left)
    return (s[:left] + "..." + s[-right:]).strip()


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

    # Extract \"interesting\" tokens: 3+ chars, alpha-numeric.
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


def _build_facts_snapshot(
    *,
    agent_user_id: int,
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
    snap: Dict[str, Any] = {
        "agent_user_id": int(agent_user_id),
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
            st = ReplyInboxState.query.filter_by(user_id=int(agent_user_id)).first()
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
                .filter(Post.user_id != int(agent_user_id))
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
                .filter(Post.user_id != int(agent_user_id))
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
                    .filter(Reactions.user_id == int(agent_user_id))
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
                    .filter(Post.user_id == int(agent_user_id))
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
                    int(getattr(rp, "user_id", 0) or 0)
                    for rp in reply_posts
                    if int(getattr(rp, "user_id", 0) or 0) > 0
                }
            )
            users = (
                User_mgmt.query.filter(User_mgmt.id.in_(author_ids)).all()
                if author_ids
                else []
            )
            author_name_by_id = {
                int(u.id): getattr(u, "username", None) for u in users if u is not None
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
            author_id = int(getattr(rp, "user_id", 0) or 0)
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
                    "user_id": author_id or None,
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
            Post.query.filter(Post.user_id == int(agent_user_id))
            .filter(Post.comment_to == -1)
            .order_by(desc(Post.reaction_count), desc(Post.id))
            .limit(int(top_posts_limit))
        )
        top_posts = q_top.all()
    except Exception:
        top_posts = []

    # Recent comments.
    try:
        q_recent = (
            Post.query.filter(Post.user_id == int(agent_user_id))
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
                    Post.query.filter(Post.user_id == int(agent_user_id))
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
                    Post.query.filter(Post.user_id == int(agent_user_id))
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
                    uid = int(getattr(pp, "user_id", 0) or 0)
                    if uid > 0:
                        user_ids.add(uid)
                except Exception:
                    continue
            for op in op_map.values():
                try:
                    uid = int(getattr(op, "user_id", 0) or 0)
                    if uid > 0:
                        user_ids.add(uid)
                except Exception:
                    continue

            username_by_id: Dict[int, Optional[str]] = {}
            if user_ids:
                users = User_mgmt.query.filter(User_mgmt.id.in_(sorted(user_ids))).all()
                username_by_id = {
                    int(u.id): getattr(u, "username", None)
                    for u in users
                    if u is not None
                }

            for pid, p in comment_posts_by_id.items():
                parent_id = int(getattr(p, "comment_to", -1) or -1)
                thread_root_id = int(getattr(p, "thread_id", 0) or 0)
                parent_post = parent_map.get(parent_id)
                thread_op_post = op_map.get(thread_root_id)

                parent_user_id = (
                    int(getattr(parent_post, "user_id", 0) or 0)
                    if parent_post is not None
                    else None
                )
                if parent_user_id is not None and parent_user_id <= 0:
                    parent_user_id = None

                thread_op_user_id = (
                    int(getattr(thread_op_post, "user_id", 0) or 0)
                    if thread_op_post is not None
                    else None
                )
                if thread_op_user_id is not None and thread_op_user_id <= 0:
                    thread_op_user_id = None

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
    for lst in [top_posts, recent_comments, query_hits]:
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

    strict_no_inference = bool(
        memory_degraded or (memory_returned_k <= 0 and query_hits_viable_n <= 0)
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


def _sanitize_interview_reply(
    reply: str,
    *,
    facts_snapshot: Dict[str, Any],
    memory_snapshot: Dict[str, Any],
    strict_no_inference: bool,
) -> Tuple[str, Dict[str, Any]]:
    text = (reply or "").strip()
    if not text:
        return text, {"sanitized": False, "reason": "empty"}

    known_ids = set(_collect_known_record_ids(facts_snapshot, memory_snapshot))
    claimed_ids = set()
    for m in re.findall(
        r"\b(?:post_id|thread_root_id|comment_to|reply_post_id|parent_post_id|thread_op_post_id)\s*=\s*(\d+)\b",
        text,
        flags=re.IGNORECASE,
    ):
        try:
            v = int(str(m).strip())
        except Exception:
            continue
        if v > 0:
            claimed_ids.add(v)

    unknown_ids = sorted([v for v in claimed_ids if v not in known_ids])
    if unknown_ids:
        fallback = (
            "I can't confirm those specific ids from my records right now. "
            "Can you give me a post_id, thread_root_id, or username to verify?"
        )
        return fallback, {
            "sanitized": True,
            "reason": "unknown_ids",
            "unknown_ids": unknown_ids,
            "known_ids_count": len(known_ids),
        }

    if strict_no_inference:
        lowered = text.lower()
        has_strong_claim = any(
            w in lowered
            for w in [
                "i commented on",
                "i posted about",
                "i replied to",
                "i upvoted",
                "i downvoted",
                "i trust",
                "i first encountered",
            ]
        )
        has_reference = bool(claimed_ids)
        if has_strong_claim and not has_reference:
            semantic_candidates = _extract_semantic_candidates(
                facts_snapshot=facts_snapshot,
                memory_snapshot=memory_snapshot,
                max_candidates=2,
            )
            if semantic_candidates:
                candidate_bits = []
                for c in semantic_candidates:
                    candidate_bits.append(
                        f"\"{c.get('text')}\" (score={float(c.get('score') or 0.0):.2f}, "
                        f"round={c.get('round_id')}, thread_root_id={c.get('thread_root_id')})"
                    )
                fallback = (
                    "I can't confirm one exact post yet, but I found likely matches: "
                    + "; ".join(candidate_bits)
                    + ". Did you mean one of those?"
                )
                return fallback, {
                    "sanitized": True,
                    "reason": "strict_no_inference_semantic_disambiguation",
                    "candidate_count": len(semantic_candidates),
                    "known_ids_count": len(known_ids),
                }
            facts_candidates = _extract_facts_candidates(
                facts_snapshot=facts_snapshot, max_candidates=2
            )
            if facts_candidates:
                candidate_bits = []
                for c in facts_candidates:
                    candidate_bits.append(
                        f"post_id={c.get('post_id')} thread_root_id={c.get('thread_root_id')} "
                        f"round={c.get('round')}: \"{c.get('text')}\""
                    )
                fallback = (
                    "I can't confirm one exact match yet, but these look likely: "
                    + "; ".join(candidate_bits)
                    + ". Did you mean one of these?"
                )
                return fallback, {
                    "sanitized": True,
                    "reason": "strict_no_inference_facts_disambiguation",
                    "candidate_count": len(facts_candidates),
                    "known_ids_count": len(known_ids),
                }
            fallback = (
                "I can't confirm that from my records for this query. "
                "If you can share a little more detail (topic wording, who was involved, or rough timing), "
                "I can narrow it down. If you have it, a post_id or thread_root_id can also help verify."
            )
            return fallback, {
                "sanitized": True,
                "reason": "strict_no_inference_without_ids",
                "known_ids_count": len(known_ids),
            }

    # De-loop explicit-ID requests when semantic candidates exist.
    if (
        "can't confirm" in text.lower()
        and "post_id" in text.lower()
        and "thread_root_id" in text.lower()
    ):
        semantic_candidates = _extract_semantic_candidates(
            facts_snapshot=facts_snapshot,
            memory_snapshot=memory_snapshot,
            max_candidates=2,
        )
        if semantic_candidates:
            candidate_bits = []
            for c in semantic_candidates:
                candidate_bits.append(
                    f"\"{c.get('text')}\" (score={float(c.get('score') or 0.0):.2f}, round={c.get('round_id')})"
                )
            fallback = (
                "I can't confirm one exact post yet, but I found likely matches: "
                + "; ".join(candidate_bits)
                + ". Did you mean one of these?"
            )
            return fallback, {
                "sanitized": True,
                "reason": "semantic_disambiguation_replaced_id_loop",
                "candidate_count": len(semantic_candidates),
                "known_ids_count": len(known_ids),
            }
        facts_candidates = _extract_facts_candidates(
            facts_snapshot=facts_snapshot, max_candidates=2
        )
        if facts_candidates:
            candidate_bits = []
            for c in facts_candidates:
                candidate_bits.append(
                    f"post_id={c.get('post_id')} thread_root_id={c.get('thread_root_id')}: \"{c.get('text')}\""
                )
            fallback = (
                "I can't confirm one exact post yet, but I found likely matches: "
                + "; ".join(candidate_bits)
                + ". Did you mean one of these?"
            )
            return fallback, {
                "sanitized": True,
                "reason": "facts_disambiguation_replaced_id_loop",
                "candidate_count": len(facts_candidates),
                "known_ids_count": len(known_ids),
            }

    return text, {
        "sanitized": False,
        "reason": "pass",
        "known_ids_count": len(known_ids),
    }


def _resolve_llm_backend(
    *,
    backend_mode: str,
    exp: Exps,
    agent_user: User_mgmt,
    admin_user: Admin_users,
) -> Tuple[str, str, str, str, float, int]:
    """
    Return (mode, model, base_url, api_key, temperature, max_tokens) for interview generation.
    """
    mode = (backend_mode or "agent_runtime").strip().lower()
    if mode not in {"agent_runtime", "admin"}:
        mode = "agent_runtime"

    if mode == "admin":
        model = (getattr(admin_user, "llm", "") or "").strip() or "llama3.2:latest"
        base_url = _normalize_llm_base_url(getattr(admin_user, "llm_url", "") or "")
        api_key = "NULL"
        temperature = 0.7
        max_tokens = 450
        return mode, model, base_url, api_key, temperature, max_tokens

    # agent_runtime
    model = (getattr(agent_user, "user_type", "") or "").strip() or "llama3.2:latest"
    base_url = _normalize_llm_base_url(getattr(exp, "llm_default", "") or "")
    api_key = (getattr(exp, "llm_api_key_default", "") or "").strip() or "NULL"
    try:
        temperature = float(getattr(exp, "llm_temperature_default", 0.7) or 0.7)
    except Exception:
        temperature = 0.7
    try:
        max_tokens = int(getattr(exp, "llm_max_tokens_default", 450) or 450)
    except Exception:
        max_tokens = 450

    if not base_url:
        runtime_client = (
            Client.query.filter_by(id_exp=int(exp.idexp))
            .order_by(Client.status.desc(), Client.id.desc())
            .first()
        )
        if runtime_client is not None:
            base_url = _normalize_llm_base_url(getattr(runtime_client, "llm", "") or "")
            api_key = (
                (getattr(runtime_client, "llm_api_key", "") or "").strip() or "NULL"
            )
            try:
                temperature = float(
                    getattr(runtime_client, "llm_temperature", temperature)
                    or temperature
                )
            except Exception:
                pass
            try:
                runtime_max_tokens = getattr(runtime_client, "llm_max_tokens", max_tokens)
                if runtime_max_tokens is not None:
                    max_tokens = int(runtime_max_tokens)
            except Exception:
                pass

    return mode, model, base_url, api_key, temperature, max_tokens


def _generate_reply(
    *,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    system_message: str,
    user_message: str,
) -> str:
    if not base_url:
        raise RuntimeError("LLM base_url not configured")
    if not model:
        raise RuntimeError("LLM model not configured")

    # Import autogen lazily so importing this module doesn't break tooling environments.
    from autogen import AssistantAgent

    cfg = {
        "cache_seed": None,
        "config_list": [
            {
                "model": model,
                "base_url": base_url,
                "timeout": 10000,
                "api_type": "open_ai",
                "api_key": api_key or "NULL",
                "price": [0, 0],
            }
        ],
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }

    agent = AssistantAgent(
        name="interview-agent",
        llm_config=cfg,
        system_message=system_message,
        max_consecutive_auto_reply=1,
    )
    user = AssistantAgent(name="interview-user", max_consecutive_auto_reply=0)

    user.initiate_chat(agent, silent=True, message=user_message)
    try:
        content = agent.chat_messages[user][-1]["content"]
    except Exception:
        content = ""

    return (content or "").strip()


@api_interview.get("/<int:exp_id>/agents")
@login_required
def api_interview_agents(exp_id: int):
    admin_user = _require_privileged()
    if not admin_user:
        return _json_error("Forbidden", 403, code="forbidden")

    # LLM agents register their model name in user_type (anything other than "user").
    try:
        q = (
            User_mgmt.query.filter(User_mgmt.is_page == 0)
            .filter(User_mgmt.user_type != "user")
            .order_by(User_mgmt.id.asc())
        )
        users = q.all()
    except Exception as exc:
        return _json_error(f"Failed to load agents: {exc}", 500, code="db_error")

    data = []
    for u in users:
        data.append(
            {
                "user_id": int(u.id),
                "username": u.username,
                "user_type": getattr(u, "user_type", None),
                "language": getattr(u, "language", None),
                "leaning": getattr(u, "leaning", None),
                "toxicity": getattr(u, "toxicity", None),
                "profession": getattr(u, "profession", None),
            }
        )

    return _json_success(data)


@api_interview.post("/<int:exp_id>/session")
@login_required
def api_interview_create_session(exp_id: int):
    admin_user = _require_privileged()
    if not admin_user:
        return _json_error("Forbidden", 403, code="forbidden")

    payload = request.get_json(silent=True) or {}
    agent_user_id = payload.get("agent_user_id")
    if agent_user_id is None:
        return _json_error("agent_user_id required", 400, code="bad_request")

    try:
        agent_user_id = int(agent_user_id)
    except Exception:
        return _json_error("agent_user_id must be an int", 400, code="bad_request")

    agent_user = User_mgmt.query.get(agent_user_id)
    if not agent_user:
        return _json_error("Agent not found", 404, code="not_found")

    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp:
        return _json_error("Experiment not found", 404, code="not_found")
    db_binding = _ensure_experiment_server_db_binding(exp)

    backend_mode = (payload.get("backend_mode") or "agent_runtime").strip().lower()
    if backend_mode not in {"agent_runtime", "admin"}:
        backend_mode = "agent_runtime"
    memory_mode = _normalize_memory_mode(payload.get("memory_mode"))
    preload_memory = _as_bool(payload.get("preload_memory"), False)

    run_id = (payload.get("run_id") or "").strip() or None
    run_id_source = "override" if run_id else "log_scan"
    run_id_selected_reason = "provided_by_request" if run_id else "pending_log_scan"
    run_id_candidates_checked: List[Dict[str, Any]] = []
    if not run_id:
        run_pick = _detect_run_id_from_server_log(
            exp,
            agent_user_id=int(agent_user_id),
            probe_memory_coverage=preload_memory,
        )
        run_id = str(run_pick.get("run_id") or "").strip() or None
        run_id_source = str(run_pick.get("source") or "log_scan")
        run_id_selected_reason = str(run_pick.get("selected_reason") or "log_scan")
        checked = run_pick.get("candidates_checked")
        if isinstance(checked, list):
            run_id_candidates_checked = [c for c in checked if isinstance(c, dict)]
        if not run_id:
            run_id_source = "none"
            run_id_selected_reason = "no_run_detected"

    interests = _get_top_interests_for_user(agent_user_id)
    persona = _build_persona_snapshot(agent_user, interests, exp)
    if preload_memory:
        memory_snapshot = _build_memory_snapshot(
            exp,
            run_id=run_id,
            agent_user_id=agent_user_id,
            memory_mode=memory_mode,
            query_text=_INTERVIEW_MEMORY_DEFAULT_QUERY,
        )
    else:
        memory_snapshot = _build_deferred_memory_snapshot(
            run_id=run_id,
            agent_user_id=agent_user_id,
            memory_mode=memory_mode,
        )

    mode, model, base_url, _api_key, temperature, max_tokens = _resolve_llm_backend(
        backend_mode=backend_mode,
        exp=exp,
        agent_user=agent_user,
        admin_user=admin_user,
    )

    sess = AdminInterviewSession(
        exp_id=int(exp_id),
        admin_username=getattr(current_user, "username", "") or "",
        agent_user_id=int(agent_user_id),
        agent_username=getattr(agent_user, "username", "") or "",
        run_id=run_id,
        backend_mode=mode,
        llm_model=model,
        llm_base_url=base_url,
        persona_snapshot=persona,
        interests_snapshot_json=json.dumps(interests),
        memory_snapshot_json=json.dumps(memory_snapshot),
    )
    db.session.add(sess)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return _json_error(
            f"Failed to create interview session: {exc}", 500, code="db_error"
        )

    sys_msg = AdminInterviewMessage(
        session_id=sess.id,
        role="system",
        content=(
            f"Interview session started with @{sess.agent_username}. "
            f"run_id={run_id or 'none'} (source={run_id_source}). backend={mode}. "
            f"memory_mode={memory_snapshot.get('memory_mode_used') or memory_mode}."
        ),
        meta_json=json.dumps(
            {
                "run_id_source": run_id_source,
                "run_id_selected_reason": run_id_selected_reason,
                "run_id_candidates_checked": run_id_candidates_checked,
                "memory_preloaded": preload_memory,
                "db_binding": db_binding,
                "memory_mode_requested": memory_mode,
                "memory_mode_used": memory_snapshot.get("memory_mode_used"),
            }
        ),
    )
    db.session.add(sys_msg)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return _json_error(
            f"Session created but failed to write system message: {exc}",
            500,
            code="db_error",
        )

    return _json_success(
        {
            "session_id": int(sess.id),
            "run_id": run_id,
            "run_id_source": run_id_source,
            "run_id_selected_reason": run_id_selected_reason,
            "run_id_candidates_checked": run_id_candidates_checked,
            "db_binding": db_binding,
            "backend_mode": mode,
            "memory_preloaded": preload_memory,
            "memory_mode_requested": memory_snapshot.get(
                "memory_mode_requested", memory_mode
            ),
            "memory_mode_used": memory_snapshot.get("memory_mode_used"),
            "llm_model": model,
            "llm_base_url": base_url,
            "persona_snapshot": persona,
            "interests": interests,
            "memory_snapshot": memory_snapshot,
            "messages": [
                {
                    "id": int(sys_msg.id),
                    "role": sys_msg.role,
                    "content": sys_msg.content,
                }
            ],
        }
    )


@api_interview.get("/<int:exp_id>/session/<int:session_id>")
@login_required
def api_interview_get_session(exp_id: int, session_id: int):
    admin_user = _require_privileged()
    if not admin_user:
        return _json_error("Forbidden", 403, code="forbidden")

    sess = AdminInterviewSession.query.get(int(session_id))
    if not sess or int(sess.exp_id) != int(exp_id):
        return _json_error("Session not found", 404, code="not_found")

    msgs = (
        AdminInterviewMessage.query.filter_by(session_id=int(session_id))
        .order_by(AdminInterviewMessage.id.asc())
        .all()
    )
    messages = [{"id": int(m.id), "role": m.role, "content": m.content} for m in msgs]

    interests = []
    try:
        interests = json.loads(sess.interests_snapshot_json or "[]")
        if not isinstance(interests, list):
            interests = []
    except Exception:
        interests = []

    memory_snapshot = {}
    try:
        memory_snapshot = json.loads(sess.memory_snapshot_json or "{}")
        if not isinstance(memory_snapshot, dict):
            memory_snapshot = {}
    except Exception:
        memory_snapshot = {}

    return _json_success(
        {
            "session_id": int(sess.id),
            "run_id": sess.run_id,
            "backend_mode": sess.backend_mode,
            "memory_mode_requested": memory_snapshot.get(
                "memory_mode_requested", _INTERVIEW_MEMORY_MODE_DEFAULT
            ),
            "memory_mode_used": memory_snapshot.get("memory_mode_used"),
            "llm_model": sess.llm_model,
            "llm_base_url": sess.llm_base_url,
            "persona_snapshot": sess.persona_snapshot,
            "interests": interests,
            "memory_snapshot": memory_snapshot,
            "messages": messages,
        }
    )


@api_interview.post("/<int:exp_id>/session/<int:session_id>/refresh_context")
@login_required
def api_interview_refresh_context(exp_id: int, session_id: int):
    admin_user = _require_privileged()
    if not admin_user:
        return _json_error("Forbidden", 403, code="forbidden")

    sess = AdminInterviewSession.query.get(int(session_id))
    if not sess or int(sess.exp_id) != int(exp_id):
        return _json_error("Session not found", 404, code="not_found")

    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp:
        return _json_error("Experiment not found", 404, code="not_found")
    db_binding = _ensure_experiment_server_db_binding(exp)

    payload = request.get_json(silent=True) or {}
    query_text = (
        payload.get("query_text") or ""
    ).strip() or _INTERVIEW_MEMORY_DEFAULT_QUERY
    memory_mode = _extract_requested_memory_mode(sess.memory_snapshot_json)

    memory_snapshot = _build_memory_snapshot(
        exp,
        run_id=(sess.run_id or "").strip() or None,
        agent_user_id=int(sess.agent_user_id),
        memory_mode=memory_mode,
        query_text=query_text,
    )
    sess.memory_snapshot_json = json.dumps(memory_snapshot)
    db.session.commit()

    return _json_success(
        {
            "memory_snapshot": memory_snapshot,
            "memory_mode_requested": memory_snapshot.get("memory_mode_requested"),
            "memory_mode_used": memory_snapshot.get("memory_mode_used"),
            "db_binding": db_binding,
        }
    )


@api_interview.post("/<int:exp_id>/session/<int:session_id>/message")
@login_required
def api_interview_send_message(exp_id: int, session_id: int):
    try:
        admin_user = _require_privileged()
        if not admin_user:
            return _json_error("Forbidden", 403, code="forbidden")

        sess = AdminInterviewSession.query.get(int(session_id))
        if not sess or int(sess.exp_id) != int(exp_id):
            return _json_error("Session not found", 404, code="not_found")

        payload = request.get_json(silent=True) or {}
        content = (payload.get("content") or "").strip()
        if not content:
            return _json_error("content required", 400, code="bad_request")

        auto_refresh = bool(payload.get("auto_refresh_memory", True))
        debug_trace = _interview_debug_enabled(payload)
        memory_mode = _extract_requested_memory_mode(sess.memory_snapshot_json)

        admin_msg = AdminInterviewMessage(
            session_id=int(sess.id),
            role="admin",
            content=content,
        )
        db.session.add(admin_msg)
        db.session.commit()

        exp = Exps.query.filter_by(idexp=int(exp_id)).first()
        if not exp:
            return _json_error("Experiment not found", 404, code="not_found")
        db_binding = _ensure_experiment_server_db_binding(exp)

        agent_user = User_mgmt.query.get(int(sess.agent_user_id))
        if not agent_user:
            return _json_error("Agent not found", 404, code="not_found")

        contextual_query_text = _build_contextual_admin_query_text(
            int(sess.id), content
        )

        if auto_refresh:
            memory_snapshot = _build_memory_snapshot(
                exp,
                run_id=(sess.run_id or "").strip() or None,
                agent_user_id=int(sess.agent_user_id),
                memory_mode=memory_mode,
                query_text=contextual_query_text,
            )
            sess.memory_snapshot_json = json.dumps(memory_snapshot)
            db.session.commit()
        else:
            try:
                memory_snapshot = json.loads(sess.memory_snapshot_json or "{}")
                if not isinstance(memory_snapshot, dict):
                    memory_snapshot = {}
            except Exception:
                memory_snapshot = {}

        memory_pack = _format_memory_pack(memory_snapshot or {})
        facts_snapshot = _build_facts_snapshot(
            agent_user_id=int(sess.agent_user_id),
            admin_text=contextual_query_text,
        )
        facts_pack = _format_facts_pack(facts_snapshot)

        # Some read helpers can swallow SQL errors and leave PostgreSQL tx aborted.
        # Reset session state before lazy-loading ORM attributes for backend resolution.
        db.session.rollback()

        # Build transcript window (last ~12 msgs excluding system).
        msgs = (
            AdminInterviewMessage.query.filter_by(session_id=int(sess.id))
            .order_by(AdminInterviewMessage.id.asc())
            .all()
        )
        transcript = []
        for m in msgs:
            if m.role not in {"admin", "agent"}:
                continue
            who = "ADMIN" if m.role == "admin" else "AGENT_UNVERIFIED"
            transcript.append(f"{who}: {m.content}")
        transcript = transcript[-12:]

        evidence_guard, evidence_guard_meta = _build_evidence_guard(
            facts_snapshot=facts_snapshot,
            memory_snapshot=memory_snapshot,
        )

        persona = (sess.persona_snapshot or "").strip()
        system_message = (
            "You are being interviewed by a researcher (the experiment admin).\n"
            "They are evaluating your persona, memory, and social behavior in the simulation.\n"
            "Stay fully in character. Speak casually and naturally (Reddit-style, not corporate).\n\n"
            "Truthfulness rules (very important):\n"
            "- Do NOT guess or invent actions, posts, comments, votes, or other users' replies.\n"
            "- Use FACTS PACK as ground truth for what you posted/commented, who replied to you, and how many likes/dislikes it got.\n"
            '- Reply sections in FACTS PACK are "replies you\'ve seen" (read/commented/voted), so treat them as seen evidence only.\n'
            '- For "who did you reply to / who was OP" questions, use reply_target fields in FACTS PACK '
            "(parent=..., thread_op=...). If username is present, answer with it.\n"
            '- For "what was their original comment" questions, use parent_text when available.\n'
            "- Treat AGENT_UNVERIFIED transcript lines as potentially wrong prior drafts. Never use them as evidence.\n"
            "- When the admin asks about a specific topic/person/keyword, use the 'matching the admin's question' section.\n"
            "  If that section is empty, you have no evidence that you wrote about it.\n"
            "- If FACTS PACK shows '(none)' for a section, treat it as no evidence. Do not invent.\n"
            "- Use MEMORY PACK for subjective context: retrieved memories, relationships, community vibe, and thread summaries.\n"
            "- If you cannot find evidence in FACTS PACK or MEMORY PACK, say you don't remember / can't confirm.\n"
            "- Never introduce a new specific title/name/event unless it appears in evidence or the admin's latest message.\n"
            "- If you previously said something wrong in this interview, explicitly correct yourself.\n\n"
            "Style:\n"
            "- Answer the admin directly.\n"
            '- For questions about your actions ("Did you post/comment/vote…?"), start with a direct yes/no (or "can\'t confirm"), then justify.\n'
            "- Keep it concise.\n"
            "- If the admin's question is ambiguous, ask ONE short clarifying question to help you identify the right evidence "
            "(e.g., which username/topic/thread_root_id/approx round range they mean).\n"
            "- End your reply with ONE short follow-up question that helps the researcher continue the interview.\n"
            "  Prefer clarification questions when needed; otherwise ask if they want you to expand on a specific detail.\n"
            "- Avoid generic small-talk questions; only ask interview-relevant questions.\n"
            "- Prefer @username in natural prose when a username is present in evidence.\n"
            "- Include ids only when the admin asks for verification or when ids are needed to disambiguate "
            "(e.g., post_id=123, thread_root_id=123).\n"
            "- If you say you *didn't* do something, do not list random ids. Only cite ids as 'checked recent comments: …'.\n"
            "- Do not ask other users to 'chime in' or join the interview; only you and the admin are talking.\n"
            "- Do not mention 'FACTS PACK' or 'MEMORY PACK' explicitly.\n\n"
            "PERSONA:\n"
            f"{persona}\n"
        )

        user_message = (
            f"{facts_pack}\n\n"
            f"{memory_pack}\n\n"
            f"{evidence_guard}\n\n"
            "CONVERSATION SO FAR (most recent last):\n" + "\n".join(transcript) + "\n\n"
            f"LATEST ADMIN MESSAGE:\n{content}\n\n"
            "Respond to the admin's latest message."
        )

        mode, model, base_url, api_key, temperature, max_tokens = _resolve_llm_backend(
            backend_mode=sess.backend_mode,
            exp=exp,
            agent_user=agent_user,
            admin_user=admin_user,
        )

        # Interviews should be grounded and stable; clamp temperature to reduce confabulation.
        try:
            temperature = float(temperature)
        except Exception:
            temperature = 0.4
        temperature = min(temperature, 0.2)

        meta = {
            "backend_mode": mode,
            "llm_model": model,
            "llm_base_url": base_url,
            "contextual_query_text": contextual_query_text,
            "memory_mode_requested": memory_snapshot.get(
                "memory_mode_requested", memory_mode
            ),
            "memory_mode_used": memory_snapshot.get("memory_mode_used"),
            "memory_fallback_reason": memory_snapshot.get("fallback_reason"),
            "memory_pack_chars": len(memory_pack or ""),
            "facts_pack_chars": len(facts_pack or ""),
            "persona_chars": len(persona or ""),
            "transcript_msgs": len(transcript),
            "facts_snapshot": facts_snapshot,
            "evidence_guard": evidence_guard_meta,
            "db_binding": db_binding,
        }
        retrieval_meta = memory_snapshot.get("retrieval_meta")
        if isinstance(retrieval_meta, dict):
            meta["memory_retrieval_meta"] = retrieval_meta
            meta["memory_search_returned_k"] = retrieval_meta.get("returned_k")
            meta["memory_search_degraded_mode"] = retrieval_meta.get("degraded_mode")

        try:
            reply = _generate_reply(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens if max_tokens != -1 else 450,
                system_message=system_message,
                user_message=user_message,
            )
        except Exception as exc:
            reply = f"(interview backend error: {exc})"
            meta["error"] = str(exc)

        try:
            strict_no_inference = bool(
                evidence_guard_meta.get("strict_no_inference", False)
            )
        except Exception:
            strict_no_inference = False
        reply, sanitize_meta = _sanitize_interview_reply(
            reply,
            facts_snapshot=facts_snapshot,
            memory_snapshot=memory_snapshot,
            strict_no_inference=strict_no_inference,
        )
        meta["reply_sanitize"] = sanitize_meta
        if debug_trace:
            meta["retrieval_trace"] = _build_retrieval_trace(
                contextual_query_text=contextual_query_text,
                facts_snapshot=facts_snapshot,
                memory_snapshot=memory_snapshot,
                sanitize_meta=sanitize_meta,
            )

        agent_msg = AdminInterviewMessage(
            session_id=int(sess.id),
            role="agent",
            content=reply,
            meta_json=json.dumps(meta),
        )
        db.session.add(agent_msg)
        db.session.commit()

        # Return refreshed transcript for UI.
        msgs = (
            AdminInterviewMessage.query.filter_by(session_id=int(sess.id))
            .order_by(AdminInterviewMessage.id.asc())
            .all()
        )
        out_messages = [
            {"id": int(m.id), "role": m.role, "content": m.content} for m in msgs
        ]

        return _json_success(
            {
                "reply": reply,
                "meta": meta,
                "memory_mode_requested": memory_snapshot.get(
                    "memory_mode_requested", memory_mode
                ),
                "memory_mode_used": memory_snapshot.get("memory_mode_used"),
                "memory_snapshot": memory_snapshot,
                "messages": out_messages,
            }
        )
    except Exception as exc:
        db.session.rollback()
        return _json_error(
            f"Failed to send interview message: {exc}", 500, code="interview_send_error"
        )
