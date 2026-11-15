"""Alembic 0011: the forum-only content recommenders are added once and only for forums."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "y_web" / "alembic" / "versions"
FORUM_ONLY = {"HotRanking", "TopRanking", "MostCommented"}


def _run(engine, filename):
    spec = importlib.util.spec_from_file_location("m0011", VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()


def test_rows_are_added_once_and_marked_forum(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE content_recsys (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "value TEXT NOT NULL, category TEXT, enabled TEXT)"
        )
        conn.exec_driver_sql(
            "INSERT INTO content_recsys (name, value, category, enabled) "
            "VALUES ('ReverseChrono', '(RC) Reverse Chrono', 'Global', 'HPC,Standard')"
        )
    _run(engine, "0011_add_forum_recsys_rows.py")
    _run(engine, "0011_add_forum_recsys_rows.py")  # idempotent
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT name, enabled FROM content_recsys WHERE name IN "
            "('HotRanking', 'TopRanking', 'MostCommented')"
        ).fetchall()
    assert {r[0] for r in rows} == FORUM_ONLY and len(rows) == 3
    assert {r[1] for r in rows} == {"Forum"}


def test_a_database_without_the_table_is_left_alone(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    _run(engine, "0011_add_forum_recsys_rows.py")
    assert sa.inspect(engine).get_table_names() == []


def test_the_forum_declares_its_rows_hidden_from_other_catalogues():
    import pytest

    from y_web.platforms import registry

    providers = [p for p in registry.all_providers() if p.key == "forum"]
    if not providers:
        pytest.skip("needs a forum repository")
    for provider in providers:
        rows = {r["name"]: r["enabled"] for r in provider.recsys_catalog}
        for name in FORUM_ONLY:
            assert rows[name] == "Forum"
            # the other catalogues filter with a substring test on "standard" / "hpc"
            assert (
                "standard" not in rows[name].lower() and "hpc" not in rows[name].lower()
            )
