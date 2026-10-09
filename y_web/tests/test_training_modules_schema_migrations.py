"""C3 - ``schema_module`` migrations run after the core Alembic upgrade and after
installation (E2). Uses a fake plugin, not TrainingModules."""

import json

from sqlalchemy import inspect, text

from y_web.src.external_runtime import backend_plugins, registry
from y_web.tests.test_training_modules_manifest_keys import _make_plugin

MIGRATE_OK = '''
from sqlalchemy import text

CALLS = []

def migrate(engine):
    CALLS.append(1)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS fake_tm_probe (id INTEGER PRIMARY KEY, v TEXT)"))
    return True
'''


def _write_schema(repo, body):
    (repo / "pkg" / "schema.py").write_text(body)


def _admin_engine(app):
    from y_web import db

    return db.engines["db_admin"]


def test_migration_runs_with_db_admin_engine_and_is_idempotent(
    tmp_path, monkeypatch, app
):
    repo = _make_plugin(tmp_path, monkeypatch, {"schema_module": "pkg.schema:migrate"})
    _write_schema(repo, MIGRATE_OK)

    first = backend_plugins.run_backend_plugin_schema_migrations(app, ["fake_suite"])
    assert first["fake_suite"] == {"ran": True, "ok": True, "error": None}

    with app.app_context():
        engine = _admin_engine(app)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO fake_tm_probe (v) VALUES ('keep me')"))
        before = {c["name"] for c in inspect(engine).get_columns("fake_tm_probe")}

        second = backend_plugins.run_backend_plugin_schema_migrations(
            app, ["fake_suite"]
        )
        assert second["fake_suite"]["ok"] is True
        after = {c["name"] for c in inspect(engine).get_columns("fake_tm_probe")}
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT v FROM fake_tm_probe")).fetchall()
    assert before == after
    assert [r[0] for r in rows] == ["keep me"]


def test_suite_without_schema_module_is_skipped(tmp_path, monkeypatch, app):
    _make_plugin(tmp_path, monkeypatch)
    assert backend_plugins.run_backend_plugin_schema_migrations(app, ["fake_suite"]) == {}


def test_absent_plugin_is_skipped(tmp_path, monkeypatch, app):
    spec = registry.runtime_spec("training_modules")
    missing = registry.ExternalRuntimeSpec(**{**spec.__dict__, "path": tmp_path / "nope"})
    monkeypatch.setitem(registry.SUPPORTED_EXTERNAL_REPOS, "training_modules", missing)
    assert (
        backend_plugins.run_backend_plugin_schema_migrations(app, ["training_modules"])
        == {}
    )


def test_failing_migration_is_reported_and_never_raises(tmp_path, monkeypatch, app):
    repo = _make_plugin(tmp_path, monkeypatch, {"schema_module": "pkg.schema:migrate"})
    _write_schema(repo, "def migrate(engine):\n    raise RuntimeError('boom')\n")
    report = backend_plugins.run_backend_plugin_schema_migrations(app, ["fake_suite"])
    assert report["fake_suite"]["ok"] is False
    assert "boom" in report["fake_suite"]["error"]


def test_migration_returning_false_is_a_reported_failure(tmp_path, monkeypatch, app):
    repo = _make_plugin(tmp_path, monkeypatch, {"schema_module": "pkg.schema:migrate"})
    _write_schema(repo, "def migrate(engine):\n    return False\n")
    report = backend_plugins.run_backend_plugin_schema_migrations(app, ["fake_suite"])
    assert report["fake_suite"]["ok"] is False and report["fake_suite"]["error"]


def test_invalid_manifest_does_not_run_the_migration(tmp_path, monkeypatch, app):
    repo = _make_plugin(tmp_path, monkeypatch, {"schema_module": "pkg.missing:migrate"})
    assert backend_plugins.run_backend_plugin_schema_migrations(app, ["fake_suite"]) == {}


def test_create_app_runs_plugin_migrations_after_alembic(tmp_path, monkeypatch):
    """Startup wiring: the fake suite's table exists in db_admin after create_app()."""
    from y_web import create_app, db

    repo = _make_plugin(tmp_path, monkeypatch, {"schema_module": "pkg.schema:migrate"})
    _write_schema(repo, MIGRATE_OK)

    app = create_app(db_type="sqlite")
    with app.app_context():
        assert "fake_tm_probe" in inspect(db.engines["db_admin"]).get_table_names()
        # core schema is intact (Alembic ran first)
        assert "admin_users" in inspect(db.engines["db_admin"]).get_table_names()


def test_install_action_helper_runs_the_suite_migration(tmp_path, monkeypatch, app):
    """After install the Plugin Manager route calls this helper (E2)."""
    from y_web.routes.admin.sub.experiments._external_runtimes import (
        _run_suite_schema_migration,
    )

    repo = _make_plugin(tmp_path, monkeypatch, {"schema_module": "pkg.schema:migrate"})
    _write_schema(repo, MIGRATE_OK)
    with app.test_request_context("/"):
        _run_suite_schema_migration("fake_suite")
        with app.app_context():
            assert "fake_tm_probe" in inspect(_admin_engine(app)).get_table_names()
