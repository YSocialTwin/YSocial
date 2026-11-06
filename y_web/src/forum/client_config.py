"""Client configuration of a forum experiment on YForum (plan F12, strada B).

The form is the one of the standard forum client: every parameter YForum implements is offered and written under the
key YForum reads. Three things of the standard form have no counterpart in YForum and are not offered: the archetypes
(YForum refuses to enable them), the real-time clock and the endless duration. The experiment switches (annotations,
opinions, stress/reward, memory) come from the server configuration through
:func:`y_web.src.forum.experiment_config.apply_switches_to_client`. The module is pure: no Flask, no database.
"""

from typing import Any, Dict, Iterable, Mapping, Optional

from y_web.src.forum.experiment_config import apply_switches_to_client

# the recommenders of YForum's registry (content and follow); the form offers those the catalog also lists
FORUM_CONTENT_RECSYS = (
    "CommonInterests",
    "CommonUserInterests",
    "HotRanking",
    "MostCommented",
    "ReverseChrono",
    "ReverseChronoComments",
    "ReverseChronoFollowers",
    "ReverseChronoFollowersPopularity",
    "ReverseChronoPopularity",
    "SimilarUsersPosts",
    "SimilarUsersReactions",
    "TopRanking",
)
FORUM_FOLLOW_RECSYS = (
    "AdamicAdar",
    "CommonNeighbors",
    "Jaccard",
    "PreferentialAttachment",
)

DEFAULT_HOURLY = {
    "0": 0.023, "1": 0.021, "2": 0.020, "3": 0.020, "4": 0.018, "5": 0.017,
    "6": 0.017, "7": 0.018, "8": 0.020, "9": 0.020, "10": 0.021, "11": 0.022,
    "12": 0.024, "13": 0.027, "14": 0.030, "15": 0.032, "16": 0.032, "17": 0.032,
    "18": 0.032, "19": 0.031, "20": 0.030, "21": 0.029, "22": 0.027, "23": 0.025,
}  # fmt: skip

# the relative weights of the actions (0-10, as in the standard form); share_image feeds YForum's ``image`` action
ACTION_WEIGHTS = {
    "post": 3.0,
    "comment": 5.0,
    "read": 2.0,
    "search": 1.0,
    "share_link": 2.0,
    "share_image": 2.0,
}

# the agent memory parameters: form name -> (kind, default); they carry the same name in YForum's ``agents``
MEMORY_FIELDS = {
    "memory_pair_limit": ("int", 5),
    "memory_prompt_max_chars": ("int", 1600),
    "memory_social_decay_lambda": ("float", 0.05),
    "memory_social_corruption_rate": ("float", 0.02),
    "memory_social_resummarize_every_events": ("int", 4),
    "memory_thread_decay_lambda": ("float", 0.03),
    "memory_thread_corruption_rate": ("float", 0.01),
    "memory_thread_resummarize_every_events": ("int", 4),
    "memory_evidence_tail_max": ("int", 8),
    "memory_digest_update_cadence_rounds": ("int", 3),
    "memory_digest_events_limit": ("int", 80),
    "memory_cold_start_window": ("int", 5),
    "memory_semantic_enabled": ("bool", False),
    "memory_search_k": ("int", 8),
    "memory_search_max_chars": ("int", 900),
    "memory_search_time_window_rounds": ("int", 40),
    "memory_tier_a_max_chars": ("int", 350),
    "memory_tier_b_max_chars": ("int", 900),
    "memory_tier_c_max_chars": ("int", 900),
    "memory_total_max_chars": ("int", 2200),
    "memory_tier_c_uncertainty_threshold": ("float", 0.45),
    "memory_reflection_cadence_rounds": ("int", 3),
    "memory_reflection_min_events": ("int", 12),
    "memory_reflection_trigger_importance_sum": ("float", 3.5),
    "memory_reflection_max_items_per_run": ("int", 60),
    "memory_embedding_model": ("str", "snowflake-arctic-embed:110m"),
    "memory_embedding_async": ("bool", False),
    "memory_importance_mode": ("str", "heuristic_then_batch_llm"),
}

LLM_DEFAULTS = {
    "llm": "http://127.0.0.1:11434/v1",
    "llm_api_key": "NULL",
    "llm_max_tokens": -1,
    "llm_temperature": 1.5,
    "llm_v_agent": "qwen3-vl:8b",
    "llm_v": "http://127.0.0.1:11434/v1",
    "llm_v_api_key": "NULL",
    "llm_v_max_tokens": 300,
    "llm_v_temperature": 0.5,
}


