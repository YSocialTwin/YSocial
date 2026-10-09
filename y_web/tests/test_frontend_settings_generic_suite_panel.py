"""
Regression tests for the GENERIC "frontend plugin suite" admin panel at
/admin/frontend_settings.

Background: the panel used to hardcode a single suite, "frontend_adds_on",
in both the backend routes (`y_web/routes/admin/sub/experiments/_frontend_settings.py`)
and the template (`y_web/templates/admin/frontend_settings.html`) -- even
though the underlying discovery/validation functions in
`y_web.src.external_runtime.frontend_plugins` (`frontend_plugin_repo_keys`,
`discover_frontend_modules`, `validate_frontend_suite`) were already generic
and repo_key-parameterized. This meant a second suite registered with
group="frontend_plugins" in SUPPORTED_EXTERNAL_REPOS -- such as
reactive_agents' "Responsive Agents" module -- had no admin UI at all to
enable/configure it per experiment, only its own bespoke JSON API.

These tests confirm the generalized routes
(/admin/frontend_settings/suite/<repo_key>/get and .../save) work for BOTH
registered suites, reject an unknown repo_key, and that the base
/admin/frontend_settings page renders one box per suite.
"""

import json
import sqlite3

import pytest

from y_web import db
from y_web.src.external_runtime import plugin_loader, registry


def _frontend_adds_on_installed():
    return registry.runtime_spec("frontend_adds_on").path.exists()


def _reactive_agents_installed():
    return registry.runtime_spec("reactive_agents").path.exists()


def _make_exp(app):
    from y_web.src.models import Exps

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            exp_name="suite-panel-test-exp",
            db_name="experiments/suite-panel-test/database_server.db",
            owner="admin",
            exp_descr="test",
            status=1,
            running=0,
            port=5000,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


