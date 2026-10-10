"""Scenario Design API: the rule for the Training Modules "continue" button is saved, validated, copied."""
from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import _client_as
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp)


def _url(exp_id, sid=""):
    return f"/admin/scenario_design/api/experiments/{exp_id}/scenarios" + (f"/{sid}" if sid else "")


def test_the_rule_defaults_to_never_and_is_saved_validated_and_copied(core_app):  # noqa: F811
    sd_client = _client_as(core_app, "admin")
    exp_id = _experiment(core_app, *PLATFORMS[0])
    created = sd_client.post(_url(exp_id), json={"name": "S1"})
    assert created.status_code == 201, created.data
    sid = created.get_json()["scenario"]["id"]
    assert sd_client.get(_url(exp_id, sid)).get_json()["scenario"]["advance_rule"] == {"mode": "never"}

    ok = sd_client.put(_url(exp_id, sid), json={"advance_rule": {"mode": "after_time", "minutes": "12"}})
    assert ok.status_code == 200 and ok.get_json()["scenario"]["advance_rule"] == {"mode": "after_time", "minutes": 12}
    assert sd_client.get(_url(exp_id, sid)).get_json()["scenario"]["advance_rule"]["minutes"] == 12

    bad = sd_client.put(_url(exp_id, sid), json={"advance_rule": {"mode": "after_time", "minutes": 0}})
    assert bad.status_code == 400 and bad.get_json()["error"]["code"] == "invalid_advance_rule"
    assert sd_client.get(_url(exp_id, sid)).get_json()["scenario"]["advance_rule"]["minutes"] == 12

    copy = sd_client.post(_url(exp_id, sid) + "/duplicate")
    assert copy.status_code == 201 and copy.get_json()["scenario"]["advance_rule"] == {"mode": "after_time", "minutes": 12}

    off = sd_client.put(_url(exp_id, sid), json={"advance_rule": {"mode": "never"}})
    assert off.get_json()["scenario"]["advance_rule"] == {"mode": "never"}