class ForumClientFormError(ValueError):
    """A value of the client form is missing or out of range."""


_TRUE = {"on", "true", "1", "yes"}


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


def _flag(form, key) -> bool:
    return str(form.get(key) or "").strip().lower() in _TRUE


def parse_client_form(
    form: Mapping[str, Any],
    *,
    content_recsys: Iterable[str] = FORUM_CONTENT_RECSYS,
    follow_recsys: Iterable[str] = FORUM_FOLLOW_RECSYS,
) -> Dict[str, Any]:
    """Validate the posted values; return the typed values the configuration is built from.

    ``content_recsys`` and ``follow_recsys`` are the recommender names the experiment accepts.
    """
    content_names, follow_names = list(content_recsys), list(follow_recsys)
    content = (form.get("recsys_type") or form.get("content_recsys") or "").strip()
    follow = (form.get("frecsys_type") or form.get("follow_recsys") or "").strip()
    # the first option of each list ("ContentRecSys", "FollowRecSys") and "random" mean the experiment's recommender
    content = None if content in ("", "random", "ContentRecSys") else content
    follow = None if follow in ("", "random", "default", "FollowRecSys") else follow
    if content is not None and content not in content_names:
        raise ForumClientFormError(f"unknown content recommender {content!r}")
    if follow is not None and follow not in follow_names:
        raise ForumClientFormError(f"unknown follow recommender {follow!r}")

    weights = {
        action: _number(form, action, float, 0.0, 10.0, default)
        for action, default in ACTION_WEIGHTS.items()
    }
    if not sum(weights.values()) > 0:
        raise ForumClientFormError("at least one action must have a weight above 0")

    hourly = {}
    for hour in range(24):
        raw = form.get(f"hourly_{hour}")
        hourly[str(hour)] = (
            _number({"v": raw}, "v", float, 0.0, 1.0, DEFAULT_HOURLY[str(hour)])
            if raw not in (None, "")
            else DEFAULT_HOURLY[str(hour)]
        )

    memory: Dict[str, Any] = {}
    for key, (kind, default) in MEMORY_FIELDS.items():
        if kind == "bool":
            memory[key] = _flag(form, key)
        elif kind == "str":
            memory[key] = (form.get(key) or "").strip() or default
        elif kind == "int":
            memory[key] = _number(form, key, int, 0, 10**9, default)
        else:
            memory[key] = _number(form, key, float, 0.0, 10**9, default)
    if not memory["memory_semantic_enabled"]:
        memory["memory_embedding_async"] = False

    initial = form.get("initial_agents")
    starting = None
    if initial not in (None, ""):
        starting = _number(form, "initial_agents", int, 1, 10**7, None)

    llm: Dict[str, Any] = {}
    for key, default in LLM_DEFAULTS.items():
        if isinstance(default, int) and not isinstance(default, bool):
            llm[key] = _number(form, key, int, -1, 10**6, default)
        elif isinstance(default, float):
            llm[key] = _number(form, key, float, 0.0, 5.0, default)
        else:
            llm[key] = (form.get(key) or "").strip() or default

    # "Run until stopped": days = -1, as in every other client form; YForum's ``num_days`` 0 means until stopped
    days = (
        -1
        if _flag(form, "infinite_duration") or str(form.get("days")).strip() == "-1"
        else _number(form, "days", int, 1, 3650, 30)
    )
    return {
        "days": days,
        "starting_agents": starting,
        "percentage_new_agents_iteration": _number(
            form, "percentage_new_agents_iteration", float, 0.0, 1.0, 0.07
        ),
        "percentage_removed_agents_iteration": _number(
            form, "percentage_removed_agents_iteration", float, 0.0, 1.0, 0.014
        ),
        "weights": weights,
        "hourly_activity": hourly,
        "visibility_rounds": _number(form, "visibility_rounds", int, 1, 100000, 36),
        "max_length_thread_reading": _number(
            form, "max_length_thread_reading", int, 1, 1000, 4
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
        "max_thread_context_chars": _number(
            form, "max_thread_context_chars", int, 1, 10**6, 3200
        ),
        "max_replies_per_round": _number(
            form, "max_replies_per_round", int, 0, 1000, 2
        ),
        "reply_cooldown_rounds": _number(
            form, "reply_cooldown_rounds", int, 0, 100000, 2
        ),
        "content_recsys": content,
        "follow_recsys": follow,
        "memory": memory,
        "llm": llm,
        # the model is chosen with the client (the "LLM Model" field of the standard form, ``user_type``)
        "llm_model": (form.get("user_type") or form.get("llm_model") or "").strip(),
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
    population_attributes: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """The ``client_config.json`` of a forum client.

    ``llm_agents_enabled`` is the experiment's switch: the agents then use the model chosen in the form (required),
    otherwise they are rule-based. The number of slots per day
    and the seed come from the server configuration (YForum refuses a client that disagrees with its server on the
    slots). ``population_attributes`` (leanings, ages, toxicity levels, languages, education levels of the population)
    fill the ``agents`` section as in the standard form.
    """
    llm_enabled = bool(llm_agents_enabled)
    if llm_enabled and not values.get("llm_model"):
        raise ForumClientFormError("select the LLM model of the agents")
    slots = int(
        (server_config.get("simulation") or {}).get("num_slots_per_day", 24) or 24
    )
    weights = values["weights"]
    llm = values["llm"]

    config: Dict[str, Any] = {
        "client_name": client_name,
        "mode": "llm" if llm_enabled else "rule_based",
        "num_days": 0 if int(values["days"]) == -1 else int(values["days"]),
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
            "hourly_activity": dict(values["hourly_activity"]),
            # YForum's schema takes weights in [0, 1]: the form's 0-10 scale divided by ten (the choice is weighted,
            # so the relative weights are the ones of the standard form)
            "actions_likelihood": {
                "post": weights["post"] / 10,
                "comment": weights["comment"] / 10,
                "read": weights["read"] / 10,
                "search": weights["search"] / 10,
                "share_link": weights["share_link"] / 10,
                "image": weights["share_image"] / 10,
            },
        },
        "posts": {"visibility_rounds": values["visibility_rounds"]},
        "agents": {
            "llm_agents": [values["llm_model"]] if llm_enabled else [None],
            "max_length_thread_reading": values["max_length_thread_reading"],
            "reading_from_follower_ratio": values["reading_from_follower_ratio"],
            "probability_of_daily_follow": values["probability_of_daily_follow"],
            "probability_of_secondary_follow": values[
                "probability_of_secondary_follow"
            ],
            "probability_of_follow_back": values["probability_of_follow_back"],
            "attention_window": values["attention_window"],
            "max_thread_context_chars": values["max_thread_context_chars"],
            "max_replies_per_round": values["max_replies_per_round"],
            "reply_cooldown_rounds": values["reply_cooldown_rounds"],
        },
        "population": {"file": population_file, "format": "auto"},
        "recsys": {},
    }
    if values.get("starting_agents"):
        config["simulation"]["starting_agents"] = values["starting_agents"]
    if values.get("content_recsys"):
        config["recsys"]["content"] = values["content_recsys"]
    if values.get("follow_recsys"):
        config["recsys"]["follow"] = values["follow_recsys"]
    if network_file:
        config["population"]["network_file"] = network_file

    attrs = population_attributes or {}
    agents = config["agents"]
    for source, target in (
        ("political_leanings", "political_leanings"),
        ("toxicity_levels", "toxicity_levels"),
        ("languages", "languages"),
        ("education_levels", "education_levels"),
    ):
        if attrs.get(source):
            agents[target] = list(attrs[source])
    ages = attrs.get("ages")
    if ages:
        agents["age"] = {"min": min(ages), "max": max(ages)}

    if llm_enabled:
        # YForum needs a positive token limit: "-1" (no limit) of the standard form keeps YForum's default of 800
        config["servers"] = {
            "llm": llm["llm"],
            "llm_api_key": llm["llm_api_key"],
            "llm_temperature": llm["llm_temperature"],
            "llm_v": llm["llm_v"],
            "llm_v_api_key": llm["llm_v_api_key"],
            "llm_v_temperature": llm["llm_v_temperature"],
        }
        for key in ("llm_max_tokens", "llm_v_max_tokens"):
            if llm[key] >= 1:
                config["servers"][key] = llm[key]
        agents["llm_v_agent"] = [llm["llm_v_agent"]]
        config["llm"] = {"backend": "compat", "language": language or "en"}
        agents.update(values["memory"])

    switches = dict(switches or {})
    apply_switches_to_client(
        config,
        emotion=switches.get("emotion"),
        opinion=switches.get("opinion"),
        stress_reward=switches.get("stress_reward"),
        memory=switches.get("memory") if llm_enabled else False,
        stress_reward_config=stress_reward_config,
    )
    return config
