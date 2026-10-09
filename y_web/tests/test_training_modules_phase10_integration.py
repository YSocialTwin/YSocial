"""Phase 10 (G10) integration: library, native Onboarding and the pin against the real core. Skips without the plugin."""

import io
import json
import re
import zipfile

import pytest
from sqlalchemy import text

from y_web.src.external_runtime import backend_plugins
from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    PLATFORMS, _experiment, _experiment_paths_under_tmp, _participant)

LIB = "/admin/training/api/library"
PLATFORM, SIMULATOR = PLATFORMS[0]
ONBOARDING = {
    "title": "Welcome to the training", "subtitle": "", "button_label": "",
    "blocks": [
        {"id": "intro", "type": "paragraph", "text": "Please read **everything**."},
        {"id": "path", "type": "overview"},
        {"id": "ok", "type": "confirmations", "items": [{"id": "read", "label": "I have read this", "required": True}]},
    ],
}


def _count(app, sql, **params):
    from y_web import db

    with app.app_context():
        with db.engines["db_admin"].connect() as c:
            return c.execute(text(sql), params).scalar()


def _publish_instance(admin, definition):
    created = _post(admin, f"{LIB}/instances", {"kind": "onboarding", "title": "Core welcome"}).get_json()["instance"]
    uid = created["instance_uid"]
    saved = admin.put(f"{LIB}/instances/{uid}/draft", json={"revision": 1, "definition": definition}, headers={"X-CSRF-Token": "tok"})
    assert saved.status_code == 200 and saved.get_json()["problems"] == []
    assert _post(admin, f"{LIB}/instances/{uid}/publish", {"revision": 2}).status_code == 200
    return uid


def _native_module(admin, uid, version=1):
    module = _post(admin, f"{API}/modules", {"title": "Native only"}).get_json()["module"]["module_uid"]
    step = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
        "type": "component", "component_ref": "tm_native:onboarding", "title": "Welcome", "revision": 1,
        "config": {"settings": {"instance_uid": uid, "instance_version": version}}})
    assert step.status_code == 201, step.get_json()
    published = _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": step.get_json()["revision"]})
    assert published.status_code == 200, published.get_json()
    return module, step.get_json()["step"]["step_key"]


@requires_plugin
def test_native_onboarding_end_to_end_through_the_real_core(core_app):
    from y_web import db

    app, admin = core_app, _client_as(core_app, "admin")
    with app.app_context():
        names = {r[0] for r in db.engines["db_admin"].connect().execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"tm_component_instance", "tm_component_instance_version", "tm_component_response"} <= names
    inst = _publish_instance(admin, ONBOARDING)
    module, key = _native_module(admin, inst)
    exp = _experiment(app, PLATFORM, SIMULATOR)
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Native run"}).get_json()["run"]["id"]
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200
    account, username, email = _participant(app, exp)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201

    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    run_page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', run_page).group(1)
    assert me.post(f"/training/runs/{rid}/steps/{key}/start", data={"csrf_token": token}).status_code == 303
    page = me.get(f"/training/runs/{rid}/steps/{key}/page").get_data(as_text=True)
    assert "Welcome to the training" in page and "<strong>everything</strong>" in page and "I have read this" in page
    assert "Onboarding page" in page                                    # the automatic path overview
    assert username not in page and email not in page                    # pseudonymous page
    bad = me.post(f"/training/runs/{rid}/steps/{key}/submit", data={"csrf_token": token})
    assert bad.status_code == 422
    assert me.post(f"/training/runs/{rid}/steps/{key}/submit", data={"ack": "read"}).status_code == 403   # no CSRF token
    ok = me.post(f"/training/runs/{rid}/steps/{key}/submit", data={"csrf_token": token, "ack": "read"})
    assert ok.status_code == 303
    assert _count(app, "SELECT COUNT(*) FROM tm_step_progress WHERE status='completed' AND step_key=:k", k=key) == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='onboarding_acknowledged' AND source='native'") == 1
    assert _count(app, "SELECT COUNT(*) FROM tm_event WHERE type='onboarding_viewed' AND source='native'") == 1
    assert "Thank you" in me.get(f"/training/runs/{rid}").get_data(as_text=True) or "done" in me.get(f"/training/runs/{rid}").get_data(as_text=True)

    export = _post(admin, f"{API}/runs/{rid}/exports", {"reason": "native check"})
    assert export.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(export.data)).namelist()
    events = zipfile.ZipFile(io.BytesIO(export.data)).read("events.csv").decode()
    assert "events.csv" in names and "onboarding_acknowledged" in events and "verified" in events
    assert username not in events and email not in events


@requires_plugin
def test_the_library_follows_the_plugin_switch_and_keeps_its_tables(core_app):
    app, admin = core_app, _client_as(core_app, "admin")
    inst = _publish_instance(admin, ONBOARDING)
    assert admin.get("/admin/training/library").status_code == 200
    with app.app_context():
        backend_plugins.set_plugin_enabled("training_modules", False, "tester")
    assert admin.get("/admin/training/library").status_code == 404
    assert admin.get(f"{LIB}/instances").status_code == 404
    with app.app_context():
        backend_plugins.set_plugin_enabled("training_modules", True, "tester")
    assert admin.get(f"{LIB}/instances/{inst}").status_code == 200       # nothing was lost
    report = backend_plugins.run_backend_plugin_schema_migrations(app, ["training_modules"])
    assert report["training_modules"]["ok"] is True
    assert _count(app, "SELECT COUNT(*) FROM tm_component_instance") >= 1


@requires_plugin
def test_participants_cannot_use_the_library(core_app):
    student = _client_as(core_app, "user")
    for path in (f"{LIB}/instances", f"{LIB}/kinds", "/admin/training/library"):
        assert student.get(path).status_code in (302, 403), path
