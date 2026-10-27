"""Client configuration, population and topic catalog for IM clients (plan, 5.3).

Pure functions with no Flask or database access, so they can be tested alone. The routes in
``y_web/routes/admin/sub/clients/_im.py`` read the form and the database and call them.
"""

import copy
import datetime
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


CHAT_TYPES = ("channel", "supergroup", "group")
CHAT_VISIBILITIES = ("public", "private")
MAX_CHAT_ROWS = 200


def build_topic_catalog(
    topic_weights: Dict[str, float], chats: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """``topic_catalog.json`` from ``{topic name: weight}``; ids are unique and weights positive.

    ``chats`` are the catalog chats of :func:`parse_chat_rows` (their ``topics`` are topic *names*, turned into
    catalog ids here); they are written under ``chats`` and IM creates them when it builds the topology.
    """
    topics, seen, ids = [], set(), {}
    for name, weight in topic_weights.items():
        name = str(name).strip()
        if not name:
            continue
        tid, n = topic_id(name), 2
        while tid in seen:
            tid = f"{topic_id(name)}-{n}"
            n += 1
        seen.add(tid)
        ids[name] = tid
        topics.append({"id": tid, "label": name, "weight": max(float(weight), 0.01)})
    if not topics:
        raise ImClientFormError("the experiment has no topics: add at least one before creating a client")
    catalog: Dict[str, Any] = {"topics": topics}
    if chats:
        out = []
        for chat in chats:
            unknown = [t for t in chat["topics"] if t not in ids]
            if unknown:
                raise ImClientFormError(f"chat '{chat['title']}': unknown topic {unknown[0]}")
            out.append({**chat, "topics": [ids[t] for t in chat["topics"]]})
        catalog["chats"] = out
    return catalog


def parse_chat_rows(form, topics_by_id: Dict[Any, str]) -> List[Dict[str, Any]]:
    """The catalog chats typed in the *Chats by Topic* editor (``chat.<row>.<field>`` form fields).

    Each row is a channel or a group with the topics it is about. Rows whose title and topics are both empty are
    ignored (an untouched row); a row with a title and no topic, or the reverse, is an error that names the row.
    Returns chats with ``topics`` as topic names, ready for :func:`build_topic_catalog`.
    """
    rows = sorted(
        {int(m.group(1)) for key in form.keys() for m in [re.match(r"^chat\.(\d+)\.", str(key))] if m}
    )
    if len(rows) > MAX_CHAT_ROWS:
        raise ImClientFormError(f"at most {MAX_CHAT_ROWS} chats can be defined here")
    chats, used = [], set()
    for position, row in enumerate(rows, start=1):
        get = lambda field, row=row: (form.get(f"chat.{row}.{field}") or "").strip()  # noqa: E731
        topics = [name for tid, name in topics_by_id.items() if _flag(form.get(f"chat.{row}.topic.{tid}"))]
        title = get("title")
        if not title and not topics:
            continue
        if not title or not topics:
            raise ImClientFormError(f"chat {position}: a title and at least one topic are required")
        kind = get("type") or "channel"
        if kind not in CHAT_TYPES:
            raise ImClientFormError(f"chat '{title}': type must be one of {', '.join(CHAT_TYPES)}")
        visibility = get("visibility") or "public"
        if visibility not in CHAT_VISIBILITIES:
            raise ImClientFormError(f"chat '{title}': visibility must be public or private")
        chat_id, n = "chat-" + topic_id(title), 2
        while chat_id in used:
            chat_id = f"chat-{topic_id(title)}-{n}"
            n += 1
        used.add(chat_id)
        chat: Dict[str, Any] = {
            "id": chat_id,
            "type": kind,
            "title": title,
            "visibility": visibility,
            "topics": topics,
        }
        if get("popularity"):
            chat["popularity"] = _num(get("popularity"), f"chat '{title}': popularity", 0, 1e6, None)
        owner = get("owner")
        if owner:
            chat["owner"] = owner if owner.startswith("page:") or owner == "auto" else f"page:{owner}"
        if kind == "channel" and _flag(form.get(f"chat.{row}.discussion")):
            chat["discussion_group"] = True
        chats.append(chat)
    return chats


def split_llm_url(url: Optional[str]) -> Optional[str]:
    """IM's ``llm.address`` from the "LLM Server URL" of the form (``localhost:11434/v1`` -> ``http://localhost:11434``).

    IM appends ``/v1/chat/completions`` itself and accepts a full URL as address, so the scheme is kept (``http``
    when missing) and a trailing ``/v1`` is dropped.
    """
    text = (url or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "http://" + text
    text = text.rstrip("/")
    if text.endswith("/v1"):
        text = text[: -len("/v1")]
    return text.rstrip("/")


def parse_client_form(form, label_of=lambda text: text) -> Dict[str, Any]:
    """Validated client settings from the form (any mapping with ``get``).

    The opinion, stress/reward and memory switches come from the experiment page, as in the other platforms: the
    form carries them as hidden ``experiment_*`` fields. ``label_of`` translates the field labels used in errors.
    """
    from y_web.src.im import advanced_settings

    backend = (form.get("llm_backend") or "echo").strip().lower()
    if backend not in LLM_BACKENDS:
        raise ImClientFormError(f"llm_backend must be one of {', '.join(LLM_BACKENDS)}")
    api_key_env = (form.get("llm_api_key_env") or "").strip() or None
    if api_key_env and not _ENV_NAME.match(api_key_env):
        raise ImClientFormError("llm_api_key_env must be an environment variable name, not a key")
    seed = _num(form.get("seed"), "seed", 0, 2**31 - 1, None, int)
    start_date = (form.get("start_date") or "").strip() or None
    if start_date:
        try:
            datetime.date.fromisoformat(start_date)
        except ValueError:
            raise ImClientFormError("start_date must be a date (YYYY-MM-DD)") from None
    memory_enabled = _flag(form.get("memory_enabled"))
    try:
        advanced = advanced_settings.parse_fields(form, memory=memory_enabled, label_of=label_of)
    except advanced_settings.AdvancedSettingsError as exc:
        raise ImClientFormError(str(exc)) from None
    # the model of the form is the one picked after "Fetch Models" (``llm_model``); "model" is kept as a fallback
    model = (form.get("llm_model") or form.get("user_type") or "").strip() or None
    address = split_llm_url(form.get("llm")) or (form.get("llm_address") or "").strip() or None
    return {
        "days": _num(form.get("days"), "days", 1, 3650, 1, int),
        "start_date": start_date,
        "ticks_per_round": _num(form.get("ticks_per_round"), "ticks_per_round", 1, 60, None, int),
        "seed": seed if seed is not None else random.randint(1, 2**31 - 1),
        "backend": backend,
        "model": model,
        "address": address,
        "port": _num(form.get("llm_port"), "llm_port", 1, 65535, None, int),
        "temperature": _num(form.get("llm_temperature"), "llm_temperature", 0, 5, None),
        "max_tokens": _num(form.get("llm_max_tokens"), "llm_max_tokens", -1, 100000, None, int),
        "max_concurrency": _num(form.get("llm_max_concurrency"), "llm_max_concurrency", 1, 1024, None, int),
        "timeout_seconds": _num(form.get("llm_timeout_seconds"), "llm_timeout_seconds", 1, 3600, None),
        "api_key_env": api_key_env,
        "memory_enabled": memory_enabled,
        "stress_reward": _flag(form.get("experiment_stress_reward_enabled") or form.get("stress_reward_enabled")),
        "opinion_enabled": _flag(form.get("experiment_opinion_dynamics_enabled") or form.get("opinion_enabled")),
        "opinion_model": (form.get("opinion_model") or "bounded_confidence").strip(),
        "emotion_annotation": _flag(form.get("experiment_emotion_annotation")),
        "advanced": advanced or None,
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
    if settings.get("emotion_annotation"):
        simulation["emotion_annotation"] = True
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
        # YWeb reads plain rotated files only (the logs are not a setting of the form)
        "logging": {"compress_rotated": False},
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
