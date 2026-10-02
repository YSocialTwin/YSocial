"""
Tests for the "backend settings" plugin suite infrastructure (Fase 1 of the
Scenario Design implementation plan).

Mirrors the conventions of test_frontend_adds_on_plugin_suite.py, applied to
the new, parallel backend_plugins.py module instead of
frontend_plugins.py/plugin_loader.py. Covers:

  * manifest validation (y_web.src.external_runtime.backend_plugins)
  * suite/blueprint registration + static asset serving, including
    path-traversal protection
  * fault isolation: one broken suite must never prevent another valid
    suite from registering, nor crash app startup
  * idempotent re-registration

The registry.py group-registration/ordering tests live in
test_registry_backend_settings_group.py, and the sidebar-visibility
context-processor tests live in test_backend_plugin_sidebar_visibility.py
(split out so each Scenario Design Fase 1 commit carries only the tests
for what it changes).

These tests exercise the REAL external/ScenarioDesign repo scaffolded
alongside this change (not a mock), since discovery/validation
intentionally reads manifests live from disk rather than from a cache —
the same convention test_frontend_adds_on_plugin_suite.py uses for
external/frontend_adds-on.
"""
import json

import pytest

from y_web.src.external_runtime import backend_plugins
from y_web.src.external_runtime import registry


# ---------------------------------------------------------------------------
# Manifest discovery / validation
# ---------------------------------------------------------------------------
def test_backend_plugin_repo_keys_includes_scenario_design():
    assert "scenario_design" in backend_plugins.backend_plugin_repo_keys()


def test_validate_backend_suite_valid_for_scenario_design():
    report = backend_plugins.validate_backend_suite("scenario_design")
    assert report["installed"] is True
    assert report["valid"] is True, report["errors"]
    assert report["suite"]["suite_id"] == "scenario_design"
    module_ids = [m["module_id"] for m in report["modules"]]
    assert "scenario_editor" in module_ids
    scenario_editor = next(m for m in report["modules"] if m["module_id"] == "scenario_editor")
    assert scenario_editor["valid"] is True, scenario_editor["errors"]


def test_validate_backend_suite_unknown_repo_key():
    report = backend_plugins.validate_backend_suite("not_a_real_repo_key")
    assert report["installed"] is False
    assert report["valid"] is False
    assert report["errors"]


def test_validate_backend_suite_missing_backend_blueprint_field_is_rejected(tmp_path, monkeypatch):
    """Unlike the frontend manifest schema, 'backend_blueprint' is required."""
    repo_path = tmp_path / "broken_suite"
    (repo_path / "meta").mkdir(parents=True)
    (repo_path / "meta" / "registry.json").write_text(
        json.dumps(
            {
                "suite": {"suite_id": "broken_suite"},
                "backend_plugins": [
                    {"module_id": "m1", "display_name": "M1", "version": "0.1.0"}
                ],
            }
        ),
        encoding="utf-8",
    )

    fake_spec = registry.ExternalRuntimeSpec(
        key="broken_suite",
        group="backend_settings",
        group_label="Backend Settings",
        category="backend_extensions",
        category_label="Backend Extensions",
        label="Broken Suite",
        path=repo_path,
        github_repo="example/broken_suite",
        repo_url="https://example.invalid/broken_suite.git",
        default_branch="main",
        install_commands=(),
        validate_entrypoints=(),
        validate_import=None,
        is_private=True,
    )
    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, "broken_suite", fake_spec)

    report = backend_plugins.validate_backend_suite("broken_suite")
    assert report["installed"] is True
    assert report["valid"] is False
    module_report = report["modules"][0]
    assert any("backend_blueprint" in err for err in module_report["errors"])


# ---------------------------------------------------------------------------
# Blueprint / static asset registration
# ---------------------------------------------------------------------------
def test_register_backend_plugin_suites_registers_blueprint_and_static_route(app):
    report = backend_plugins.register_backend_plugin_suites(app)
    assert report["suites"]["scenario_design"]["installed"] is True
    assert report["suites"]["scenario_design"]["valid"] is True
    assert "scenario_editor" in report["suites"]["scenario_design"]["registered_modules"]

    assert "scenario_design" in app.blueprints
    assert "backend_settings_static_scenario_design" in app.blueprints

    client = app.test_client()
    resp = client.get("/admin/scenario_design/")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["suite"] == "scenario_design"
    assert payload["status"] == "ok"

    static_resp = client.get(
        "/plugins/scenario_design/scenario_editor/static/modules/scenario_editor/static/placeholder.txt"
    )
    assert static_resp.status_code == 200
    assert b"Scenario Design" in static_resp.data

    # Path traversal must be refused, not silently served.
    traversal_resp = client.get(
        "/plugins/scenario_design/scenario_editor/static/../../../../etc/passwd"
    )
    assert traversal_resp.status_code == 404

    # An unknown module_id under a valid suite must 404, not serve anything.
    unknown_module_resp = client.get(
        "/plugins/scenario_design/does_not_exist/static/modules/scenario_editor/static/placeholder.txt"
    )
    assert unknown_module_resp.status_code == 404


def test_register_backend_plugin_suites_is_idempotent(app):
    first = backend_plugins.register_backend_plugin_suites(app)
    second = backend_plugins.register_backend_plugin_suites(app)
    assert first["suites"]["scenario_design"]["valid"] is True
    assert second["suites"]["scenario_design"]["valid"] is True
    # Re-registering a blueprint of the same name a second time on the same
    # app is a Flask error unless guarded; proves register_backend_plugin_suites
    # (and _register_static_blueprint's app.blueprints guard) tolerate being
    # called twice without raising -- e.g. once at create_app() time and once
    # more defensively from a management command/test harness.


def test_fault_isolation_broken_suite_does_not_block_valid_one(app, tmp_path, monkeypatch):
    """A broken sibling suite must never prevent scenario_design (or any
    other valid suite) from registering, and must never raise out of
    register_backend_plugin_suites()."""
    repo_path = tmp_path / "broken_suite"
    (repo_path / "meta").mkdir(parents=True)
    (repo_path / "meta" / "registry.json").write_text("{not valid json", encoding="utf-8")

    fake_spec = registry.ExternalRuntimeSpec(
        key="broken_suite",
        group="backend_settings",
        group_label="Backend Settings",
        category="backend_extensions",
        category_label="Backend Extensions",
        label="Broken Suite",
        path=repo_path,
        github_repo="example/broken_suite",
        repo_url="https://example.invalid/broken_suite.git",
        default_branch="main",
        install_commands=(),
        validate_entrypoints=(),
        validate_import=None,
        is_private=True,
    )
    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, "broken_suite", fake_spec)

    report = backend_plugins.register_backend_plugin_suites(app)
    assert report["suites"]["broken_suite"]["installed"] is True
    assert report["suites"]["broken_suite"]["valid"] is False
    assert report["suites"]["broken_suite"]["errors"]

    assert report["suites"]["scenario_design"]["valid"] is True
    assert "scenario_design" in app.blueprints


def test_backend_suite_availability_true_when_valid():
    availability = backend_plugins.backend_suite_availability()
    assert availability.get("scenario_design") is True
