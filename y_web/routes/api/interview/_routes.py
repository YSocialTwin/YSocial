from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from flask import request
from flask_login import current_user, login_required

from y_web import db
from y_web.src.models import (
    AdminInterviewMessage,
    AdminInterviewSession,
    Exps,
    User_mgmt,
)

from ._blueprint import api_interview, _INTERVIEW_MEMORY_DEFAULT_QUERY, _INTERVIEW_MEMORY_MODE_DEFAULT
from ._helpers import (
    _json_error,
    _json_success,
    _normalize_memory_mode,
    _require_privileged,
)
from ._memory import (
    _as_bool,
    _build_deferred_memory_snapshot,
    _build_memory_snapshot,
    _build_persona_snapshot,
    _detect_run_id_from_experiment_db,
    _detect_run_id_from_server_log,
    _extract_requested_memory_mode,
    _format_memory_pack,
    _get_top_interests_for_user,
    _interview_debug_enabled,
    _memory_snapshot_has_structured_content,
    _resolve_interview_profile_pic,
)
from ._server import (
    _build_unavailable_memory_snapshot,
    _ensure_experiment_db_bind,
    _ensure_experiment_server_db_binding,
    _memory_server_unavailable,
)
from ._facts import (
    _build_contextual_admin_query_text,
    _build_evidence_guard,
    _build_facts_snapshot,
    _build_retrieval_trace,
    _format_facts_pack,
    _try_direct_recent_activity_reply,
)
from ._llm import (
    _generate_reply,
    _resolve_llm_backend,
    _sanitize_interview_reply,
)


@api_interview.get("/<int:exp_id>/agents")
@login_required
def api_interview_agents(exp_id: int):
    admin_user = _require_privileged()
    if not admin_user:
        return _json_error("Forbidden", 403, code="forbidden")

    exp = Exps.query.filter_by(idexp=int(exp_id)).first()
    if not exp:
        return _json_error("Experiment not found", 404, code="not_found")
    _ensure_experiment_db_bind(exp)

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
                "profile_pic": _resolve_interview_profile_pic(u, exp),
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
    _ensure_experiment_db_bind(exp)
    db_binding = _ensure_experiment_server_db_binding(exp)

    backend_mode = (payload.get("backend_mode") or "agent_runtime").strip().lower()
    if backend_mode not in {"agent_runtime", "admin"}:
        backend_mode = "agent_runtime"
    memory_mode = _normalize_memory_mode(payload.get("memory_mode"))
    preload_memory = _as_bool(payload.get("preload_memory"), True)

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
            run_pick = _detect_run_id_from_experiment_db(
                exp, agent_user_id=int(agent_user_id)
            )
            run_id = str(run_pick.get("run_id") or "").strip() or None
            run_id_source = str(run_pick.get("source") or "none")
            run_id_selected_reason = str(
                run_pick.get("selected_reason") or "no_run_detected"
            )
            checked = run_pick.get("candidates_checked")
            if isinstance(checked, list):
                run_id_candidates_checked.extend(
                    [c for c in checked if isinstance(c, dict)]
                )
            if not run_id:
                run_id_source = "none"
                run_id_selected_reason = "no_run_detected"

    interests = _get_top_interests_for_user(agent_user_id)
    persona = _build_persona_snapshot(agent_user, interests, exp)
    if _memory_server_unavailable(db_binding):
        memory_snapshot = _build_unavailable_memory_snapshot(
            run_id=run_id,
            agent_user_id=agent_user_id,
            memory_mode=memory_mode,
        )
    elif preload_memory:
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

    if (
        preload_memory
        and run_id
        and not _memory_server_unavailable(db_binding)
        and not _memory_snapshot_has_structured_content(memory_snapshot)
        and run_id_source == "override"
    ):
        run_pick = _detect_run_id_from_server_log(
            exp,
            agent_user_id=int(agent_user_id),
            probe_memory_coverage=True,
        )
        retry_run_id = str(run_pick.get("run_id") or "").strip() or None
        if retry_run_id and retry_run_id != run_id:
            retry_snapshot = _build_memory_snapshot(
                exp,
                run_id=retry_run_id,
                agent_user_id=agent_user_id,
                memory_mode=memory_mode,
                query_text=_INTERVIEW_MEMORY_DEFAULT_QUERY,
            )
            if _memory_snapshot_has_structured_content(retry_snapshot):
                run_id = retry_run_id
                run_id_source = str(run_pick.get("source") or "log_scan_latest")
                run_id_selected_reason = "override_replaced_with_detected_run"
                memory_snapshot = retry_snapshot

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

    if _memory_server_unavailable(db_binding):
        memory_snapshot = _build_unavailable_memory_snapshot(
            run_id=(sess.run_id or "").strip() or None,
            agent_user_id=int(sess.agent_user_id),
            memory_mode=memory_mode,
        )
    else:
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
        content = (payload.get("content") or payload.get("message") or "").strip()
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
        _ensure_experiment_db_bind(exp)
        db_binding = _ensure_experiment_server_db_binding(exp)

        agent_user = User_mgmt.query.get(int(sess.agent_user_id))
        if not agent_user:
            return _json_error("Agent not found", 404, code="not_found")

        contextual_query_text = _build_contextual_admin_query_text(
            int(sess.id), content
        )

        if auto_refresh:
            if _memory_server_unavailable(db_binding):
                memory_snapshot = _build_unavailable_memory_snapshot(
                    run_id=(sess.run_id or "").strip() or None,
                    agent_user_id=int(sess.agent_user_id),
                    memory_mode=memory_mode,
                )
            else:
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
        direct_reply = _try_direct_recent_activity_reply(
            admin_text=content,
            facts_snapshot=facts_snapshot,
        )

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
            "- In FACTS PACK, 'Recent posts you made', 'Top threads you started', and 'Recent comments you made' are direct evidence of your own activity.\n"
            '- Reply sections in FACTS PACK are "replies you\'ve seen" (read/commented/voted), so treat them as seen evidence only.\n'
            '- For "who did you reply to / who was OP" questions, use reply_target fields in FACTS PACK '
            "(parent=..., thread_op=...). If username is present, answer with it.\n"
            '- For "what was their original comment" questions, use parent_text when available.\n'
            "- Treat AGENT_UNVERIFIED transcript lines as potentially wrong prior drafts. Never use them as evidence.\n"
            "- When the admin asks about a specific topic/person/keyword, use the 'matching the admin's question' section.\n"
            "  If that section is empty, you have no evidence that you wrote about it.\n"
            "- If FACTS PACK shows '(none)' for a section, treat it as no evidence. Do not invent.\n"
            "- Use MEMORY PACK for subjective context: retrieved memories, relationships, community vibe, and thread summaries.\n"
            "- MEMORY PACK entries labeled '[event]' with text starting 'post |' or 'comment |' are also evidence of your own recorded actions.\n"
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

        if direct_reply is not None:
            reply, direct_meta = direct_reply
            meta["direct_answer"] = direct_meta
        else:
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
