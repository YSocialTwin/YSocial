from y_web.routes.admin.sub.clients._crud import (
    _adhoc_agent_specs,
    _build_adhoc_client_initial_values,
    _coerce_adhoc_client_setting,
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
