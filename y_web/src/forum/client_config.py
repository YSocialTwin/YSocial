"""Client configuration of a forum experiment on YForum (plan F12, strada B).

The form of a forum HPC client offers only what YForum reads. This module turns the posted values into the
``client_config.json`` of YForum, whose schema is strict: out-of-range values are refused with a message instead of being
written, and the experiment switches (annotations, opinions, stress/reward, memory) come from the server configuration
through :func:`y_web.src.forum.experiment_config.apply_switches_to_client`. The module is pure: no Flask, no database.
"""

from typing import Any, Dict, Iterable, Mapping, Optional

from y_web.src.forum.experiment_config import apply_switches_to_client

# the actions of the forum a client can be asked to perform, with the default weight YForum uses
ACTIONS = ("post", "comment", "read", "search", "share", "share_link", "image")
DEFAULT_LIKELIHOOD = {
    "post": 0.2,
    "comment": 0.5,
    "read": 0.2,
    "search": 0.1,
    "share": 0.0,
    "share_link": 0.0,
    "image": 0.0,
}


class ForumClientFormError(ValueError):
    """A value of the client form is missing or out of range."""


def _number(form, key, kind, lo, hi, default):
    raw = form.get(key)
    if raw in (None, ""):
        return default
    try:
        value = kind(raw)
    except (TypeError, ValueError):
        raise ForumClientFormError(f"{key} must be a number") from None
    if not lo <= value <= hi:
        raise ForumClientFormError(f"{key} must be between {lo} and {hi}")
    return value


def parse_client_form(
    form: Mapping[str, Any],
    *,
    content_recsys: Iterable[str],
    follow_recsys: Iterable[str],
) -> Dict[str, Any]:
    """Validate the posted values; return the typed values the configuration is built from.

    ``content_recsys`` and ``follow_recsys`` are the recommender names the experiment accepts.
    """
    content_names, follow_names = list(content_recsys), list(follow_recsys)
    content = (form.get("content_recsys") or "").strip() or None
    follow = (form.get("follow_recsys") or "").strip() or None
    if content is not None and content not in content_names:
        raise ForumClientFormError(f"unknown content recommender {content!r}")
    if follow is not None and follow not in follow_names:
        raise ForumClientFormError(f"unknown follow recommender {follow!r}")

    likelihood = {
        action: _number(form, f"likelihood_{action}", float, 0.0, 1.0, default)
        for action, default in DEFAULT_LIKELIHOOD.items()
    }
    if not sum(likelihood.values()) > 0:
        raise ForumClientFormError("at least one action must have a weight above 0")

    return {
        "days": _number(form, "days", int, 1, 3650, 3),
        "percentage_new_agents_iteration": _number(
            form, "percentage_new_agents_iteration", float, 0.0, 1.0, 0.0
        ),
        "percentage_removed_agents_iteration": _number(
            form, "percentage_removed_agents_iteration", float, 0.0, 1.0, 0.0
        ),
        "actions_likelihood": likelihood,
        "max_length_thread_reading": _number(
            form, "max_length_thread_reading", int, 1, 100, 4
        ),
        "reading_from_follower_ratio": _number(
            form, "reading_from_follower_ratio", float, 0.0, 1.0, 0.6
        ),
        "probability_of_daily_follow": _number(
            form, "probability_of_daily_follow", float, 0.0, 1.0, 0.1
        ),
        "probability_of_secondary_follow": _number(
            form, "probability_of_secondary_follow", float, 0.0, 1.0, 0.0
        ),
        "probability_of_follow_back": _number(
            form, "probability_of_follow_back", float, 0.0, 1.0, 0.0
        ),
        "attention_window": _number(form, "attention_window", int, 1, 100000, 336),
        "content_recsys": content,
        "follow_recsys": follow,
        "n_posts": _number(form, "n_posts", int, 1, 1000, 10),
        "n_neighbors": _number(form, "n_neighbors", int, 1, 1000, 10),
        "leaning_bias": _number(form, "leaning_bias", float, 0.0, 100.0, 1.5),
        "subreddit_vibe": (form.get("subreddit_vibe") or "").strip(),
        "llm_model": (form.get("llm_model") or "").strip(),
        "llm_url": (form.get("llm_url") or "").strip(),
        "llm_api_key": (form.get("llm_api_key") or "").strip(),
        "llm_max_tokens": _number(form, "llm_max_tokens", int, 1, 100000, 800),
        "llm_temperature": _number(form, "llm_temperature", float, 0.0, 2.0, 0.6),
    }


