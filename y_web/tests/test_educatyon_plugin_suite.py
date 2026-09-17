"""
Tests for the EducatYon frontend plugin suite integration.

Covers:
  * manifest discovery/validation (y_web.src.external_runtime.frontend_plugins)
  * suite/blueprint registration + static asset serving (plugin_loader)
  * the JIT per-experiment schema migration (external/EducatYon/.../migrations.py)
  * the "zero impact when not enabled" guarantee for active_modules_context()
  * the minimal post_annotation API end-to-end (enable -> create -> list)

These tests exercise the REAL external/EducatYon repo scaffolded alongside
this change (not a mock), since discovery/validation intentionally reads
manifests live from disk rather than from a cache.
"""
import json
import os
import sqlite3
import tempfile

import pytest
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.src.external_runtime import frontend_plugins
from y_web.src.external_runtime import plugin_loader


# ---------------------------------------------------------------------------
# Manifest discovery / validation
# ---------------------------------------------------------------------------
def test_discover_frontend_modules_finds_post_annotation():
    modules = frontend_plugins.discover_frontend_modules("educatyon")
    module_ids = [m.get("module_id") for m in modules]
    assert "post_annotation" in module_ids


def test_validate_frontend_suite_valid_for_educatyon():
    report = frontend_plugins.validate_frontend_suite("educatyon")
    assert report["installed"] is True
    assert report["valid"] is True, report["errors"]
    assert report["suite"]["suite_id"] == "educatyon"
    module_ids = [m["module_id"] for m in report["modules"]]
    assert "post_annotation" in module_ids
    post_annotation = next(m for m in report["modules"] if m["module_id"] == "post_annotation")
    assert post_annotation["valid"] is True, post_annotation["errors"]


def test_validate_frontend_suite_unknown_repo_key():
    report = frontend_plugins.validate_frontend_suite("not_a_real_repo_key")
    assert report["installed"] is False
    assert report["valid"] is False
    assert report["errors"]


def test_frontend_plugin_repo_keys_includes_educatyon():
    assert "educatyon" in frontend_plugins.frontend_plugin_repo_keys()


# ---------------------------------------------------------------------------
# JIT migration (module's own schema, applied to one experiment DB)
# ---------------------------------------------------------------------------
def test_post_annotation_migration_creates_tables():
    module = plugin_loader._import_from_suite("educatyon", "modules.post_annotation.backend.migrations")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        # Start from an empty-but-valid sqlite file (as a real experiment DB would be).
        sqlite3.connect(db_path).close()

        assert module.migrate_sqlite_server(db_path, quiet=True) is True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "plugin_educatyon_post_annotation" in tables
        assert "plugin_educatyon_post_annotation_topic" in tables

        # Idempotent: calling it again must not error or duplicate anything.
        assert module.migrate_sqlite_server(db_path, quiet=True) is True
    finally:
        os.unlink(db_path)


def test_ensure_module_schema_targets_the_right_experiment_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        sqlite3.connect(db_path).close()
        monkeypatch.setattr(plugin_loader, "_experiment_db_path", lambda exp_id: db_path)

        assert plugin_loader.ensure_module_schema("educatyon", "post_annotation", exp_id=999, quiet=True) is True

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "plugin_educatyon_post_annotation" in tables
    finally:
        os.unlink(db_path)


def test_ensure_module_schema_unknown_module_returns_false():
    assert plugin_loader.ensure_module_schema("educatyon", "does_not_exist", exp_id=1) is False


# ---------------------------------------------------------------------------
# Blueprint / static asset registration
# ---------------------------------------------------------------------------
def test_register_frontend_plugin_suites_registers_blueprint_and_static_route(app):
    report = plugin_loader.register_frontend_plugin_suites(app)
    assert report["suites"]["educatyon"]["installed"] is True
    assert report["suites"]["educatyon"]["valid"] is True
    assert "post_annotation" in report["suites"]["educatyon"]["registered_modules"]
    assert plugin_loader.is_module_available("educatyon", "post_annotation") is True

    assert "educatyon_post_annotation" in app.blueprints
    assert "educatyon_static_educatyon" in app.blueprints

    client = app.test_client()
    resp = client.get("/plugins/educatyon/post_annotation/static/modules/post_annotation/frontend/plugin.js")
    assert resp.status_code == 200
    assert b"EducatYon" in resp.data

    # Path traversal must be refused, not silently served.
    resp2 = client.get("/plugins/educatyon/post_annotation/static/../../../../etc/passwd")
    assert resp2.status_code == 404

    # An unknown module_id under a valid suite must 404, not serve anything.
    resp3 = client.get("/plugins/educatyon/does_not_exist/static/modules/post_annotation/frontend/plugin.js")
    assert resp3.status_code == 404


