"""Alembic 0011 (admin_users.llm_api_key): idempotent upgrade that keeps the rows, applied at start-up."""

import importlib.util
import shutil
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "y_web" / "alembic" / "versions"
TEMPLATE = ROOT / "data_schema" / "database_dashboard.db"
FILENAME = "0011_add_admin_users_llm_api_key.py"


def _upgrade(engine):
    spec = importlib.util.spec_from_file_location("m0011", VERSIONS / FILENAME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()


def test_upgrade_adds_the_column_once_and_keeps_existing_rows(tmp_path):
    db_file = tmp_path / "dashboard.db"
    shutil.copy(TEMPLATE, db_file)
    engine = sa.create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:  # a database that predates the column
        columns = {c["name"] for c in sa.inspect(conn).get_columns("admin_users")}
        if "llm_api_key" in columns:
            conn.exec_driver_sql("ALTER TABLE admin_users DROP COLUMN llm_api_key")
        rows = conn.execute(sa.text("SELECT COUNT(*) FROM admin_users")).scalar()
    _upgrade(engine)
    _upgrade(engine)  # idempotent
    names = [c["name"] for c in sa.inspect(engine).get_columns("admin_users")]
    assert names.count("llm_api_key") == 1
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM admin_users")).scalar() == rows
        )
        assert not conn.execute(
            sa.text("SELECT 1 FROM admin_users WHERE llm_api_key NOT IN ('')")
        ).fetchall()


def test_application_start_applies_the_migration(core_app):  # noqa: F811
    from y_web import db

    with core_app.app_context():
        engine = db.engines["db_admin"]
        assert "llm_api_key" in {
            c["name"] for c in sa.inspect(engine).get_columns("admin_users")
        }
