"""Client configuration, population and topic catalog for IM clients (plan, 5.3).

Pure functions with no Flask or database access, so they can be tested alone. The routes in
``y_web/routes/admin/sub/clients/_im.py`` read the form and the database and call them.
"""

import copy
import json
import os
import random
import re
from typing import Any, Dict, Iterable, List, Optional

IM_SLOTS_PER_DAY = 24  # IM fixes num_slots_per_day to 24
LLM_BACKENDS = ("echo", "ollama", "vllm", "openai")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SLUG = re.compile(r"[^a-z0-9]+")


class ImClientFormError(ValueError):
    """A value of the client form is invalid (the message is shown to the researcher)."""


def _num(value, name, lo, hi, default, cast=float):
    if value in (None, ""):
        return default
    try:
        number = cast(value)
    except (TypeError, ValueError):
        raise ImClientFormError(f"{name} must be a number") from None
    if not lo <= number <= hi:
        raise ImClientFormError(f"{name} must be between {lo} and {hi}")
    return number


def _flag(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def topic_id(name: str) -> str:
    """A stable catalog id for a topic name (``"Climate Change"`` -> ``"climate-change"``)."""
    slug = _SLUG.sub("-", str(name).strip().lower()).strip("-")
    return slug or "topic"


def build_topic_catalog(topic_weights: Dict[str, float]) -> Dict[str, Any]:
    """``topic_catalog.json`` from ``{topic name: weight}``; ids are unique and weights positive."""
    topics, seen = [], set()
    for name, weight in topic_weights.items():
        name = str(name).strip()
        if not name:
            continue
        tid, n = topic_id(name), 2
        while tid in seen:
            tid = f"{topic_id(name)}-{n}"
            n += 1
        seen.add(tid)
        topics.append({"id": tid, "label": name, "weight": max(float(weight), 0.01)})
    if not topics:
        raise ImClientFormError("the experiment has no topics: add at least one before creating a client")
    return {"topics": topics}


def parse_client_form(form) -> Dict[str, Any]:
    """Validated client settings from the form (any mapping with ``get``)."""
    backend = (form.get("llm_backend") or "echo").strip().lower()
    if backend not in LLM_BACKENDS:
        raise ImClientFormError(f"llm_backend must be one of {', '.join(LLM_BACKENDS)}")
    api_key_env = (form.get("llm_api_key_env") or "").strip() or None
    if api_key_env and not _ENV_NAME.match(api_key_env):
        raise ImClientFormError("llm_api_key_env must be an environment variable name, not a key")
    advanced = None
    raw_advanced = (form.get("advanced_json") or "").strip()
    if raw_advanced:
        try:
            advanced = json.loads(raw_advanced)
        except ValueError as exc:
            raise ImClientFormError(f"advanced settings are not valid JSON: {exc}") from None
        if not isinstance(advanced, dict):
            raise ImClientFormError("advanced settings must be a JSON object")
    seed = _num(form.get("seed"), "seed", 0, 2**31 - 1, None, int)
    return {
        "days": _num(form.get("days"), "days", 1, 3650, 1, int),
        "seed": seed if seed is not None else random.randint(1, 2**31 - 1),
        "backend": backend,
        "model": (form.get("llm_model") or "").strip() or None,
        "address": (form.get("llm_address") or "").strip() or None,
        "port": _num(form.get("llm_port"), "llm_port", 1, 65535, None, int),
        "temperature": _num(form.get("llm_temperature"), "llm_temperature", 0, 5, None),
        "max_tokens": _num(form.get("llm_max_tokens"), "llm_max_tokens", 1, 100000, None, int),
        "max_concurrency": _num(form.get("llm_max_concurrency"), "llm_max_concurrency", 1, 1024, None, int),
        "timeout_seconds": _num(form.get("llm_timeout_seconds"), "llm_timeout_seconds", 1, 3600, None),
        "api_key_env": api_key_env,
        "memory_enabled": _flag(form.get("memory_enabled")),
        "stress_reward": _flag(form.get("stress_reward_enabled")),
        "opinion_enabled": _flag(form.get("opinion_enabled")),
        "opinion_model": (form.get("opinion_model") or "bounded_confidence").strip(),
        "advanced": advanced,
    }


def build_client_config(
    *,
    client_name: str,
    settings: Dict[str, Any],
    topics: Iterable[str],
    activity_profiles: Dict[str, str],
    hourly_activity: Optional[Dict[str, float]] = None,
    prompt_language: Optional[str] = None,
) -> Dict[str, Any]:
    """The ``client_<name>-<population>.json`` content (runtime keys are added by the normalizer)."""
    llm: Dict[str, Any] = {"backend": settings["backend"]}
    for key, source in (
        ("model", "model"),
        ("address", "address"),
        ("port", "port"),
        ("temperature", "temperature"),
        ("llm_max_tokens", "max_tokens"),
        ("max_concurrency", "max_concurrency"),
        ("timeout_seconds", "timeout_seconds"),
        ("llm_api_key_env", "api_key_env"),
    ):
        if settings.get(source) is not None:
            llm[key] = settings[source]

    simulation: Dict[str, Any] = {
        "num_days": settings["days"],
        "activity_profiles": dict(activity_profiles),
        "discussion_topics": [t for t in topics if str(t).strip()],
    }
    if hourly_activity:
        simulation["hourly_activity"] = {str(h): float(v) for h, v in hourly_activity.items()}

    config: Dict[str, Any] = {
        "client_name": client_name,
        "seed": settings["seed"],
        "llm": llm,
        "simulation": simulation,
        "telegram": {"topics": {"catalog_file": "topic_catalog.json"}},
        "agents": {"memory_enabled": bool(settings.get("memory_enabled"))},
        "stress_reward": {"enabled": bool(settings.get("stress_reward"))},
    }
    if prompt_language:
        config["prompt_language"] = prompt_language
    if settings.get("opinion_enabled"):
        config["opinion_dynamics"] = {
            "enabled": True,
            "model_name": settings.get("opinion_model") or "bounded_confidence",
        }
    if settings.get("advanced"):
        config = deep_merge(config, settings["advanced"])
        # the runtime keys are YWeb's to write; the secret must stay out of the file
        for key in ("client_id", "namespace", "server_name", "address", "agents_file"):
            config.pop(key, None)
        config.get("llm", {}).pop("llm_api_key", None)
    return config


def schema_errors(config: dict, schema_file: str) -> List[str]:
    """Violations of IM's JSON schema (empty when valid, or when ``jsonschema`` or the schema is missing)."""
    try:
        import jsonschema
    except ImportError:
        return []
    if not os.path.isfile(schema_file):
        return []
    with open(schema_file, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    validator = jsonschema.Draft7Validator(schema)
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or 'config'}: {error.message}"
        for error in sorted(validator.iter_errors(config), key=lambda e: list(e.absolute_path))
    ]


