"""Read-only engine and timeline of the IM read model (plan, Phase 7)."""

import hashlib
import os
import sqlite3
import sys

import pytest
import sqlalchemy

from y_web.src.im import engine, timeline
from y_web.tests.im_fixture_db import build_random_db


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "database_server.db")
    build_random_db(path)
    return path


def _digest(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_reader_is_read_only_and_leaves_the_file_untouched(db_path):
    before = _digest(db_path)
    with engine.open_reader(db_path) as session:
        models = engine.im_modules()[0]
        assert session.query(models.Message).count() == 220
        with pytest.raises(sqlalchemy.exc.OperationalError):
            session.execute(
                sqlalchemy.text(
                    "INSERT INTO rounds(id, day, slot, status) VALUES (999, 1, 1, 'open')"
                )
            )
        with pytest.raises(sqlalchemy.exc.OperationalError):
            session.execute(sqlalchemy.text("DELETE FROM messages"))
    assert _digest(db_path) == before
    assert (
        not os.path.exists(db_path + "-wal") or os.path.getsize(db_path + "-wal") == 0
    )


def test_importing_the_read_services_does_not_import_ray():
    """Checked in a fresh interpreter: other tests in the session may have imported Ray already."""
    import subprocess
    import textwrap

    code = textwrap.dedent("""
        import sys
        from y_web.src.im import engine, reader
        engine.im_modules()
        assert "ray" not in sys.modules, "ray was imported"
        """)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-600:]


def test_missing_and_foreign_databases_are_refused(tmp_path):
    with pytest.raises(engine.ImReadError):
        with engine.open_reader(str(tmp_path / "none.db")):
            pass
    foreign = tmp_path / "foreign.db"
    sqlite3.connect(foreign).executescript("CREATE TABLE post (id INTEGER)")
    with pytest.raises(engine.ImReadError, match="not an instant messaging database"):
        with engine.open_reader(str(foreign)):
            pass


def test_newer_schema_is_refused_with_a_clear_message(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (999, '2026-01-01')"
    )
    conn.commit()
    conn.close()
    with pytest.raises(engine.ImSchemaTooNew, match="newer than the installed runtime"):
        with engine.open_reader(db_path):
            pass


def test_snapshot_copy_is_consistent_cached_and_refreshed(
    db_path, tmp_path, monkeypatch
):
    monkeypatch.setattr(engine, "snapshot_dir", lambda: str(tmp_path / "snaps"))
    first = engine.snapshot_copy(db_path)
    assert first == engine.snapshot_copy(db_path)  # cached by signature
    assert (
        sqlite3.connect(first).execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        == 220
    )
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM messages WHERE id = 'm0000'")
    conn.commit()
    conn.close()
    second = engine.snapshot_copy(db_path)
    assert second != first
    assert (
        sqlite3.connect(second).execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        == 219
    )
    assert len(os.listdir(os.path.dirname(second))) == 1  # the old signature is gone


def test_reader_falls_back_to_a_snapshot_when_the_live_file_cannot_be_opened(
    db_path, tmp_path, monkeypatch
):
    monkeypatch.setattr(engine, "snapshot_dir", lambda: str(tmp_path / "snaps"))
    real = engine._open
    calls = []

    def flaky(path):
        calls.append(path)
        if len(calls) == 1:
            raise sqlalchemy.exc.OperationalError(
                "x", {}, Exception("unable to open database file")
            )
        return real(path)

    monkeypatch.setattr(engine, "_open", flaky)
    with engine.open_reader(db_path) as session:
        assert (
            session.execute(sqlalchemy.text("SELECT COUNT(*) FROM messages")).scalar()
            == 220
        )
    assert calls[0] == db_path and calls[1] != db_path


def test_timeline_round_trip_and_clamp():
    for r in (1, 24, 25, 48, 100):
        assert timeline.ordinal(*timeline.day_slot(r)) == r
    assert timeline.day_slot(25) == (2, 1)
    assert timeline.hour_of_slot(1) == 0 and timeline.slot_of_hour(23) == 24
    for bad in ((0, 1), (1, 0), (1, 25)):
        with pytest.raises(ValueError):
            timeline.ordinal(*bad)
    with pytest.raises(ValueError):
        timeline.day_slot(0)
    assert timeline.clamp_round(None, 10) == 10
    assert timeline.clamp_round("x", 10) == 10
    assert timeline.clamp_round("0", 10) == 1 and timeline.clamp_round("99", 10) == 10
    assert timeline.clamp_round("4", 10) == 4 and timeline.clamp_round("4", 0) == 0
