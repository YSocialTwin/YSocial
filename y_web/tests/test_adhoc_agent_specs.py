import pytest
pytestmark = pytest.mark.unit

from y_web.routes.admin.sub.clients._crud import (
    _adhoc_agent_specs,
    _adhoc_stress_reward_config_for_experiment,
    _build_adhoc_client_initial_values,
    _coerce_adhoc_client_setting,
    _filter_adhoc_agent_specs_for_experiment,
)


def test_adhoc_agent_specs_include_propaganda_client_settings():
    specs = _adhoc_agent_specs()

    propaganda = next(spec for spec in specs if spec["agent_type"] == "propaganda")

    assert propaganda["requires_llm"] is True
    assert propaganda["requires_opinion_dynamics"] is True
    assert any(
        parameter["name"] == "propaganda_campaigns"
        for parameter in propaganda["client_parameters"]
    )
    assert any(
        parameter["name"] == "opening_llm_prompt_override"
        for parameter in propaganda["client_parameters"]
    )
    assert any(
        parameter["name"] == "reply_llm_prompt_override"
        for parameter in propaganda["client_parameters"]
    )
    assert [section["key"] for section in propaganda["client_parameter_sections"]] == [
        "campaign",
        "conversation",
        "opening_prompt",
        "reply_prompt",
    ]
    assert not any(
        parameter["name"] == "llm_prompt_override"
        for parameter in propaganda["client_parameters"]
    )
    assert propaganda["prompt_templates"]


def test_adhoc_agent_specs_include_comic_relief_settings():
    specs = _adhoc_agent_specs()

    comic_relief = next(spec for spec in specs if spec["agent_type"] == "comic_relief")

    assert comic_relief["requires_llm"] is True
    assert not any(
        parameter["name"] == "humor_styles"
        for parameter in comic_relief["client_parameters"]
    )
    assert any(
        parameter["name"] == "opening_llm_prompt_override"
        for parameter in comic_relief["client_parameters"]
    )
    assert any(
        parameter["name"] == "reply_llm_prompt_override"
        for parameter in comic_relief["client_parameters"]
    )
    assert comic_relief["prompt_templates"]


def test_adhoc_agent_specs_include_mop_client_settings():
    specs = _adhoc_agent_specs()

    mop = next(spec for spec in specs if spec["agent_type"] == "master_of_puppets")

    assert mop["requires_llm"] is True
    assert any(
        parameter["name"] == "mop_campaigns" for parameter in mop["client_parameters"]
    )
    assert not any(
        parameter["name"] == "llm_prompt_instructions"
        for parameter in mop["client_parameters"]
    )


def test_adhoc_agent_specs_include_stress_attacker_settings():
    specs = _adhoc_agent_specs()

    stress_attacker = next(
        spec for spec in specs if spec["agent_type"] == "stress_attacker"
    )

    assert stress_attacker["requires_llm"] is True
    assert stress_attacker["requires_stress_reward"] is True
    assert any(
        parameter["name"] == "target_filters"
        for parameter in stress_attacker["client_parameters"]
    )
    assert any(
        parameter["name"] == "report_burst_enabled"
        for parameter in stress_attacker["client_parameters"]
    )
    assert any(
        parameter["name"] == "critical_comment_mode"
        for parameter in stress_attacker["client_parameters"]
    )
    assert any(
        parameter["name"] == "critical_comment_text"
        for parameter in stress_attacker["client_parameters"]
    )
    assert any(
        parameter["name"] == "llm_prompt_override"
        for parameter in stress_attacker["client_parameters"]
    )
    assert not any(
        parameter["name"] == "llm_prompt_instructions"
        for parameter in stress_attacker["client_parameters"]
    )
    prompt_override = next(
        parameter
        for parameter in stress_attacker["client_parameters"]
        if parameter["name"] == "llm_prompt_override"
    )
    assert prompt_override["section"] == "comment_strategy"
    assert prompt_override["visible_if"] == {
        "setting": "critical_comment_mode",
        "equals": "llm",
    }
    assert all(
        section["key"] != "prompt_customization"
        for section in stress_attacker["client_parameter_sections"]
    )
    assert stress_attacker["prompt_templates"]


def test_adhoc_agent_specs_include_moderator_conditional_prompt_settings():
    specs = _adhoc_agent_specs()

    moderator = next(spec for spec in specs if spec["agent_type"] == "moderator")

    assert any(
        parameter["name"] == "standard_message"
        for parameter in moderator["client_parameters"]
    )
    assert not any(
        parameter["name"] == "llm_prompt_instructions"
        for parameter in moderator["client_parameters"]
    )
    prompt_override = next(
        parameter
        for parameter in moderator["client_parameters"]
        if parameter["name"] == "llm_prompt_override"
    )
    assert prompt_override["section"] == "moderation"
    assert prompt_override["visible_if"] == {
        "setting": "moderation_action_type",
        "equals": "personalized",
    }
    assert all(
        section["key"] != "prompt_customization"
        for section in moderator["client_parameter_sections"]
    )


