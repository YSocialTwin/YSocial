"""C9 - optional ``training_components`` manifest key of any plugin (E1). Fake plugins."""

import json

import pytest
from flask import Flask

from y_web.src.external_runtime import backend_plugins as bp
from y_web.src.external_runtime import registry
from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_manifest_keys import _make_plugin


def good(**over):
    base = {
        "type_key": "questionnaire",
        "label": "Questionnaire",
        "icon": "clipboard",
        "category": "Questionnaire",
        "contract_version": "1",
        "config_schema": {
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "mode": {"type": "string", "enum": ["a", "b"]},
                "n": {"type": "number"},
                "flag": {"type": "boolean"},
            },
        },
        "launch": {"endpoint": "/q/launch"},
        "instance_picker": {"endpoint": "/q/search"},
        "signals": {"advance_button": True},
    }
    base.update(over)
    return base


def test_valid_descriptor_is_normalized_with_defaults():
    comp, problems = bp.validate_training_component(
        {
            "type_key": "landing",
            "label": "Landing",
            "contract_version": "1",
            "launch": {"endpoint": "/l"},
        }
    )
    assert problems == []
    assert comp["icon"] == "box" and comp["category"] == "Other"
    assert comp["signals"] == {
        "declared": True,
        "verified": False,
        "advance_button": False,
    }
    assert comp["config_schema"] == {"type": "object", "properties": {}}
    assert "instance_picker" not in comp


def test_full_descriptor_keeps_its_declarations():
    comp, problems = bp.validate_training_component(good())
    assert problems == []
    assert (
        comp["signals"]["advance_button"] is True
        and comp["signals"]["declared"] is True
    )
    assert comp["instance_picker"] == {"endpoint": "/q/search"}


@pytest.mark.parametrize(
    "mutation, needle",
    [
        ({"type_key": "Bad-Key"}, "type_key"),
        ({"type_key": 7}, "type_key"),
        ({"label": " "}, "label"),
        ({"contract_version": "9"}, "contract_version"),
        ({"contract_version": None}, "contract_version"),
        ({"config_schema": {"type": "array"}}, "config_schema"),
        (
            {
                "config_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "object"}},
                }
            },
            "flat",
        ),
        (
            {
                "config_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "string", "enum": []}},
                }
            },
            "enum",
        ),
        (
            {
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "required": ["ghost"],
                }
            },
            "required",
        ),
        ({"launch": {"endpoint": "https://evil.example/x"}}, "launch.endpoint"),
        ({"launch": {"endpoint": "//evil.example/x"}}, "launch.endpoint"),
        ({"launch": "/q/launch"}, "launch.endpoint"),
        ({"health": {"endpoint": "relative/path"}}, "health.endpoint"),
        ({"signals": {"declared": "yes"}}, "signals"),
    ],
)
def test_invalid_descriptors_are_rejected_with_a_reason(mutation, needle):
    comp, problems = bp.validate_training_component(good(**mutation))
    assert comp is None
    assert any(needle in p for p in problems), problems


def test_missing_launch_and_non_dict_descriptors_are_rejected():
    d = good()
    del d["launch"]
    assert bp.validate_training_component(d)[0] is None
    assert bp.validate_training_component("nope")[0] is None


def _fake_repo(tmp_path, monkeypatch, key, group, components, **extra):
    """Install a fake plugin with an arbitrary group (the key works for any plugin)."""
    repo = _make_plugin(
        tmp_path, monkeypatch, {"training_components": components, **extra}
    )
    spec = registry.runtime_spec("fake_suite")
    monkeypatch.setitem(
        registry.SUPPORTED_EXTERNAL_REPOS,
        key,
        registry.ExternalRuntimeSpec(**{**spec.__dict__, "key": key, "group": group}),
    )
    return repo


def test_key_is_read_from_any_plugin_group(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch, "fake_frontend", "frontend_plugins", [good()])
    result = bp.read_training_components("fake_frontend")
    assert result["problems"] == []
    (comp,) = result["components"]
    assert (
        comp["component_ref"] == "fake_frontend:questionnaire"
        and comp["repo_key"] == "fake_frontend"
    )


def test_bad_descriptors_are_reported_and_good_ones_survive(tmp_path, monkeypatch):
    comps = [
        good(),
        good(label=""),
        good(),
        "junk",
    ]  # ok, bad label, duplicate, not an object
    _fake_repo(tmp_path, monkeypatch, "fake_suite", "backend_settings", comps)
    result = bp.read_training_components("fake_suite")
    assert [c["type_key"] for c in result["components"]] == ["questionnaire"]
    assert len(result["problems"]) == 3
    assert any("duplicate" in p for p in result["problems"])


def test_non_list_key_is_a_problem_not_a_crash(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch, "fake_suite", "backend_settings", {"oops": 1})
    result = bp.read_training_components("fake_suite")
    assert result["components"] == [] and result["problems"] == [
        "training_components must be a list"
    ]


def test_missing_key_unknown_repo_and_absent_plugin_are_empty(tmp_path, monkeypatch):
    _make_plugin(tmp_path, monkeypatch)
    assert bp.read_training_components("fake_suite") == {
        "components": [],
        "problems": [],
    }
    assert bp.read_training_components("no_such_repo")["components"] == []
    spec = registry.runtime_spec("training_modules")
    monkeypatch.setitem(
        registry.SUPPORTED_EXTERNAL_REPOS,
        "training_modules",
        registry.ExternalRuntimeSpec(**{**spec.__dict__, "path": tmp_path / "nope"}),
    )
    assert bp.read_training_components("training_modules")["components"] == []


def test_invalid_training_components_never_block_plugin_loading(tmp_path, monkeypatch):
    _fake_repo(
        tmp_path, monkeypatch, "fake_suite", "backend_settings", [good(label="")]
    )
    report = bp.validate_backend_suite("fake_suite")
    assert report["valid"] is True
    assert any("training_components" in w for w in report["warnings"])
    assert "training_components" not in report
    app = Flask(__name__)
    out = bp.register_backend_plugin_suites(app)
    assert out["suites"]["fake_suite"]["valid"] is True
    assert "fake_suite_bp" in app.blueprints


def test_valid_components_appear_in_the_suite_report(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch, "fake_suite", "backend_settings", [good()])
    report = bp.validate_backend_suite("fake_suite")
    assert [c["type_key"] for c in report["training_components"]] == ["questionnaire"]


def test_catalog_aggregates_installed_enabled_plugins(core_app, tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch, "fake_suite", "backend_settings", [good()])
    with core_app.app_context():
        refs = [c["component_ref"] for c in bp.training_component_catalog()]
        assert "fake_suite:questionnaire" in refs
        bp.set_plugin_enabled("fake_suite", False)
        assert "fake_suite:questionnaire" not in [
            c["component_ref"] for c in bp.training_component_catalog()
        ]
