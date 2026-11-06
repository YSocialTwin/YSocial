"""The client configuration of a forum experiment on YForum (plan F12): validated with YForum's strict schema."""

import copy
import sys
from pathlib import Path

import pytest

from y_web.src.forum import network
from y_web.src.forum.client_config import (
    FORUM_CONTENT_RECSYS,
    FORUM_FOLLOW_RECSYS,
    MEMORY_FIELDS,
    ForumClientFormError,
    build_client_config,
    parse_client_form,
)
from y_web.src.forum.experiment_config import generate_forum_server_config

YFORUM = Path(__file__).resolve().parents[2] / "external" / "YForum"


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
    return parse_client_form(form)


def _server(**kw):
    return generate_forum_server_config("e", "u", "d", seed=11, slots_per_day=12, **kw)


def _build(values, **kw):
    args = dict(
        client_name="c1",
        population_file="pop.json",
        owner="admin",
        llm_agents_enabled=False,
        language="en",
        server_config=_server(),
    )
    args.update(kw)
    return build_client_config(values, **args)


def test_the_recommenders_are_those_of_yforums_registry():
    if not (YFORUM / "YForum").exists():
        pytest.skip("external/YForum is not checked out")
    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.YServer.recommendation import registry
    except Exception:
        pytest.skip("the registry cannot be imported here")
    finally:
        sys.path.remove(str(YFORUM))
    names = getattr(registry, "CONTENT_RECSYS", None) or getattr(
        registry, "content_names", lambda: None
    )
    if callable(names):
        names = names()
    if not names:
        pytest.skip("registry layout differs")
    assert set(FORUM_CONTENT_RECSYS) == set(names)


def test_the_defaults_give_a_valid_rule_based_client(schemas):
    config = _build(_values())
    out = schemas(copy.deepcopy(config), "config/client_config")
    assert out["mode"] == "rule_based" and out["agents"]["llm_agents"] == [None]
    assert out["num_slots_per_day"] == 12 and out["seed"] == 11  # the server's
    assert out["population"]["file"] == "pop.json"
    assert out["posts"]["visibility_rounds"] == 36
    assert out["simulation"]["actions_likelihood"]["comment"] == 0.5
    assert len(out["simulation"]["hourly_activity"]) == 24
    assert "servers" not in config and "memory_pair_limit" not in config["agents"]


def test_every_parameter_of_the_standard_form_reaches_the_configuration(schemas):
    form = {
        "days": "5",
        "initial_agents": "40",
        "percentage_new_agents_iteration": "0.1",
        "percentage_removed_agents_iteration": "0.02",
        "post": "4",
        "comment": "6",
        "read": "1",
        "search": "2",
        "share_link": "3",
        "share_image": "7",
        "visibility_rounds": "20",
        "max_length_thread_reading": "6",
        "reading_from_follower_ratio": "0.4",
        "probability_of_daily_follow": "0.2",
        "probability_of_secondary_follow": "0.3",
        "probability_of_follow_back": "0.1",
        "attention_window": "100",
        "max_thread_context_chars": "2000",
        "max_replies_per_round": "3",
        "reply_cooldown_rounds": "1",
        "recsys_type": "HotRanking",
        "frecsys_type": "Jaccard",
        "user_type": "llama3.2",
        "llm": "http://127.0.0.1:11434/v1",
        "llm_api_key": "k",
        "llm_max_tokens": "512",
        "llm_temperature": "0.7",
        "llm_v_agent": "minicpm-v",
        "llm_v": "http://127.0.0.1:11435/v1",
        "llm_v_api_key": "kv",
        "llm_v_max_tokens": "200",
        "llm_v_temperature": "0.3",
        "hourly_8": "0.05",
        "memory_pair_limit": "9",
        "memory_semantic_enabled": "on",
        "memory_embedding_async": "on",
        "memory_importance_mode": "heuristic",
        "memory_search_k": "11",
    }
    out = schemas(
        copy.deepcopy(
            _build(
                _values(**form),
                llm_agents_enabled=True,
                language="it",
                switches={
                    "emotion": True,
                    "opinion": True,
                    "stress_reward": True,
                    "memory": True,
                },
                stress_reward_config={"backward_rounds": 6},
                population_attributes={
                    "political_leanings": ["left", "right"],
                    "ages": [20, 50],
                    "languages": ["english"],
                    "toxicity_levels": ["no"],
                    "education_levels": ["phd"],
                },
                network_file="c1_network.csv",
            )
        ),
        "config/client_config",
    )
    assert out["mode"] == "llm" and out["num_days"] == 5
    assert out["simulation"]["starting_agents"] == 40
    likelihood = out["simulation"]["actions_likelihood"]
    assert {k: likelihood[k] for k in ("post", "comment", "read", "search", "share_link", "image")} == {
        "post": 0.4, "comment": 0.6, "read": 0.1, "search": 0.2,
        "share_link": 0.3, "image": 0.7,
    }  # fmt: skip
    assert out["simulation"]["hourly_activity"]["8"] == 0.05
    assert out["posts"]["visibility_rounds"] == 20
    a = out["agents"]
    assert a["llm_agents"] == ["llama3.2"] and a["llm_v_agent"] == ["minicpm-v"]
    assert a["max_thread_context_chars"] == 2000 and a["max_replies_per_round"] == 3
    assert a["reply_cooldown_rounds"] == 1 and a["probability_of_follow_back"] == 0.1
    assert a["age"] == {"min": 20, "max": 50} and a["political_leanings"] == [
        "left",
        "right",
    ]
    assert a["memory_enabled"] is True and a["memory_pair_limit"] == 9
    assert a["memory_semantic_enabled"] is True and a["memory_embedding_async"] is True
    assert a["memory_search_k"] == 11 and a["memory_importance_mode"] == "heuristic"
    assert (
        out["servers"]["llm_api_key"] == "k"
        and out["servers"]["llm_v_max_tokens"] == 200
    )
    assert out["servers"]["llm_temperature"] == 0.7
    assert out["llm"]["language"] == "it"
    assert (out["recsys"]["content"], out["recsys"]["follow"]) == (
        "HotRanking",
        "Jaccard",
    )
    assert out["population"]["network_file"] == "c1_network.csv"
    assert out["simulation"]["emotion_annotation"] is True
    assert out["simulation"]["opinion_dynamics"]["enabled"] is True
    assert out["stress_reward"] == {"enabled": True, "backward_rounds": 6}