def test_target_filters_client_setting_is_validated_against_population_features():
    parameter = {
        "name": "target_filters",
        "type": "target_filters",
        "required": False,
    }

    value = _coerce_adhoc_client_setting(
        parameter,
        '[{"feature": "leaning", "value": "Democrat"}, {"feature": "gender", "value": "female"}, {"feature": "topic", "value": "Climate"}, {"feature": "custom:Class", "value": "Mage"}, {"feature": "min_age", "value": "40"}]',
        experiment_topic_ids=set(),
        experiment_topics_by_id={},
        opinion_groups_by_name={},
        age_classes_by_name={},
        leaning_names=set(),
        population_filter_options={
            "features": [
                {
                    "key": "leaning",
                    "value_type": "enum",
                    "values": [{"value": "Democrat", "label": "Democrat"}],
                },
                {
                    "key": "gender",
                    "value_type": "enum",
                    "values": [{"value": "female", "label": "female"}],
                },
                {
                    "key": "topic",
                    "value_type": "enum",
                    "values": [{"value": "Climate", "label": "Climate"}],
                },
                {
                    "key": "custom:Class",
                    "value_type": "enum",
                    "values": [{"value": "Mage", "label": "Mage"}],
                },
                {
                    "key": "min_age",
                    "value_type": "integer",
                    "values": [],
                },
            ]
        },
    )

    assert value == [
        {"feature": "leaning", "value": "Democrat"},
        {"feature": "gender", "value": "female"},
        {"feature": "topic", "value": "Climate"},
        {"feature": "custom:Class", "value": "Mage"},
        {"feature": "min_age", "value": 40},
    ]


def test_enum_multi_client_setting_normalizes_and_validates_values():
    parameter = {
        "name": "humor_styles",
        "type": "enum_multi[dad_jokes, nerdy, wordplay]",
        "required": True,
    }

    value = _coerce_adhoc_client_setting(
        parameter,
        ["dad_jokes", "wordplay", "dad_jokes"],
        experiment_topic_ids=set(),
        experiment_topics_by_id={},
        opinion_groups_by_name={},
        age_classes_by_name={},
        leaning_names=set(),
        population_filter_options={"features": []},
    )

    assert value == ["dad_jokes", "wordplay"]


def test_stress_attacker_is_filtered_out_when_stress_reward_disabled(monkeypatch):
    specs = _adhoc_agent_specs()

    class DummyExp:
        pass

    monkeypatch.setattr(
        "y_web.routes.admin.sub.clients._crud._opinion_dynamics_enabled_for_client_creation",
        lambda _exp: True,
    )
    monkeypatch.setattr(
        "y_web.routes.admin.sub.clients._crud._stress_reward_enabled_for_adhoc",
        lambda _exp: False,
    )

    filtered = _filter_adhoc_agent_specs_for_experiment(DummyExp(), specs)

    assert all(spec["agent_type"] != "stress_attacker" for spec in filtered)


def test_adhoc_stress_reward_config_reads_hpc_server_config(tmp_path, monkeypatch):
    exp_dir = tmp_path / "y_web" / "experiments" / "exp_hpc"
    exp_dir.mkdir(parents=True)
    (exp_dir / "server_config.json").write_text(
        '{"stress_reward": {"enabled": true, "backward_rounds": 12}}',
        encoding="utf-8",
    )

    class DummyExp:
        simulator_type = "HPC"

    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "y_web.routes.admin.sub.clients._crud._get_experiment_folder_name",
        lambda _exp: "exp_hpc",
    )

    config = _adhoc_stress_reward_config_for_experiment(DummyExp())

    assert config["enabled"] is True
    assert config["backward_rounds"] == 12


