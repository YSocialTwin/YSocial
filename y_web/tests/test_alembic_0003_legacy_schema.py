import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.unit

_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/0003_add_filter_bubble_recsys_row.py"
)


def _run_upgrade(engine):
    spec = importlib.util.spec_from_file_location("mig0003", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()


def test_upgrade_adds_missing_columns_on_legacy_table():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE content_recsys (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " name TEXT NOT NULL, value TEXT NOT NULL)"
            )
        )
    _run_upgrade(engine)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT value, category, enabled FROM content_recsys WHERE name='FilterBubble'"
            )
        ).fetchone()
    assert tuple(row) == ("Personalized Feed", "Personalization", "HumanOnly")


def test_upgrade_is_idempotent_on_current_schema():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE content_recsys (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " name TEXT NOT NULL, value TEXT NOT NULL, enabled TEXT, category TEXT)"
            )
        )
    _run_upgrade(engine)
    _run_upgrade(engine)
    with engine.connect() as conn:
        n = conn.execute(
            sa.text("SELECT count(*) FROM content_recsys WHERE name='FilterBubble'")
        ).scalar()
    assert n == 1
