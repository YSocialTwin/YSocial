from y_web.routes.admin.sub.clients._crud import (
    _adhoc_agent_specs,
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
    parameter = {"name": "propaganda_campaigns", "type": "topic_targets", "required": True}

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
    parameter = {"name": "propaganda_campaigns", "type": "topic_targets", "required": True}

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
