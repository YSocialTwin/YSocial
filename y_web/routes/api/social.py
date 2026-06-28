from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from y_web import db
from y_web.routes.api.interview._facts import (
    _build_facts_snapshot,
    _format_facts_pack,
)
from y_web.routes.api.interview._helpers import _coerce_experiment_user_id
from y_web.routes.api.interview._llm import (
    _generate_reply,
    _resolve_llm_backend,
    _sanitize_interview_reply,
)
from y_web.routes.api.interview._memory import (
    _build_memory_snapshot,
    _build_persona_snapshot,
    _detect_run_id_from_server_log,
    _experiment_sqlite_db_path,
    _format_memory_pack,
    _get_top_interests_for_user_in_exp,
    _load_experiment_user_sqlite,
    _resolve_interview_profile_pic,
)
from y_web.routes.api.interview._server import (
    _ensure_experiment_db_bind,
    _ensure_experiment_server_db_binding,
    _memory_server_unavailable,
)
from y_web.routes.social.helpers import _experiment_memory_enabled
from y_web.src.experiment.helpers import ensure_experiment_user
from y_web.src.models import (
    Admin_users,
    Exps,
    Follow,
    ForumChatMessage,
    ForumChatSession,
    User_mgmt,
)

api_social = Blueprint("api_social", __name__, url_prefix="/api/social")


def _json_success(data=None, meta=None, status=200):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def _json_error(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def _social_chat_owner_user(exp: Exps) -> User_mgmt | None:
    username = getattr(current_user, "username", "") or ""
    is_photo = str(getattr(exp, "platform_type", "") or "").strip().lower() == "photo_sharing"
    db_path = _experiment_sqlite_db_path(exp)
    if db_path is not None and db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "select id from user_mgmt where username = ? limit 1",
                    (username,),
                ).fetchone()
            finally:
                conn.close()
            if row is not None:
                return _load_experiment_user_sqlite(exp, row["id"])
        except Exception:
            pass

    if is_photo:
        try:
            created_user, _created = ensure_experiment_user(
                exp,
                user_id=getattr(current_user, "id", 0) or 0,
                username=username,
                email=str(getattr(current_user, "email", "") or ""),
                password=str(getattr(current_user, "password", "") or ""),
                joined_on=0,
            )
            if created_user is not None:
                return created_user
        except Exception:
            pass
        return None

    user = User_mgmt.query.filter_by(username=username).first()
    if user is not None:
        return user

    try:
        created_user, _created = ensure_experiment_user(
            exp,
            user_id=getattr(current_user, "id", 0) or 0,
            username=username,
            email=str(getattr(current_user, "email", "") or ""),
            password=str(getattr(current_user, "password", "") or ""),
            joined_on=0,
        )
        if created_user is not None:
            return created_user
    except Exception:
        pass

    return None


