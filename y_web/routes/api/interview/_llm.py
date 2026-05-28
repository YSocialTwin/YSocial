from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from y_web.src.models import Admin_users, Client, Exps, User_mgmt

from ._facts import (
    _collect_known_record_ids,
    _extract_facts_candidates,
    _extract_semantic_candidates,
)
from ._helpers import _normalize_llm_base_url


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
                getattr(runtime_client, "llm_api_key", "") or ""
            ).strip() or "NULL"
            try:
                temperature = float(
                    getattr(runtime_client, "llm_temperature", temperature)
                    or temperature
                )
            except Exception:
                pass
            try:
                runtime_max_tokens = getattr(
                    runtime_client, "llm_max_tokens", max_tokens
                )
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

    from y_web.src.llm.autogen_compat import AssistantAgent

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
