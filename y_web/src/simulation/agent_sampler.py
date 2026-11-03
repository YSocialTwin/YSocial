"""
Agent-sampling helpers for YSocial simulation.

Extracted from process_runner.py (Phase 12a).

Functions
---------
get_users_per_hour   — map each hour to the list of agents active during that hour
sample_agents        — sample a subset of agents for a given time slot
ensure_agents_have_archetype — back-fill archetype attribute on agents that lack one
process_agent        — execute one agent's actions for a single time slot
"""

import random
import sys
import traceback
from collections import defaultdict

import numpy as np

from y_web.src.models import ActivityProfile, PopulationActivityProfile
from y_web.src.simulation import federation_hooks

_REPLY_TO_MENTION_DISABLED = False


DEFAULT_ARCHETYPE = "broadcaster"


def archetype_of(agent):
    """Archetype of an agent; ``None`` or empty (an agent rebuilt from a server that does not store it) is the default.

    ``getattr(agent, "archetype", default)`` is not enough: the attribute exists and is ``None``, so the default was
    never used and the agent matched no archetype of the distribution (nobody was sampled).
    """
    return getattr(agent, "archetype", None) or DEFAULT_ARCHETYPE


def _is_fatal_reply_error(exc: Exception) -> bool:
    """Return True when a reply failure is irrecoverable for the current runtime."""
    message = f"{type(exc).__name__}: {exc}".lower()
    fatal_markers = (
        "actordiederror",
        "actoralreadyexistserror",
        "the actor died unexpectedly before finishing this task",
        "owner's node has crashed",
        "owner worker exit type: system_error",
    )
    return any(marker in message for marker in fatal_markers)


def _rule_based_agents_enabled(config):
    agents = None

    if isinstance(config, dict):
        raw_agents = config.get("agents")
        if isinstance(raw_agents, dict):
            llm_agents = raw_agents.get("llm_agents")
            return (
                isinstance(llm_agents, list)
                and len(llm_agents) == 1
                and llm_agents[0] is None
            )
        if isinstance(raw_agents, list):
            agents = raw_agents
    elif isinstance(config, list):
        agents = config

    if agents is not None:
        return any(isinstance(agent, dict) and agent.get("llm") for agent in agents)

    return False


def _validator_allowed_actions():
    """
    Actions available to the validator archetype.

    Forum experiments replaced legacy SHARE with more specific sharing aliases.
    Keep the old SHARE token for microblogging, but also allow the forum
    link/image sharing actions so validators can still behave as content curators.
    """
    return {
        "READ",
        "SEARCH",
        "SHARE",
        "NEWS",
        "SHARE_LINK",
        "SHARE_IMAGE",
    }


def find_activity_profile(session, key):
    """The ``ActivityProfile`` an agent names, whether the agent holds its id or its name (None when there is none)."""
    query = session.query(ActivityProfile)
    try:
        found = query.filter(ActivityProfile.id == int(key)).first()
    except (TypeError, ValueError):
        found = None
    return found or query.filter(ActivityProfile.name == str(key)).first()


def get_users_per_hour(population, agents, session):
    # get population activity profiles
    activity_profiles = defaultdict(list)
    population_activity_profiles = (
        session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population.id)
        .all()
    )
    for ap in population_activity_profiles:
        profile = (
            session.query(ActivityProfile)
            .filter(ActivityProfile.id == ap.activity_profile)
            .first()
        )
        activity_profiles[profile.name] = [int(x) for x in profile.hours.split(",")]

    hours_to_users = defaultdict(list)
    for ag in agents:
        # Check if agent has activity_profile attribute
        if not hasattr(ag, "activity_profile"):
            print(
                f"Warning: Agent {ag.name} (is_page={getattr(ag, 'is_page', 'unknown')}) missing activity_profile attribute",
                file=sys.stderr,
            )
            continue

        if ag.activity_profile is None:
            print(
                f"Warning: Agent {ag.name} (is_page={getattr(ag, 'is_page', 'unknown')}) has None activity_profile",
                file=sys.stderr,
            )
            continue

        # Use get with default to handle missing profiles gracefully
        profile = activity_profiles.get(ag.activity_profile)
        if profile is None:
            # Not among the profiles of the population (a merged population has none of its own): look the profile
            # up directly, as the agent names it - by id or by name
            try:
                profile_obj = find_activity_profile(session, ag.activity_profile)
                if profile_obj:
                    profile = [int(x) for x in profile_obj.hours.split(",")]
                    activity_profiles[ag.activity_profile] = profile
                else:
                    # Profile doesn't exist, skip this agent
                    print(
                        f"Warning: Activity profile {ag.activity_profile} not found in database for agent {ag.name} (is_page={getattr(ag, 'is_page', 'unknown')})",
                        file=sys.stderr,
                    )
                    continue
            except Exception as e:
                print(
                    f"Warning: Error fetching activity profile for agent {ag.name}: {e}",
                    file=sys.stderr,
                )
                continue

        for h in profile:
            hours_to_users[h].append(ag)

    return hours_to_users


