"""The experiment switches of a forum HPC experiment reach the keys YForum reads (plan F12).

The configurations built here are validated against the strict JSON Schemas of YForum, so a key the runtime does not
know (or a switch written only as a mirror) fails the test. Skipped when YForum is not checked out.
"""

import copy
import json
import sys
from pathlib import Path

import pytest

from y_web.src.forum.experiment_config import (
    ForumConfigError,
    apply_experiment_switches,
    apply_switches_to_client,
    generate_forum_server_config,
    read_switches,
)

YFORUM = Path(__file__).resolve().parents[2] / "external" / "YForum"


@pytest.fixture(scope="module")
def schemas():
    if not (YFORUM / "YForum" / "config_validation.py").exists():
        pytest.skip("external/YForum is not checked out")
    pytest.importorskip("jsonschema")
    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.config_validation import validate
    except Exception as exc:  # pragma: no cover - optional dependency
        pytest.skip(f"YForum cannot be imported: {exc}")
    finally:
        sys.path.remove(str(YFORUM))
    return validate


@pytest.fixture
def client_config():
    path = YFORUM / "example" / "rule_based" / "client_config.json"
    if not path.exists():
        pytest.skip("the YForum example client configuration is missing")
    return json.loads(path.read_text(encoding="utf-8"))


def _server(**kw):
    return generate_forum_server_config(
        exp_name="demo",
        db_uri="experiments/x/database_server.db",
        data_path="experiments/x/",
        **kw,
    )


def test_the_generated_server_configuration_satisfies_the_yforum_schema(schemas):
    config = _server(topics=["politics", " ", "sport"], seed=7)
    result = schemas(config, "config/server_config")
    assert result["seed"] == 7 and result["topics"] == ["politics", "sport"]
    assert result["platform_type"] == "forum"
    # federation and human participants are opt-in: nothing here turns them on
    assert result["federation"]["enabled"] is False
    assert result["human"]["enabled"] is False


def test_every_switch_is_written_where_the_runtime_reads_it(schemas, client_config):
    server = _server(
        toxicity_annotation=True,
        sentiment_annotation=True,
        emotion_annotation=True,
        opinion_dynamics_enabled=True,
        stress_reward_enabled=True,
        memory_enabled=True,
        perspective_api="KEY",
    )
    checked = schemas(server, "config/server_config")
    assert checked["toxicity_annotation"] is True
    assert checked["sentiment_annotation"] is True
    assert checked["emotion_annotation"] is True
    assert checked["stress_reward"] == {"enabled": True}
    assert checked["perspective_api"] == "KEY"

    client = apply_switches_to_client(
        copy.deepcopy(client_config),
        emotion=True,
        opinion=True,
        stress_reward=True,
        memory=True,
        stress_reward_config={"backward_rounds": 12, "system": {}},
    )
    out = schemas(client, "config/client_config")
    assert out["simulation"]["emotion_annotation"] is True
    assert out["simulation"]["opinion_dynamics"]["enabled"] is True
    assert out["stress_reward"]["enabled"] is True
    assert out["stress_reward"]["backward_rounds"] == 12
    assert out["agents"]["memory_enabled"] is True


def test_switching_off_turns_the_runtime_keys_off_too(schemas, client_config):
    on = _server(
        toxicity_annotation=True, stress_reward_enabled=True, memory_enabled=True
    )
    apply_experiment_switches(
        on,
        toxicity=False,
        sentiment=False,
        emotion=False,
        opinion=False,
        stress_reward=False,
        memory=False,
    )
    out = schemas(on, "config/server_config")
    assert out["toxicity_annotation"] is False and out["stress_reward"] == {
        "enabled": False
    }
    assert out["perspective_api"] is None and out["memory"] == {"enabled": False}

    client = apply_switches_to_client(
        copy.deepcopy(client_config),
        emotion=False,
        opinion=False,
        stress_reward=False,
        memory=False,
    )
    checked = schemas(client, "config/client_config")
    assert checked["simulation"]["opinion_dynamics"]["enabled"] is False
    assert checked["agents"]["memory_enabled"] is False
    assert checked["stress_reward"]["enabled"] is False


def test_a_stress_reward_under_simulation_is_kept_in_step(schemas, client_config):
    # in YForum a key under simulation wins over the top-level one
    client = copy.deepcopy(client_config)
    client.setdefault("simulation", {})["stress_reward"] = {"enabled": False}
    apply_switches_to_client(client, stress_reward=True)
    assert client["stress_reward"]["enabled"] is True
    assert client["simulation"]["stress_reward"]["enabled"] is True
    schemas(client, "config/client_config")


def test_none_leaves_a_switch_as_it_is():
    config = _server(opinion_dynamics_enabled=True, memory_enabled=True)
    apply_experiment_switches(config, toxicity=True)
    assert config["opinion_dynamics_enabled"] is True
    assert config["memory"] == {"enabled": True}
    client = {
        "agents": {"memory_enabled": True},
        "simulation": {"opinion_dynamics": {"enabled": True}},
    }
    apply_switches_to_client(client, emotion=False)
    assert client["agents"]["memory_enabled"] is True
    assert client["simulation"]["opinion_dynamics"]["enabled"] is True


def test_the_page_reads_back_what_was_written():
    config = _server(
        toxicity_annotation=True,
        opinion_dynamics_enabled=True,
        stress_reward_enabled=True,
    )
    assert read_switches(config) == {
        "toxicity": True,
        "sentiment": False,
        "emotion": False,
        "opinion": True,
        "stress_reward": True,
        "memory": False,
    }


@pytest.mark.parametrize("bad", ["x", 0, 97])
def test_slots_per_day_must_be_in_range(bad):
    with pytest.raises(ForumConfigError):
        _server(slots_per_day=bad)