def test_topic_target_client_setting_is_validated_against_experiment_topics():
    parameter = {
        "name": "propaganda_campaigns",
        "type": "topic_targets",
        "required": True,
    }

    value = _coerce_adhoc_client_setting(
        parameter,
        '[{"topic_id": 7, "target_opinion_group": "Supportive", "target_agent_opinion_group": "Supportive", "target_leaning": "Left", "target_age_classes": ["Young"]}]',
        experiment_topic_ids={7, 8},
        experiment_topics_by_id={7: "Climate"},
        opinion_groups_by_name={
            "Supportive": {
                "name": "Supportive",
                "lower_bound": 0.7,
                "upper_bound": 0.9,
                "value": 0.8,
            }
        },
        age_classes_by_name={
            "Young": {
                "name": "Young",
                "age_start": 18,
                "age_end": 25,
            }
        },
        leaning_names={"Left", "Right"},
    )

    assert value == [
        {
            "topic_id": 7,
            "topic_name": "Climate",
            "target_opinion": 0.8,
            "target_opinion_group": "Supportive",
            "target_agent_opinion_group": "Supportive",
            "target_agent_opinion_group_bounds": {
                "name": "Supportive",
                "lower_bound": 0.7,
                "upper_bound": 0.9,
                "value": 0.8,
            },
            "target_leaning": "Left",
            "target_age_classes": [
                {
                    "name": "Young",
                    "age_start": 18,
                    "age_end": 25,
                }
            ],
        }
    ]


def test_topic_target_client_setting_normalizes_group_names():
    parameter = {
        "name": "propaganda_campaigns",
        "type": "topic_targets",
        "required": True,
    }

    value = _coerce_adhoc_client_setting(
        parameter,
        '[{"topic_id": 7, "target_opinion_group": " supportive ", "target_agent_opinion_group": " supportive "}]',
        experiment_topic_ids={7},
        experiment_topics_by_id={7: "Climate"},
        opinion_groups_by_name={
            "Supportive": {
                "name": "Supportive",
                "lower_bound": 0.7,
                "upper_bound": 0.9,
                "value": 0.8,
            }
        },
        age_classes_by_name={},
        leaning_names=set(),
    )

    assert value[0]["target_opinion_group"] == "Supportive"
    assert value[0]["target_agent_opinion_group_bounds"]["name"] == "Supportive"


def test_mop_target_setting_accepts_optional_opinion_group():
    parameter = {
        "name": "mop_campaigns",
        "type": "mop_targets",
        "required": True,
    }

    value = _coerce_adhoc_client_setting(
        parameter,
        '[{"topic_id": 7, "target_opinion_group": " supportive "}, {"topic_id": 8, "target_opinion_group": ""}]',
        experiment_topic_ids={7, 8},
        experiment_topics_by_id={7: "Climate", 8: "War"},
        opinion_groups_by_name={
            "Supportive": {
                "name": "Supportive",
                "lower_bound": 0.7,
                "upper_bound": 0.9,
                "value": 0.8,
            }
        },
        age_classes_by_name={},
        leaning_names=set(),
    )

    assert value == [
        {
            "topic_id": 7,
            "topic_name": "Climate",
            "target_opinion": 0.8,
            "target_opinion_group": "Supportive",
        },
        {
            "topic_id": 8,
            "topic_name": "War",
            "target_opinion": None,
            "target_opinion_group": "",
        },
    ]


def test_build_adhoc_client_initial_values_reads_existing_config():
    config = {
        "client": {
            "client_id": "prop1",
            "agent_type": "propaganda",
            "servers": {
                "llm_backend": "ollama",
                "llm": "http://127.0.0.1:11434/v1",
                "llm_api_key": "NULL",
                "llm_max_tokens": 512,
                "llm_temperature": 0.4,
            },
            "simulation": {
                "days": 45,
                "run_until_stopped": False,
                "clock_mode": "simulated",
                "clock_timezone": "Europe/Rome",
                "feed_refresh": "hourly",
            },
            "agents": {"llm_agents": ["llama3.2:latest"]},
            "agent_settings": {
                "epsilon": 0.1,
                "propaganda_campaigns": [
                    {
                        "topic_id": 7,
                        "topic_name": "Climate",
                        "target_opinion_group": "Supportive",
                        "target_opinion": 0.8,
                        "target_agent_opinion_group": "Skeptical",
                        "target_leaning": "Left",
                        "target_age_classes": [
                            {"name": "Young", "age_start": 18, "age_end": 25}
                        ],
                    }
                ],
            },
            "metadata": {
                "name": "propaganda client",
                "description": "live edit",
                "population_id": 17,
                "agent_type_slug": "propaganda",
            },
        }
    }

    values = _build_adhoc_client_initial_values(config)

    assert values["name"] == "propaganda client"
    assert values["descr"] == "live edit"
    assert values["agent_type"] == "propaganda"
    assert values["population_id"] == 17
    assert values["llm_backend"] == "ollama"
    assert values["llm_agent"] == "llama3.2:latest"
    assert values["days"] == 45
    assert values["infinite_duration"] is False
    assert values["agent_settings"]["epsilon"] == 0.1
    assert values["agent_settings"]["propaganda_campaigns"][0]["topic_id"] == 7
    assert (
        values["agent_settings"]["propaganda_campaigns"][0]["target_opinion_group"]
        == "Supportive"
    )
