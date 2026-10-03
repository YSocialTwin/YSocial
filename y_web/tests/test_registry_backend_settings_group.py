"""
Tests for the registry.py integration of the new "backend_settings"
runtime group (scenario_design entry in SUPPORTED_EXTERNAL_REPOS,
grouped_runtime_specs() ordering).

Split out from test_backend_plugins_registry.py so each atomic commit in
the Scenario Design Fase 1 sequence carries exactly the tests for what it
changes (piano di implementazione, Fase 1, commit #2: feat(core-registry)).
"""

from y_web.src.external_runtime import registry


# ---------------------------------------------------------------------------
# registry.py integration: group registration + ordering
# ---------------------------------------------------------------------------
def test_scenario_design_registered_with_backend_settings_group():
    spec = registry.runtime_spec("scenario_design")
    assert spec.group == "backend_settings"
    assert spec.group_label == "Backend Settings"


def test_grouped_runtime_specs_includes_backend_settings_group():
    groups = {
        group_key: label
        for group_key, label, _specs in registry.grouped_runtime_specs()
    }
    assert "backend_settings" in groups
    assert groups["backend_settings"] == "Backend Settings"
