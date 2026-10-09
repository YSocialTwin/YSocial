"""Phase 9 (G9) integration: deactivation, simulated uninstall, reinstall and orphans against the real core.

The plugin's tables survive every one of these; nothing here deletes the plugin folder (the core's
``delete_runtime_repo`` removes it with ``rmtree`` and never touches ``tm_*``, which is what the
"uninstall" test simulates by switching the suite off and re-running its migration). Skips without the plugin.
"""

import json

import pytest
from sqlalchemy import text

from y_web.src.external_runtime import backend_plugins
from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _module, _participant)

PLATFORM, SIMULATOR = PLATFORMS[0]


def _set_enabled(app, enabled):
    with app.app_context():
        backend_plugins.set_plugin_enabled("training_modules", enabled, "tester")


def _count(app, sql, **params):
    from y_web import db

    with app.app_context():
        with db.engines["db_admin"].connect() as c:
            return c.execute(text(sql), params).scalar()


def _tables(app):
    from y_web import db

    with app.app_context():
        with db.engines["db_admin"].connect() as c:
            return {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tm\\_%' ESCAPE '\\'"))}


@pytest.fixture
def running(core_app):
    """An active run with one enrolled participant (account, e-mail), plus the experiment id."""
    admin = _client_as(core_app, "admin")
    exp = _experiment(core_app, PLATFORM, SIMULATOR)
    uid = _module(admin, PLATFORM, SIMULATOR)
    rid = _post(admin, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "G9 run"}).get_json()["run"]["id"]
    for b in admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"]:
        assert admin.put(f"{API}/runs/{rid}/bindings/{b['step_key']}", json={"exp_id": exp},
                         headers={"X-CSRF-Token": "tok"}).status_code == 200
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, username, email = _participant(core_app, exp)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201
    return {"admin": admin, "rid": rid, "exp": exp, "account": account, "email": email}


def _participant_client(app, email):
    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    return me


@requires_plugin
def test_deactivation_hides_everything_keeps_data_and_reactivation_resumes(core_app, running):
    app, admin, rid = core_app, running["admin"], running["rid"]
    me = _participant_client(app, running["email"])
    assert me.get(f"/training/runs/{rid}").status_code == 200
    assert "sidebar-group-training_modules" in admin.get("/admin/dashboard").get_data(as_text=True)
    before = _count(app, "SELECT COUNT(*) FROM tm_event WHERE enrollment_id IN (SELECT id FROM tm_enrollment WHERE run_id=:r)", r=rid)
    tables = _tables(app)
    assert {"tm_module", "tm_run", "tm_enrollment", "tm_event", "tm_setting"} <= tables

    _set_enabled(app, False)
    for path in ("/training", f"/training/runs/{rid}", "/admin/training/modules", "/admin/training/runs",
                 "/admin/training/activity", "/admin/training/settings", f"{API}/runs", f"{API}/runs/{rid}/orphans"):
        assert (me if path.startswith("/training") else admin).get(path).status_code == 404, path
    assert admin.get(f"{API}/runs/{rid}/exports").status_code == 404
    assert _post(admin, f"{API}/runs/{rid}/exports", {"reason": "while disabled"}).status_code == 404
    assert _post(admin, "/training/api/v1/completions", {}).status_code == 404
    assert "sidebar-group-training_modules" not in admin.get("/admin/dashboard").get_data(as_text=True)
    assert app.test_client().get("/login").status_code == 200           # the core is untouched
    login = app.test_client().post("/login", data={"email": running["email"], "password": "x"})
    # post_login hook is inactive: no redirect to /training, the core's own experiment selection is shown
    assert login.status_code == 200 and "Location" not in login.headers   # (enabled: 302 to /training)
    assert _tables(app) == tables                                       # nothing dropped
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE enrollment_id IN (SELECT id FROM tm_enrollment WHERE run_id=:r)", r=rid) == before

    _set_enabled(app, True)
    assert me.get(f"/training/runs/{rid}").status_code == 200
    assert admin.get(f"{API}/runs/{rid}/enrollments").get_json()["enrollments"][0]["status"] == "enrolled"


@requires_plugin
def test_simulated_uninstall_and_reinstall_resume_from_the_kept_tables(core_app, running):
    app, admin, rid = core_app, running["admin"], running["rid"]
    enrolled = _count(app, "SELECT COUNT(*) FROM tm_enrollment WHERE run_id=:r", r=rid)
    _set_enabled(app, False)
    # "uninstall" = the plugin folder is gone and the suite is off: the core must not depend on tm_* at all
    assert app.test_client().get("/login").status_code == 200
    assert _client_as(app, "admin").get("/admin/dashboard").status_code == 200
    # "reinstall" = the schema migration runs again on the existing tables: idempotent, no data lost
    report = backend_plugins.run_backend_plugin_schema_migrations(app, ["training_modules"])
    assert report["training_modules"]["ok"] is True, report
    report = backend_plugins.run_backend_plugin_schema_migrations(app, ["training_modules"])
    assert report["training_modules"]["ok"] is True, report
    assert _count(app, "SELECT COUNT(*) FROM tm_enrollment WHERE run_id=:r", r=rid) == enrolled
    _set_enabled(app, True)
    assert admin.get(f"{API}/runs/{rid}").get_json()["run"]["status"] == "active"
    assert _participant_client(app, running["email"]).get(f"/training/runs/{rid}").status_code == 200


@requires_plugin
def test_deleted_account_and_experiment_are_reported_and_handled(core_app, running):
    from y_web import db
    from y_web.src.models import Admin_users, Exps, User_Experiment

    app, admin, rid = core_app, running["admin"], running["rid"]
    me = _participant_client(app, running["email"])
    with app.app_context():
        db.session.query(User_Experiment).filter_by(user_id=running["account"]).delete()
        db.session.query(Admin_users).filter_by(id=running["account"]).delete()
        db.session.query(Exps).filter_by(idexp=running["exp"]).delete()
        db.session.commit()
    body = admin.get(f"{API}/runs/{rid}/orphans").get_json()
    assert len(body["orphaned_enrollments"]) == 1 and len(body["orphaned_bindings"]) >= 1
    assert running["email"] not in json.dumps(body)
    assert me.get(f"/training/runs/{rid}").status_code == 403          # the session of a deleted account is refused
    assert admin.get(f"{API}/runs/{rid}/enrollments").get_json()["enrollments"][0]["orphaned"] is True
    r = _post(admin, f"{API}/runs/{rid}/exports", {"reason": "after deletions"})
    assert r.status_code == 200 and r.headers["X-TM-Partial"] in ("true", "false")
