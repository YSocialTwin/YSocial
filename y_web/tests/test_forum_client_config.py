"""The client configuration of a forum experiment on YForum (plan F12): validated with YForum's strict schema."""

import copy
import sys
from pathlib import Path

import pytest

from y_web.src.forum.client_config import (
    ForumClientFormError,
    build_client_config,
    parse_client_form,
)
from y_web.src.forum.experiment_config import generate_forum_server_config

YFORUM = Path(__file__).resolve().parents[2] / "external" / "YForum"
CONTENT = ["ReverseChrono", "ReverseChronoFollowersPopularity", "HotRanking"]
FOLLOW = ["PreferentialAttachment", "Jaccard"]


@pytest.fixture(scope="module")
def schemas():
    if not (YFORUM / "YForum" / "config_validation.py").exists():
        pytest.skip("external/YForum is not checked out")
    pytest.importorskip("jsonschema")
    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.config_validation import validate
    finally:
        sys.path.remove(str(YFORUM))
    return validate


def _values(**form):
    return parse_client_form(form, content_recsys=CONTENT, follow_recsys=FOLLOW)


def _server(**kw):
    return generate_forum_server_config("e", "u", "d", seed=11, slots_per_day=12, **kw)


def test_the_defaults_give_a_valid_rule_based_client(schemas):
    config = build_client_config(
        _values(),
        client_name="c1",
        population_file="pop.json",
        owner="admin",
        llm_agents_enabled=False,
        language="en",
        server_config=_server(),
    )
    out = schemas(config, "config/client_config")
    assert out["mode"] == "rule_based" and out["agents"]["llm_agents"] == [None]
    assert out["num_slots_per_day"] == 12 and out["seed"] == 11  # the server's
    assert out["population"]["file"] == "pop.json"
    assert "servers" not in config and "llm" not in config


def test_an_llm_client_carries_the_model_and_the_switches(schemas):
    values = _values(
        llm_model="llama3.2",
        llm_url="http://127.0.0.1:11434/v1",
        content_recsys="HotRanking",
        follow_recsys="Jaccard",
        likelihood_post="0.3",
        days="5",
    )
    config = build_client_config(
        values,
        client_name="c2",
        population_file="pop.json",
        owner="admin",
        llm_agents_enabled=True,
        language="it",
        server_config=_server(),
        switches={
            "emotion": True,
            "opinion": True,
            "stress_reward": True,
            "memory": True,
        },
        stress_reward_config={"backward_rounds": 6},
    )
    out = schemas(copy.deepcopy(config), "config/client_config")
    assert out["mode"] == "llm" and out["num_days"] == 5
    assert out["agents"]["llm_agents"] == ["llama3.2"]
    assert out["servers"]["llm"] == "http://127.0.0.1:11434/v1"
    assert out["llm"]["language"] == "it"
    assert (
        out["recsys"]["content"] == "HotRanking"
        and out["recsys"]["follow"] == "Jaccard"
    )
    assert out["simulation"]["actions_likelihood"]["post"] == 0.3
    assert out["simulation"]["emotion_annotation"] is True
    assert out["simulation"]["opinion_dynamics"]["enabled"] is True
    assert out["stress_reward"] == {"enabled": True, "backward_rounds": 6}
    assert out["agents"]["memory_enabled"] is True


def test_memory_is_off_for_rule_based_agents(schemas):
    config = build_client_config(
        _values(),
        client_name="c",
        population_file="p.json",
        owner="a",
        llm_agents_enabled=False,
        language="en",
        server_config=_server(),
        switches={"memory": True},
    )
    assert schemas(config, "config/client_config")["agents"]["memory_enabled"] is False


@pytest.mark.parametrize(
    "form",
    [
        {"days": "0"},
        {"days": "x"},
        {"probability_of_daily_follow": "1.5"},
        {"content_recsys": "Nope"},
        {"follow_recsys": "Nope"},
        {"llm_temperature": "3"},
        {
            "likelihood_post": "0",
            "likelihood_comment": "0",
            "likelihood_read": "0",
            "likelihood_search": "0",
        },
    ],
)
def test_out_of_range_values_are_refused(form):
    with pytest.raises(ForumClientFormError):
        _values(**form)


def test_a_model_is_required_for_llm_agents():
    with pytest.raises(ForumClientFormError, match="llm_model"):
        build_client_config(
            _values(),
            client_name="c",
            population_file="p.json",
            owner="a",
            llm_agents_enabled=True,
            language="en",
            server_config=_server(),
        )