def sample_agents(agents, expected_active_users, archetypes=None):
    """
    Sample agents based on their daily activity level and archetype distribution.
    If archetypes are enabled, sample according to the specified distribution.
    Otherwise, sample based solely on daily activity levels.

    :param agents:
    :param expected_active_users:
    :param archetypes:
    :return:
    """
    sagents = []

    if archetypes["enabled"]:
        candidates_per_archetype = {}
        weights_per_archetype = {}
        # identify the percentages of each archetype
        user_types = {}
        for k, v in archetypes["distribution"].items():
            user_types[k] = max(int(v * expected_active_users), 1)

        for a in agents:
            # Use getattr with default to handle agents without archetype attribute (e.g., when resuming old simulations)
            # Default to 'broadcaster' as it's the most permissive archetype with full action capabilities
            agent_archetype = archetype_of(a)
            if agent_archetype not in candidates_per_archetype:
                candidates_per_archetype[agent_archetype] = []
                weights_per_archetype[agent_archetype] = []
            candidates_per_archetype[agent_archetype].append(a)
            weights_per_archetype[agent_archetype].append(a.daily_activity_level)

        for atype, count in user_types.items():
            if atype in candidates_per_archetype:
                cands = candidates_per_archetype[atype]
                wts = weights_per_archetype[atype]
                # normalize weights
                wts = [w / sum(wts) for w in wts]
                try:
                    sampled = np.random.choice(
                        cands,
                        size=min(count, len(cands)),
                        p=wts,
                        replace=False,
                    )
                except Exception:
                    sampled = np.random.choice(
                        cands,
                        size=min(count, len(cands)),
                        replace=False,
                    )
                sagents.extend(sampled)
    else:
        weights = [a.daily_activity_level for a in agents]
        # normalize weights to sum to 1
        weights = [w / sum(weights) for w in weights]

        try:
            sagents = np.random.choice(
                agents,
                size=expected_active_users,
                p=weights,
                replace=False,
            )
        except Exception:
            sagents = np.random.choice(
                agents, size=expected_active_users, replace=False
            )

    return sagents


def ensure_agents_have_archetype(agents, archetypes):
    """
    Ensure all agents have an archetype attribute before saving.
    If archetypes are enabled and an agent doesn't have an archetype,
    assign a default based on the archetype distribution.

    Pages are excluded from archetype assignment as they don't use the archetype system.

    :param agents: List of agent objects
    :param archetypes: Archetype configuration dict
    """
    if archetypes and archetypes.get("enabled", False):
        # Get distribution for weighted random assignment
        distribution = archetypes.get("distribution", {"broadcaster": 1.0})
        archetype_choices = list(distribution.keys())
        archetype_weights = list(distribution.values())

        for agent in agents:
            # Skip pages - they don't use archetypes
            if hasattr(agent, "is_page") and agent.is_page == 1:
                continue

            if not hasattr(agent, "archetype") or agent.archetype is None:
                # Assign archetype based on distribution
                agent.archetype = random.choices(
                    archetype_choices, weights=archetype_weights, k=1
                )[0]
                print(
                    f"Assigned archetype '{agent.archetype}' to agent {agent.name}",
                    file=sys.stderr,
                )


def describe_empty_slot(candidates, expected_active_users, archetypes):
    """Why a slot sampled nobody although the client has agents (a short text for the log)."""
    if not candidates:
        return "no agent has an activity profile that covers this hour"
    counts = {}
    for a in candidates:
        key = str(getattr(a, "archetype", None))
        counts[key] = counts.get(key, 0) + 1
    wanted = (
        sorted((archetypes or {}).get("distribution", {}))
        if (archetypes or {}).get("enabled")
        else []
    )
    return (
        f"{len(candidates)} candidates, {expected_active_users} expected, archetypes of the candidates {counts}"
        + (f", archetypes of the distribution {wanted}" if wanted else "")
    )


def warn_if_empty_slot(
    warned_days,
    day,
    hour,
    n_agents,
    sampled,
    candidates,
    expected_active_users,
    archetypes,
    stream=None,
):
    """Warn on stderr, once per simulated day, when a slot ends with nobody sampled although agents exist.

    ``warned_days`` is a set kept by the caller (one per run). Returns the message written or ``None``. Nothing is
    written for a slot that sampled somebody, for a client without agents, or for a day already warned about.
    """
    if n_agents <= 0 or len(sampled) > 0 or day in warned_days:
        return None
    warned_days.add(day)
    message = (
        f"Warning: day {day} hour {hour}: no agent was sampled although the client has {n_agents} agents "
        f"({describe_empty_slot(candidates, expected_active_users, archetypes)}); the client advances without acting. "
        "Further empty slots of this day are not reported."
    )
    print(message, file=stream or sys.stderr, flush=True)
    return message


