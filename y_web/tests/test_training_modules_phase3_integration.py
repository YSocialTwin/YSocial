"""Phase 3 (G3) integration: authoring area of the real TrainingModules plugin
inside the real core (sidebar group, role scoping, plugin switch, catalog).

Plugin-dependent tests skip when the plugin is not checked out.
"""

import json
import uuid

import pytest
from werkzeug.security import generate_password_hash

from y_web.src.external_runtime import backend_plugins, registry
from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_manifest_keys import _make_plugin


def _installed():
    return registry.runtime_spec("training_modules").path.exists()


requires_plugin = pytest.mark.skipif(
    not _installed(), reason="TrainingModules plugin not checked out"
)

API = "/admin/training/api"


def _client_as(app, role):
    from y_web import db
    from y_web.src.models import Admin_users

    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        row = Admin_users(
            username=f"p3{tag}",
            email=f"p3{tag}@example.test",
            password=generate_password_hash("x"),
            last_seen="2026-01-01",
            role=role,
        )
        db.session.add(row)
        db.session.commit()
        uid = row.get_id()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = uid
        sess["_fresh"] = True
        sess["tm_csrf"] = "tok"
    return client


def _post(client, url, body=None, method="post"):
    return getattr(client, method)(url, json=body or {}, headers={"X-CSRF-Token": "tok"})


def _scenario_step(client, uid, revision, slot="s1"):
    return _post(
        client,
        f"{API}/modules/{uid}/versions/1/steps",
        {
            "revision": revision,
            "type": "scenario",
            "title": f"Step {slot}",
            "config": {"slot_key": slot, "hint_name": "Intro", "platform_type": "microblogging"},
        },
    )


@requires_plugin
def test_training_group_is_in_the_sidebar_for_staff_only(core_app):
    for role in ("admin", "researcher"):
        client = _client_as(core_app, role)
        html = client.get("/admin/dashboard").get_data(as_text=True)
        assert 'id="sidebar-group-training_modules"' in html, role
        assert 'href="/admin/training/modules"' in html
        assert 'href="/admin/training/components"' in html
    with core_app.test_request_context("/"):
        assert backend_plugins.backend_suite_sidebar_groups("user") == []
        assert backend_plugins.backend_suite_sidebar_groups("student") == []


@requires_plugin
def test_full_authoring_cycle_with_researcher_scoping(core_app):
    alice = _client_as(core_app, "researcher")
    bob = _client_as(core_app, "researcher")
    admin = _client_as(core_app, "admin")

    created = _post(alice, f"{API}/modules", {"title": "Alice module"})
    assert created.status_code == 201
    uid = created.get_json()["module"]["module_uid"]
    r = _scenario_step(alice, uid, 1)
    assert r.status_code == 201
    r = _post(alice, f"{API}/modules/{uid}/versions/1/publish", {"revision": r.get_json()["revision"]})
    assert r.status_code == 200 and r.get_json()["version"]["status"] == "published"
    digest = r.get_json()["version"]["content_hash"]

    # another researcher cannot see or touch it; the admin can
    assert bob.get(f"{API}/modules").get_json()["modules"] == []
    assert bob.get(f"{API}/modules/{uid}").status_code == 404
    assert bob.get(f"/admin/training/modules/{uid}/edit").status_code == 404
    assert _post(bob, f"{API}/modules/{uid}/versions", {}).status_code == 404
    assert [m["title"] for m in admin.get(f"{API}/modules").get_json()["modules"]] == ["Alice module"]
    assert admin.get(f"/admin/training/modules/{uid}/edit").status_code == 200

    # published version is immutable, a new draft leaves it untouched
    v1 = alice.get(f"{API}/modules/{uid}/versions/1").get_json()["version"]
    assert _scenario_step(alice, uid, v1["revision"], "s2").status_code == 409
    draft = _post(alice, f"{API}/modules/{uid}/versions", {})
    assert draft.status_code == 201 and draft.get_json()["version"]["version_no"] == 2
    assert alice.get(f"{API}/modules/{uid}/versions/1").get_json()["version"]["content_hash"] == digest


