"""World Simulation models and their additive, idempotent migration (F5.1)."""

import sqlalchemy as sa

from y_web.src.models import admin as admin_models
from y_web.src.system.startup_migrations import (
    FEDERATION_TABLES,
    ensure_federation_tables,
)

NAMES = {
    "federation",
    "federation_member",
    "federation_identity_link",
    "federation_schedule_queue",
}


def _engine(tmp_path, name="admin.db"):
    return sa.create_engine(f"sqlite:///{tmp_path / name}")


def test_models_are_bound_to_the_admin_database():
    for name in FEDERATION_TABLES:
        assert getattr(admin_models, name).__bind_key__ == "db_admin"
    assert {getattr(admin_models, n).__tablename__ for n in FEDERATION_TABLES} == NAMES


def test_migration_creates_the_tables_once(tmp_path):
    engine = _engine(tmp_path)
    assert set(ensure_federation_tables(engine)) == NAMES
    assert ensure_federation_tables(engine) == []  # second run: nothing to do, no error
    assert NAMES <= set(sa.inspect(engine).get_table_names())


def test_migration_leaves_existing_tables_and_rows_untouched(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE exps (idexp INTEGER PRIMARY KEY, exp_name TEXT)"
        )
        conn.exec_driver_sql("INSERT INTO exps (exp_name) VALUES ('legacy')")
    before = [c["name"] for c in sa.inspect(engine).get_columns("exps")]
    ensure_federation_tables(engine)
    assert [c["name"] for c in sa.inspect(engine).get_columns("exps")] == before
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT exp_name FROM exps").scalar() == "legacy"


def test_exps_model_is_unchanged():
    columns = {c.name for c in admin_models.Exps.__table__.columns}
    assert not any("federation" in c for c in columns)


def test_uniqueness_constraints(tmp_path):
    engine = _engine(tmp_path)
    ensure_federation_tables(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO federation (federation_id, name, seed, granularity, status, host, token, folder, config_json, description, owner, created_at)"
            " VALUES ('f1', 'w', 1, 'slot', 'stopped', '127.0.0.1', 't', '', '{}', '', '', CURRENT_TIMESTAMP)"
        )
        conn.exec_driver_sql(
            "INSERT INTO federation_member (federation_pk, exp_id, member, platform_type, position) VALUES (1, 10, 'a', 'microblogging', 0)"
        )
    for member, exp in (
        ("a", 11),
        ("b", 10),
    ):  # duplicate member name, duplicate experiment
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO federation_member (federation_pk, exp_id, member, platform_type, position)"
                    f" VALUES (1, {exp}, '{member}', 'forum', 1)"
                )
        except sa.exc.IntegrityError:
            continue
        raise AssertionError("duplicate member accepted")
