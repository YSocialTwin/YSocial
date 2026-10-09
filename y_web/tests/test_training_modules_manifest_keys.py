"""C2 - optional manifest keys ``schema_module``, ``hooks``, ``permissions``
validated by ``validate_backend_suite`` (E1). Uses a fake plugin, not TrainingModules."""

import json
import sys

import pytest
from flask import Flask

from y_web.src.external_runtime import backend_plugins, registry


def _make_plugin(tmp_path, monkeypatch, extra=None, files=("pkg/schema.py", "pkg/hooks.py")):
    # the loader caches imported plugin modules by synthetic namespace name
    for name in [n for n in sys.modules if n.startswith("_ysocial_ext__fake_suite")]:
        del sys.modules[name]
    repo = tmp_path / "fake_suite"
    (repo / "meta").mkdir(parents=True)
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").write_text(
        "from flask import Blueprint\nbp = Blueprint('fake_suite_bp', __name__)\n"
    )
    for rel in files:
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def migrate(engine):\n    return True\n\ndef hook(*a, **k):\n    return None\n")
    manifest = {
        "suite": {"suite_id": "fake_suite"},
        "backend_plugins": [
            {
                "module_id": "m1",
                "display_name": "M1",
                "version": "0.1.0",
                "backend_blueprint": "pkg:bp",
            }
        ],
    }
    manifest.update(extra or {})
    (repo / "meta" / "registry.json").write_text(json.dumps(manifest), encoding="utf-8")
    spec = registry.ExternalRuntimeSpec(
        key="fake_suite",
        group="backend_settings",
        group_label="Backend Settings",
        category="backend_extensions",
        category_label="Backend Extensions",
        label="Fake",
        path=repo,
        github_repo="example/fake",
        repo_url="https://example.invalid/fake.git",
        default_branch="main",
        install_commands=(),
        validate_entrypoints=(),
        validate_import=None,
        is_private=True,
    )
    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, "fake_suite", spec)
    return repo


def test_manifest_without_optional_keys_is_unchanged(tmp_path, monkeypatch):
    _make_plugin(tmp_path, monkeypatch)
    report = backend_plugins.validate_backend_suite("fake_suite")
    assert report["valid"] is True, report["errors"]
    for key in ("schema_module", "hooks", "permissions"):
        assert key not in report


def test_valid_optional_keys_are_exposed_in_the_report(tmp_path, monkeypatch):
    _make_plugin(
        tmp_path,
        monkeypatch,
        {
            "schema_module": "pkg.schema:migrate",
            "hooks": {"post_login": "pkg.hooks:hook", "experiment_access_guard": "pkg.hooks:hook"},
            "permissions": "pkg.hooks:hook",
        },
    )
    report = backend_plugins.validate_backend_suite("fake_suite")
    assert report["valid"] is True, report["errors"]
    assert report["schema_module"] == "pkg.schema:migrate"
    assert report["hooks"] == {
        "post_login": "pkg.hooks:hook",
        "experiment_access_guard": "pkg.hooks:hook",
    }
    assert report["permissions"] == "pkg.hooks:hook"


@pytest.mark.parametrize(
    "extra, needle",
    [
        ({"schema_module": "no_colon"}, "schema_module"),
        ({"schema_module": "pkg.missing:migrate"}, "not found on disk"),
        ({"schema_module": 42}, "schema_module"),
        ({"schema_module": "../evil:migrate"}, "invalid module path"),
        ({"hooks": ["post_login"]}, "'hooks' must be an object"),
        ({"hooks": {"post_login": "pkg.nothere:h"}}, "post_login"),
        ({"permissions": "pkg.hooks"}, "permissions"),
    ],
)
def test_invalid_optional_keys_are_reported_and_invalidate_the_suite(
    tmp_path, monkeypatch, extra, needle
):
    _make_plugin(tmp_path, monkeypatch, extra)
    report = backend_plugins.validate_backend_suite("fake_suite")
    assert report["valid"] is False
    assert any(needle in err for err in report["errors"]), report["errors"]


def test_invalid_manifest_never_crashes_registration_and_is_in_suite_report(
    tmp_path, monkeypatch
):
    _make_plugin(tmp_path, monkeypatch, {"schema_module": "pkg.missing:migrate"})
    app = Flask(__name__)
    report = backend_plugins.register_backend_plugin_suites(app)
    suite = report["suites"]["fake_suite"]
    assert suite["installed"] is True and suite["valid"] is False
    assert any("schema_module" in e for e in suite["errors"])
    assert "fake_suite_bp" not in app.blueprints