# ---------------------------------------------------------------------------
# active_modules_context(): the "zero impact unless enabled" choke point
# ---------------------------------------------------------------------------
def _make_exp(app):
    from y_web.src.models import Exps

    with app.app_context():
        exp = Exps(
            platform_type="microblogging",
            exp_name="edu-test-exp",
            db_name="experiments/edu-test/database_server.db",
            owner="admin",
            exp_descr="test",
            status=1,
            running=0,
            port=5000,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


def test_active_modules_context_empty_without_registered_suite(app):
    # Fresh module-level state: nothing registered yet in this process for
    # a throwaway repo key that will never validate.
    plugin_loader._REGISTERED_SUITES.clear()
    with app.app_context():
        assert plugin_loader.active_modules_context(exp_id=1) == []


def test_active_modules_context_empty_when_module_not_enabled(app):
    plugin_loader.register_frontend_plugin_suites(app)
    with app.app_context():
        exp_id = _make_exp(app)
        assert plugin_loader.active_modules_context(exp_id) == []


def test_active_modules_context_returns_module_when_enabled(app):
    plugin_loader.register_frontend_plugin_suites(app)
    from y_web.src.models import EducatyonExpModuleSettings

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id,
            module_id="post_annotation",
            enabled=True,
            config_json=json.dumps({"opinion_scale": "binary"}),
        ))
        db.session.commit()

        modules = plugin_loader.active_modules_context(exp_id)
        assert len(modules) == 1
        assert modules[0]["module_id"] == "post_annotation"
        assert modules[0]["api_base"] == f"/{exp_id}/api/plugins/educatyon/post_annotation"
        assert modules[0]["frontend_entry"].endswith("modules/post_annotation/frontend/plugin.js")
        assert modules[0]["config"]["opinion_scale"] == "binary"
        # Untouched parameters still carry their manifest default.
        assert modules[0]["config"]["annotate_posts"] is True


# ---------------------------------------------------------------------------
# End-to-end API flow: enable -> create annotation -> list it back
# ---------------------------------------------------------------------------
@pytest.fixture
def educatyon_app(app):
    """The shared `app` fixture, with the post_annotation blueprint registered.

    Registering the suite imports the module's model classes for the first
    time in this process, so we re-run create_all() afterwards to create
    their tables in the fixture's temp db_exp file — create_all() is
    additive/idempotent, so this never touches the tables already created
    by the base `app` fixture.
    """
    plugin_loader.register_frontend_plugin_suites(app)
    with app.app_context():
        try:
            db.create_all(bind_key="__all__")
        except TypeError:
            db.create_all()
    return app


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_post_annotation_api_end_to_end(educatyon_app):
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id, module_id="post_annotation", enabled=True, config_json="{}",
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    # Not enabled for a *different* experiment -> 404, never a silent 200.
    resp_disabled = client.get(f"/999999/api/plugins/educatyon/post_annotation/topics")
    assert resp_disabled.status_code == 404

    # Create an annotation on the enabled experiment.
    create_resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={
            "target_type": "post",
            "target_id": 42,
            "topics": [{"label": "Climate change", "opinion": 1.0}],
        },
    )
    assert create_resp.status_code == 200, create_resp.data
    payload = create_resp.get_json()
    assert payload["ok"] is True
    annotation_id = payload["annotation_id"]
    assert annotation_id

    list_resp = client.get(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        query_string={"target_type": "post", "target_id": 42},
    )
    assert list_resp.status_code == 200
    listed = list_resp.get_json()
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert listed["annotations"][0]["topics"][0]["label"] == "Climate change"
    assert listed["annotations"][0]["topics"][0]["opinion_value"] == 1.0


def test_post_annotation_rejects_disabled_target_type(educatyon_app):
    from y_web.src.models import EducatyonExpModuleSettings, User_mgmt

    app = educatyon_app
    client = app.test_client()

    with app.app_context():
        exp_id = _make_exp(app)
        db.session.add(EducatyonExpModuleSettings(
            exp_id=exp_id,
            module_id="post_annotation",
            enabled=True,
            config_json=json.dumps({"annotate_comments": False}),
        ))
        db.session.commit()
        test_user = db.session.scalars(
            db.select(User_mgmt).filter_by(username="testuser")
        ).first()
        user_id = test_user.id

    _login(client, user_id)

    resp = client.post(
        f"/{exp_id}/api/plugins/educatyon/post_annotation/annotations",
        json={"target_type": "comment", "target_id": 1, "topics": [{"label": "x", "opinion": 0}]},
    )
    assert resp.status_code == 403
