"""Alembic 0008 (admin_users.lang): single head, idempotent upgrade, applied by the app at start-up."""

import importlib.util
import shutil
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "y_web" / "alembic" / "versions"
TEMPLATE = ROOT / "data_schema" / "database_dashboard.db"


def _script_dir():
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "y_web" / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _run(engine, filename):
    spec = importlib.util.spec_from_file_location(filename[:4], VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()


def test_the_revision_chain_is_linear_and_ends_with_the_language_column():
    script = _script_dir()
    assert script.get_heads() == ["0009_add_signup_tables"]
    assert (
        script.get_revision("0009_add_signup_tables").down_revision
        == "0008_add_admin_users_lang"
    )
    assert script.get_revision("0008_add_admin_users_lang").down_revision == (
        "0007_sync_legacy_dashboard_schema"
    )


def test_upgrade_adds_the_column_once_and_keeps_existing_rows(tmp_path):
    db_file = tmp_path / "dashboard.db"
    shutil.copy(TEMPLATE, db_file)
    engine = sa.create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:  # a database that predates the column
        cols = {c["name"] for c in sa.inspect(conn).get_columns("admin_users")}
        if "lang" in cols:
            conn.exec_driver_sql("ALTER TABLE admin_users DROP COLUMN lang")
    _run(engine, "0007_sync_legacy_dashboard_schema.py")
    _run(engine, "0008_add_admin_users_lang.py")
    _run(engine, "0008_add_admin_users_lang.py")  # idempotent
    names = [c["name"] for c in sa.inspect(engine).get_columns("admin_users")]
    assert names.count("lang") == 1
    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT COUNT(*) FROM admin_users WHERE lang IS NOT NULL")
            ).scalar()
            == 0
        )


def test_application_start_applies_the_migration(core_app):  # noqa: F811
    from y_web import db

    with core_app.app_context():
        engine = db.engines["db_admin"]
        assert "lang" in {
            c["name"] for c in sa.inspect(engine).get_columns("admin_users")
        }
        with engine.connect() as conn:
            head = (
                conn.execute(sa.text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
        assert "0009_add_signup_tables" in head


def test_filter_bubble_row_migration_tolerates_a_database_without_the_table():
    """0003 seeds ``content_recsys``; on a database that does not have the table yet it must do nothing, not crash."""
    spec = importlib.util.spec_from_file_location(
        "m0003", VERSIONS / "0003_add_filter_bubble_recsys_row.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        op = Operations(MigrationContext.configure(conn))
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            module.downgrade()
        assert "content_recsys" not in sa.inspect(conn).get_table_names()
        conn.execute(
            sa.text(
                "CREATE TABLE content_recsys (name TEXT, value TEXT, category TEXT, enabled TEXT)"
            )
        )
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
        assert (
            conn.execute(
                sa.text("SELECT COUNT(*) FROM content_recsys WHERE name='FilterBubble'")
            ).scalar()
            == 1
        )
