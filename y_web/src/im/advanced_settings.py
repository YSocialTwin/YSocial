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

Field = Tuple[str, str, str, Any, Any]
Group = Tuple[str, str, str, List[Field]]


class AdvancedSettingsError(ValueError):
    """A submitted advanced value is invalid (the message names the field)."""


_P = 10**6  # an upper bound that only guards against absurd values

# --- the main table -------------------------------------------------------------------------------
GROUPS: List[Group] = [
    (
        "scheduling",
        "Scheduling",
        "How many sessions an agent may open in a round.",
        [
            ("telegram.scheduling.multi_session_min_level", "int", "Minimum activity level for several sessions", 4, (0, 100)),
            ("telegram.scheduling.extra_session_rate", "float", "Extra session rate", 0.5, (0, 100)),
            ("telegram.scheduling.max_sessions_per_round", "int", "Maximum sessions per round", 3, (1, 100)),
        ],
    ),
    (
        "topology",
        "Chat Topology",
        "How chats, channels and their owners are generated.",
        [
            ("telegram.topology.generate_if_missing", "bool", "Generate the topology if missing", True, None),
            ("telegram.topology.shared_across_clients", "bool", "Share the topology across clients", False, None),
            ("telegram.topology.max_owned_chats", "int", "Maximum chats owned by an agent", 2, (1, 1000)),
            ("telegram.topology.channel_owner_share", "float", "Share of agents owning a channel", 0.1, (0, 1)),
            ("telegram.topology.discussion_share", "float", "Share of channels with a discussion group", 0.5, (0, 1)),
            ("telegram.topology.network_ignores_topics", "bool", "Ignore topics when building the network", False, None),
        ],
    ),
    (
        "topics",
        "Topics and Chats",
        "How the experiment topics map onto agents and chats.",
        [
            ("telegram.topics.assignment", "choice", "Topic assignment", "from_population", ("from_population", "assign", "merge")),
            ("telegram.topics.topics_per_agent", "int", "Topics per agent", 3, (1, 1000)),
            ("telegram.topics.on_unmapped", "choice", "Unmapped topics", "warn_drop", ("warn_drop", "error")),
            ("telegram.topics.chats_per_topic", "int", "Chats per topic", 2, (1, 1000)),
            ("telegram.topics.channel_topics_k", "int", "Topics per channel", 2, (1, 1000)),
            ("telegram.topics.auto_topic_group", "bool", "Create a group for each topic", True, None),
            ("telegram.topics.off_topic_rate", "float", "Off-topic rate", 0.05, (0, 1)),
        ],
    ),
    (
        "attention",
        "Attention",
        "Which chats an agent looks at in a session and how they are ranked.",
        [
            ("telegram.attention.max_chats_per_session", "int", "Maximum chats per session", 5, (1, 1000)),
            ("telegram.attention.notifications_always_offered", "bool", "Always offer chats with notifications", True, None),
            ("telegram.attention.owned_always", "bool", "Always offer owned chats", True, None),
            ("telegram.attention.weights.notifications", "float", "Weight of notifications", 3.0, (0, _P)),
            ("telegram.attention.weights.topic_affinity", "float", "Weight of topic affinity", 2.0, (0, _P)),
            ("telegram.attention.weights.recent_activity", "float", "Weight of recent activity", 1.0, (0, _P)),
        ],
    ),
    (
        "reactive",
        "Reactive Replies",
        "Replies and reactions triggered by the activity of other agents.",
        [
            ("telegram.reactive.enabled", "bool", "Enable reactive replies", True, None),
            ("telegram.reactive.probability", "float", "Probability of reacting", 0.7, (0, 1)),
            ("telegram.reactive.median_minutes", "float", "Median reaction delay (minutes)", 8.0, (0, 10080)),
            ("telegram.reactive.sigma", "float", "Spread of the reaction delay", 1.0, (0, 100)),
            ("telegram.reactive.max_per_round", "int", "Maximum reactions per round", 3, (0, 1000)),
            ("telegram.reactive.max_chain_depth", "int", "Maximum chain depth", 6, (1, 1000)),
            ("telegram.reactive.max_wait_rounds", "int", "Maximum wait (rounds)", 24, (1, 100000)),
            ("telegram.reactive.actions_likelihood.reply", "float", "Reactive reply likelihood", 4.0, (0, _P)),
            ("telegram.reactive.actions_likelihood.react", "float", "Reactive reaction likelihood", 3.0, (0, _P)),
            ("telegram.reactive.actions_likelihood.forward", "float", "Reactive forward likelihood", 1.0, (0, _P)),
            ("telegram.reactive.actions_likelihood.post", "float", "Reactive post likelihood", 0.5, (0, _P)),
        ],
    ),
    (
        "discovery",
        "Chat Discovery",
        "How agents find chats to join or leave.",
        [
            ("telegram.discovery.mode", "choice", "Discovery mode", "llm", ("llm", "rule")),
            ("telegram.discovery.leave_prob", "float", "Probability of leaving a chat", 0.05, (0, 1)),
        ],
    ),
    (
        "agent_actions",
        "Optional Agent Actions",
        "Actions an agent may take besides posting, replying and reacting.",
        [
            ("telegram.agent_actions.forwarding.enabled", "bool", "Allow forwarding", True, None),
            ("telegram.agent_actions.search.enabled", "bool", "Allow search", True, None),
            ("telegram.agent_actions.search.likelihood", "float", "Search likelihood", 0.5, (0, _P)),
            ("telegram.agent_actions.private_message.enabled", "bool", "Allow private messages", True, None),
            ("telegram.agent_actions.private_message.likelihood", "float", "Private message likelihood", 0.5, (0, _P)),
            ("telegram.agent_actions.forum_topics.enabled", "bool", "Allow forum topics", True, None),
            ("telegram.agent_actions.forum_topics.create_likelihood", "float", "Forum topic creation likelihood", 0.2, (0, _P)),
            ("telegram.agent_actions.forum_topics.delete_likelihood", "float", "Forum topic deletion likelihood", 0.05, (0, _P)),
        ],
    ),
    (
        "baseline",
        "Baseline Activity",
        "Background activity that does not come from the agents.",
        [
            ("telegram.baseline.policy", "choice", "Baseline policy", "none", ("none", "static", "reactive")),
            ("telegram.baseline.beta", "float", "Baseline strength", 0.5, (0, _P)),
        ],
    ),
    (
        "moderation",
        "Moderation",
        "Automatic restrictions on the chats.",
        [
            ("telegram.moderation.policy", "choice", "Moderation policy", "none", ("none", "rate_limit")),
            ("telegram.moderation.rate_limit_posts", "int", "Posts allowed before the limit", 5, (2, 100000)),
            ("telegram.moderation.restrict_rounds", "int", "Restriction length (rounds)", 24, (1, 100000)),
        ],
    ),
    (
        "emergence",
        "Emergence, Chat Creation and Forums",
        "Chats that appear during the run.",
        [
            ("telegram.emergence.enabled", "bool", "Let chats emerge", False, None),
            ("telegram.emergence.open_slot_rate", "float", "Open slot rate", 0.02, (0, 1)),
            ("telegram.chat_creation.enabled", "bool", "Let agents create chats", False, None),
            ("telegram.chat_creation.likelihood", "float", "Chat creation likelihood", 0.1, (0, _P)),
            ("telegram.forum.enabled", "bool", "Enable forum chats", False, None),
            ("telegram.forum.min_topics", "int", "Minimum topics of a forum", 2, (2, 1000)),
        ],
    ),
    (
        "archetypes",
        "Agent Archetypes",
        "Share of validators, broadcasters and explorers (the three must add up to 1).",
        [
            ("simulation.agent_archetypes.enabled", "bool", "Enable archetypes", False, None),
            ("simulation.agent_archetypes.distribution.validator", "float", "Validators", 0.33, (0, 1)),
            ("simulation.agent_archetypes.distribution.broadcaster", "float", "Broadcasters", 0.33, (0, 1)),
            ("simulation.agent_archetypes.distribution.explorer", "float", "Explorers", 0.34, (0, 1)),
        ],
    ),
    (
        "population",
        "Churn and New Agents",
        "Agents leaving and joining during the run.",
        [
            ("agents.churn.enabled", "bool", "Enable churn", False, None),
            ("agents.churn.churn_probability", "float", "Churn probability", 0.01, (0, 1)),
            ("agents.churn.inactivity_threshold", "int", "Inactivity threshold (rounds)", 5, (1, 100000)),
            ("agents.churn.churn_percentage", "float", "Maximum share of agents that churn", 0.1, (0, 1)),
            ("agents.new_agents.enabled", "bool", "Enable new agents", False, None),
            ("agents.new_agents.probability_new_agents", "float", "New agents probability", 0.01, (0, 1)),
            ("agents.new_agents.percentage_new_agents", "float", "Share of new agents", 0.01, (0, 1)),
        ],
    ),
    (
        "llm_runtime",
        "Language Model Reliability",
        "Concurrency, timeouts and the failure guard of the language model calls.",
        [
            ("llm.max_concurrency", "int", "Maximum concurrent requests", 8, (1, 1024)),
            ("llm.timeout_seconds", "float", "Timeout (seconds)", 120.0, (1, 3600)),
            ("llm.max_retries", "int", "Maximum retries", 3, (0, 100)),
            ("llm.pass_seed", "bool", "Pass the seed to the model", True, None),
            ("llm.record_responses", "bool", "Record the responses", False, None),
            ("llm.max_failed_session_ratio", "float", "Maximum share of failed sessions", 0.5, (0, 1)),
            ("llm.failure_window_sessions", "int", "Failure window (sessions)", 20, (1, 100000)),
            ("llm.failure_min_sessions", "int", "Failure minimum (sessions)", 5, (1, 100000)),
            ("simulation.emotion_batch_size", "int", "Emotion annotation batch size", 10, (1, 10000)),
        ],
    ),
    (
        "runtime",
        "Client Runtime",
        "Timeouts and polling of the client process.",
        [
            ("ready_timeout_seconds", "float", "Ready timeout (seconds)", 180.0, (1, 86400)),
            ("server_call_timeout_seconds", "float", "Server call timeout (seconds)", 120.0, (1, 86400)),
            ("max_server_retries", "int", "Maximum server retries", 3, (0, 1000)),
            ("shutdown_grace_seconds", "float", "Shutdown grace (seconds)", 3.0, (0, 3600)),
            ("heartbeat_interval", "float", "Heartbeat interval (seconds)", 5.0, (0.1, 3600)),
            ("barrier_poll_seconds", "float", "Barrier poll (seconds)", 0.2, (0.01, 60)),
        ],
    ),
    (
        "logging",
        "Logging",
        "Which logs the client writes (the verbose ones are off by default).",
        [
            ("logging.enable_console_log", "bool", "Console log", True, None),
            ("logging.enable_execution_log", "bool", "Execution log", True, None),
            ("logging.enable_actor_log", "bool", "Actor log", True, None),
            ("logging.enable_client_log", "bool", "Client log", True, None),
            ("logging.enable_llm_usage_log", "bool", "Language model usage log", True, None),
            ("logging.enable_prompt_log", "bool", "Prompt log", False, None),
            ("logging.enable_action_log", "bool", "Action log", False, None),
            ("logging.enable_tick_log", "bool", "Tick log", False, None),
            ("logging.compress_rotated", "bool", "Compress rotated logs", True, None),
        ],
    ),
]

