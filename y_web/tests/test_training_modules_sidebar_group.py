"""C8 - top-level sidebar group declared in the manifest (``suite.sidebar.group``),
rendered by head.html with the existing group markup (E7). Fake plugin."""

import json

import pytest

from y_web.src.external_runtime import backend_plugins, registry
from y_web.tests.test_training_modules_baseline_auth import (  # noqa: F401
    _make_admin_user,
    core_app,
)
from y_web.tests.test_training_modules_manifest_keys import _make_plugin

@pytest.fixture(autouse=True)
def _without_the_real_training_plugin(monkeypatch):
    """These C8 tests exercise the generic mechanism with a fake plugin; the real
    TrainingModules checkout (which declares its own group) must not take part."""
    monkeypatch.delitem(registry.SUPPORTED_EXTERNAL_REPOS, "training_modules", raising=False)


PKG_INIT = '''
from flask import Blueprint, jsonify
bp = Blueprint("fake_suite_bp", __name__)

@bp.route("/fake/a")
def a():
    return jsonify(ok="a")

@bp.route("/fake/b")
def b():
    return jsonify(ok="b")
'''

GROUP = {
    "label": "Training",
    "icon": "book-open",
    "items": [
        {"label": "Modules", "icon": "layers", "endpoint": "fake_suite_bp.a"},
        {"label": "Settings", "icon": "settings", "endpoint": "fake_suite_bp.b", "roles": ["admin"]},
        {"label": "Ghost", "icon": "x", "endpoint": "fake_suite_bp.missing"},
    ],
}


def _build(core_app, tmp_path, monkeypatch, sidebar):
    repo = _make_plugin(tmp_path, monkeypatch)
    (repo / "pkg" / "__init__.py").write_text(PKG_INIT)
    manifest = json.loads((repo / "meta" / "registry.json").read_text())
    if sidebar is not None:
        manifest["suite"]["sidebar"] = sidebar
    (repo / "meta" / "registry.json").write_text(json.dumps(manifest))
    report = backend_plugins.register_backend_plugin_suites(core_app)
    assert report["suites"]["fake_suite"]["valid"], report
    return core_app


def _page(app, role):
    with app.app_context():
        uid = _make_admin_user(role).get_id()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = uid
        sess["_fresh"] = True
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_group_is_rendered_with_the_existing_group_markup(core_app, tmp_path, monkeypatch):
    app = _build(core_app, tmp_path, monkeypatch, {"group": GROUP})
    html = _page(app, "admin")
    assert 'id="sidebar-group-fake_suite"' in html
    assert 'class="dashboard-aside-group"' in html
    assert 'id="sidebar-submenu-fake_suite"' in html
    assert ">Training<" in html and 'href="/fake/a"' in html and 'href="/fake/b"' in html


def test_items_are_filtered_by_role_and_unresolvable_ones_are_skipped(
    core_app, tmp_path, monkeypatch
):
    app = _build(core_app, tmp_path, monkeypatch, {"group": GROUP})
    researcher_html = _page(app, "researcher")
    assert 'href="/fake/a"' in researcher_html and 'href="/fake/b"' not in researcher_html
    assert "Ghost" not in researcher_html
    with app.test_request_context("/"):
        assert backend_plugins.backend_suite_sidebar_groups(None) == []
        assert backend_plugins.backend_suite_sidebar_groups("user") == []
        (group,) = backend_plugins.backend_suite_sidebar_groups("admin")
        assert [i["label"] for i in group["items"]] == ["Modules", "Settings"]


def test_flat_entry_is_unchanged_and_no_group_means_no_extra_markup(
    core_app, tmp_path, monkeypatch
):
    app = _build(
        core_app,
        tmp_path,
        monkeypatch,
        {"label": "Fake", "icon": "box", "endpoint": "fake_suite_bp.a"},
    )
    html = _page(app, "admin")
    assert 'id="sidebar-ext-fake_suite"' in html
    assert 'id="sidebar-group-fake_suite"' not in html
    with app.test_request_context("/"):
        assert backend_plugins.backend_suite_sidebar_groups("admin") == []


def test_flat_entry_and_group_can_coexist(core_app, tmp_path, monkeypatch):
    app = _build(
        core_app,
        tmp_path,
        monkeypatch,
        {"label": "Fake", "icon": "box", "endpoint": "fake_suite_bp.a", "group": GROUP},
    )
    html = _page(app, "admin")
    assert 'id="sidebar-ext-fake_suite"' in html and 'id="sidebar-group-fake_suite"' in html


@pytest.mark.parametrize(
    "bad",
    [
        {"group": "nope"},
        {"group": {"label": "", "items": [{"label": "x", "endpoint": "fake_suite_bp.a"}]}},
        {"group": {"label": "T", "items": []}},
        {"group": {"label": "T", "items": [{"label": "x"}]}},
        {"group": {"label": "T", "items": [{"label": "x", "endpoint": "e", "roles": "admin"}]}},
    ],
)
def test_malformed_group_warns_but_neither_invalidates_nor_renders(
    core_app, tmp_path, monkeypatch, bad
):
    app = _build(core_app, tmp_path, monkeypatch, bad)
    report = backend_plugins.validate_backend_suite("fake_suite")
    assert report["valid"] is True
    assert any("sidebar.group" in w for w in report["warnings"])
    assert 'id="sidebar-group-fake_suite"' not in _page(app, "admin")


def test_disabled_suite_hides_its_group(core_app, tmp_path, monkeypatch):
    app = _build(core_app, tmp_path, monkeypatch, {"group": GROUP})
    with app.app_context():
        backend_plugins.set_plugin_enabled("fake_suite", False)
    assert 'id="sidebar-group-fake_suite"' not in _page(app, "admin")


def test_without_plugins_the_sidebar_has_no_plugin_group(core_app):
    html = _page(core_app, "admin")
    assert 'id="sidebar-group-training_modules"' not in html
    assert 'id="sidebar-group-extensions"' in html
