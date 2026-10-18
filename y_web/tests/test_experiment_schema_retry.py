import sqlite3

import pytest

pytestmark = pytest.mark.unit


def test_sqlite_schema_retry_is_not_cached_on_locked_failure(monkeypatch):
    from y_web.src.experiment import schema

    schema._ENSURED_SCHEMAS.clear()

    calls = []

    def fake_ensure_sqlite(db_path):
        calls.append(db_path)
        return len(calls) > 1

    monkeypatch.setattr(schema, "ensure_sqlite_experiment_schema", fake_ensure_sqlite)
    monkeypatch.setattr(schema, "_post_table_exists", lambda uri: True)

    uri = "sqlite:///tmp/retry_schema.db"

    assert schema.ensure_experiment_schema_for_uri(uri) is False
    assert schema.ensure_experiment_schema_for_uri(uri) is True
    assert calls == ["tmp/retry_schema.db", "tmp/retry_schema.db"]
    assert uri in schema._ENSURED_SCHEMAS


def test_sqlite_locked_operation_returns_false(monkeypatch, tmp_path):
    from y_web.src.experiment import schema

    db_path = tmp_path / "schema.db"

    def fake_connect(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(schema.sqlite3, "connect", fake_connect)

    assert schema.ensure_sqlite_experiment_schema(str(db_path)) is False


def test_schema_is_not_cached_before_the_post_table_exists(tmp_path):
    """An HPC server creates its tables after the web app first sees the empty file; the columns must still
    be added once they exist (regression: ``no such column: post.image_post_id`` on a new HPC experiment)."""
    from y_web.src.experiment import schema

    schema._ENSURED_SCHEMAS.clear()
    db_path = tmp_path / "database_server.db"
    uri = f"sqlite:///{db_path}"

    assert schema.ensure_experiment_schema_for_uri(uri) is True  # empty file: nothing to extend yet
    assert uri not in schema._ENSURED_SCHEMAS

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE post (id INTEGER PRIMARY KEY, tweet TEXT, round INTEGER, user_id TEXT)")
    conn.commit()
    conn.close()

    assert schema.ensure_experiment_schema_for_uri(uri) is True
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(post)")}
    conn.close()
    assert {"image_post_id", "dedupe_key", "client_action_id", "created_at"} <= columns
    assert uri in schema._ENSURED_SCHEMAS
