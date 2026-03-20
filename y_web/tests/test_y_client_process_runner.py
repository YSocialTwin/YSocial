from types import SimpleNamespace

from y_web.utils.y_client_process_runner import (
    _get_client_archetypes,
    process_agent,
)


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

    assert result == ("alice", True)
    assert calls
    assert all(call[2] is sim_clock for call in calls)
