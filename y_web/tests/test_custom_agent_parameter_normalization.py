from y_web.routes.admin.sub.agents import _normalize_custom_agent_parameter_value


def test_normalize_custom_agent_parameter_value_accepts_comma_float():
    parameter = {"name": "toxicity_threshold", "type": "float"}

    value = _normalize_custom_agent_parameter_value(parameter, "0,10")

    assert value == "0.1"


def test_normalize_custom_agent_parameter_value_coerces_integer():
    parameter = {"name": "candidate_window_rounds", "type": "integer"}

    value = _normalize_custom_agent_parameter_value(parameter, "24")

    assert value == "24"