def _social_chat_followed_agent_ids(exp: Exps, owner_user_id) -> set:
    owner_id = _coerce_experiment_user_id(owner_user_id)
    followed_ids: set = set()
    latest_actions: dict = {}
    db_path = _experiment_sqlite_db_path(exp)
    is_photo = str(getattr(exp, "platform_type", "") or "").strip().lower() == "photo_sharing"

    def _mark_active(target_id, action):
        target_id = _coerce_experiment_user_id(target_id)
        if target_id is None or target_id == owner_id or target_id in latest_actions:
            return
        latest_actions[target_id] = str(action or "").strip().lower()

    if is_photo and db_path is not None and db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    select f.user_id as source_id, f.follower_id as target_id, f.action, f.rowid as rid
                    from follow f
                    left join rounds r on f.round = r.id
                    where f.user_id = ? or f.follower_id = ?
                    order by coalesce(r.day, 0) desc, coalesce(r.hour, 0) desc, f.rowid desc
                    """,
                    (owner_id, owner_id),
                ).fetchall()
            finally:
                conn.close()
            for row in rows:
                target_id = row["target_id"] if str(row["source_id"]) == str(owner_id) else row["source_id"]
                _mark_active(target_id, row["action"])
        except Exception:
            latest_actions = {}
    elif isinstance(owner_id, str) and db_path is not None and db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    select f.user_id as source_id, f.follower_id as target_id, f.action, f.rowid as rid
                    from follow f
                    left join rounds r on f.round = r.id
                    where f.user_id = ? or f.follower_id = ?
                    order by coalesce(r.day, 0) desc, coalesce(r.hour, 0) desc, f.rowid desc
                    """,
                    (owner_id, owner_id),
                ).fetchall()
            finally:
                conn.close()
            for row in rows:
                target_id = row["target_id"] if str(row["source_id"]) == str(owner_id) else row["source_id"]
                _mark_active(target_id, row["action"])
        except Exception:
            latest_actions = {}
    else:
        follow_events = (
            Follow.query.filter(Follow.user_id == owner_id)
            .order_by(Follow.id.desc())
            .all()
        )
        reverse_events = (
            Follow.query.filter(Follow.follower_id == owner_id)
            .order_by(Follow.id.desc())
            .all()
        )
        for event in sorted(
            [*follow_events, *reverse_events],
            key=lambda item: int(getattr(item, "id", 0) or 0),
            reverse=True,
        ):
            target_id = (
                getattr(event, "follower_id", None)
                if str(getattr(event, "user_id", None)) == str(owner_id)
                else getattr(event, "user_id", None)
            )
            _mark_active(target_id, getattr(event, "action", ""))

    for target_id, action in latest_actions.items():
        if action == "follow":
            followed_ids.add(target_id)
    return followed_ids


def _social_chat_photo_contacts(exp: Exps, owner_user_id) -> list[User_mgmt]:
    owner_id = _coerce_experiment_user_id(owner_user_id)
    if owner_id is None:
        return []

    contacts = []
    seen_ids = set()
    for contact_id in sorted(_social_chat_followed_agent_ids(exp, owner_id), key=lambda value: str(value)):
        contact = _load_experiment_user_sqlite(exp, contact_id)
        if contact is None:
            continue
        contact_key = _coerce_experiment_user_id(getattr(contact, "id", None))
        if contact_key is None or contact_key == owner_id or contact_key in seen_ids:
            continue
        if int(getattr(contact, "is_page", 0) or 0) != 0:
            continue
        seen_ids.add(contact_key)
        contacts.append(contact)
    return contacts


def _social_chat_admin_user(exp: Exps) -> Admin_users | None:
    owner_name = str(getattr(exp, "owner", "") or "").strip()
    if owner_name:
        owner_admin = Admin_users.query.filter_by(username=owner_name).first()
        if owner_admin is not None:
            return owner_admin

    current_admin = Admin_users.query.filter_by(
        username=getattr(current_user, "username", "") or ""
    ).first()
    if current_admin is not None:
        return current_admin

    return Admin_users.query.order_by(Admin_users.id.asc()).first()


