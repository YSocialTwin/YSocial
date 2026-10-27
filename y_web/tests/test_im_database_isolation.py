"""YWeb must never apply the YSocial schema to an instant messaging database (plan, DEC-04)."""

import hashlib
import sqlite3
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _make_im_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE run_info (run_id TEXT, config_hash TEXT)")
    conn.execute("INSERT INTO run_info VALUES ('r1', 'h')")
    conn.commit()
    conn.close()


def _fingerprint(path):
    conn = sqlite3.connect(path)
    try:
        schema = conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return hashlib.sha256(repr(schema).encode()).hexdigest()


def test_sqlite_schema_ensure_leaves_im_database_untouched(tmp_path):
    from y_web.src.experiment.schema import ensure_sqlite_experiment_schema

    db = str(tmp_path / "im.db")
    _make_im_db(db)
    before = _fingerprint(db)
    assert ensure_sqlite_experiment_schema(db) is False
    assert _fingerprint(db) == before
    names = {
        r[0]
        for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert names == {"run_info"}


def test_sqlite_schema_ensure_still_builds_a_ysocial_database(tmp_path):
    from y_web.src.experiment.schema import ensure_sqlite_experiment_schema

    db = str(tmp_path / "ys.db")
    assert ensure_sqlite_experiment_schema(db) is True
    names = {
        r[0]
        for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "rounds" in names and "run_info" not in names


def test_open_experiment_session_does_not_create_tables_for_im(tmp_path, monkeypatch):
    from y_web.src.experiment import helpers

    db = str(tmp_path / "im.db")
    _make_im_db(db)
    before = _fingerprint(db)
    monkeypatch.setattr(helpers, "_experiment_engine_uri", lambda exp: f"sqlite:///{db}")
    called = []
    monkeypatch.setattr(helpers, "_ensure_experiment_orm_tables", lambda e: called.append(1))
    monkeypatch.setattr(helpers, "_ensure_photo_sharing_orm_tables", lambda *a: called.append(2))
    monkeypatch.setattr(helpers, "ensure_experiment_schema_for_uri", lambda u: called.append(3))
    session, engine = helpers.open_experiment_session(
        SimpleNamespace(platform_type="instant_messaging")
    )
    session.close()
    engine.dispose()
    assert called == []
    assert _fingerprint(db) == before


def test_im_platform_helpers():
    from y_web.src.im import IM_PLATFORM, is_im_experiment

    assert IM_PLATFORM == "instant_messaging"
    assert is_im_experiment(SimpleNamespace(platform_type="instant_messaging"))
    assert not is_im_experiment(SimpleNamespace(platform_type="microblogging"))
    assert not is_im_experiment(SimpleNamespace())
