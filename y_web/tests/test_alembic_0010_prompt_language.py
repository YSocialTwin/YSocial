"""Alembic 0010 (exps.prompt_language, client.prompt_language): idempotent, keeps rows, defaults to English."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "y_web" / "alembic" / "versions"


def _run(engine, filename):
    spec = importlib.util.spec_from_file_location(filename[:4], VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()


def test_columns_are_added_once_with_english_default(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:  # tables as they were before the column existed
        conn.exec_driver_sql(
            "CREATE TABLE exps (idexp INTEGER PRIMARY KEY, exp_name TEXT)"
        )
        conn.exec_driver_sql("CREATE TABLE client (id INTEGER PRIMARY KEY, name TEXT)")
        conn.exec_driver_sql("INSERT INTO exps (exp_name) VALUES ('legacy-exp')")
        conn.exec_driver_sql("INSERT INTO client (name) VALUES ('legacy-client')")
    _run(engine, "0010_add_prompt_language.py")
    _run(engine, "0010_add_prompt_language.py")  # idempotent
    for table in ("exps", "client"):
        names = [c["name"] for c in sa.inspect(engine).get_columns(table)]
        assert names.count("prompt_language") == 1
    with engine.connect() as conn:
        for table in ("exps", "client"):
            assert (
                conn.exec_driver_sql(f"SELECT prompt_language FROM {table}").scalar()
                == "en"
            )


def test_a_database_without_the_tables_is_left_alone(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    _run(engine, "0010_add_prompt_language.py")
    assert sa.inspect(engine).get_table_names() == []


def test_models_declare_the_columns():
    from y_web.src.models.admin import Client, Exps

    for model in (Exps, Client):
        column = model.__table__.c.prompt_language
        assert not column.nullable and str(column.server_default.arg) == "en"