def build_client_config(
    values: Mapping[str, Any],
    *,
    client_name: str,
    population_file: str,
    owner: str,
    llm_agents_enabled: bool,
    language: str,
    server_config: Mapping[str, Any],
    switches: Optional[Mapping[str, bool]] = None,
    stress_reward_config: Optional[Dict[str, Any]] = None,
    network_file: Optional[str] = None,
) -> Dict[str, Any]:
    """The ``client_config.json`` of a forum client.

    The number of slots per day and the seed come from the server configuration (YForum refuses a client that disagrees
    with its server on the slots). Annotations are the server's; the client carries the emotion switch, the opinion
    dynamics, stress/reward and memory.
    """
    if llm_agents_enabled and not values.get("llm_model"):
        raise ForumClientFormError("llm_model is required for language-model agents")
    slots = int(
        (server_config.get("simulation") or {}).get("num_slots_per_day", 24) or 24
    )

    config: Dict[str, Any] = {
        "client_name": client_name,
        "mode": "llm" if llm_agents_enabled else "rule_based",
        "num_days": int(values["days"]),
        "num_slots_per_day": slots,
        "seed": int(server_config.get("seed", 0) or 0),
        "owner": owner,
        "simulation": {
            "name": client_name,
            "percentage_new_agents_iteration": values[
                "percentage_new_agents_iteration"
            ],
            "percentage_removed_agents_iteration": values[
                "percentage_removed_agents_iteration"
            ],
            "actions_likelihood": dict(values["actions_likelihood"]),
        },
        "agents": {
            "llm_agents": [values["llm_model"]] if llm_agents_enabled else [None],
            "max_length_thread_reading": values["max_length_thread_reading"],
            "reading_from_follower_ratio": values["reading_from_follower_ratio"],
            "probability_of_daily_follow": values["probability_of_daily_follow"],
            "probability_of_secondary_follow": values[
                "probability_of_secondary_follow"
            ],
            "probability_of_follow_back": values["probability_of_follow_back"],
            "attention_window": values["attention_window"],
        },
        "population": {"file": population_file, "format": "auto"},
        "recsys": {
            "n_posts": values["n_posts"],
            "n_neighbors": values["n_neighbors"],
            "leaning_bias": values["leaning_bias"],
        },
    }
    if values.get("subreddit_vibe"):
        config["simulation"]["subreddit_vibe"] = values["subreddit_vibe"]
    if values.get("content_recsys"):
        config["recsys"]["content"] = values["content_recsys"]
    if values.get("follow_recsys"):
        config["recsys"]["follow"] = values["follow_recsys"]
    if network_file:
        config["population"]["network_file"] = network_file

    if llm_agents_enabled:
        servers: Dict[str, Any] = {
            "llm_max_tokens": values["llm_max_tokens"],
            "llm_temperature": values["llm_temperature"],
        }
        if values.get("llm_url"):
            servers["llm"] = values["llm_url"]
        if values.get("llm_api_key"):
            servers["llm_api_key"] = values["llm_api_key"]
        config["servers"] = servers
        config["llm"] = {"backend": "compat", "language": language or "en"}

    switches = dict(switches or {})
    apply_switches_to_client(
        config,
        emotion=switches.get("emotion"),
        opinion=switches.get("opinion"),
        stress_reward=switches.get("stress_reward"),
        memory=switches.get("memory") if llm_agents_enabled else False,
        stress_reward_config=stress_reward_config,
    )
    return config