def _make_admin_login_user(app):
    """A User_mgmt row whose username matches the fixture's Admin_users
    "admin" row, so `check_privileges(current_user.username)` finds it and
    grants access -- the same real, unmocked authorization path production
    requests go through, not a monkeypatched stand-in.
    """
    from y_web.src.models import User_mgmt

    with app.app_context():
        user = User_mgmt(
            username="admin",
            email="admin-login@test.com",
            password="unused",
            joined_on=1234567890,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


@pytest.fixture
def suites_app(app):
    """The shared `app` fixture with every frontend_plugins-group suite
    registered (today: frontend_adds_on and reactive_agents), mirroring
    test_frontend_adds_on_plugin_suite.py's own `frontend_adds_on_app`
    fixture but exercising the generic discovery path for all suites.

    The bare `app` fixture (conftest.py) is a minimal Flask instance with
    no admin blueprints registered -- it's never hit `/admin/...` routes in
    this repo's test suite before now. Register the real `experiments`
    blueprint (which owns /admin/frontend_settings*) the same way
    test_client_logs.py does for its own admin-route tests, rather than
    standing up the full create_app() (which would touch this machine's
    real dashboard.db and experiment folders through Alembic).
    """
    if not (_frontend_adds_on_installed() and _reactive_agents_installed()):
        pytest.skip(
            "frontend_adds_on and/or reactive_agents suite not checked out "
            "in this environment"
        )
    plugin_loader.register_frontend_plugin_suites(app)
    with app.app_context():
        try:
            db.create_all(bind_key="__all__")
        except TypeError:
            db.create_all()

    from y_web.routes.admin.sub.experiments import experiments

    if "experiments" not in app.blueprints:
        app.register_blueprint(experiments)

    # The bare `app` fixture never sets a template_folder (it's a raw
    # Flask(__name__) instance, not the real create_app()), so point its
    # Jinja loader at the real y_web/templates directory for the one test
    # here that renders frontend_settings.html.
    import os as _os

    from jinja2 import FileSystemLoader

    import y_web as _y_web_pkg

    templates_dir = _os.path.join(_os.path.dirname(_y_web_pkg.__file__), "templates")
    app.jinja_loader = FileSystemLoader(templates_dir)

    # Both registered suites here (frontend_adds_on, reactive_agents) are
    # marked is_private=True in SUPPORTED_EXTERNAL_REPOS with no explicit
    # visible_to_usernames allow-list, so since the admin-role-alone
    # visibility bypass was removed (user-reported 2026-10-08: "when the
    # new flag -e is not specified private plugins that are already
    # installed are still visible"), these routes now require
    # --development's equivalent, app.config["DEVELOPMENT_MODE"], to be
    # on for this suite to be served at all -- exactly like production.
    # test_suite_routes_hidden_without_development_mode below covers the
    # opposite, un-flagged case this fixture intentionally skips past.
    app.config["DEVELOPMENT_MODE"] = True

    return app


def test_frontend_plugin_repo_keys_includes_both_installed_suites():
    from y_web.src.external_runtime.frontend_plugins import frontend_plugin_repo_keys

    keys = frontend_plugin_repo_keys()
    assert "frontend_adds_on" in keys
    assert "reactive_agents" in keys


def test_generic_get_route_serves_reactive_agents_modules(suites_app):
    client = suites_app.test_client()
    exp_id = _make_exp(suites_app)
    admin_login_id = _make_admin_login_user(suites_app)
    _login(client, admin_login_id)

    resp = client.get(
        f"/admin/frontend_settings/suite/reactive_agents/get?exp_id={exp_id}"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["installed"] is True
    module_ids = [m["module_id"] for m in data["modules"]]
    assert "responsive_agents" in module_ids


def test_generic_get_route_still_serves_frontend_adds_on_modules(suites_app):
    """The pre-existing suite must keep working unchanged through the new
    generic route -- this is a routing generalization, not a suite swap.
    """
    client = suites_app.test_client()
    exp_id = _make_exp(suites_app)
    admin_login_id = _make_admin_login_user(suites_app)
    _login(client, admin_login_id)

    resp = client.get(
        f"/admin/frontend_settings/suite/frontend_adds_on/get?exp_id={exp_id}"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["installed"] is True
    module_ids = [m["module_id"] for m in data["modules"]]
    assert "post_annotation" in module_ids


def test_generic_get_route_rejects_unknown_repo_key(suites_app):
    client = suites_app.test_client()
    exp_id = _make_exp(suites_app)
    admin_login_id = _make_admin_login_user(suites_app)
    _login(client, admin_login_id)

    resp = client.get(
        f"/admin/frontend_settings/suite/not_a_real_suite/get?exp_id={exp_id}"
    )
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_generic_save_route_enables_reactive_agents_module_and_persists_config(
    suites_app, monkeypatch, tmp_path
):
    from y_web.src.models import FrontendAddsOnExpModuleSettings

    client = suites_app.test_client()
    exp_id = _make_exp(suites_app)
    admin_login_id = _make_admin_login_user(suites_app)
    _login(client, admin_login_id)

    # ensure_module_schema() resolves the experiment's on-disk sqlite file
    # via plugin_loader._experiment_db_path(); the fixture experiment above
    # doesn't have a real one on disk, so point it at an empty-but-valid
    # temp sqlite file, exactly like this repo's own
    # test_ensure_module_schema_targets_the_right_experiment_db does for
    # frontend_adds_on's own post_annotation module.
    db_path = tmp_path / "exp_db_exp.sqlite"
    sqlite3.connect(str(db_path)).close()
    monkeypatch.setattr(
        plugin_loader, "_experiment_db_path", lambda exp_id: str(db_path)
    )

    save_resp = client.post(
        "/admin/frontend_settings/suite/reactive_agents/save",
        json={
            "exp_id": exp_id,
            "module_id": "responsive_agents",
            "enabled": True,
            "config": {"generation_mode": "autonomous"},
        },
    )
    assert save_resp.status_code == 200
    assert save_resp.get_json()["ok"] is True

    with suites_app.app_context():
        row = db.session.get(
            FrontendAddsOnExpModuleSettings, (exp_id, "responsive_agents")
        )
        assert row is not None
        assert row.enabled is True
        assert json.loads(row.config_json)["generation_mode"] == "autonomous"

    # A follow-up GET reflects the just-saved enabled/config state.
    get_resp = client.get(
        f"/admin/frontend_settings/suite/reactive_agents/get?exp_id={exp_id}"
    )
    modules = {m["module_id"]: m for m in get_resp.get_json()["modules"]}
    assert modules["responsive_agents"]["enabled"] is True
    assert modules["responsive_agents"]["config"]["generation_mode"] == "autonomous"
    assert modules["responsive_agents"]["status"] == "active"


def test_generic_save_route_rejects_unknown_repo_key(suites_app):
    client = suites_app.test_client()
    exp_id = _make_exp(suites_app)
    admin_login_id = _make_admin_login_user(suites_app)
    _login(client, admin_login_id)

    resp = client.post(
        "/admin/frontend_settings/suite/not_a_real_suite/save",
        json={"exp_id": exp_id, "module_id": "whatever", "enabled": True, "config": {}},
    )
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_frontend_settings_page_renders_a_box_per_registered_suite(suites_app):
    """The base page shell must offer BOTH suites a box (hidden until an
    experiment is picked and the per-suite fetch confirms it's installed),
    not just the historical frontend_adds_on one.
    """
    client = suites_app.test_client()
    admin_login_id = _make_admin_login_user(suites_app)
    _login(client, admin_login_id)

    resp = client.get("/admin/frontend_settings")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="box-suite-reactive_agents"' in html
    assert 'id="box-suite-frontend_adds_on"' in html
    assert "data-suite-get-url-template=" in html
    assert "data-suite-save-url-template=" in html


def test_suite_routes_hidden_without_development_mode(suites_app):
    """User-reported (2026-10-08): without --development, an installed
    private suite must stay hidden from this panel even for a logged-in
    admin -- not just un-offered in the listing, but a hard 404 from the
    GET/POST suite endpoints themselves (defense in depth)."""
    suites_app.config["DEVELOPMENT_MODE"] = False

    client = suites_app.test_client()
    exp_id = _make_exp(suites_app)
    admin_login_id = _make_admin_login_user(suites_app)
    _login(client, admin_login_id)

    get_resp = client.get(
        f"/admin/frontend_settings/suite/reactive_agents/get?exp_id={exp_id}"
    )
    assert get_resp.status_code == 404
    assert get_resp.get_json()["ok"] is False

    save_resp = client.post(
        "/admin/frontend_settings/suite/reactive_agents/save",
        json={
            "exp_id": exp_id,
            "module_id": "responsive_agents",
            "enabled": True,
            "config": {},
        },
    )
    assert save_resp.status_code == 404
    assert save_resp.get_json()["ok"] is False

    page_resp = client.get("/admin/frontend_settings")
    assert page_resp.status_code == 200
    html = page_resp.get_data(as_text=True)
    assert 'id="box-suite-reactive_agents"' not in html
    assert 'id="box-suite-frontend_adds_on"' not in html
