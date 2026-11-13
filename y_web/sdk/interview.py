"""What the interview endpoints expose to a platform that offers them on its own pages (facts, memory, persona, LLM reply)."""

from __future__ import annotations


def build_facts_snapshot(
    *,
    exp: "Optional[Exps]" = None,
    agent_user_id: "Any",
    admin_text: "str",
    top_posts_limit: "int" = 3,
    recent_comments_limit: "int" = 5,
    query_hits_limit: "int" = 5,
) -> "Dict[str, Any]":
    """Deterministic evidence extracted from the experiment DB (db_exp bind)."""
    from y_web.routes.api.interview._facts import _build_facts_snapshot as target

    return target(
        exp=exp,
        agent_user_id=agent_user_id,
        admin_text=admin_text,
        top_posts_limit=top_posts_limit,
        recent_comments_limit=recent_comments_limit,
        query_hits_limit=query_hits_limit,
    )


def format_facts_pack(snapshot: "Dict[str, Any]", *, max_chars: "int" = 3500) -> "str":
    from y_web.routes.api.interview._facts import _format_facts_pack as target

    return target(snapshot, max_chars=max_chars)


def generate_reply(
    *,
    model: "str",
    base_url: "str",
    api_key: "str",
    temperature: "float",
    max_tokens: "int",
    system_message: "str",
    user_message: "str",
) -> "str":
    from y_web.routes.api.interview._llm import _generate_reply as target

    return target(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        system_message=system_message,
        user_message=user_message,
    )


def resolve_llm_backend(
    *,
    backend_mode: "str",
    exp: "Exps",
    agent_user: "User_mgmt",
    admin_user: "Admin_users",
) -> "Tuple[str, str, str, str, float, int]":
    """Return (mode, model, base_url, api_key, temperature, max_tokens) for interview generation."""
    from y_web.routes.api.interview._llm import _resolve_llm_backend as target

    return target(
        backend_mode=backend_mode, exp=exp, agent_user=agent_user, admin_user=admin_user
    )


def sanitize_interview_reply(
    reply: "str",
    *,
    facts_snapshot: "Dict[str, Any]",
    memory_snapshot: "Dict[str, Any]",
    strict_no_inference: "bool",
    language: "Optional[str]" = None,
) -> "Tuple[str, Dict[str, Any]]":
    from y_web.routes.api.interview._llm import _sanitize_interview_reply as target

    return target(
        reply,
        facts_snapshot=facts_snapshot,
        memory_snapshot=memory_snapshot,
        strict_no_inference=strict_no_inference,
        language=language,
    )


def build_memory_snapshot(
    exp: "Exps",
    *,
    run_id: "Optional[str]",
    agent_user_id: "int",
    memory_mode: "Optional[str]" = None,
    query_text: "Optional[str]" = None,
) -> "Dict[str, Any]":
    from y_web.routes.api.interview._memory import _build_memory_snapshot as target

    return target(
        exp,
        run_id=run_id,
        agent_user_id=agent_user_id,
        memory_mode=memory_mode,
        query_text=query_text,
    )


def build_persona_snapshot(
    user: "User_mgmt", interests: "List[str]", exp: "Exps"
) -> "str":
    from y_web.routes.api.interview._memory import _build_persona_snapshot as target

    return target(user, interests, exp)


def detect_run_id_from_server_log(
    exp: "Exps",
    *,
    agent_user_id: "Optional[int]" = None,
    probe_memory_coverage: "bool" = True,
) -> "Dict[str, Any]":
    """Best-effort run_id discovery from recent logs, preferring runs with memory coverage"""
    from y_web.routes.api.interview._memory import (
        _detect_run_id_from_server_log as target,
    )

    return target(
        exp, agent_user_id=agent_user_id, probe_memory_coverage=probe_memory_coverage
    )


def format_memory_pack(
    snapshot: "Dict[str, Any]",
    *,
    max_chars: "int" = 4500,
    language: "Optional[str]" = None,
) -> "str":
    from y_web.routes.api.interview._memory import _format_memory_pack as target

    return target(snapshot, max_chars=max_chars, language=language)


def get_top_interests_for_user(
    user_id: "Any", *, window_rounds: "int" = 50, limit: "int" = 10
) -> "List[str]":
    from y_web.routes.api.interview._memory import _get_top_interests_for_user as target

    return target(user_id, window_rounds=window_rounds, limit=limit)


def resolve_interview_profile_pic(user: "User_mgmt", exp: "Exps") -> "str":
    from y_web.routes.api.interview._memory import (
        _resolve_interview_profile_pic as target,
    )

    return target(user, exp)


def ensure_experiment_db_bind(exp: "Exps") -> "bool":
    """Ensure local db_exp-bound models query the selected experiment DB."""
    from y_web.routes.api.interview._server import _ensure_experiment_db_bind as target

    return target(exp)


def ensure_experiment_server_db_binding(exp: "Exps") -> "Dict[str, Any]":
    """Best-effort /change_db call so memory/search is scoped to the selected experiment DB."""
    from y_web.routes.api.interview._server import (
        _ensure_experiment_server_db_binding as target,
    )

    return target(exp)


def memory_server_unavailable(db_binding: "Optional[Dict[str, Any]]") -> "bool":
    from y_web.routes.api.interview._server import _memory_server_unavailable as target

    return target(db_binding)


__all__ = [
    "build_facts_snapshot",
    "build_memory_snapshot",
    "build_persona_snapshot",
    "detect_run_id_from_server_log",
    "ensure_experiment_db_bind",
    "ensure_experiment_server_db_binding",
    "format_facts_pack",
    "format_memory_pack",
    "generate_reply",
    "get_top_interests_for_user",
    "memory_server_unavailable",
    "resolve_interview_profile_pic",
    "resolve_llm_backend",
    "sanitize_interview_reply",
]
