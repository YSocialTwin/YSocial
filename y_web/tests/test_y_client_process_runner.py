from types import SimpleNamespace

import pytest

from y_web.src.simulation.process_runner import (
    _get_client_archetypes,
    _sync_experiment_stress_reward_into_client_config,
    process_agent,
)

pytestmark = pytest.mark.unit


class DummyClient:
    pass


class ClientWithArchetypes:
    agent_archetypes = {
        "enabled": True,
        "distribution": {"validator": 1.0},
        "transitions": {},
    }


def test_get_client_archetypes_defaults_to_disabled():
    assert _get_client_archetypes(DummyClient()) == {
        "enabled": False,
        "distribution": {},
        "transitions": {},
    }


def test_get_client_archetypes_preserves_existing_config():
    assert (
        _get_client_archetypes(ClientWithArchetypes())
        == ClientWithArchetypes.agent_archetypes
    )


def test_process_agent_binds_shared_sim_clock():
    calls = []

    class DummyAgent:
        is_page = 0
        round_actions = 1
        name = "alice"

        def reply(self, tid):
            calls.append(("reply", tid, getattr(self, "sim_clock", None)))

        def select_action(self, tid, actions, max_length_thread_reading):
            calls.append(("select", tid, getattr(self, "sim_clock", None)))

    sim_clock = object()
    cl = SimpleNamespace(
        actions_likelihood={"READ": 1.0},
        pages=[],
        max_length_thread_reading=10,
        sim_clock=sim_clock,
    )
    exp = SimpleNamespace(platform_type="microblogging")
    result = process_agent(
        DummyAgent(),
        {"enabled": False, "distribution": {}, "transitions": {}},
        cl,
        exp,
        7,
        None,
        __import__("random").Random(1),
    )

    assert result == ("alice", True, None)
    assert calls
    assert all(call[2] is sim_clock for call in calls)


def test_process_agent_validator_keeps_forum_share_aliases():
    selected_actions = []

    class DummyAgent:
        is_page = 0
        round_actions = 1
        name = "alice"
        archetype = "validator"

        def select_action(self, tid, actions, max_length_thread_reading):
            selected_actions.extend(actions)

    cl = SimpleNamespace(
        actions_likelihood={
            "READ": 1.0,
            "NEWS": 1.0,
            "SHARE_LINK": 1.0,
            "SHARE_IMAGE": 1.0,
            "POST": 1.0,
        },
        pages=[],
        max_length_thread_reading=10,
        sim_clock=object(),
        config={"agents": {"llm_agents": []}},
    )
    exp = SimpleNamespace(platform_type="forum")

    result = process_agent(
        DummyAgent(),
        {"enabled": True, "distribution": {}, "transitions": {}},
        cl,
        exp,
        7,
        None,
        __import__("random").Random(1),
    )

    assert result == ("alice", True, None)
    assert any(
        action in selected_actions
        for action in ("READ", "NEWS", "SHARE_LINK", "SHARE_IMAGE")
    )
    assert (
        "SHARE_LINK" in selected_actions
        or "SHARE_IMAGE" in selected_actions
        or "NEWS" in selected_actions
    )
    assert "POST" not in selected_actions


@pytest.mark.parametrize("platform_type", ["microblogging", "forum", "hpc"])
def test_stress_reward_sync_applies_to_supported_platforms(platform_type):
    client_config = {"simulation": {}}
    server_config = {
        "stress_reward": {
            "enabled": True,
            "backward_rounds": 18,
            "system": {"churn": {"enabled": False}},
        }
    }

    updated, changed = _sync_experiment_stress_reward_into_client_config(
        client_config, server_config, platform_type
    )

    assert changed is True
    assert updated["stress_reward"]["enabled"] is True
    assert updated["stress_reward"]["backward_rounds"] == 18
    assert updated["stress_reward"]["system"]["churn"]["enabled"] is False


def test_stress_reward_sync_skips_unsupported_platforms():
    client_config = {"simulation": {}}
    server_config = {"stress_reward": {"enabled": True, "backward_rounds": 18}}

    updated, changed = _sync_experiment_stress_reward_into_client_config(
        client_config, server_config, "unknown"
    )

    assert changed is False
    assert "stress_reward" not in updated
