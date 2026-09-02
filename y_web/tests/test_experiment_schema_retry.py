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