# the likelihood of each action of an agent, in the section "Agents' Actions Relevance"
ACTIONS: List[Field] = [
    ("telegram.actions_likelihood.post", "float", "Post", 2.0, (0, _P)),
    ("telegram.actions_likelihood.forward", "float", "Forward", 2.0, (0, _P)),
    ("telegram.actions_likelihood.reply", "float", "Reply", 3.0, (0, _P)),
    ("telegram.actions_likelihood.react", "float", "React", 3.0, (0, _P)),
    ("telegram.actions_likelihood.join", "float", "Join", 0.2, (0, _P)),
    ("telegram.actions_likelihood.leave", "float", "Leave", 0.05, (0, _P)),
    ("telegram.actions_likelihood.read", "float", "Read", 1.0, (0, _P)),
]

# the details of the agents' memory, in the section "Agent Memory"
MEMORY: List[Field] = [
    ("agents.memory_backend", "choice", "Memory backend", "hybrid_semantic", ("hybrid_semantic", "simple_recent")),
    ("agents.memory_prompt_mode", "text", "Prompt mode", "subtle_forum", None),
    ("agents.memory_vote_signal_only", "bool", "Votes only as a signal", True, None),
    ("agents.memory_reply_context_max_chars", "int", "Reply context (characters)", 280, (1, 100000)),
    ("agents.memory_total_max_chars", "int", "Total memory in the prompt (characters)", 1400, (0, 100000)),
    ("agents.memory_cross_thread_callback_min_score", "float", "Minimum score to recall another thread", 0.8, (0, 1)),
    ("agents.memory_rehydrate_rounds", "int", "Rehydrate window (rounds)", 72, (0, 100000)),
    ("agents.memory_forget_deleted", "bool", "Forget deleted messages", False, None),
    ("agents.memory_high_affect_enabled", "bool", "Recall emotionally charged episodes", False, None),
    ("agents.memory_high_affect_rule_threshold", "float", "Rule threshold", 0.55, (0, 1)),
    ("agents.memory_high_affect_uncertain_low", "float", "Uncertain band, low", 0.35, (0, 1)),
    ("agents.memory_high_affect_uncertain_high", "float", "Uncertain band, high", 0.7, (0, 1)),
    ("agents.memory_high_affect_search_k", "int", "Search top-k", 12, (1, 1000)),
    ("agents.memory_high_affect_max_items", "int", "Maximum items", 6, (1, 1000)),
    ("agents.memory_high_affect_max_chars", "int", "Maximum characters", 900, (1, 100000)),
    ("agents.memory_high_affect_llm_fallback", "bool", "Ask the language model when uncertain", True, None),
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
            value = int(raw) if kind == "int" else float(raw)
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
            label_of("The lower bound of the uncertain band cannot exceed the upper one")
        )
    dist = _get_path(fragment, "simulation.agent_archetypes.distribution")
    if isinstance(dist, dict) and len(dist) == 3 and abs(sum(dist.values()) - 1.0) > 0.011:
        raise AdvancedSettingsError(label_of("The archetype shares must add up to 1"))


def values_from_config(config: Optional[dict], *, memory: bool = True) -> Dict[str, Any]:
    """``{path: value}`` for every field, taking the value from ``config`` and the default otherwise."""
    config = config or {}
    return {
        path: _get_path(config, path, default)
        for path, _k, _l, default, _b in all_fields(memory=memory)
    }


def groups() -> Iterable[Group]:
    return GROUPS
