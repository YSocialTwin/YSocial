import pytest

pytestmark = pytest.mark.unit

from y_web.routes.admin.sub.agents import (
    _custom_agent_parameter_sections,
    _normalize_custom_agent_parameter_value,
)


def test_normalize_custom_agent_parameter_value_accepts_comma_float():
    parameter = {"name": "toxicity_threshold", "type": "float"}

    value = _normalize_custom_agent_parameter_value(parameter, "0,10")

    assert value == "0.1"


def test_normalize_custom_agent_parameter_value_coerces_integer():
    parameter = {"name": "candidate_window_rounds", "type": "integer"}

    value = _normalize_custom_agent_parameter_value(parameter, "24")

    assert value == "24"


def test_normalize_custom_agent_parameter_value_coerces_enum_multi():
    parameter = {
        "name": "humor_styles",
        "type": "enum_multi[dad_jokes, nerdy, wordplay]",
    }

    value = _normalize_custom_agent_parameter_value(
        parameter, ["dad_jokes", "wordplay", "dad_jokes"]
    )

    assert value == '["dad_jokes", "wordplay"]'


def test_custom_agent_parameter_sections_preserve_defaults_and_visibility():
    spec = {
        "parameter_sections": [
            {"key": "moderation", "label": "Moderation Policy"},
            {"key": "shadow_ban", "label": "Shadow Ban"},
        ],
        "parameters": [
            {
                "name": "moderation_action_type",
                "type": "enum[one-fits-all, personalized]",
                "section": "moderation",
                "default": "one-fits-all",
            },
            {
                "name": "shadow_ban_enabled",
                "type": "enum[disabled, enabled]",
                "section": "shadow_ban",
                "default": "disabled",
            },
            {
                "name": "shadow_ban_duration_rounds",
                "type": "integer",
                "section": "shadow_ban",
                "default": 24,
                "visible_if": {"field": "shadow_ban_enabled", "equals": "enabled"},
            },
        ],
    }

    sections = _custom_agent_parameter_sections(spec)

    assert [section["key"] for section in sections] == ["moderation", "shadow_ban"]
    assert sections[0]["parameters"][0]["default"] == "one-fits-all"
    assert sections[1]["parameters"][0]["default"] == "disabled"
    assert sections[1]["parameters"][1]["visible_if"] == {
        "field": "shadow_ban_enabled",
        "equals": "enabled",
    }
