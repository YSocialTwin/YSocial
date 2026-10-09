"""Phase 1 (G1) integration: core + the real TrainingModules checkout.

Plugin-dependent tests skip when the plugin is not checked out; the
absent-plugin tests run everywhere.
"""

import uuid

import pytest
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from y_web.src.external_runtime import backend_plugins, registry


def _installed():
    return registry.runtime_spec("training_modules").path.exists()


requires_plugin = pytest.mark.skipif(
    not _installed(), reason="TrainingModules plugin not checked out"
)


def _new_app():
    from y_web import create_app

    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _login_as(app, client, role):
    from y_web import db
    from y_web.src.models import Admin_users

    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        row = Admin_users(
            username=f"tm{tag}",
            email=f"tm{tag}@example.test",
            password=generate_password_hash("x"),
            last_seen="2026-01-01",
            role=role,
        )
        db.session.add(row)
        db.session.commit()
        uid = row.get_id()
    with client.session_transaction() as sess:
        sess["_user_id"] = uid
        sess["_fresh"] = True


@requires_plugin
def test_real_plugin_manifest_is_valid_with_schema_module():
    report = backend_plugins.validate_backend_suite("training_modules")
    assert report["installed"] and report["valid"], report["errors"]
    assert report["schema_module"] == "modules.training_editor.backend.schema:migrate"
    assert [m["module_id"] for m in report["modules"]] == ["training_editor"]


@requires_plugin
def test_startup_registers_blueprint_and_creates_tm_tables():
    from y_web import db

    app = _new_app()
    assert "training_modules" in app.blueprints
    with app.app_context():
        names = set(inspect(db.engines["db_admin"]).get_table_names())
        assert {"tm_module", "tm_step", "tm_event", "tm_schema_version"} <= names
        with db.engines["db_admin"].connect() as conn:
            version = conn.execute(
                text("SELECT version FROM tm_schema_version")
            ).scalars().all()
        assert version == sorted(set(version)) and version[-1] == 4   # schema v4 (the dev DB copy may still hold older stamps)


@requires_plugin
def test_rerunning_the_migration_does_not_duplicate_or_lose_rows():
    """Each create_app() gets its own temp DB, so re-run the startup step on the same app."""
    from y_web import db

    app = _new_app()
    with app.app_context():
        with db.engines["db_admin"].begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tm_module (module_uid, title, created_at) "
                    "VALUES ('u-keep', 'Keep', '2026-01-01 00:00:00')"
                )
            )
    for _ in range(2):
        outcome = backend_plugins.run_backend_plugin_schema_migrations(app)
        assert outcome["training_modules"] == {"ran": True, "ok": True, "error": None}
    with app.app_context():
        with db.engines["db_admin"].connect() as conn:
            titles = conn.execute(text("SELECT title FROM tm_module")).scalars().all()
            versions = conn.execute(
                text("SELECT version FROM tm_schema_version")
            ).scalars().all()
    # the temp DB is a copy of the developer's dashboard.db, so it may hold other rows
    assert titles.count("Keep") == 1
    assert versions == sorted(set(versions)) and versions[-1] == 4


@requires_plugin
def test_health_route_is_role_protected_end_to_end():
    app = _new_app()
    anonymous = app.test_client().get("/admin/training/health")
    assert anonymous.status_code == 302

    for role, expected in (("admin", 200), ("researcher", 200), ("user", 403)):
        client = app.test_client()
        _login_as(app, client, role)
        assert client.get("/admin/training/health").status_code == expected, role


def test_absent_plugin_leaves_startup_and_routes_untouched(tmp_path, monkeypatch):
    """G1(1): with the plugin folder missing the app starts, nothing is registered,
    no tm_* table is created and the health route does not exist."""
    from y_web import db

    spec = registry.runtime_spec("training_modules")
    missing = registry.ExternalRuntimeSpec(**{**spec.__dict__, "path": tmp_path / "nope"})
    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, "training_modules", missing)

    app = _new_app()
    assert "training_modules" not in app.blueprints
    with app.app_context():
        names = set(inspect(db.engines["db_admin"]).get_table_names())
        # tables already present in the seed dashboard.db are not created by this app
        import sqlite3
        from pathlib import Path

        seed = Path(__file__).resolve().parents[1] / "db" / "dashboard.db"
        with sqlite3.connect(f"file:{seed}?mode=ro", uri=True) as seed_conn:
            seeded = {
                r[0]
                for r in seed_conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'tm\\_%' ESCAPE '\\'")
            }
        assert {n for n in names if n.startswith("tm_")} == seeded
    assert app.test_client().get("/admin/training/health").status_code in (302, 404)
