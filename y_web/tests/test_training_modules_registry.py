"""C1 - the ``training_modules`` runtime spec and catalogue card (TrainingModules plugin)."""

import json

import pytest

from y_web.src.external_runtime import backend_plugins, registry


def test_training_modules_spec_is_registered_in_backend_settings_group():
    spec = registry.runtime_spec("training_modules")
    assert spec.group == "backend_settings"
    assert spec.path == registry.EXTERNAL_DIR / "TrainingModules"
    assert spec.repo_url == "https://github.com/YSocialTwin/TrainingModules.git"
    assert spec.github_repo == "YSocialTwin/TrainingModules"
    assert spec.is_private is True
    assert "training_modules" in backend_plugins.backend_plugin_repo_keys()


def test_backend_settings_group_is_still_listed_once_with_both_suites():
    groups = {key: specs for key, _label, specs in registry.grouped_runtime_specs()}
    keys = [s.key for s in groups["backend_settings"]]
    assert "scenario_design" in keys and "training_modules" in keys


def test_plugins_json_has_a_training_modules_card():
    """external/plugins.json is regenerated from each installed plugin's
    meta/info.json (Plugin Manager refresh), so the card name is the info.json one."""
    if not registry.runtime_spec("training_modules").path.exists():
        pytest.skip("TrainingModules plugin not checked out")
    payload = json.loads(registry.PLUGINS_INDEX_PATH.read_text(encoding="utf-8"))
    cards = [p for p in payload["plugins"] if p["plugin_name"] == "Training Modules"]
    assert len(cards) == 1
    assert cards[0]["group"] == "Backend Settings"
    assert (
        cards[0]["repository_url"] == "https://github.com/YSocialTwin/TrainingModules"
    )


def test_absent_plugin_is_reported_as_not_installed_without_errors(
    tmp_path, monkeypatch
):
    """With the plugin folder missing the core behaves as if it did not exist."""
    spec = registry.runtime_spec("training_modules")
    missing = registry.ExternalRuntimeSpec(
        **{**spec.__dict__, "path": tmp_path / "nope"}
    )
    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, "training_modules", missing)

    report = backend_plugins.validate_backend_suite("training_modules")
    assert report["installed"] is False
    assert report["valid"] is False
    assert report["errors"] == []
    assert backend_plugins.backend_suite_availability()["training_modules"] is False