def _present(value) -> bool:
    return value not in (None, "")


def build_agent(agent, *, interests: Iterable[str], activity_profile: str, structured: Optional[dict] = None, opinions_enabled: bool = False) -> Dict[str, Any]:
    """One entry of the IM population from a YWeb ``Agent`` row (any object with the same attributes).

    Only the fields IM reads are written: others would be kept in the agent's ``extra`` and end up in the
    prompts. The id is stable (``agent-<row id>``) so analytics can join it back to the YWeb tables.
    """
    structured = structured or {}
    topics = list(structured.get("interests") or interests)
    payload: Dict[str, Any] = {
        "id": f"agent-{agent.id}",
        "username": agent.name,
        "email": f"{agent.name}@ysocial.invalid",
        "user_type": "agent",
        "is_page": 0,
        "leaning": agent.leaning,
        "age": agent.age,
        "language": agent.language,
        "education_level": agent.education_level,
        "gender": agent.gender,
        "nationality": agent.nationality,
        "profession": agent.profession,
        "toxicity": agent.toxicity,
        "activity_profile": activity_profile,
        "daily_activity_level": agent.daily_activity_level,
        "round_actions": int(agent.round_actions),
        "interests": {t: 1.0 for t in topics},
        "llm": True,
    }
    for trait in ("oe", "co", "ex", "ag", "ne"):
        if _present(getattr(agent, trait, None)):
            payload[trait] = getattr(agent, trait)
    if structured.get("custom_features"):
        payload["custom_features"] = dict(structured["custom_features"])
    if structured.get("stubborn_topics"):
        payload["stubborn_topics"] = dict(structured["stubborn_topics"])
    if opinions_enabled:
        opinions = dict(structured.get("opinions") or {})
        payload["opinions"] = opinions or {t: round(random.random(), 4) for t in topics}
    return {k: v for k, v in payload.items() if v is not None}


def build_page(page, *, topics: Iterable[str], activity_profile: str) -> Dict[str, Any]:
    """One news page (``is_page: 1`` with its feed) of the IM population."""
    topics = list(topics)
    return {
        "id": f"page-{page.id}",
        "username": page.name,
        "email": f"{page.name}@ysocial.invalid",
        "user_type": "page",
        "is_page": 1,
        "leaning": page.leaning,
        "age": 0,
        "language": "en",
        "activity_profile": activity_profile,
        "daily_activity_level": 1,
        "round_actions": 3,
        "feed_url": page.feed,
        "interests": {t: 1.0 for t in topics},
        "llm": True,
    }


def check_unique(accounts: List[Dict[str, Any]]) -> None:
    """IM rejects duplicate ids and usernames; refuse them here with a message naming the culprit."""
    for key in ("id", "username"):
        seen = set()
        for account in accounts:
            value = str(account[key]).strip().lower() if key == "username" else account[key]
            if value in seen:
                raise ImClientFormError(f"duplicate {key} in the population: {account[key]}")
            seen.add(value)
