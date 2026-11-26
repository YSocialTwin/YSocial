"""What an extension needs from the core: ``min_core_version`` and ``extension_api`` (plan, phase 2c)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.src.external_runtime import backend_plugins, frontend_plugins, manager
from y_web.src.external_runtime import registry as runtime_registry
from y_web.src.external_runtime.catalog import parse_registry
from y_web.src.external_runtime.requirements import (
    info_requirement_problems,
    install_requirement_problem,
    parse_range,
)

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = ROOT / "external"
FOUR = {
    "scenario_design": "ScenarioDesign",
    "training_modules": "TrainingModules",
    "frontend_adds_on": "frontend_adds-on",
    "reactive_agents": "reactive_agents",
}


def _problems(info, core="4.1.0", api="1.0"):
    return info_requirement_problems(info, core, api_version=api)


def test_a_sufficient_core_and_api_are_accepted():
    errors, warnings = _problems({"min_core_version": "4.1.0", "extension_api": "^1.0"})
    assert errors == [] and warnings == []


def test_an_older_core_is_refused_with_both_versions_in_the_message():
    errors, _ = _problems({"min_core_version": "4.1.0"}, core="4.0.0")
    assert len(errors) == 1
    assert "4.1.0" in errors[0] and "4.0.0" in errors[0]


def test_a_core_above_the_known_limit_is_refused():
    errors, _ = _problems({"max_core_version": "4.2.0"}, core="4.3.0")
    assert errors and "4.2.0" in errors[0]


def test_an_extension_api_the_core_does_not_offer_is_refused():
    errors, _ = _problems({"extension_api": "^2.0"}, api="1.3")
    assert errors and "^2.0" in errors[0] and "1.3" in errors[0]


def test_a_minor_of_the_same_major_satisfies_a_caret_range():
    assert _problems({"extension_api": "^1.0"}, api="1.7")[0] == []
    assert _problems({"extension_api": "^1.2"}, api="1.1")[0] != []


@pytest.mark.parametrize(
    "info",
    [
        {"min_core_version": "latest"},
        {"min_core_version": 4},
        {"max_core_version": "soon"},
        {"extension_api": "banana"},
    ],
)
def test_a_malformed_field_is_an_error(info):
    if info == {"min_core_version": 4}:
        # a bare number is a legal version string once written as text
        assert _problems(info)[0] == []
        return
    errors, _ = _problems(info)
    assert errors


def test_missing_fields_load_with_a_warning():
    errors, warnings = _problems({"name": "x"})
    assert errors == []
    assert warnings and "min_core_version" in warnings[0]


def test_info_that_is_not_an_object_is_ignored():
    assert info_requirement_problems(None, "4.1.0") == ([], [])


def test_parse_range_accepts_the_caret_and_standard_specifiers():
    assert parse_range("^1.0").contains("1.9")
    assert not parse_range("^1.0").contains("2.0")
    assert parse_range(">=1.0,<2").contains("1.5")
    assert parse_range("nonsense") is None


def _suite(tmp_path, info, key):
    meta = tmp_path / "meta"
    meta.mkdir()
    (meta / "info.json").write_text(json.dumps(info))
    registry = {"suite": {"suite_id": "x"}, key: []}
    (meta / "registry.json").write_text(json.dumps(registry))
    return SimpleNamespace(path=tmp_path, key="x", label="X")


@pytest.mark.parametrize(
    "module, key, validate",
    [
        (backend_plugins, "backend_plugins", backend_plugins.validate_backend_suite),
        (
            frontend_plugins,
            "frontend_plugins",
            frontend_plugins.validate_frontend_suite,
        ),
    ],
)
def test_a_suite_that_needs_a_newer_core_is_not_valid(
    module, key, validate, tmp_path, monkeypatch
):
    spec = _suite(tmp_path, {"min_core_version": "9.0.0", "extension_api": "^1.0"}, key)
    monkeypatch.setattr(module, "runtime_spec", lambda repo_key: spec)
    report = validate("x")
    assert report["valid"] is False
    assert any("9.0.0" in e for e in report["errors"])


@pytest.mark.parametrize(
    "module, key, validate",
    [
        (backend_plugins, "backend_plugins", backend_plugins.validate_backend_suite),
        (
            frontend_plugins,
            "frontend_plugins",
            frontend_plugins.validate_frontend_suite,
        ),
    ],
)
def test_a_suite_with_a_satisfied_requirement_is_valid_and_one_without_fields_still_loads(
    module, key, validate, tmp_path, monkeypatch
):
    spec = _suite(tmp_path, {"min_core_version": "4.0.0", "extension_api": "^1.0"}, key)
    monkeypatch.setattr(module, "runtime_spec", lambda repo_key: spec)
    assert validate("x")["valid"] is True

    bare = tmp_path / "bare"
    bare.mkdir()
    spec = _suite(bare, {"name": "x"}, key)
    monkeypatch.setattr(module, "runtime_spec", lambda repo_key: spec)
    report = validate("x")
    assert report["valid"] is True
    assert any("min_core_version" in w for w in report["warnings"])


def test_install_is_refused_before_anything_is_downloaded(monkeypatch):
    spec = SimpleNamespace(label="Scenario Design", min_ysocial_version="4.1.0")
    problem = install_requirement_problem(spec, "4.0.0")
    assert "Scenario Design" in problem and "4.1.0" in problem and "4.0.0" in problem
    assert "nothing was downloaded" in problem
    assert install_requirement_problem(spec, "4.1.0") is None
    assert install_requirement_problem(SimpleNamespace(label="x"), "4.0.0") is None

    monkeypatch.setattr(backend_plugins, "_app_version", lambda: "4.0.0")
    with pytest.raises(manager.ExternalRuntimeError, match="4.1.0"):
        manager._refuse_if_core_too_old(spec)
    monkeypatch.setattr(backend_plugins, "_app_version", lambda: "4.1.0")
    manager._refuse_if_core_too_old(spec)


def test_a_built_in_entry_can_carry_the_core_requirement():
    entry = {
        "key": "demo",
        "label": "Demo",
        "group": "g",
        "group_label": "G",
        "category": "c",
        "category_label": "C",
        "directory": "Demo",
        "repo": "o/Demo",
        "min_ysocial_version": "4.1.0",
    }
    spec = runtime_registry._builtin_spec(entry)
    assert spec.min_ysocial_version == "4.1.0"
    assert install_requirement_problem(spec, "4.0.0")
    assert install_requirement_problem(spec, "4.1.0") is None
    entry.pop("min_ysocial_version")
    assert runtime_registry._builtin_spec(entry).min_ysocial_version is None


def test_the_catalog_skips_an_entry_that_needs_a_newer_core_and_says_which():
    entry = {
        "id": "ext",
        "name": "Ext",
        "category": "backend_extensions",
        "repo": "YSocialTwin/Ext",
        "min_ysocial_version": "4.1.0",
    }
    payload = {"schema_version": 1, "plugins": [entry]}
    specs, problems = parse_registry(payload, "4.0.0")
    assert not specs and any("4.1.0" in p for p in problems)
    specs, problems = parse_registry(payload, "4.1.0")
    assert len(specs) == 1


@pytest.mark.parametrize("key, directory", sorted(FOUR.items()))
def test_each_extension_declares_what_it_needs(key, directory):
    repo = EXTERNAL / directory
    if not repo.is_dir():
        pytest.skip(f"{directory} is not checked out")
    info = json.loads((repo / "meta" / "info.json").read_text("utf-8"))
    assert info.get("min_core_version") == "4.1.0"
    assert info.get("extension_api") == "^1.0"
    registry = json.loads((repo / "meta" / "registry.json").read_text("utf-8"))
    assert registry["suite"].get("min_app_version") == "4.1.0"
    errors, warnings = info_requirement_problems(info, "4.1.0")
    assert errors == [] and warnings == []
    assert info_requirement_problems(info, "4.0.0")[0]
