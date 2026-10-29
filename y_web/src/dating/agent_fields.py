"""Mapping between a YDating population agent and the standard YSocial agent tables (decision D-10).

A dating agent is stored as a row of ``agents`` (the columns YSocial already has: name, age, gender, language,
education, profession, personality labels, ...), interests as ``interest`` features and everything the standard
agent does not have as ``custom`` features of the table ``agents_custom_features``, with keys in the ``dating.``
namespace (``dating.profile.city``, ``dating.latent.attractiveness``, ``dating.photos`` ...). The admin pages that
already edit custom features therefore edit dating agents too; no file holds the population.

The module is pure (no Flask, no database): the two directions are ``agent_to_rows`` and ``rows_to_agent``, and
``rows_to_agent(*agent_to_rows(x)) == x`` for every document the YDating schema accepts.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

PREFIX = "dating."

# document field -> column of ``agents``
COLUMN_FIELDS = {
    "username": "name",
    "age": "age",
    "gender": "gender",
    "language": "language",
    "nationality": "nationality",
    "education_level": "education_level",
    "profession": "profession",
    "leaning": "leaning",
    "archetype": "archetype",
    "daily_activity_level": "daily_activity_level",
}
PERSONALITY = ("oe", "co", "ex", "ag", "ne")
# sections of the document stored one custom feature per key
SECTIONS = ("profile", "latent", "appearance", "affective_traits")
# top-level scalars without a column
SCALARS = ("id", "match_recsys")
# JSON-valued features
BLOBS = ("photos",)
# columns with a length limit (filled by ``set_limits``); a longer value is kept whole in a custom feature
_LIMITS: Dict[str, int] = {}

# default JSON types when the schema cannot be read: only strings are stored raw
_STRING_FIELDS = {
    "id",
    "match_recsys",
    "profile.city",
    "profile.intent",
    "profile.bio",
}


def set_limits(limits: Dict[str, int]) -> None:
    """Column name -> maximum length, taken from the ``Agent`` model by the database layer."""
    _LIMITS.clear()
    _LIMITS.update(limits)


def field_types(schema: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """``section.key`` / ``key`` -> JSON type of the field, from the YDating population schema."""
    out: Dict[str, str] = {}
    if not schema:
        return out
    defs = schema.get("definitions", {})
    agent_props = (defs.get("agent") or {}).get("properties", {})
    for key, spec in agent_props.items():
        if "type" in spec:
            out[key] = spec["type"]
    for section in SECTIONS:
        for key, spec in (defs.get(section) or {}).get("properties", {}).items():
            if "type" in spec:
                out[f"{section}.{key}"] = spec["type"]
            elif "enum" in spec:
                out[f"{section}.{key}"] = "string"
    return out


def _encode(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _decode(raw: Optional[str], path: str, types: Dict[str, str]) -> Any:
    declared = types.get(path)
    if declared is None:
        declared = "string" if path in _STRING_FIELDS else None
    if raw is None:
        return "" if declared == "string" else None
    if declared == "string":
        return raw
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _fits(column: str, value: Any) -> bool:
    limit = _LIMITS.get(column)
    return limit is None or not isinstance(value, str) or len(value) <= limit


def agent_to_rows(
    agent: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str], List[Dict[str, str]]]:
    """(columns of ``agents``, interests, custom features ``[{"key", "value"}]``) of one agent document."""
    columns: Dict[str, Any] = {}
    custom: List[Dict[str, str]] = []

    def put(key: str, value: Any) -> None:
        custom.append({"key": PREFIX + key, "value": _encode(value)})

    for field, column in COLUMN_FIELDS.items():
        if field not in agent:
            continue
        value = agent[field]
        if _fits(column, value):
            columns[column] = value
        else:  # the column is shorter than the value: the column keeps a cut copy, the feature the whole
            columns[column] = value[: _LIMITS[column]]
            put(field, value)
    for trait, value in (agent.get("personality") or {}).items():
        if trait in PERSONALITY and _fits(trait, value):
            columns[trait] = value
        else:
            if trait in PERSONALITY:
                columns[trait] = str(value)[: _LIMITS.get(trait, 50)]
            put(f"personality.{trait}", value)
    for key in SCALARS:
        if key in agent:
            put(key, agent[key])
    for section in SECTIONS:
        for key, value in (agent.get(section) or {}).items():
            put(f"{section}.{key}", value)
    for key in BLOBS:
        if key in agent:
            put(key, agent[key])
    present = [s for s in SECTIONS if agent.get(s) == {}]
    for section in present:  # an empty section is kept as such
        put(f"{section}", {})
    return columns, list(agent.get("interests") or []), custom


def rows_to_agent(
    columns: Dict[str, Any],
    interests: List[str],
    custom: Dict[str, Optional[str]],
    types: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """The agent document rebuilt from the column values, the interests and the ``custom`` features."""
    types = types or {}
    agent: Dict[str, Any] = {}
    feats = {k[len(PREFIX) :]: v for k, v in custom.items() if k.startswith(PREFIX)}
    for field, column in COLUMN_FIELDS.items():
        if field in feats:  # the whole value of an overflowing column
            agent[field] = feats[field]
        elif columns.get(column) is not None:
            agent[field] = columns[column]
    personality = {}
    for trait in PERSONALITY:
        if f"personality.{trait}" in feats:
            personality[trait] = feats[f"personality.{trait}"]
        elif columns.get(trait) not in (None,):
            personality[trait] = columns[trait]
    if personality:
        agent["personality"] = personality
    for key in SCALARS:
        if key in feats:
            agent[key] = _decode(feats[key], key, types)
    for section in SECTIONS:
        values = {}
        for key, raw in feats.items():
            if key.startswith(section + "."):
                name = key[len(section) + 1 :]
                values[name] = _decode(raw, key, types)
        if values or section in feats:
            agent[section] = values
    for key in BLOBS:
        if key in feats:
            agent[key] = _decode(feats[key], key, types)
    if interests:
        agent["interests"] = list(interests)
    return agent
