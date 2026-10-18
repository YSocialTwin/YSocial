import pytest
import sqlalchemy as sa

from y_web.src.system.startup_migrations import sync_missing_model_columns

pytestmark = pytest.mark.unit


def _metadata():
    md = sa.MetaData()
    sa.Table(
        "exps",
        md,
        sa.Column("idexp", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50)),
        sa.Column("simulator_type", sa.String(20), nullable=False, server_default="'standard'"),
        sa.Column("is_remote", sa.Boolean, nullable=False),
    )
    return md


def test_adds_missing_columns_and_is_idempotent():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE exps (idexp INTEGER PRIMARY KEY, name VARCHAR(50))"))
        conn.execute(sa.text("INSERT INTO exps (name) VALUES ('a')"))
    added = sync_missing_model_columns(engine, _metadata())
    assert sorted(c for _, c in added) == ["is_remote", "simulator_type"]
    with engine.connect() as conn:
        row = conn.execute(sa.text("SELECT name, simulator_type FROM exps")).fetchone()
    assert tuple(row) == ("a", "standard")
    assert sync_missing_model_columns(engine, _metadata()) == []


def test_skips_tables_that_do_not_exist():
    engine = sa.create_engine("sqlite://")
    assert sync_missing_model_columns(engine, _metadata()) == []