def test_all_the_memory_fields_of_the_form_are_known_to_the_schema(schemas):
    # the whole memory block validates
    values = _values(user_type="m")
    out = schemas(_build(values, llm_agents_enabled=True), "config/client_config")
    for key in MEMORY_FIELDS:
        assert key in out["agents"], key


@pytest.mark.parametrize(
    "form", [{"infinite_duration": "on", "days": "30"}, {"days": "-1"}]
)
def test_run_until_stopped_is_zero_days_for_yforum(schemas, form):
    values = _values(**form)
    assert values["days"] == -1
    out = schemas(_build(values), "config/client_config")
    assert out["num_days"] == 0


def test_an_unlimited_token_count_keeps_yforums_default(schemas):
    values = _values(user_type="m", llm_max_tokens="-1", llm_v_max_tokens="-1")
    out = schemas(_build(values, llm_agents_enabled=True), "config/client_config")
    assert (
        out["servers"]["llm_max_tokens"] == 800
        and out["servers"]["llm_v_max_tokens"] == 300
    )


def test_memory_is_off_for_rule_based_agents(schemas):
    out = schemas(_build(_values(), switches={"memory": True}), "config/client_config")
    assert out["agents"]["memory_enabled"] is False
    assert "memory_pair_limit" not in out["agents"]


@pytest.mark.parametrize(
    "form",
    [
        {"days": "0"},
        {"days": "x"},
        {"probability_of_daily_follow": "1.5"},
        {"post": "11"},
        {"recsys_type": "Nope"},
        {"frecsys_type": "Nope"},
        {"llm_temperature": "9"},
        {"hourly_3": "2"},
        {
            "post": "0",
            "comment": "0",
            "read": "0",
            "search": "0",
            "share_link": "0",
            "share_image": "0",
        },
    ],
)
def test_out_of_range_values_are_refused(form):
    with pytest.raises(ForumClientFormError):
        _values(**form)


def test_a_model_is_required_for_llm_agents():
    with pytest.raises(ForumClientFormError, match="LLM model"):
        _build(_values(), llm_agents_enabled=True)


def test_the_synthetic_networks_follow_the_standard_models():
    names = [f"u{i}" for i in range(30)]
    for model in network.MODELS:
        if model == "LFR":
            continue  # the benchmark needs a larger, tuned graph
        edges = network.generate_edges(model, names)
        assert edges and all(a in names and b in names and a != b for a, b in edges)
        assert (edges[1][1], edges[1][0]) == edges[0]  # both directions of each edge
    with pytest.raises(network.NetworkError):
        network.generate_edges("XX", names)
    with pytest.raises(network.NetworkError):
        network.generate_edges("BA", names[:2])
    assert network.parse_parameters({"network_m": "3"})["network_m"] == 3
    with pytest.raises(network.NetworkError):
        network.parse_parameters({"network_p": "x"})


def test_an_uploaded_network_keeps_only_the_population_pairs():
    edges, skipped = network.filter_uploaded(
        "a,b\nb,c\na,zz\nbad\n\na,a\n", ["a", "b", "c"]
    )
    assert edges == [("a", "b"), ("b", "c")]
    assert skipped == ["a,zz", "bad", "a,a"]


def test_the_forum_recommenders_have_no_duplicates():
    assert len(set(FORUM_CONTENT_RECSYS)) == len(FORUM_CONTENT_RECSYS)
    assert len(set(FORUM_FOLLOW_RECSYS)) == len(FORUM_FOLLOW_RECSYS)
