"""Alembic 0007: a dashboard database made from the stale shipped template is brought up to the current models."""

import importlib.util
import shutil
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "data_schema" / "database_dashboard.db"
MIGRATION = (
    ROOT / "y_web" / "alembic" / "versions" / "0007_sync_legacy_dashboard_schema.py"
)


def _upgrade(engine):
    spec = importlib.util.spec_from_file_location("rev0007", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()


def _columns(engine, table):
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def test_template_database_gets_missing_tables_and_columns_and_the_step_is_idempotent(
    tmp_path,
):
    db_file = tmp_path / "dashboard.db"
    shutil.copy(TEMPLATE, db_file)
    engine = sa.create_engine(f"sqlite:///{db_file}")
    before = set(sa.inspect(engine).get_table_names())
    cols_before = _columns(engine, "experiment_schedule_status")
    assert (
        "current_group_capacity" not in cols_before or "hpc_monitor_settings" in before
    ), "template changed: update the test"

    _upgrade(engine)
    _upgrade(engine)  # a second run changes nothing and does not fail

    assert "hpc_monitor_settings" in set(sa.inspect(engine).get_table_names())
    assert {
        "current_group_capacity",
        "dynamic_filling_enabled",
        "launch_in_progress",
    } <= _columns(engine, "experiment_schedule_status")
    assert {"username_type", "pop_type"} <= _columns(engine, "population")
    assert "cover_image" in _columns(engine, "agents") and "terminal_state" in _columns(
        engine, "client_execution"
    )
    with (
        engine.connect() as conn
    ):  # the exact statement of the failing scheduler now works
        conn.execute(
            sa.text(
                "SELECT id, is_running, current_group_id, current_group_capacity, dynamic_filling_enabled, "
                "launch_in_progress, started_at FROM experiment_schedule_status"
            )
        ).fetchall()
        assert (
            conn.execute(
                sa.text("SELECT COUNT(*) FROM experiment_schedule_status")
            ).scalar()
            >= 1
        )


def test_hpc_monitor_schema_guard_creates_a_missing_table(core_app):  # noqa: F811
    """The monitor thread asks for the schema before anything else: a database without the table must not break it."""
    from y_web import db
    from y_web.migrations.add_hpc_monitor_settings import (
        ensure_hpc_monitor_settings_schema,
    )

    with core_app.app_context():
        engine = db.engines["db_admin"]
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS hpc_monitor_settings")
        assert "hpc_monitor_settings" not in sa.inspect(engine).get_table_names()
        ensure_hpc_monitor_settings_schema()
        assert {"max_hpc_per_group", "max_hpc_simulations_per_vllm_worker"} <= _columns(
            engine, "hpc_monitor_settings"
        )


def test_empty_database_gets_the_schedule_row_even_without_column_defaults(tmp_path):
    """Tables made from the models carry no server-side defaults: the seed row must set every NOT NULL column."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    _upgrade(engine)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT is_running, dynamic_filling_enabled, launch_in_progress "
                "FROM experiment_schedule_status"
            )
        ).fetchall()
    assert row == [(0, 0, 0)]
