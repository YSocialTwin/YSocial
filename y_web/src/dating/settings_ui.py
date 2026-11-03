"""How the generated dating settings are presented (client page and experiment settings page).

The settings themselves come from the JSON Schemas of the runtime (:mod:`y_web.src.dating.schema_forms`): there is
one list of keys, with type, bounds, default and description. This module only decides *where and how* each key is
shown: the section it belongs to (a title and a sentence that say what the section does), an optional sub-heading
inside the section, and a readable label. Two rules keep the pages honest:

* a key is shown on exactly one of the two pages: ``CLIENT_SECTIONS`` lists the settings of a client (what the
  agents of one population do), ``SERVER_SECTIONS`` those of the experiment (rules of the platform and of the
  run, shared by every client);
* a key without a place is shown in a last section "Other settings" (and a test fails), so a new key of the
  runtime is never lost.

The module is pure (no Flask, no database).
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple


def N_(message):
    """Mark a text for extraction; the templates translate it."""
    return message


# --------------------------------------------------------------------------------------------- labels
LABELS: Dict[str, str] = {
    # client: runtime
    "match_recsys": N_("Recommender of these agents"),
    "heartbeat_interval": N_("Heartbeat interval (seconds)"),
    "poll_interval": N_("Polling interval (seconds)"),
    "logging.enable_execution_log": N_("Write the execution log file"),
    "logging.enable_console_log": N_("Also show the log on the console"),
    # client: activity
    "activity.session_probability": N_("Session probability at the peak hour"),
    "activity.hourly_activity": N_("Activity of each hour of the day"),
    "activity.swipes_per_session": N_("Cards decided per session"),
    "activity.profiles": N_("Hourly profiles by archetype"),
    # client: swipe
    "swipe.mode": N_("Who decides the swipes"),
    "swipe.llm_swipe_share": N_("Share of swipes decided by the language model"),
    "swipe.superlike_with_llm": N_("The model may answer super like"),
    "swipe.llm_vision": N_("Show the photos to the model"),
    "swipe.w_attr": N_("Weight of attractiveness"),
    "swipe.w_sim": N_("Weight of shared interests"),
    "swipe.w_age": N_("Weight of age fit"),
    "swipe.w_dist": N_("Weight of distance"),
    "swipe.w_intent": N_("Weight of compatible intent"),
    "swipe.w_vis": N_("Weight of the visual match"),
    "swipe.noise_std": N_("Noise on the utility"),
    "swipe.revisit_inertia": N_(
        "Weight of the earlier decision on a profile seen again"
    ),
    "swipe.theta_base": N_("Like threshold"),
    "swipe.theta_selectivity": N_("Effect of selectivity on the threshold"),
    "swipe.stress_threshold_shift": N_("Effect of stress on the threshold"),
    "swipe.quota_slack": N_("Spare likes kept for later"),
    "swipe.superlike_margin": N_("Margin for a super like"),
    # client: llm
    "llm.backend": N_("Backend"),
    "llm.url": N_("LLM Server URL"),
    "llm.model": N_("LLM Model"),
    "llm.vision_model": N_("Vision model"),
    "llm.api_key_env": N_("API key environment variable"),
    "llm.temperature": N_("Temperature"),
    "llm.max_tokens": N_("Maximum tokens of an answer"),
    "llm.timeout_seconds": N_("Timeout of a call (seconds)"),
    "llm.retries": N_("Retries after a failed call"),
    "llm.max_workers": N_("Concurrent calls"),
    # client: conversation
    "conversation.enabled": N_("Agents talk to their matches"),
    "conversation.text_source": N_("Who writes the messages"),
    "conversation.sub_ticks": N_("Turns per slot"),
    "conversation.check_probability": N_("Probability of checking a chat"),
    "conversation.base_reply_probability": N_("Base probability of replying"),
    "conversation.interest_floor": N_("Minimum interest to keep talking"),
    "conversation.stress_effect": N_("Effect of stress on replying"),
    "conversation.opener_probability": N_("Probability of writing first"),
    "conversation.react_probability": N_("Probability of reacting to a message"),
    "conversation.unmatch_probability": N_("Probability of ending a match"),
    "conversation.min_messages_before_unmatch": N_(
        "Messages before a match can be ended"
    ),
    "conversation.after_date_evaluation": N_(
        "Agents evaluate the relationship after a date"
    ),
    "conversation.after_date_negative_close": N_(
        "Closing the match after a bad date (fallback)"
    ),
    "conversation.after_date_negative_ghost": N_(
        "Ghosting after a bad date (fallback)"
    ),
    "conversation.after_date_neutral_close": N_(
        "Closing the match after a so-so date (fallback)"
    ),
    "conversation.after_date_neutral_ghost": N_(
        "Ghosting after a so-so date (fallback)"
    ),
    "conversation.max_message_chars": N_("Length asked of a message (characters)"),
    "conversation.date_proposal_probability": N_("Probability of proposing a date"),
    "conversation.date_accept_base": N_("Base probability of accepting a date"),
    # client: profile generation
    "profile_generation.enabled": N_("Write the missing profile texts"),
    "profile_generation.bio_max_chars": N_("Bio length (characters)"),
    "profile_generation.n_prompt_answers": N_("Profile questions answered"),
    "profile_generation.captions": N_("Write a caption for every photo"),
    "profile_generation.images.enabled": N_("Generate the profile photos"),
    "profile_generation.images.style": N_("Look of the photos"),
    "profile_generation.images.use_caption": N_(
        "Draw the agent in the scene of the caption"
    ),
    "profile_generation.images.background": N_(
        "Generate them while the simulation runs"
    ),
    "profile_generation.images.generator": N_("Image generator"),
    "profile_generation.images.model": N_("Image model (diffusion)"),
    "profile_generation.images.inference_steps": N_("Denoising steps"),
    "profile_generation.images.folder": N_("Folder of the images"),
    # client: lifecycle
    "lifecycle.pause.enabled": N_("Agents pause their profile"),
    "lifecycle.pause.no_match_days": N_("Days without a match before pausing"),
    "lifecycle.pause.probability": N_("Daily probability of pausing"),
    "lifecycle.pause.resume_after_days": N_("Days before resuming"),
    "lifecycle.preferences.enabled": N_("Agents widen their preferences"),
    "lifecycle.preferences.no_match_days": N_("Days without a match before widening"),
    "lifecycle.preferences.widen_age_years": N_("Years added to the age range"),
    "lifecycle.preferences.widen_distance_factor": N_("Multiplier of the distance"),
    "lifecycle.preferences.max_distance_km": N_("Largest distance (km)"),
    "lifecycle.bio_refresh.enabled": N_("Agents rewrite their bio"),
    "lifecycle.bio_refresh.probability": N_("Daily probability of rewriting"),
    "lifecycle.bio_refresh.max_chars": N_("New bio length (characters)"),
    # client: stress/reward and annotations
    "stress_reward.tone_source": N_("How the tone of a message is classified"),
    "stress_reward.affect_activity": N_("Stress changes the activity"),
    "annotations.perspective_api_key_env": N_(
        "Perspective API key environment variable"
    ),
    # client: memory
    "memory.backend": N_("Memory backend"),
    "memory.language": N_("Memory language"),
    "memory.persist": N_("Keep the memory between runs"),
    "memory.prompt_mode": N_("How memory enters the prompt"),
    "memory.reply_context_max_chars": N_("Memory context in a reply (characters)"),
    "memory.cross_thread_callback_min_score": N_(
        "Minimum score to recall another chat"
    ),
    "memory.high_affect_enabled": N_("Remember emotional moments"),
    "memory.high_affect_llm_fallback": N_("Ask the model when the rules are unsure"),
    "memory.nuance_enabled": N_("Add nuance cues"),
    "memory.nuance_cues_max_chars": N_("Nuance cues (characters)"),
    "memory.pair_history_limit": N_("Items kept for a pair"),
    "memory.thread_history_limit": N_("Items kept for a chat"),
    "memory.search_k": N_("Memories retrieved"),
    "memory.search_max_chars": N_("Retrieved memories (characters)"),
    "memory.search_time_window_rounds": N_("Time window of the search (rounds)"),
    # server: run
    "simulation.num_slots_per_day": N_("Slots in a day"),
    "min_to_start": N_("Clients needed to start"),
    "timeout_seconds": N_("Client timeout (seconds)"),
    "seed": N_("Random seed"),
    "logging.enable_server_log": N_("Write the server log file"),
    "logging.enable_actor_log": N_("Write the actor log file"),
    "logging.enable_request_log": N_("Write the request log file"),
    # server: matching quotas
    "matching.likes_per_day": N_("Likes per agent per day"),
    "matching.superlikes_per_day": N_("Super likes per agent per day"),
    "matching.cards_per_day": N_("Cards shown per agent per day (0 = no limit)"),
    # server: conversations
    "conversations.opener_genders": N_("Genders allowed to write first"),
    "conversations.ghosting_threshold_slots": N_(
        "Slots of silence that count as ghosting"
    ),
    "conversations.history_messages": N_("Recent messages returned per chat"),
    "conversations.max_message_chars": N_("Longest message accepted (characters)"),
    "conversations.report_implies_block": N_("A report also blocks the profile"),
    # server: dates
    "lifecycle.dates_enabled": N_("Dates are allowed"),
    "lifecycle.min_messages_before_date": N_("Messages before a date can be proposed"),
    "lifecycle.max_proposals_per_match": N_("Proposals per match"),
    "lifecycle.response_window_slots": N_("Slots before a proposal expires"),
    "lifecycle.outcome_delay_slots": N_("Slots from acceptance to outcome"),
    "lifecycle.default_tone": N_("Default conversation tone"),
    "lifecycle.outcome.a": N_("Weight of compatibility"),
    "lifecycle.outcome.b": N_("Weight of the conversation tone"),
    "lifecycle.outcome.c": N_("Intercept"),
    "lifecycle.outcome.noise": N_("Noise on the outcome"),
    "lifecycle.outcome.negative_share": N_("Share of negative outcomes"),
    "lifecycle.pair_exit_probability": N_("Both leave after a good date"),
    "lifecycle.churn.enabled": N_("Agents leave the platform"),
    "lifecycle.churn.daily_probability": N_("Daily probability of leaving"),
    "lifecycle.churn.no_match_days": N_("Days without a match that raise it"),
    "lifecycle.churn.no_match_multiplier": N_("Multiplier after those days"),
    "lifecycle.pause_enabled": N_("Profiles can be paused"),
    "lifecycle.profile_updates_enabled": N_("Profiles can be edited"),
    "archetypes.enabled": N_("Archetypes change over time"),
    "archetypes.transitions": N_("Transition probabilities"),
    "memory_embeddings.async": N_("Embed memories later"),
    "stress_reward.backward_rounds": N_("Window of past slots"),
    "stress_reward.hidden_negative_signals": N_("Blocks and reports raise stress"),
    "stress_reward.streak_days": N_("Days without a match before the streak"),
    "stress_reward.base_stress": N_("Base stress"),
    "stress_reward.base_reward": N_("Base reward"),
    # server: human participation
    "human.max_humans": N_("Maximum participants"),
    "human.pace.min_round_seconds": N_("Minimum duration of a round (seconds)"),
    "human.limits.max_text_chars": N_("Longest text a person may send"),
    "human.limits.max_photos": N_("Photos per profile"),
    "human.limits.max_actions_per_request": N_("Actions per request"),
    "human.limits.requests_per_minute": N_("Requests per minute"),
    "human.limits.burst": N_("Burst of requests"),
    "human.limits.max_body_bytes": N_("Largest request (bytes)"),
    "human.interactions.swipe": N_("Swipe"),
    "human.interactions.messages": N_("Messages"),
    "human.interactions.reactions": N_("Reactions"),
    "human.interactions.dates": N_("Dates"),
    "human.interactions.unmatch": N_("Unmatch"),
    "human.interactions.block": N_("Block"),
    "human.interactions.report": N_("Report"),
    "human.interactions.pause": N_("Pause the profile"),
    "human.interactions.profile_edit": N_("Edit the profile"),
    # server: recommender (common parameters)
    "matching.common.stack_size": N_("Cards per request"),
    "matching.common.candidate_pool_size": N_("Candidates scored per viewer"),
    "matching.common.distance_filter": N_("Only show profiles within the distance"),
    "matching.common.bidirectional_age": N_("Age range must fit both ways"),
    "matching.common.exploration_rate": N_("Share of random cards"),
    "matching.common.max_exposure_per_day": N_(
        "Appearances of a profile per day (0 = no cap)"
    ),
    "matching.common.newcomer_boost_days": N_("Days a new profile is boosted"),
    "matching.common.newcomer_boost": N_("Boost of a new profile"),
    "matching.common.superlike_first": N_("Received super likes come first"),
    "matching.common.pass_cooldown_days": N_(
        "Days before a passed profile returns (0 = never)"
    ),
    "matching.common.revisit_after_days": N_(
        "Days before a decided profile can be judged again (0 = never)"
    ),
    "matching.common.likes_seen_visible": N_("Profiles that liked you come first"),
}

# --------------------------------------------------------------------------------------------- sections
# (id, title, what it does, [(sub-heading or None, [keys; a key ending in "." stands for every key below it])],
#  switch of the experiment configuration that must be on for the section to be used, or None)
Section = Tuple[str, str, str, List[Tuple[Optional[str], List[str]]], Optional[str]]

CLIENT_SECTIONS: List[Section] = [
    (
        "llm",
        N_("Large Language Models"),
        N_(
            "The language model of the agents: it writes the profile texts and the messages and decides the swipes. Enter the address of the server, fetch its models and choose one."
        ),
        [(None, ["llm."])],
        None,
    ),
    (
        "images",
        N_("Images"),
        N_(
            "The model that looks at the photos and the model that draws them. The photos are described to the agents with their captions; with a vision model the agents can also look at the images."
        ),
        [
            (
                N_("Vision model (the agents look at the photos)"),
                ["llm.vision_model", "swipe.llm_vision"],
            ),
            (N_("Profile photos"), ["profile_generation.images."]),
        ],
        None,
    ),
    (
        "recommender",
        N_("Recommender"),
        N_(
            "Which model proposes the cards to the agents of this client. Every client can use its own model; the parameters of each model are shared by the whole experiment and are set in the experiment settings."
        ),
        [(None, ["match_recsys"])],
        None,
    ),
    (
        "activity",
        N_("Activity"),
        N_(
            "When the agents open the app and how many cards they decide each time. Each slot is one round of the experiment."
        ),
        [(None, ["activity."])],
        None,
    ),
    (
        "swipe",
        N_("Swiping"),
        N_(
            "How an agent decides on a card: a utility built from the weights below, compared with a threshold. The weights are relative to each other."
        ),
        [
            (
                N_("Who decides"),
                [
                    "swipe.mode",
                    "swipe.llm_swipe_share",
                    "swipe.superlike_with_llm",
                ],
            ),
            (
                N_("Weights of the utility"),
                [
                    "swipe.w_attr",
                    "swipe.w_sim",
                    "swipe.w_age",
                    "swipe.w_dist",
                    "swipe.w_intent",
                    "swipe.w_vis",
                ],
            ),
            (
                N_("Threshold and noise"),
                [
                    "swipe.noise_std",
                    "swipe.revisit_inertia",
                    "swipe.theta_base",
                    "swipe.theta_selectivity",
                    "swipe.stress_threshold_shift",
                    "swipe.quota_slack",
                    "swipe.superlike_margin",
                ],
            ),
        ],
        None,
    ),
    (
        "conversation",
        N_("Conversations"),
        N_(
            "How the agents talk to their matches: who writes the messages, how often they check a chat, reply, react or leave it, and when they propose or accept a date. Limits and dates are rules of the platform: see the experiment settings."
        ),
        [
            (
                N_("Messages"),
                [
                    "conversation.enabled",
                    "conversation.text_source",
                    "conversation.sub_ticks",
                    "conversation.max_message_chars",
                ],
            ),
            (
                N_("Replying and reacting"),
                [
                    "conversation.check_probability",
                    "conversation.opener_probability",
                    "conversation.base_reply_probability",
                    "conversation.interest_floor",
                    "conversation.stress_effect",
                    "conversation.react_probability",
                ],
            ),
            (
                N_("Ending a match"),
                [
                    "conversation.unmatch_probability",
                    "conversation.min_messages_before_unmatch",
                ],
            ),
            (
                N_("Dates"),
                [
                    "conversation.date_proposal_probability",
                    "conversation.date_accept_base",
                ],
            ),
            (
                N_("After a date"),
                [
                    "conversation.after_date_evaluation",
                    "conversation.after_date_negative_close",
                    "conversation.after_date_negative_ghost",
                    "conversation.after_date_neutral_close",
                    "conversation.after_date_neutral_ghost",
                ],
            ),
        ],
        None,
    ),
    (
        "profile_generation",
        N_("Profile texts"),
        N_(
            "What the language model writes when the population file leaves it empty: bios, answers to the profile questions and photo captions."
        ),
        [(None, ["profile_generation."])],
        None,
    ),
    (
        "lifecycle",
        N_("Agent behaviour over time"),
        N_(
            "What an agent does when it is not finding matches or after some time on the app. Dates, couples and leaving the platform are rules of the platform: see the experiment settings."
        ),
        [
            (N_("Pausing the profile"), ["lifecycle.pause."]),
            (N_("Widening the preferences"), ["lifecycle.preferences."]),
            (N_("Rewriting the bio"), ["lifecycle.bio_refresh."]),
        ],
        None,
    ),
    (
        "stress_reward",
        N_("Stress and reward"),
        N_(
            "How the client reads the messages and applies stress to the activity. Their rules are in the experiment settings."
        ),
        [(None, ["stress_reward."])],
        "stress_reward",
    ),
    (
        "memory",
        N_("Agent memory"),
        N_("What the agents remember of their chats."),
        [(None, ["memory."])],
        "memory",
    ),
    (
        "annotations",
        N_("Toxicity annotation"),
        N_("Where the toxicity score comes from."),
        [(None, ["annotations."])],
        "toxicity",
    ),
    (
        "runtime",
        N_("Connection and logs"),
        N_(
            "How the client talks to the server and what it writes in its log. The defaults suit almost every run."
        ),
        [
            (N_("Connection"), ["heartbeat_interval", "poll_interval"]),
            (N_("Logs"), ["logging."]),
        ],
        None,
    ),
]

SERVER_SECTIONS: List[Section] = [
    (
        "run",
        N_("Time and start"),
        N_(
            "How the simulated time is divided and when the run starts. The slot length and the seed are shared by every client of the experiment and are locked once the run has started."
        ),
        [
            (
                None,
                [
                    "simulation.num_slots_per_day",
                    "seed",
                    "min_to_start",
                    "timeout_seconds",
                ],
            )
        ],
        None,
    ),
    (
        "matching",
        N_("Daily quotas"),
        N_(
            "How many likes and super likes an agent has each day, and how many cards it is shown."
        ),
        [
            (
                None,
                [
                    "matching.likes_per_day",
                    "matching.superlikes_per_day",
                    "matching.cards_per_day",
                ],
            )
        ],
        None,
    ),
    (
        "conversations",
        N_("Conversation rules"),
        N_(
            "Rules of the platform for chats: who writes first and the limits the server enforces. How the agents behave in a chat is set in each client."
        ),
        [(None, ["conversations."])],
        None,
    ),
    (
        "dates",
        N_("Dates, couples and leaving"),
        N_(
            "Whether dates exist, how a date is proposed and answered, how its outcome is drawn and what happens to the people afterwards."
        ),
        [
            (
                N_("Proposing a date"),
                [
                    "lifecycle.dates_enabled",
                    "lifecycle.min_messages_before_date",
                    "lifecycle.max_proposals_per_match",
                    "lifecycle.response_window_slots",
                ],
            ),
            (
                N_("Outcome of a date"),
                [
                    "lifecycle.outcome_delay_slots",
                    "lifecycle.default_tone",
                    "lifecycle.outcome.",
                    "lifecycle.pair_exit_probability",
                ],
            ),
            (N_("Leaving the platform"), ["lifecycle.churn."]),
            (
                N_("Profiles"),
                ["lifecycle.pause_enabled", "lifecycle.profile_updates_enabled"],
            ),
        ],
        None,
    ),
    (
        "stress_reward",
        N_("Stress and reward"),
        N_(
            "How events (matches, silence, blocks, reports) become stress and reward. How a client uses them is set in the client."
        ),
        [(None, ["stress_reward."])],
        "stress_reward",
    ),
    (
        "memory_embeddings",
        N_("Memory"),
        N_("Optional behaviour of the persisted memory."),
        [(None, ["memory_embeddings."])],
        "memory",
    ),
    (
        "logs",
        N_("Logs"),
        N_("What the server writes in its log files."),
        [(None, ["logging."])],
        None,
    ),
]

OTHER = (
    "other",
    N_("Other settings"),
    N_("Settings of the runtime without a place of their own."),
    None,
)


# Settings that make sense only when the experiment uses language models: with LLM agents off they are not shown
# (the client takes their rule-based value, see client_config.rule_settings).
LLM_ONLY = (
    "llm.",
    "swipe.mode",
    "swipe.llm_swipe_share",
    "swipe.superlike_with_llm",
    "swipe.llm_vision",
    "conversation.text_source",
    "profile_generation.enabled",
    "profile_generation.bio_max_chars",
    "profile_generation.n_prompt_answers",
    "profile_generation.captions",
    "stress_reward.tone_source",
    "memory.high_affect_llm_fallback",
)

# Readable names of the values of a choice (the value itself is what the runtime stores).
CHOICE_LABELS: Dict[str, Dict[str, str]] = {
    "profile_generation.images.style": {
        "photorealistic": N_("Photorealistic human faces"),
        "cartoon": N_("Fantasy cartoon characters"),
    },
    "profile_generation.images.generator": {
        "diffusion": N_("Image model"),
        "stub": N_("Placeholder"),
    },
    "swipe.mode": {
        "rule": N_("Rules"),
        "llm": N_("Language model"),
        "mixed": N_("Mixed"),
    },
    "conversation.text_source": {
        "llm": N_("Language model"),
        "template": N_("Canned phrases"),
    },
    "stress_reward.tone_source": {
        "llm": N_("Language model"),
        "neutral": N_("Always neutral"),
    },
}

# What each recommender does, in a sentence (shown where a model is chosen).
RECSYS_INFO: Dict[str, str] = {
    "random": N_(
        "Candidates in random order: a baseline and control group, no preference is used."
    ),
    "proximity_activity": N_("Nearby and recently active profiles come first."),
    "preference_similarity": N_(
        "Ranks the candidates by how well they fit what the viewer is looking for (age, distance, intent, interests)."
    ),
    "desirability_elo": N_(
        "Gives every profile a desirability rating that moves with the swipes it receives, and shows each agent profiles of a similar level."
    ),
    "hybrid": N_(
        "A weighted blend of the ranks of other models. It is the default of a new experiment."
    ),
    "visual_preference": N_(
        "Learns the visual taste of each agent from the captions of the profiles it liked or passed."
    ),
    "reciprocal": N_(
        "Estimates the chance that both sides like each other and favours mutual interest: in the comparison of the runtime it produces the most matches."
    ),
    "collaborative": N_(
        "Agents who liked the same profiles get similar suggestions; it needs some swipe history first."
    ),
    "stable_batch": N_(
        "Every few slots it pairs agents with a stable matching on symmetric weights; the assigned partners lead the stack."
    ),
    "llm_rerank": N_(
        "A base model proposes the candidates and a language model re-orders the best ones. Needs a language model and is slower."
    ),
}


def _matches(path: str, key: str) -> bool:
    return path.startswith(key) if key.endswith(".") else path == key


def label_of(path: str) -> str:
    """The label of a setting (a readable fallback for a key without one)."""
    if path in LABELS:
        return LABELS[path]
    last = path.split(".")[-1].replace("_", " ")
    return last[:1].upper() + last[1:]


# --------------------------------------------------------------------------------------------- widgets
# How a setting is drawn (the page templates know these names):
#   toggle      a switch (boolean)
#   segmented   one tag out of a few (a choice of up to four values)
#   slider      a probability, from 0 to 1, with its value shown
#   importance  the 0-10 scale the other admin pages use for relative weights (one step is IMPORTANCE_STEP)
#   hourly      the 24 hourly rates with a bar chart
#   taglist     a list of words edited as tags
#   json        a structured value (advanced)
IMPORTANCE = (
    "swipe.w_attr",
    "swipe.w_sim",
    "swipe.w_age",
    "swipe.w_dist",
    "swipe.w_intent",
    "swipe.w_vis",
)
IMPORTANCE_STEP = 0.05
TAGLISTS: Dict[str, List[str]] = {
    "conversations.opener_genders": ["woman", "man", "non-binary"],
}
# Settings that most people never touch: hidden behind "Show advanced settings".
ADVANCED = (
    "llm.api_key_env",
    "llm.timeout_seconds",
    "llm.retries",
    "llm.max_workers",
    "llm.max_tokens",
    "swipe.noise_std",
    "swipe.theta_selectivity",
    "swipe.stress_threshold_shift",
    "swipe.quota_slack",
    "swipe.superlike_margin",
    "activity.profiles",
    "conversation.sub_ticks",
    "conversation.interest_floor",
    "conversation.stress_effect",
    "conversation.min_messages_before_unmatch",
    "conversation.max_message_chars",
    "conversation.date_accept_base",
    "profile_generation.images.generator",
    "profile_generation.images.background",
    "profile_generation.images.inference_steps",
    "profile_generation.images.folder",
    "memory.language",
    "memory.persist",
    "memory.prompt_mode",
    "memory.reply_context_max_chars",
    "memory.cross_thread_callback_min_score",
    "memory.high_affect_llm_fallback",
    "memory.nuance_enabled",
    "memory.nuance_cues_max_chars",
    "memory.pair_history_limit",
    "memory.thread_history_limit",
    "memory.search_k",
    "memory.search_max_chars",
    "memory.search_time_window_rounds",
    "annotations.",
    "heartbeat_interval",
    "poll_interval",
    "logging.",
    "lifecycle.outcome.",
    "lifecycle.outcome_delay_slots",
    "archetypes.transitions",
    "conversations.history_messages",
    "conversations.max_message_chars",
    "conversations.ghosting_threshold_slots",
    "human.limits.",
    "human.pace.",
    "memory_embeddings.",
    "stress_reward.backward_rounds",
    "stress_reward.streak_days",
    "stress_reward.base_stress",
    "stress_reward.base_reward",
    "matching.common.candidate_pool_size",
    "matching.common.exploration_rate",
    "matching.common.max_exposure_per_day",
    "matching.common.newcomer_boost_days",
    "matching.common.newcomer_boost",
    "matching.common.pass_cooldown_days",
    "matching.common.bidirectional_age",
)


def is_advanced(path: str) -> bool:
    return any(_matches(path, key) for key in ADVANCED)


# Small text-to-image models of the Hugging Face hub that YDating runs as they are (downloaded on first use); any
# other diffusers id can be typed. Sizes are the approximate weights of the model files.
DIFFUSION_MODELS: List[Tuple[str, str]] = [
    ("segmind/tiny-sd", N_("tiny-sd: the smallest, fastest (about 1 GB). Default")),
    (
        "nota-ai/bk-sdm-tiny",
        N_("bk-sdm-tiny: compact Stable Diffusion, similar size (about 1 GB)"),
    ),
    (
        "nota-ai/bk-sdm-small",
        N_("bk-sdm-small: a little larger, better detail (about 1.4 GB)"),
    ),
    (
        "stabilityai/sd-turbo",
        N_(
            "sd-turbo: distilled, 1 to 4 steps, best quality for the time (about 2.6 GB)"
        ),
    ),
]
DIFFUSION_MODEL = "profile_generation.images.model"


def widget_of(f: Any) -> str:
    """The widget a setting is drawn with (see the table above)."""
    if f.path == DIFFUSION_MODEL:
        return "diffusion_model"
    if f.path == "match_recsys":
        return "recsys"
    if f.path == "llm.backend":
        return "hidden"
    if f.path == "llm.url":
        return "model_url"
    if f.path == "llm.model":
        return "model_select"
    if f.path == "llm.vision_model":
        return "vision_select"
    if f.path in IMPORTANCE:
        return "importance"
    if f.path in TAGLISTS:
        return "taglist"
    if f.kind == "numlist" and f.length == 24:
        return "hourly"
    if f.kind == "bool":
        return "toggle"
    if f.kind == "choice":
        return "segmented" if len(f.choices) <= 4 else "select"
    if (
        f.kind == "float"
        and f.minimum == 0
        and f.maximum == 1
        and f.exclusive_minimum is None
    ):
        return "slider"
    if f.kind == "json":
        return "json"
    if f.kind in ("int", "float"):
        return "number"
    return "text"


def _item(f: Any, options: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    return {
        "options": (options or {}).get(f.path),
        "f": f,
        "label": label_of(f.path),
        "widget": widget_of(f),
        "advanced": is_advanced(f.path),
        "suggestions": TAGLISTS.get(f.path),
        "choice_labels": CHOICE_LABELS.get(f.path, {}),
        "recsys_info": RECSYS_INFO if f.path == "match_recsys" else None,
        "diffusion_models": DIFFUSION_MODELS if f.path == DIFFUSION_MODEL else None,
    }


def item_for(f: Any) -> Dict[str, Any]:
    """The drawing instructions of one setting (label, widget, choices), for pages that lay fields out themselves."""
    return _item(f)


def placed_paths(sections: Iterable[Section]) -> List[str]:
    return [
        key for _i, _t, _d, subs, _s in sections for _h, keys in subs for key in keys
    ]


def layout(
    fields: List[Any],
    sections: List[Section],
    switches: Optional[Dict[str, bool]] = None,
    options: Optional[Dict[str, List[str]]] = None,
    llm_enabled: bool = True,
) -> List[Dict[str, Any]]:
    """Group ``fields`` (``schema_forms.Field``) into the ``sections``; keys nobody claims go to "Other settings".

    A component that is switched off in the experiment configuration (memory, stress and reward, toxicity
    annotation) is not shown at all, and neither are the settings that need a language model when the experiment
    has no LLM agents (``llm_enabled`` False). A section without fields is left out.
    """
    switches = switches or {}
    if not llm_enabled:
        fields = [f for f in fields if not any(_matches(f.path, k) for k in LLM_ONLY)]
    taken = set()
    out: List[Dict[str, Any]] = []
    for sid, title, descr, subs, switch in sections:
        if switch and not switches.get(switch, False):
            for (
                _h,
                keys,
            ) in (
                subs
            ):  # a switched-off component keeps its keys out of "Other settings"
                for key in keys:
                    for f in fields:
                        if _matches(f.path, key):
                            taken.add(f.path)
            continue
        blocks = []
        for heading, keys in subs:
            chosen = []
            for key in keys:
                for f in fields:
                    if f.path not in taken and _matches(f.path, key):
                        chosen.append(_item(f, options))
                        taken.add(f.path)
            if chosen:
                blocks.append({"heading": heading, "fields": chosen})
        if blocks:
            out.append(
                {
                    "id": sid,
                    "title": title,
                    "description": descr,
                    "blocks": blocks,
                    "switch": switch,
                    "inactive": False,
                    "advanced_only": all(
                        item["advanced"] for b in blocks for item in b["fields"]
                    ),
                }
            )
    rest = [f for f in fields if f.path not in taken]
    if rest:
        sid, title, descr, _ = OTHER
        out.append(
            {
                "id": sid,
                "title": title,
                "description": descr,
                "blocks": [
                    {
                        "heading": None,
                        "fields": [_item(f, options) for f in rest],
                    }
                ],
                "switch": None,
                "inactive": False,
                "advanced_only": False,
            }
        )
    return out
