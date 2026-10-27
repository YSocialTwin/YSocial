"""Structured form of the IM client's advanced settings (pure functions, no Flask).

The client form of instant messaging (IM) exposes every setting a researcher may need as a typed field, not as
a free JSON text. One declarative table (:data:`GROUPS`) drives the three uses: the template renders the
fields, :func:`parse_fields` reads and validates the submitted values, and the tests check the table against
IM's JSON schema (``schemas/config/client_config.json``), so a default or a bound cannot drift unnoticed.

A field is ``(path, kind, label, default, bounds)``: ``path`` is the dotted key in the client configuration,
``kind`` one of ``int``/``float``/``bool``/``choice``/``text``, ``bounds`` ``(lo, hi)`` or the choices.
Booleans travel with a hidden ``<name>__present`` marker, because an unchecked box submits nothing.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple

PREFIX = "adv."


def N_(message):
    """Mark a label for extraction without translating it (the template and the errors translate it)."""
    return message


Field = Tuple[str, str, str, Any, Any]
Group = Tuple[str, str, str, List[Field]]


class AdvancedSettingsError(ValueError):
    """A submitted advanced value is invalid (the message names the field)."""


_P = 10**6  # an upper bound that only guards against absurd values

# --- the main table -------------------------------------------------------------------------------
GROUPS: List[Group] = [
    (
        "scheduling",
        N_("Scheduling"),
        N_("How many sessions an agent may open in a round."),
        [
            ("telegram.scheduling.multi_session_min_level", "int", N_("Minimum activity level for several sessions"), 4, (0, 100)),
            ("telegram.scheduling.extra_session_rate", "float", N_("Extra session rate"), 0.5, (0, 100)),
            ("telegram.scheduling.max_sessions_per_round", "int", N_("Maximum sessions per round"), 3, (1, 100)),
        ],
    ),
    (
        "topology",
        N_("Chat Topology"),
        N_("How chats, channels and their owners are generated."),
        [
            ("telegram.topology.generate_if_missing", "bool", N_("Generate the topology if missing"), True, None),
            ("telegram.topology.shared_across_clients", "bool", N_("Share the topology across clients"), False, None),
            ("telegram.topology.max_owned_chats", "int", N_("Maximum chats owned by an agent"), 2, (1, 1000)),
            ("telegram.topology.channel_owner_share", "float", N_("Share of agents owning a channel"), 0.1, (0, 1)),
            ("telegram.topology.discussion_share", "float", N_("Share of channels with a discussion group"), 0.5, (0, 1)),
            ("telegram.topology.network_ignores_topics", "bool", N_("Ignore topics when building the network"), False, None),
        ],
    ),
    (
        "topics",
        N_("Topics and Chats"),
        N_("How the experiment topics map onto agents and chats."),
        [
            ("telegram.topics.assignment", "choice", N_("Topic assignment"), "from_population", ("from_population", "assign", "merge")),
            ("telegram.topics.topics_per_agent", "int", N_("Topics per agent"), 3, (1, 1000)),
            ("telegram.topics.on_unmapped", "choice", N_("Unmapped topics"), "warn_drop", ("warn_drop", "error")),
            ("telegram.topics.chats_per_topic", "int", N_("Chats per topic"), 2, (1, 1000)),
            ("telegram.topics.channel_topics_k", "int", N_("Topics per channel"), 2, (1, 1000)),
            ("telegram.topics.auto_topic_group", "bool", N_("Create a group for each topic"), True, None),
            ("telegram.topics.off_topic_rate", "float", N_("Off-topic rate"), 0.05, (0, 1)),
        ],
    ),
    (
        "attention",
        N_("Attention"),
        N_("Which chats an agent looks at in a session and how they are ranked."),
        [
            ("telegram.attention.max_chats_per_session", "int", N_("Maximum chats per session"), 5, (1, 1000)),
            ("telegram.attention.notifications_always_offered", "bool", N_("Always offer chats with notifications"), True, None),
            ("telegram.attention.owned_always", "bool", N_("Always offer owned chats"), True, None),
            ("telegram.attention.weights.notifications", "float", N_("Weight of notifications"), 3.0, (0, _P)),
            ("telegram.attention.weights.topic_affinity", "float", N_("Weight of topic affinity"), 2.0, (0, _P)),
            ("telegram.attention.weights.recent_activity", "float", N_("Weight of recent activity"), 1.0, (0, _P)),
        ],
    ),
    (
        "reactive",
        N_("Reactive Replies"),
        N_("Replies and reactions triggered by the activity of other agents."),
        [
            ("telegram.reactive.enabled", "bool", N_("Enable reactive replies"), True, None),
            ("telegram.reactive.probability", "float", N_("Probability of reacting"), 0.7, (0, 1)),
            ("telegram.reactive.median_minutes", "float", N_("Median reaction delay (minutes)"), 8.0, (0, 10080)),
            ("telegram.reactive.sigma", "float", N_("Spread of the reaction delay"), 1.0, (0, 100)),
            ("telegram.reactive.max_per_round", "int", N_("Maximum reactions per round"), 3, (0, 1000)),
            ("telegram.reactive.max_chain_depth", "int", N_("Maximum chain depth"), 6, (1, 1000)),
            ("telegram.reactive.max_wait_rounds", "int", N_("Maximum wait (rounds)"), 24, (1, 100000)),
            ("telegram.reactive.actions_likelihood.reply", "float", N_("Reactive reply likelihood"), 4.0, (0, _P)),
            ("telegram.reactive.actions_likelihood.react", "float", N_("Reactive reaction likelihood"), 3.0, (0, _P)),
            ("telegram.reactive.actions_likelihood.forward", "float", N_("Reactive forward likelihood"), 1.0, (0, _P)),
            ("telegram.reactive.actions_likelihood.post", "float", N_("Reactive post likelihood"), 0.5, (0, _P)),
        ],
    ),
    (
        "discovery",
        N_("Chat Discovery"),
        N_("How agents find chats to join or leave."),
        [
            ("telegram.discovery.mode", "choice", N_("Discovery mode"), "llm", ("llm", "rule")),
            ("telegram.discovery.leave_prob", "float", N_("Probability of leaving a chat"), 0.05, (0, 1)),
        ],
    ),
    (
        "agent_actions",
        N_("Optional Agent Actions"),
        N_("Actions an agent may take besides posting, replying and reacting."),
        [
            ("telegram.agent_actions.forwarding.enabled", "bool", N_("Allow forwarding"), True, None),
            ("telegram.agent_actions.search.enabled", "bool", N_("Allow search"), True, None),
            ("telegram.agent_actions.search.likelihood", "float", N_("Search likelihood"), 0.5, (0, _P)),
            ("telegram.agent_actions.private_message.enabled", "bool", N_("Allow private messages"), True, None),
            ("telegram.agent_actions.private_message.likelihood", "float", N_("Private message likelihood"), 0.5, (0, _P)),
            ("telegram.agent_actions.forum_topics.enabled", "bool", N_("Allow forum topics"), True, None),
            ("telegram.agent_actions.forum_topics.create_likelihood", "float", N_("Forum topic creation likelihood"), 0.2, (0, _P)),
            ("telegram.agent_actions.forum_topics.delete_likelihood", "float", N_("Forum topic deletion likelihood"), 0.05, (0, _P)),
        ],
    ),
    (
        "baseline",
        N_("Baseline Activity"),
        N_("Background activity that does not come from the agents."),
        [
            ("telegram.baseline.policy", "choice", N_("Baseline policy"), "none", ("none", "static", "reactive")),
            ("telegram.baseline.beta", "float", N_("Baseline strength"), 0.5, (0, _P)),
        ],
    ),
    (
        "moderation",
        N_("Moderation"),
        N_("Automatic restrictions on the chats."),
        [
            ("telegram.moderation.policy", "choice", N_("Moderation policy"), "none", ("none", "rate_limit")),
            ("telegram.moderation.rate_limit_posts", "int", N_("Posts allowed before the limit"), 5, (2, 100000)),
            ("telegram.moderation.restrict_rounds", "int", N_("Restriction length (rounds)"), 24, (1, 100000)),
        ],
    ),
    (
        "emergence",
        N_("Emergence, Chat Creation and Forums"),
        N_("Chats that appear during the run."),
        [
            ("telegram.emergence.enabled", "bool", N_("Let chats emerge"), False, None),
            ("telegram.emergence.open_slot_rate", "float", N_("Open slot rate"), 0.02, (0, 1)),
            ("telegram.chat_creation.enabled", "bool", N_("Let agents create chats"), False, None),
            ("telegram.chat_creation.likelihood", "float", N_("Chat creation likelihood"), 0.1, (0, _P)),
            ("telegram.forum.enabled", "bool", N_("Enable forum chats"), False, None),
            ("telegram.forum.min_topics", "int", N_("Minimum topics of a forum"), 2, (2, 1000)),
        ],
    ),
    (
        "population",
        N_("Churn and New Agents"),
        N_("Agents leaving and joining during the run."),
        [
            ("agents.churn.enabled", "bool", N_("Enable churn"), False, None),
            ("agents.churn.churn_probability", "float", N_("Churn probability"), 0.01, (0, 1)),
            ("agents.churn.inactivity_threshold", "int", N_("Inactivity threshold (rounds)"), 5, (1, 100000)),
            ("agents.churn.churn_percentage", "float", N_("Maximum share of agents that churn"), 0.1, (0, 1)),
            ("agents.new_agents.enabled", "bool", N_("Enable new agents"), False, None),
            ("agents.new_agents.probability_new_agents", "float", N_("New agents probability"), 0.01, (0, 1)),
            ("agents.new_agents.percentage_new_agents", "float", N_("Share of new agents"), 0.01, (0, 1)),
        ],
    ),
    (
        "llm_runtime",
        N_("Language Model Reliability"),
        N_("Concurrency, timeouts and the failure guard of the language model calls."),
        [
            ("llm.max_concurrency", "int", N_("Maximum concurrent requests"), 8, (1, 1024)),
            ("llm.timeout_seconds", "float", N_("Timeout (seconds)"), 120.0, (1, 3600)),
            ("llm.max_retries", "int", N_("Maximum retries"), 3, (0, 100)),
            ("llm.pass_seed", "bool", N_("Pass the seed to the model"), True, None),
            ("llm.record_responses", "bool", N_("Record the responses"), False, None),
            ("llm.max_failed_session_ratio", "float", N_("Maximum share of failed sessions"), 0.5, (0, 1)),
            ("llm.failure_window_sessions", "int", N_("Failure window (sessions)"), 20, (1, 100000)),
            ("llm.failure_min_sessions", "int", N_("Failure minimum (sessions)"), 5, (1, 100000)),
            ("simulation.emotion_batch_size", "int", N_("Emotion annotation batch size"), 10, (1, 10000)),
        ],
    ),
    (
        "runtime",
        N_("Client Runtime"),
        N_("Timeouts and polling of the client process."),
        [
            ("ready_timeout_seconds", "float", N_("Ready timeout (seconds)"), 180.0, (1, 86400)),
            ("server_call_timeout_seconds", "float", N_("Server call timeout (seconds)"), 120.0, (1, 86400)),
            ("max_server_retries", "int", N_("Maximum server retries"), 3, (0, 1000)),
            ("shutdown_grace_seconds", "float", N_("Shutdown grace (seconds)"), 3.0, (0, 3600)),
            ("heartbeat_interval", "float", N_("Heartbeat interval (seconds)"), 5.0, (0.1, 3600)),
            ("barrier_poll_seconds", "float", N_("Barrier poll (seconds)"), 0.2, (0.01, 60)),
        ],
    ),
]

# the likelihood of each action of an agent, in the section "Agents' Actions Relevance"
# the score (0-10) the form shows times this factor is the weight written: joining and leaving chats are rare
ACTION_SCALE = {"join": 0.1, "leave": 0.05}

ACTIONS: List[Field] = [
    ("telegram.actions_likelihood.post", "float", N_("Post"), 2.0, (0, _P)),
    ("telegram.actions_likelihood.forward", "float", N_("Forward"), 2.0, (0, _P)),
    ("telegram.actions_likelihood.reply", "float", N_("Reply"), 3.0, (0, _P)),
    ("telegram.actions_likelihood.react", "float", N_("React"), 3.0, (0, _P)),
    ("telegram.actions_likelihood.join", "float", N_("Join"), 0.2, (0, _P)),
    ("telegram.actions_likelihood.leave", "float", N_("Leave"), 0.05, (0, _P)),
    ("telegram.actions_likelihood.read", "float", N_("Read"), 1.0, (0, _P)),
]

# the details of the agents' memory, in the section "Agent Memory"
MEMORY: List[Field] = [
    ("agents.memory_backend", "choice", N_("Memory backend"), "hybrid_semantic", ("hybrid_semantic", "simple_recent")),
    ("agents.memory_prompt_mode", "text", N_("Prompt mode"), "subtle_forum", None),
    ("agents.memory_vote_signal_only", "bool", N_("Votes only as a signal"), True, None),
    ("agents.memory_reply_context_max_chars", "int", N_("Reply context (characters)"), 280, (1, 100000)),
    ("agents.memory_total_max_chars", "int", N_("Total memory in the prompt (characters)"), 1400, (0, 100000)),
    ("agents.memory_cross_thread_callback_min_score", "float", N_("Minimum score to recall another thread"), 0.8, (0, 1)),
    ("agents.memory_rehydrate_rounds", "int", N_("Rehydrate window (rounds)"), 72, (0, 100000)),
    ("agents.memory_forget_deleted", "bool", N_("Forget deleted messages"), False, None),
    ("agents.memory_high_affect_enabled", "bool", N_("Recall emotionally charged episodes"), False, None),
    ("agents.memory_high_affect_rule_threshold", "float", N_("Rule threshold"), 0.55, (0, 1)),
    ("agents.memory_high_affect_uncertain_low", "float", N_("Uncertain band, low"), 0.35, (0, 1)),
    ("agents.memory_high_affect_uncertain_high", "float", N_("Uncertain band, high"), 0.7, (0, 1)),
    ("agents.memory_high_affect_search_k", "int", N_("Search top-k"), 12, (1, 1000)),
    ("agents.memory_high_affect_max_items", "int", N_("Maximum items"), 6, (1, 1000)),
    ("agents.memory_high_affect_max_chars", "int", N_("Maximum characters"), 900, (1, 100000)),
    ("agents.memory_high_affect_llm_fallback", "bool", N_("Ask the language model when uncertain"), True, None),
]


def field_name(path: str) -> str:
    """The form field name of a configuration path."""
    return PREFIX + path


def all_fields(*, memory: bool = True) -> List[Field]:
    fields: List[Field] = [f for _gid, _label, _descr, group in GROUPS for f in group]
    fields += ACTIONS
    if memory:
        fields += MEMORY
    return fields


def defaults(*, memory: bool = True) -> Dict[str, Any]:
    """``{path: default}`` of every field (what the form pre-fills)."""
    return {path: default for path, _k, _l, default, _b in all_fields(memory=memory)}


def _set_path(target: dict, path: str, value) -> None:
    keys = path.split(".")
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value


def _get_path(source: dict, path: str, default=None):
    for key in path.split("."):
        if not isinstance(source, dict) or key not in source:
            return default
        source = source[key]
    return source


def _flag(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_one(form, field: Field, label_of=lambda text: text):
    path, kind, label, _default, bounds = field
    name = field_name(path)
    if kind == "bool":
        if not form.get(name + "__present"):
            return None
        return _flag(form.get(name))
    raw = form.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    raw = str(raw).strip()
    if kind in ("int", "float"):
        try:
            value = int(raw) if kind == "int" else round(float(raw), 6)
        except ValueError:
            raise AdvancedSettingsError(f"{label_of(label)}: not a number") from None
        lo, hi = bounds
        if not lo <= value <= hi:
            raise AdvancedSettingsError(f"{label_of(label)}: must be between {lo} and {hi}")
        return value
    if kind == "choice":
        if raw not in bounds:
            raise AdvancedSettingsError(f"{label_of(label)}: must be one of {', '.join(bounds)}")
        return raw
    return raw  # text


def parse_fields(form, *, memory: bool = False, label_of=lambda text: text) -> Dict[str, Any]:
    """The nested configuration fragment submitted by the structured form (absent fields are left out).

    ``memory`` says whether the agent memory fields are read: they are ignored when the experiment has memory
    off, so a stale form cannot write them. ``label_of`` translates the labels in the error messages.
    """
    out: Dict[str, Any] = {}
    for field in all_fields(memory=memory):
        value = _parse_one(form, field, label_of)
        if value is not None:
            _set_path(out, field[0], value)
    _cross_checks(out, label_of)
    return out


def _cross_checks(fragment: dict, label_of) -> None:
    low = _get_path(fragment, "agents.memory_high_affect_uncertain_low")
    high = _get_path(fragment, "agents.memory_high_affect_uncertain_high")
    if low is not None and high is not None and low > high:
        raise AdvancedSettingsError(
            label_of(N_("The lower bound of the uncertain band cannot exceed the upper one"))
        )


def values_from_config(config: Optional[dict], *, memory: bool = True) -> Dict[str, Any]:
    """``{path: value}`` for every field, taking the value from ``config`` and the default otherwise."""
    config = config or {}
    return {
        path: _get_path(config, path, default)
        for path, _k, _l, default, _b in all_fields(memory=memory)
    }


def groups() -> Iterable[Group]:
    return GROUPS