@requires_plugin
def test_pages_render_inside_the_core_admin_layout(core_app):
    admin = _client_as(core_app, "admin")
    uid = _post(admin, f"{API}/modules", {"title": "Layout check"}).get_json()["module"]["module_uid"]
    for path, needle in [
        ("/admin/training/modules", "Layout check"),
        (f"/admin/training/modules/{uid}/edit", "Publish version"),
        ("/admin/training/components", "Component catalog"),
    ]:
        resp = admin.get(path)
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200 and needle in html, path
        assert 'id="sidebar-group-training_modules"' in html  # core layout was used
        assert html.count("<!doctype html>") + html.count("<!DOCTYPE html>") == 1


@requires_plugin
def test_participants_and_anonymous_users_are_refused(core_app):
    student = _client_as(core_app, "user")
    for path in (f"{API}/modules", f"{API}/types", "/admin/training/modules", "/admin/training/components"):
        assert student.get(path).status_code == 403, path
    assert _post(student, f"{API}/modules", {"title": "x"}).status_code == 403
    anonymous = core_app.test_client()
    assert anonymous.get(f"{API}/modules").status_code in (302, 401)


@requires_plugin
def test_disabled_plugin_makes_every_page_and_api_unreachable(core_app):
    admin = _client_as(core_app, "admin")
    assert admin.get("/admin/training/modules").status_code == 200
    with core_app.app_context():
        backend_plugins.set_plugin_enabled("training_modules", False, "tester")
    for path in ("/admin/training/modules", "/admin/training/components", f"{API}/modules", f"{API}/types"):
        assert admin.get(path).status_code == 404, path
    assert _post(admin, f"{API}/modules", {"title": "x"}).status_code == 404
    html = admin.get("/admin/dashboard").get_data(as_text=True)
    assert "sidebar-group-training_modules" not in html
    with core_app.app_context():
        backend_plugins.set_plugin_enabled("training_modules", True, "tester")
    assert admin.get("/admin/training/modules").status_code == 200


@requires_plugin
def test_native_palette_without_third_party_plugins(core_app):
    admin = _client_as(core_app, "admin")
    types = admin.get(f"{API}/types").get_json()["types"]
    assert [t["type_ref"] for t in types] == ["scenario", "external_component"]
    assert admin.get(f"{API}/components").get_json()["components"] == []


@requires_plugin
def test_third_party_types_come_from_the_core_catalog(core_app, tmp_path, monkeypatch):
    """A fake plugin declaring ``training_components`` shows up in the palette and
    its step type can be added, configured and published (real core reader)."""
    descriptor = {
        "type_key": "questionnaire",
        "label": "Questionnaire",
        "category": "Questionnaire",
        "contract_version": "1",
        "config_schema": {"type": "object", "required": ["form_id"], "properties": {"form_id": {"type": "string"}}},
        "launch": {"endpoint": "/q/launch"},
    }
    _make_plugin(tmp_path, monkeypatch, {"training_components": [descriptor]})
    admin = _client_as(core_app, "admin")
    ref = "fake_suite:questionnaire"
    types = {t["type_ref"]: t for t in admin.get(f"{API}/types").get_json()["types"]}
    assert ref in types and types[ref]["selectable"] and types[ref]["native"] is False

    uid = _post(admin, f"{API}/modules", {"title": "With survey"}).get_json()["module"]["module_uid"]
    r = _post(
        admin,
        f"{API}/modules/{uid}/versions/1/steps",
        {"revision": 1, "type": "component", "component_ref": ref, "title": "Survey",
         "config": {"component_ref": ref, "contract_version": "1", "settings": {"form_id": "f1"}}},
    )
    assert r.status_code == 201, r.get_json()
    pub = _post(admin, f"{API}/modules/{uid}/versions/1/publish", {"revision": r.get_json()["revision"]})
    assert pub.status_code == 200, pub.get_json()

    # a disabled plugin offers no types any more -> unresolved step blocks a new draft's publication
    with core_app.app_context():
        backend_plugins.set_plugin_enabled("fake_suite", False, "tester")
    types = {t["type_ref"] for t in admin.get(f"{API}/types").get_json()["types"]}
    assert ref not in types
    _post(admin, f"{API}/modules/{uid}/versions", {})
    report = admin.get(f"{API}/modules/{uid}/versions/2/validate").get_json()
    assert [i["code"] for i in report["errors"]] == ["component_missing_in_catalog"]
