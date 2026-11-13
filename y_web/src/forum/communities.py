"""The ``communities`` section of a forum client configuration (opt-in, off by default).

Two actions of the agents, read by YClientReddit (Standard forum) and YForum (HPC forum) from the key ``communities``:

* ``creation``: before a post an agent founds, with ``probability``, a new thematic community (a topic); ``max_topics``
  caps the communities of the forum (0 = no cap);
* ``crosspost``: after a post an agent shows it, with ``probability``, in up to ``max_per_post`` related communities.

The module is pure: no Flask, no database. The form fields are ``communities_creation`` (checkbox),
``communities_creation_probability``, ``communities_max_topics``, ``communities_crosspost`` (checkbox),
``communities_crosspost_probability`` and ``communities_max_per_post``.
"""

from typing import Any, Dict, Mapping, Optional

DEFAULTS = {
    "creation": {"enabled": False, "probability": 0.05, "max_topics": 0},
    "crosspost": {"enabled": False, "probability": 0.15, "max_per_post": 1},
}
_TRUE = {"on", "true", "1", "yes"}


class CommunitiesFormError(ValueError):
    """A value of the form is out of range."""


def _number(form, key, kind, lo, hi, default):
    raw = form.get(key)
    if raw in (None, ""):
        return default
    try:
        value = kind(raw)
    except (TypeError, ValueError):
        raise CommunitiesFormError(f"{key} must be a number") from None
    if not lo <= value <= hi:
        raise CommunitiesFormError(f"{key} must be between {lo} and {hi}")
    return value


def parse_form(form: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The typed values of the two actions from the posted form (absent fields: the defaults, both off)."""
    flag = lambda key: str(form.get(key) or "").strip().lower() in _TRUE  # noqa: E731
    creation, crosspost = DEFAULTS["creation"], DEFAULTS["crosspost"]
    return {
        "creation": {
            "enabled": flag("communities_creation"),
            "probability": _number(
                form,
                "communities_creation_probability",
                float,
                0.0,
                1.0,
                creation["probability"],
            ),
            "max_topics": _number(
                form, "communities_max_topics", int, 0, 100000, creation["max_topics"]
            ),
        },
        "crosspost": {
            "enabled": flag("communities_crosspost"),
            "probability": _number(
                form,
                "communities_crosspost_probability",
                float,
                0.0,
                1.0,
                crosspost["probability"],
            ),
            "max_per_post": _number(
                form, "communities_max_per_post", int, 1, 20, crosspost["max_per_post"]
            ),
        },
    }


def config_section(values: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The ``communities`` key to write into the client configuration; ``None`` when both actions are off (the key is
    then left out and the clients behave as before)."""
    if not values or not any(
        (values.get(name) or {}).get("enabled") for name in DEFAULTS
    ):
        return None
    return {name: dict(values[name]) for name in DEFAULTS}
