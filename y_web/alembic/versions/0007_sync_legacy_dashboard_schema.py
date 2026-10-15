"""bring a stale dashboard database up to the current models

The dashboard template shipped in ``data_schema/database_dashboard.db`` predates several tables and columns, which
used to be added only by the legacy manual migration runner (``y_web/db_init/migrations.py``). That runner is not
executed when Flask-Migrate/Alembic drives startup, so a clean installation ended up without, for instance,
``hpc_monitor_settings`` and ``experiment_schedule_status.current_group_capacity``, and the background monitors
failed with "no such table / no such column".

This revision is idempotent: it creates every missing table of the ``db_admin`` bind from the models and adds the
columns that older databases lack. Databases that are already current are left untouched.

Revision ID: 0007_sync_legacy_dashboard_schema
Revises: 0006_add_plugin_state_table
Create Date: 2026-10-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0007_sync_legacy_dashboard_schema"
down_revision: Union[str, None] = "0006_add_plugin_state_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, DDL type/default) for columns that older dashboard databases lack.
_COLUMNS = (
    ("experiment_schedule_status", "current_group_capacity", "INTEGER"),
    ("experiment_schedule_status", "dynamic_filling_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("experiment_schedule_status", "launch_in_progress", "INTEGER NOT NULL DEFAULT 0"),
    ("population", "username_type", "VARCHAR(50) NOT NULL DEFAULT 'microblogging'"),
    ("population", "pop_type", "VARCHAR(50) DEFAULT NULL"),
    ("agents", "cover_image", "VARCHAR(400) DEFAULT ''"),
    ("client_execution", "terminal_state", "VARCHAR(20) DEFAULT 'running'"),
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Missing tables, straight from the models (checkfirst: existing tables are never touched).
    import y_web.src.models  # noqa: F401  (registers every model on its metadata)
    from y_web import db

    db.metadatas["db_admin"].create_all(bind=bind, checkfirst=True)

    # 2. Missing columns on tables that already existed.
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, column, ddl in _COLUMNS:
        if table not in existing_tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        op.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')

    # 3. The schedule status is a single-row table the scheduler expects to find.
    if "experiment_schedule_status" in existing_tables:
        has_row = bind.exec_driver_sql("SELECT 1 FROM experiment_schedule_status LIMIT 1").first()
        if has_row is None:
            bind.exec_driver_sql("INSERT INTO experiment_schedule_status (is_running) VALUES (0)")


def downgrade() -> None:
    # Additive and idempotent: nothing to undo.
    pass