def _social_chat_message_payload(message: ForumChatMessage) -> dict:
    return {
        "id": int(message.id),
        "role": str(message.role or ""),
        "content": str(message.content or ""),
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _social_chat_session_payload(
    session: ForumChatSession, *, include_messages: bool = False
) -> dict:
    payload = {
        "id": int(session.id),
        "target_user_id": _coerce_experiment_user_id(session.target_user_id),
        "target_username": str(session.target_username or ""),
        "target_profile_pic": str(session.target_profile_pic or ""),
        "last_message_preview": str(session.last_message_preview or ""),
        "last_message_at": (
            session.last_message_at.isoformat() if session.last_message_at else None
        ),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "run_id": str(session.run_id or ""),
    }
    if include_messages:
        payload["messages"] = [
            _social_chat_message_payload(msg)
            for msg in sorted(session.messages or [], key=lambda item: int(item.id))
        ]
    return payload


def _social_chat_render_memory_pack(snapshot: dict | None) -> str:
    if not isinstance(snapshot, dict) or not snapshot:
        return ""
    try:
        return _format_memory_pack(snapshot, max_chars=2200).strip()
    except Exception:
        return ""


def _social_chat_build_transcript(
    session: ForumChatSession, *, max_messages: int = 12
) -> str:
    messages = sorted(session.messages or [], key=lambda item: int(item.id))
    tail = messages[-max_messages:]
    lines = []
    for msg in tail:
        role = (
            "You"
            if str(msg.role or "") == "user"
            else str(session.target_username or "Agent")
        )
        content = str(msg.content or "").strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def _social_chat_build_memory_query(
    session: ForumChatSession, latest_user_message: str, *, max_messages: int = 4
) -> str:
    latest = str(latest_user_message or "").strip()
    chunks = []
    if latest:
        chunks.append(latest)

    messages = sorted(session.messages or [], key=lambda item: int(item.id))
    tail = messages[-max_messages:]
    for msg in reversed(tail):
        content = str(getattr(msg, "content", "") or "").strip()
        if not content or content == latest:
            continue
        chunks.append(content)

    query = " | ".join(chunks).strip(" |")
    return query or "private microblogging chat context and recent interactions"


def _social_chat_upsert_session(
    *, exp: Exps, owner_user: User_mgmt, target_user: User_mgmt
) -> ForumChatSession:
    session = (
        ForumChatSession.query.filter_by(
            owner_user_id=_coerce_experiment_user_id(owner_user.id),
            target_user_id=_coerce_experiment_user_id(target_user.id),
        )
        .order_by(ForumChatSession.updated_at.desc(), ForumChatSession.id.desc())
        .first()
    )
    if session is not None:
        if not session.target_profile_pic:
            session.target_profile_pic = _resolve_interview_profile_pic(
                target_user, exp
            )
        return session

    interests = _get_top_interests_for_user_in_exp(exp, target_user.id)
    session = ForumChatSession(
        owner_user_id=_coerce_experiment_user_id(owner_user.id),
        owner_username=str(owner_user.username or ""),
        target_user_id=_coerce_experiment_user_id(target_user.id),
        target_username=str(target_user.username or ""),
        target_profile_pic=_resolve_interview_profile_pic(target_user, exp),
        persona_snapshot=_build_persona_snapshot(target_user, interests, exp),
    )
    db.session.add(session)
    db.session.flush()
    return session


def _social_chat_refresh_runtime_context(
    *, exp: Exps, target_user: User_mgmt, session: ForumChatSession, query_text: str
) -> dict:
    if not session.persona_snapshot:
        interests = _get_top_interests_for_user_in_exp(exp, target_user.id)
        session.persona_snapshot = _build_persona_snapshot(target_user, interests, exp)

    run_id = str(session.run_id or "").strip() or None
    if not run_id:
        detected = _detect_run_id_from_server_log(
            exp,
            agent_user_id=_coerce_experiment_user_id(target_user.id),
            probe_memory_coverage=True,
        )
        run_id = str(detected.get("run_id") or "").strip() or None
        session.run_id = run_id

    snapshot = {}
    db_binding = _ensure_experiment_server_db_binding(exp)
    if run_id and not _memory_server_unavailable(db_binding):
        try:
            snapshot = _build_memory_snapshot(
                exp,
                run_id=run_id,
                agent_user_id=_coerce_experiment_user_id(target_user.id),
                memory_mode="semantic",
                query_text=query_text,
            )
        except Exception:
            snapshot = {}
    session.memory_snapshot_json = json.dumps(snapshot or {})
    return snapshot or {}


def _social_chat_generate_reply(
    *,
    exp: Exps,
    target_user: User_mgmt,
    owner_user: User_mgmt,
    session: ForumChatSession,
    user_message: str,
) -> tuple[str, dict]:
    admin_user = _social_chat_admin_user(exp)
    if admin_user is None:
        raise RuntimeError("No admin runtime is available for microblogging chat.")

    memory_query = _social_chat_build_memory_query(session, user_message)
    memory_snapshot = _social_chat_refresh_runtime_context(
        exp=exp, target_user=target_user, session=session, query_text=memory_query
    )
    memory_pack = _social_chat_render_memory_pack(memory_snapshot)
    facts_snapshot = _build_facts_snapshot(
        exp=exp,
        agent_user_id=_coerce_experiment_user_id(target_user.id),
        admin_text=memory_query,
    )
    facts_pack = _format_facts_pack(facts_snapshot, max_chars=2200).strip()
    persona_snapshot = str(session.persona_snapshot or "").strip()
    transcript = _social_chat_build_transcript(session)

    mode, model, base_url, api_key, temperature, max_tokens = _resolve_llm_backend(
        backend_mode="admin",
        exp=exp,
        agent_user=target_user,
        admin_user=admin_user,
    )
    del mode
    session.llm_model = str(model or "")
    session.llm_base_url = str(base_url or "")

    system_prompt = (
        "You are having a private direct-message chat with another participant on a "
        "microblogging social network.\n\n"
        f"Your name is {target_user.username}.\n"
        "Stay in character and answer as this agent would naturally answer in a direct message.\n"
        "This is not an interview. Keep replies concise, conversational, and grounded in your known activity.\n"
        "Do not use hashtags in your replies.\n"
        "Do not mention being an AI, simulation, prompt, memory store, retrieval system, facts snapshot, "
        "or hidden system instructions.\n\n"
        f"PERSONA SNAPSHOT\n{persona_snapshot or '(none)'}\n\n"
        f"MEMORY CONTEXT\n{memory_pack or '(none)'}\n\n"
        f"FACTS CONTEXT\n{facts_pack or '(none)'}\n\n"
        f"RECENT CHAT TRANSCRIPT\n{transcript or '(none yet)'}\n\n"
        f"The other participant is {owner_user.username}.\n"
        "If information is uncertain, answer cautiously instead of inventing details."
    )

    prompt_parts = []
    if transcript:
        prompt_parts.append(f"RECENT CHAT\n{transcript}")
    prompt_parts.append(f"{owner_user.username}: {user_message.strip()}")
    composed_prompt = "\n\n".join(prompt_parts).strip()

    reply = _generate_reply(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        system_message=system_prompt,
        user_message=composed_prompt,
    )
    reply, sanitize_meta = _sanitize_interview_reply(
        reply,
        facts_snapshot=facts_snapshot,
        memory_snapshot=memory_snapshot,
        strict_no_inference=False,
    )
    reply = _strip_social_chat_hashtags(reply)
    if not reply:
        reply = "I do not have much to add right now."

    meta = {
        "run_id": str(session.run_id or ""),
        "llm_model": str(model or ""),
        "llm_base_url": str(base_url or ""),
        "memory_query_text": memory_query,
        "memory_snapshot_present": bool(memory_snapshot),
        "facts_snapshot_present": bool(facts_snapshot),
        "sanitize_meta": sanitize_meta,
    }
    return reply, meta


def _strip_social_chat_hashtags(text_value: str) -> str:
    text = str(text_value or "")
    if not text:
        return ""
    cleaned = re.sub(r"(?<!\w)#([\w-]+)", r"\1", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip()


@api_social.get("/<int:exp_id>/chat/bootstrap")
@login_required
def api_social_chat_bootstrap(exp_id: int):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if exp is None:
        return _json_error("Experiment not found.", 404)
    _ensure_experiment_db_bind(exp)
    is_photo = str(getattr(exp, "platform_type", "") or "").strip().lower() == "photo_sharing"

    owner_user = _social_chat_owner_user(exp)
    if owner_user is None:
        return _json_error("Experiment user not found for current session.", 404)
    owner_id = _coerce_experiment_user_id(owner_user.id)
    followed_agent_ids = _social_chat_followed_agent_ids(exp, owner_id)
    if is_photo:
        agents = _social_chat_photo_contacts(exp, owner_id)
    elif isinstance(owner_id, str):
        agents = [
            _load_experiment_user_sqlite(exp, agent_id)
            for agent_id in sorted(followed_agent_ids, key=lambda value: str(value))
        ]
        agents = [
            agent
            for agent in agents
            if agent is not None
            and int(getattr(agent, "is_page", 0) or 0) == 0
            and _coerce_experiment_user_id(getattr(agent, "id", None)) != owner_id
        ]
    else:
        agents_query = (
            User_mgmt.query.filter(User_mgmt.is_page == 0)
            .filter(User_mgmt.id != owner_id)
            .filter(User_mgmt.id.in_(followed_agent_ids or {-1}))
        )
        agents_query = agents_query.filter(User_mgmt.user_type != "user")
        agents = agents_query.order_by(User_mgmt.username.asc()).all()
    sessions = (
        ForumChatSession.query.filter_by(owner_user_id=owner_id)
        .order_by(
            ForumChatSession.last_message_at.desc(),
            ForumChatSession.updated_at.desc(),
            ForumChatSession.id.desc(),
        )
        .all()
    )
    sessions = [
        sess
        for sess in sessions
        if _coerce_experiment_user_id(sess.target_user_id) in followed_agent_ids
    ]

    session_map = {
        _coerce_experiment_user_id(sess.target_user_id): sess for sess in sessions
    }
    agent_payload = []
    for agent in agents:
        agent_id = _coerce_experiment_user_id(agent.id)
        sess = session_map.get(agent_id)
        agent_payload.append(
            {
                "user_id": agent_id,
                "username": str(agent.username or ""),
                "profile_pic": _resolve_interview_profile_pic(agent, exp),
                "profession": str(getattr(agent, "profession", "") or ""),
                "preview": str((sess.last_message_preview if sess else "") or ""),
                "session_id": int(sess.id) if sess else None,
                "last_message_at": (
                    sess.last_message_at.isoformat()
                    if (sess and sess.last_message_at)
                    else None
                ),
            }
        )

    return _json_success(
        {
            "owner": {
                "user_id": owner_id,
                "username": str(owner_user.username or ""),
            },
            "agents": agent_payload,
            "sessions": [_social_chat_session_payload(sess) for sess in sessions],
        }
    )


@api_social.post("/<int:exp_id>/chat/session")
@login_required
def api_social_chat_open_session(exp_id: int):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if exp is None:
        return _json_error("Experiment not found.", 404)
    _ensure_experiment_db_bind(exp)
    is_photo = str(getattr(exp, "platform_type", "") or "").strip().lower() == "photo_sharing"

    owner_user = _social_chat_owner_user(exp)
    if owner_user is None:
        return _json_error("Experiment user not found for current session.", 404)
    owner_id = _coerce_experiment_user_id(owner_user.id)
    followed_agent_ids = _social_chat_followed_agent_ids(exp, owner_id)

    payload = request.get_json(silent=True) or {}
    agent_user_id = _coerce_experiment_user_id(payload.get("agent_user_id"))
    target_user = _load_experiment_user_sqlite(exp, agent_user_id) if is_photo else None
    if target_user is None:
        target_query = User_mgmt.query.filter(User_mgmt.is_page == 0).filter(
            User_mgmt.id == agent_user_id
        )
        target_query = target_query.filter(User_mgmt.user_type != "user")
        target_user = target_query.first()
    if target_user is None:
        return _json_error("Target agent not found.", 404)
    if _coerce_experiment_user_id(target_user.id) not in followed_agent_ids:
        return _json_error("You can chat only with followed agents.", 403)

    session = _social_chat_upsert_session(
        exp=exp, owner_user=owner_user, target_user=target_user
    )
    db.session.commit()
    return _json_success(_social_chat_session_payload(session, include_messages=True))


@api_social.get("/<int:exp_id>/chat/session/<int:session_id>")
@login_required
def api_social_chat_get_session(exp_id: int, session_id: int):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if exp is None:
        return _json_error("Experiment not found.", 404)
    _ensure_experiment_db_bind(exp)
    is_photo = str(getattr(exp, "platform_type", "") or "").strip().lower() == "photo_sharing"

    owner_user = _social_chat_owner_user(exp)
    if owner_user is None:
        return _json_error("Experiment user not found for current session.", 404)
    owner_id = _coerce_experiment_user_id(owner_user.id)
    followed_agent_ids = _social_chat_followed_agent_ids(exp, owner_id)

    session = ForumChatSession.query.filter_by(
        id=int(session_id), owner_user_id=owner_id
    ).first()
    if session is None:
        return _json_error("Chat session not found.", 404)
    if _coerce_experiment_user_id(session.target_user_id) not in followed_agent_ids:
        return _json_error("You can chat only with followed agents.", 403)

    if is_photo:
        return _json_success(_social_chat_session_payload(session, include_messages=True))

    return _json_success(_social_chat_session_payload(session, include_messages=True))


@api_social.post("/<int:exp_id>/chat/session/<int:session_id>/message")
@login_required
def api_social_chat_send_message(exp_id: int, session_id: int):
    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if exp is None:
        return _json_error("Experiment not found.", 404)
    _ensure_experiment_db_bind(exp)
    is_photo = str(getattr(exp, "platform_type", "") or "").strip().lower() == "photo_sharing"

    owner_user = _social_chat_owner_user(exp)
    if owner_user is None:
        return _json_error("Experiment user not found for current session.", 404)
    owner_id = _coerce_experiment_user_id(owner_user.id)
    followed_agent_ids = _social_chat_followed_agent_ids(exp, owner_id)

    session = ForumChatSession.query.filter_by(
        id=int(session_id), owner_user_id=owner_id
    ).first()
    if session is None:
        return _json_error("Chat session not found.", 404)
    target_id = _coerce_experiment_user_id(session.target_user_id)
    if target_id not in followed_agent_ids:
        return _json_error("You can chat only with followed agents.", 403)

    target_user = _load_experiment_user_sqlite(exp, target_id) if is_photo else None
    if target_user is None:
        target_query = User_mgmt.query.filter_by(id=target_id)
        target_query = target_query.filter(User_mgmt.user_type != "user")
        target_user = target_query.first()
    if target_user is None:
        return _json_error("Target agent not found.", 404)

    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content") or "").strip()
    if not content:
        return _json_error("content is required.", 400)

    user_msg = ForumChatMessage(
        session_id=int(session.id),
        role="user",
        content=content,
        meta_json=None,
    )
    db.session.add(user_msg)
    db.session.flush()

    try:
        reply, meta = _social_chat_generate_reply(
            exp=exp,
            target_user=target_user,
            owner_user=owner_user,
            session=session,
            user_message=content,
        )
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Failed to generate reply: {exc}", 500)

    assistant_msg = ForumChatMessage(
        session_id=int(session.id),
        role="assistant",
        content=reply or "(no reply)",
        meta_json=json.dumps(meta or {}),
    )
    db.session.add(assistant_msg)
    session.last_message_preview = str(reply or "(no reply)")[:180]
    session.last_message_at = datetime.now(timezone.utc)
    session.target_profile_pic = (
        session.target_profile_pic or _resolve_interview_profile_pic(target_user, exp)
    )
    db.session.commit()

    return _json_success(
        {
            "session": _social_chat_session_payload(session),
            "user_message": _social_chat_message_payload(user_msg),
            "assistant_message": _social_chat_message_payload(assistant_msg),
        }
    )