def process_agent(g, archetypes, cl, exp, tid, FakeAgent, local_random):
    """
    Process a single agent's actions for one time slot.

    :param g: The agent to process
    :param archetypes: Archetype configuration
    :param cl: Client instance
    :param exp: Experiment instance
    :param tid: Current time ID
    :param FakeAgent: FakeAgent class (for microblogging) or None
    :param local_random: Thread-local random.Random instance for thread safety
    :return: Tuple of (agent_name, success_flag)
    """
    global _REPLY_TO_MENTION_DISABLED

    try:
        # Canonical client logs aggregate by simulation day/hour.
        # Agents do not own a clock in the Standard branch, so bind the shared
        # client clock before any decorated action method runs.
        try:
            g.sim_clock = cl.sim_clock
        except Exception:
            pass

        if FakeAgent is not None and not getattr(g, "is_page", 0):
            if _rule_based_agents_enabled(getattr(cl, "config", {})):
                g.__class__ = FakeAgent

        if archetypes["enabled"]:
            # filtering the actions based on the archetype
            # Use getattr with default to handle agents without archetype attribute (e.g., when resuming old simulations)
            # Default to 'broadcaster' as it's the most permissive archetype with full action capabilities
            agent_archetype = archetype_of(g)
            if agent_archetype == "validator":
                acts = [
                    a
                    for a, v in cl.actions_likelihood.items()
                    if v > 0 and a in _validator_allowed_actions()
                ]
                if FakeAgent is not None and _rule_based_agents_enabled(
                    getattr(cl, "config", {})
                ):
                    g.__class__ = FakeAgent
            elif agent_archetype == "broadcaster":
                acts = [a for a, v in cl.actions_likelihood.items() if v > 0]
            elif agent_archetype == "explorer":
                acts = ["FOLLOW"]
                if FakeAgent is not None and _rule_based_agents_enabled(
                    getattr(cl, "config", {})
                ):
                    g.__class__ = FakeAgent
            else:  # an archetype this experiment does not define: act as the most permissive one
                acts = [a for a, v in cl.actions_likelihood.items() if v > 0]

        else:
            acts = [a for a, v in cl.actions_likelihood.items() if v > 0]

        # Get a random integer within g.round_actions.
        # If g.is_page == 1, then rounds = 0 (the page does not perform actions)
        if g.is_page == 1:
            rounds = 1
        else:
            round_actions = int(g.round_actions)
            # attention multiplier of the federation (F4.3): the same number without it
            round_actions = federation_hooks.scaled_round_actions(g, round_actions)
            if round_actions < 1 and int(g.round_actions) >= 1:
                rounds = 0  # the multiplier took the agent out of this slot
            else:
                lower = max(round_actions - 2, 1)
                rounds = local_random.randint(lower, round_actions)
            # Round_actions max is set for each agent by sampling from a user defined distribution.
            # Execute at least "lower" actions per user (to guarantee the activity level distribution).

        churned = False
        churned_id = None
        try:
            if not getattr(g, "is_page", 0) and g.evaluate_stress_reward_churn(
                tid, rng=local_random
            ):
                churned = True
                churned_id = int(getattr(g, "user_id", 0) or 0)
        except Exception:
            churned = False
            churned_id = None

        if churned:
            return (g.name, True, churned_id)

        for _ in range(rounds):
            # sample two elements from a list with replacement
            if len(acts) > 1:
                candidates = local_random.choices(
                    acts,
                    k=2,
                    weights=[cl.actions_likelihood[a] for a in acts],
                )
                candidates.append("NONE")
            else:
                candidates = acts + ["NONE"]

            try:
                # reply to received mentions
                if g not in cl.pages:
                    if not _REPLY_TO_MENTION_DISABLED:
                        should_reply = not archetypes["enabled"]
                        if archetypes["enabled"]:
                            # Use getattr with default to handle agents without archetype attribute
                            should_reply = archetype_of(g) == "broadcaster"

                        if should_reply:
                            try:
                                g.reply(tid=tid)
                            except Exception as reply_exc:
                                if _is_fatal_reply_error(reply_exc):
                                    _REPLY_TO_MENTION_DISABLED = True
                                    print(
                                        "Warning: disabling mention replies for the remainder "
                                        "of this client run after a fatal Ray actor failure",
                                        file=sys.stderr,
                                    )
                                raise

                # select action to be performed
                g.select_action(
                    tid=tid,
                    actions=candidates,
                    max_length_thread_reading=cl.max_length_thread_reading,
                )
            except Exception as e:
                print(f"Error ({g.name}): {e}")
                print(traceback.format_exc())
                pass

        return (g.name, True, None)
    except Exception as e:
        print(f"Error processing agent {g.name}: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return (g.name, False, None)
