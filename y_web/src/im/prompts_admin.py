"""Prompts of an IM experiment: what the admin page shows and how an edit is stored.

The runtime builds its prompts from three layers (``yinstantmessaging.client.prompts``): the English pack, the pack of
the prompt language and, over both, ``prompts_im.json`` (``prompts_im.<lang>.json`` for another language) in the
experiment folder. The page edits the last layer and writes **only the keys that differ from the package**, so a
prompt left alone keeps following the package when it is improved. The runtime renders templates with a closed list
of ``{fields}``: a template may drop a field but never name one the package prompt does not offer.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

PREFIX = "p."


def N_(message):
    return message


# (id, title, description, keys); a key that matches no group goes to "Other"
GROUPS: List[Tuple[str, str, str, List[str]]] = [
    ("persona", N_("Agents and pages"), N_("Who the model is told it is: the system prompt of an agent, of a news page, and how personality traits are worded."),
     ["persona_system", "page_system", "persona_big_five", "persona_custom"]),
    ("session", N_("Sessions"), N_("What the model receives at the start of a session of an agent or a news page, and how the date is written."),
     ["session_user", "page_user", "datetime_line", "weekdays", "nothing_new"]),
    ("feed", N_("Messages in the feed"), N_("How each message the agent reads is shown to it."),
     ["feed_item", "feed_forwarded", "feed_reply_to", "feed_addressed", "feed_thread_context", "feed_search_hit"]),
    ("chats", N_("Chat lists"), N_("How the chats the agent owns, follows or could join are listed."),
     ["owned_channels", "chat_line", "chat_about", "followed_chats", "followed_line", "joinable_chats", "joinable_line",
      "forum_chats", "forum_line", "rename_chats", "rename_line", "create_topics", "no_weights", "role_names", "chat_type_names"]),
    ("topics", N_("Topics of the posts"), N_("How the topic and the chat of each post the agent has to write are given."),
     ["topic_header", "topic_line_any", "topic_line", "topic_line_open", "topic_off_note"]),
    ("actions", N_("Action instructions"), N_("What the model is told about the fields each action needs."),
     ["help_reply", "help_react", "help_create_chat", "help_join", "help_leave", "help_read", "help_search", "help_private",
      "help_create_topic", "help_delete_topic", "help_rename_chat"]),
    ("stress", N_("Stress"), N_("How the stress level is worded when stress/reward is on."),
     ["stress_level_none", "stress_level_slight", "stress_level_moderate", "stress_level_high", "stress_level_extreme",
      "stress_level_block"]),
]


def prompt_file(folder: str, language: str) -> Path:
    return Path(folder) / ("prompts_im.json" if language == "en" else f"prompts_im.{language}.json")


def _runtime():
    from y_web.src.im.engine import ensure_im_importable

    ensure_im_importable()
    from yinstantmessaging import prompt_store
    from yinstantmessaging.client import prompts

    return prompt_store, prompts


def language_of(experiment) -> str:
    prompt_store, _prompts = _runtime()
    return prompt_store._clean(getattr(experiment, "prompt_language", None) or "en")


def base_templates(language: str) -> Dict[str, Any]:
    """The package prompts of ``language`` (English underneath, as the runtime layers them)."""
    _store, prompts = _runtime()
    return dict(prompts.SimPrompts(None, language).templates)


def custom_templates(folder: str, language: str) -> Dict[str, Any]:
    try:
        data = json.loads(prompt_file(folder, language).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def fields_of(text: str) -> set:
    """The ``{fields}`` a template names (the root of each one)."""
    store, _prompts = _runtime()
    return {m.group("root") or m.group("jroot") for m in store._FIELD.finditer(text or "")}


def sections(base: Dict[str, Any], custom: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The page model: groups of ``{key, kind, value, default, modified, fields}`` items."""
    placed, out = set(), []
    for gid, title, descr, keys in GROUPS:
        items = [_item(k, base, custom) for k in keys if k in base]
        placed.update(keys)
        if items:
            out.append({"id": gid, "title": title, "descr": descr, "items": items})
    rest = [_item(k, base, custom) for k in base if k not in placed]
    if rest:
        out.append({"id": "other", "title": N_("Other"), "descr": N_("Prompts that belong to no section above."), "items": rest})
    return out


def _item(key: str, base: Dict[str, Any], custom: Dict[str, Any]) -> Dict[str, Any]:
    default = base[key]
    value = custom.get(key, default)
    if isinstance(default, dict):
        kind = "map"
        value = {sub: (value.get(sub, default[sub]) if isinstance(value, dict) else default[sub]) for sub in default}
        fields = set()
    elif isinstance(default, list):
        kind = "list"
        value = value if isinstance(value, list) and len(value) == len(default) else default
        fields = set()
    else:
        kind = "text"
        value = value if isinstance(value, str) else default
        fields = fields_of(default)
    return {
        "key": key,
        "kind": kind,
        "value": value,
        "modified": key in custom and custom[key] != default,
        "fields": sorted(fields),
        "rows": min(10, max(2, str(value).count("\n") + 1 + len(str(value)) // 90)) if kind == "text" else 1,
    }


def parse_form(form, base: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """``(override, errors)``: the keys whose submitted value differs from the package, validated."""
    override: Dict[str, Any] = {}
    errors: List[str] = []
    for key, default in base.items():
        if isinstance(default, dict):
            got = {sub: form.get(f"{PREFIX}{key}.{sub}") for sub in default}
            if all(v is None for v in got.values()):
                continue
            new = {sub: (v.strip() if v is not None else default[sub]) for sub, v in got.items()}
            if any(not v for v in new.values()):
                errors.append(f"{key}: no value can be empty")
            elif new != default:
                override[key] = new
        elif isinstance(default, list):
            raw = form.get(f"{PREFIX}{key}")
            if raw is None:
                continue
            new = [x.strip() for x in raw.split(",")]
            if len(new) != len(default) or any(not x for x in new):
                errors.append(f"{key}: {len(default)} comma-separated values are needed")
            elif new != default:
                override[key] = new
        else:
            raw = form.get(f"{PREFIX}{key}")
            if raw is None:
                continue
            new = raw.replace("\r\n", "\n")
            if new == default:
                continue
            if not new.strip():
                errors.append(f"{key}: the prompt cannot be empty")
                continue
            extra = fields_of(new) - fields_of(default)
            if extra:
                errors.append(f"{key}: unknown field {{{sorted(extra)[0]}}}")
                continue
            override[key] = new
    return override, errors


def save(folder: str, language: str, override: Dict[str, Any]) -> None:
    path = prompt_file(folder, language)
    if not override:
        if path.exists():
            os.remove(path)
        return
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(override, indent=4, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
