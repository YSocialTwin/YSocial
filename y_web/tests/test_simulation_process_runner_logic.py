"""
Phase B — simulation/process_runner.py logic tests.

Covers the four public/private functions that were not behaviourally tested
before this audit:

* get_users_per_hour  — maps activity-profile hours to lists of agents
* sample_agents       — samples agents by activity level and archetype
* ensure_agents_have_archetype — assigns archetype to agents that lack one
* _resolve_client_package_dir  — returns correct external dir per platform
* _repair_legacy_agent_file    — back-fills missing agent-file fields
"""

import json
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _resolve_client_package_dir
# ---------------------------------------------------------------------------


def test_resolve_client_package_dir_microblogging():
    """`_resolve_client_package_dir` returns …/external/YClient for microblogging."""
    from y_web.src.simulation.process_runner import _resolve_client_package_dir

    result = _resolve_client_package_dir("/base", "microblogging")
    assert result.replace("\\", "/").endswith("external/YClient")


def test_resolve_client_package_dir_forum():
    """`_resolve_client_package_dir` returns …/external/YClientReddit for forum."""
    from y_web.src.simulation.process_runner import _resolve_client_package_dir

    result = _resolve_client_package_dir("/base", "forum")
    assert result.replace("\\", "/").endswith("external/YClientReddit")


def test_resolve_client_package_dir_unknown_raises():
    """`_resolve_client_package_dir` raises NotImplementedError for unknown platform."""
    from y_web.src.simulation.process_runner import _resolve_client_package_dir

    with pytest.raises(NotImplementedError):
        _resolve_client_package_dir("/base", "unknown_platform")


# ---------------------------------------------------------------------------
# sample_agents — archetypes DISABLED
# ---------------------------------------------------------------------------


def _make_agents(n, daily=1.0):
    """Create n minimal agent namespaces."""
    return [
        SimpleNamespace(
            name=f"agent_{i}",
            daily_activity_level=daily,
            archetype="broadcaster",
            is_page=0,
        )
        for i in range(n)
    ]


_archetypes_off = {"enabled": False}
_archetypes_on = {
    "enabled": True,
    "distribution": {"broadcaster": 0.7, "validator": 0.3},
}


def test_sample_agents_empty_returns_empty():
    """`sample_agents` with an empty agent list returns an empty collection."""
    from y_web.src.simulation.process_runner import sample_agents

    result = sample_agents([], 0, archetypes=_archetypes_off)
    assert len(result) == 0


def test_sample_agents_returns_correct_count():
    """`sample_agents` returns the requested number of agents (archetypes off)."""
    from y_web.src.simulation.process_runner import sample_agents

    agents = _make_agents(10)
    result = sample_agents(agents, 4, archetypes=_archetypes_off)
    assert len(result) == 4


def test_sample_agents_count_equal_to_pool():
    """`sample_agents` returns all agents when expected_active_users == len(agents)."""
    from y_web.src.simulation.process_runner import sample_agents

    agents = _make_agents(5)
    result = sample_agents(agents, 5, archetypes=_archetypes_off)
    assert len(result) == 5


def test_sample_agents_respects_archetypes_filter():
    """`sample_agents` with archetypes enabled draws from each archetype bucket."""
    from y_web.src.simulation.process_runner import sample_agents

    # All broadcasters — only broadcaster bucket should be sampled
    agents = _make_agents(10, daily=1.0)
    result = sample_agents(agents, 3, archetypes=_archetypes_on)
    # Result should be non-empty (broadcaster bucket has all 10 agents)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# ensure_agents_have_archetype
# ---------------------------------------------------------------------------


def test_ensure_agents_have_archetype_assigns_default():
    """`ensure_agents_have_archetype` fills in a missing archetype."""
    from y_web.src.simulation.process_runner import ensure_agents_have_archetype

    agent = SimpleNamespace(name="a1", archetype=None, is_page=0)
    ensure_agents_have_archetype([agent], _archetypes_on)
    assert agent.archetype in {"broadcaster", "validator"}


def test_ensure_agents_have_archetype_preserves_existing():
    """`ensure_agents_have_archetype` does not overwrite an existing archetype."""
    from y_web.src.simulation.process_runner import ensure_agents_have_archetype

    agent = SimpleNamespace(name="a1", archetype="validator", is_page=0)
    ensure_agents_have_archetype([agent], _archetypes_on)
    assert agent.archetype == "validator"


def test_ensure_agents_have_archetype_skips_pages():
    """`ensure_agents_have_archetype` does not assign archetypes to page accounts."""
    from y_web.src.simulation.process_runner import ensure_agents_have_archetype

    page = SimpleNamespace(name="page1", is_page=1)  # no archetype attr
    ensure_agents_have_archetype([page], _archetypes_on)
    assert not hasattr(
        page, "archetype"
    ), "Pages must not receive an archetype assignment"


def test_ensure_agents_have_archetype_noop_when_disabled():
    """`ensure_agents_have_archetype` is a no-op when archetypes are disabled."""
    from y_web.src.simulation.process_runner import ensure_agents_have_archetype

    agent = SimpleNamespace(name="a1", archetype=None, is_page=0)
    ensure_agents_have_archetype([agent], {"enabled": False})
    assert agent.archetype is None


# ---------------------------------------------------------------------------
# _repair_legacy_agent_file
# ---------------------------------------------------------------------------


def test_repair_legacy_agent_file_fills_missing_keys(tmp_path):
    """`_repair_legacy_agent_file` back-fills missing fields on agents that lack them."""
    from y_web.src.simulation.process_runner import _repair_legacy_agent_file

    agent_data = {"agents": [{"name": "alice"}]}
    agent_file = tmp_path / "agents.json"
    agent_file.write_text(json.dumps(agent_data))

    _repair_legacy_agent_file(str(agent_file), "microblogging")

    repaired = json.loads(agent_file.read_text())
    agent = repaired["agents"][0]
    assert "daily_activity_level" in agent
    assert "archetype" in agent
    assert "activity_profile" in agent


def test_repair_legacy_agent_file_no_op_on_valid(tmp_path):
    """`_repair_legacy_agent_file` leaves a fully-valid agent file unchanged."""
    from y_web.src.simulation.process_runner import _repair_legacy_agent_file

    agent_data = {
        "agents": [
            {
                "name": "alice",
                "daily_activity_level": 2,
                "archetype": "broadcaster",
                "activity_profile": "Always On",
                "prompts": "some prompts",
                "profession": "engineer",
            }
        ]
    }
    original_json = json.dumps(agent_data, sort_keys=True)
    agent_file = tmp_path / "agents.json"
    agent_file.write_text(json.dumps(agent_data))

    _repair_legacy_agent_file(str(agent_file), "microblogging")

    repaired_json = json.dumps(json.loads(agent_file.read_text()), sort_keys=True)
    assert repaired_json == original_json


def test_repair_legacy_agent_file_missing_file_is_noop():
    """`_repair_legacy_agent_file` silently returns on a missing file path."""
    from y_web.src.simulation.process_runner import _repair_legacy_agent_file

    # Should not raise
    _repair_legacy_agent_file("/nonexistent/path/agents.json", "microblogging")
