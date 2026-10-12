"""C7 - enable/disable switch for backend plugin suites (E6): 404 guard, menu,
hooks, Plugin Manager actions and the 'restart required' notice. Fake plugin."""

import importlib
import json

import pytest

from y_web.src.external_runtime import backend_plugins, plugin_hooks
from y_web.tests.test_training_modules_baseline_auth import (  # noqa: F401
    _make_admin_user,
    core_app,
)
from y_web.tests.test_training_modules_manifest_keys import _make_plugin

PKG_INIT = '''
from flask import Blueprint, jsonify
bp = Blueprint("fake_suite_bp", __name__)

@bp.route("/fake/ping")
def ping():
    return jsonify(pong=True)
'''
HOOKS = "CALLS = []\ndef on_login(user):\n    CALLS.append(user)\n    return '/fake/landing'\n"


@pytest.fixture
def fake_app(core_app, tmp_path, monkeypatch):
    repo = _make_plugin(
        tmp_path,
        monkeypatch,
        {
            "hooks": {"post_login": "pkg.hooks:on_login"},
        },
    )
    (repo / "pkg" / "__init__.py").write_text(PKG_INIT)
    (repo / "pkg" / "hooks.py").write_text(HOOKS)
    manifest = json.loads((repo / "meta" / "registry.json").read_text())
    manifest["suite"]["sidebar"] = {"label": "Fake", "icon": "box", "endpoint": "fake_suite_bp.ping"}
    (repo / "meta" / "registry.json").write_text(json.dumps(manifest))
    report = backend_plugins.register_backend_plugin_suites(core_app)
    assert report["suites"]["fake_suite"]["valid"], report
    return core_app


def _set(app, enabled, who="tester"):
    with app.app_context():
        backend_plugins.set_plugin_enabled("fake_suite", enabled, who)


def _admin_client(app):
    with app.app_context():
        admin_id = _make_admin_user("admin").get_id()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = admin_id
        sess["_fresh"] = True
    return client


def test_enabled_by_default_without_any_row(fake_app):
    with fake_app.app_context():
        assert backend_plugins.plugin_enabled("fake_suite") is True
    assert fake_app.test_client().get("/fake/ping").status_code == 200


def test_disabled_suite_answers_404_and_reenabling_restores_it(fake_app):
    client = fake_app.test_client()
    _set(fake_app, False)
    assert client.get("/fake/ping").status_code == 404
    assert client.get("/plugins/fake_suite/m1/static/meta/registry.json").status_code == 404
    _set(fake_app, True)
    assert client.get("/fake/ping").status_code == 200


def test_core_routes_are_unaffected_by_a_disabled_suite(fake_app):
    _set(fake_app, False)
    assert fake_app.test_client().get("/login").status_code == 200


def test_state_records_who_changed_it(fake_app):
    from y_web import db
    from y_web.src.models import PluginState

    _set(fake_app, False, "giulio")
    with fake_app.app_context():
        row = db.session.get(PluginState, "fake_suite")
        assert row.enabled is False and row.updated_by == "giulio"


def test_menu_and_availability_hide_a_disabled_suite(fake_app):
    with fake_app.test_request_context("/"):
        assert any(e["repo_key"] == "fake_suite" for e in backend_plugins.backend_suite_sidebar_entries())
        assert backend_plugins.backend_suite_availability()["fake_suite"] is True
    _set(fake_app, False)
    with fake_app.test_request_context("/"):
        assert not any(e["repo_key"] == "fake_suite" for e in backend_plugins.backend_suite_sidebar_entries())
        assert backend_plugins.backend_suite_availability()["fake_suite"] is False


def test_disabled_suite_receives_no_hook_calls(fake_app):
    with fake_app.app_context():
        assert plugin_hooks.call_first_non_null("post_login", object()) == "/fake/landing"
    _set(fake_app, False)
    with fake_app.app_context():
        assert plugin_hooks.call_first_non_null("post_login", object()) is None


def test_unreadable_state_table_means_enabled(fake_app, monkeypatch):
    from y_web import db

    def boom(*a, **k):
        raise RuntimeError("no such table")

    monkeypatch.setattr(db.session, "get", boom, raising=False)
    with fake_app.app_context():
        assert backend_plugins.plugin_enabled("fake_suite") is True


# --------------------------------------------------------------- Plugin Manager
@pytest.fixture
def manager_client(fake_app, monkeypatch):
    er = importlib.import_module(
        "y_web.routes.admin.sub.experiments._external_runtimes"
    )

    monkeypatch.setattr(er, "runtime_visible_to_user", lambda spec, user: True)
    return fake_app, _admin_client(fake_app)


def test_manager_can_disable_and_enable_a_suite(manager_client):
    app, client = manager_client
    resp = client.post("/admin/external_runtimes/fake_suite/disable", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert backend_plugins.plugin_enabled("fake_suite") is False
    assert app.test_client().get("/fake/ping").status_code == 404
    client.post("/admin/external_runtimes/fake_suite/enable", follow_redirects=True)
    with app.app_context():
        assert backend_plugins.plugin_enabled("fake_suite") is True


def test_manager_toggle_requires_an_admin(fake_app, monkeypatch):
    er = importlib.import_module(
        "y_web.routes.admin.sub.experiments._external_runtimes"
    )

    monkeypatch.setattr(er, "runtime_visible_to_user", lambda spec, user: True)
    with fake_app.app_context():
        researcher_id = _make_admin_user("researcher").get_id()
    client = fake_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = researcher_id
        sess["_fresh"] = True
    client.post("/admin/external_runtimes/fake_suite/disable")  # redirects, no change
    with fake_app.app_context():
        assert backend_plugins.plugin_enabled("fake_suite") is True


def test_toggle_is_refused_for_non_backend_or_not_installed_suites(manager_client):
    app, client = manager_client
    client.post("/admin/external_runtimes/YClient/disable", follow_redirects=True)
    with app.app_context():
        from y_web import db
        from y_web.src.models import PluginState

        assert db.session.get(PluginState, "YClient") is None


def test_enabling_a_suite_not_loaded_at_startup_reports_restart_required(
    manager_client, monkeypatch
):
    app, client = manager_client
    monkeypatch.setattr(backend_plugins, "_REGISTERED_SUITES", {})
    assert backend_plugins.suite_restart_required("fake_suite") is True
    resp = client.post("/admin/external_runtimes/fake_suite/enable", follow_redirects=True)
    assert b"Restart required" in resp.data or b"restart" in resp.data.lower()


def test_plugin_manager_page_shows_the_toggle(manager_client):
    app, client = manager_client
    html = client.get("/admin/external_runtimes").get_data(as_text=True)
    assert "Enabled" in html                                             # the list shows the state
    assert 'data-run-action="disable"' in client.get("/admin/external_runtimes/fake_suite").get_data(as_text=True)
    client.post("/admin/external_runtimes/fake_suite/disable")
    html = client.get("/admin/external_runtimes").get_data(as_text=True)
    assert "Disabled" in html
    assert 'data-run-action="enable"' in client.get("/admin/external_runtimes/fake_suite").get_data(as_text=True)
