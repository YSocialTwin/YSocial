"""Agents rebuilt on a resume (archetype ``None``) are still sampled; a slot that samples nobody is reported.

World Simulation 1, experiment 7 (microblogging): after a stop and restart the client advanced the slots but no agent
acted. The resumed agents had archetype ``None`` (the server does not store it), the archetype-stratified sampler found
no candidate for validator/broadcaster/explorer and returned an empty list, silently.
"""

import io
import random
from types import SimpleNamespace

from y_web.src.simulation import agent_sampler as sampler

sample_agents = sampler.sample_agents
process_agent = sampler.process_agent


def archetype_of(a):
    return sampler.archetype_of(a)


def warn_if_empty_slot(*args, **kwargs):
    return sampler.warn_if_empty_slot(*args, **kwargs)


ARCHETYPES = {
    "enabled": True,
    "distribution": {"validator": 0.52, "broadcaster": 0.2, "explorer": 0.28},
    "transitions": {},
}


def agent(name, archetype=None, level=3, with_attribute=True):
    a = SimpleNamespace(
        name=name, daily_activity_level=level, is_page=0, round_actions=1, calls=[]
    )
    if with_attribute:
        a.archetype = archetype
    a.evaluate_stress_reward_churn = lambda tid, rng=None: False
    a.select_action = lambda tid, actions=None, **kw: a.calls.append(actions)
    a.reply = lambda tid=None: None
    return a


# ---------------------------------------------------------------------------------------------- sampling
def test_agents_without_archetype_are_sampled_as_broadcasters():
    agents = [agent(f"a{i}") for i in range(100)]
    sampled = sample_agents(agents, 3, ARCHETYPES)
    assert (
        len(sampled) == 1
    )  # 20% broadcaster share of 3 expected users, at least one: the default archetype counts


def test_agents_missing_the_attribute_are_sampled_too():
    agents = [agent(f"a{i}", with_attribute=False) for i in range(10)]
    assert len(sample_agents(agents, 5, ARCHETYPES)) == 1


def test_mixed_population_keeps_the_stratification():
    agents = [agent(f"v{i}", "validator") for i in range(20)] + [
        agent(f"e{i}", "explorer") for i in range(20)
    ]
    agents += [
        agent(f"n{i}") for i in range(20)
    ]  # unknown archetype: counted as broadcaster
    sampled = sample_agents(agents, 10, ARCHETYPES)
    kinds = sorted(archetype_of(a) for a in sampled)
    assert kinds == ["broadcaster"] * 2 + ["explorer"] * 2 + ["validator"] * 5


def test_archetype_of_defaults_only_when_missing_or_empty():
    assert archetype_of(agent("x", "explorer")) == "explorer"
    assert archetype_of(agent("x", None)) == "broadcaster"
    assert archetype_of(agent("x", "")) == "broadcaster"
    assert archetype_of(SimpleNamespace()) == "broadcaster"


def test_process_agent_acts_for_an_agent_without_archetype():
    g = agent("a")
    cl = SimpleNamespace(
        actions_likelihood={"post": 3.0, "comment": 5.0, "read": 2.0},
        pages=[],
        config={},
        max_length_thread_reading=5,
    )
    name, ok, churned = process_agent(
        g,
        ARCHETYPES,
        cl,
        SimpleNamespace(platform_type="microblogging"),
        5,
        None,
        random.Random(1),
    )
    assert (name, ok, churned) == ("a", True, None)
    assert g.calls, "the agent must have executed select_action at least once"


# ---------------------------------------------------------------------------------------------- warning
def test_warning_is_written_once_per_day_when_nobody_is_sampled():
    out, warned = io.StringIO(), set()
    cands = [agent("a"), agent("b")]
    first = warn_if_empty_slot(warned, 6, 17, 100, [], cands, 3, ARCHETYPES, stream=out)
    again = warn_if_empty_slot(warned, 6, 18, 100, [], cands, 3, ARCHETYPES, stream=out)
    nextday = warn_if_empty_slot(
        warned, 7, 0, 100, [], cands, 3, ARCHETYPES, stream=out
    )
    assert (
        first
        and "day 6 hour 17" in first
        and "no agent was sampled" in first
        and "None" in first
    )
    assert again is None
    assert nextday and "day 7" in nextday
    assert out.getvalue().count("Warning:") == 2


def test_no_warning_when_somebody_was_sampled_or_there_are_no_agents():
    out = io.StringIO()
    assert (
        warn_if_empty_slot(
            set(), 1, 1, 100, [agent("a")], [agent("a")], 3, ARCHETYPES, stream=out
        )
        is None
    )
    assert warn_if_empty_slot(set(), 1, 1, 0, [], [], 0, ARCHETYPES, stream=out) is None
    assert out.getvalue() == ""


def test_warning_names_the_activity_profile_when_there_are_no_candidates():
    message = warn_if_empty_slot(
        set(), 2, 3, 10, [], [], 0, ARCHETYPES, stream=io.StringIO()
    )
    assert "activity profile" in message
