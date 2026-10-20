"""Admin language column: migration and model (F1-3)."""

import sqlite3

from y_web.migrations.add_admin_language_column import migrate_sqlite
from y_web.src.models import Admin_users


def _columns(path):
    conn = sqlite3.connect(path)
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(admin_users)")]
    finally:
        conn.close()


def _make_db(path, with_table=True):
    conn = sqlite3.connect(path)
    if with_table:
        conn.execute("CREATE TABLE admin_users (id INTEGER PRIMARY KEY, username TEXT)")
        conn.execute("INSERT INTO admin_users (username) VALUES ('alice')")
    conn.commit()
    conn.close()


def test_migration_adds_column_and_keeps_rows(tmp_path):
    db = str(tmp_path / "d.db")
    _make_db(db)
    assert migrate_sqlite(db) is True
    assert "lang" in _columns(db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT username, lang FROM admin_users").fetchall() == [
        ("alice", None)
    ]
    conn.close()


def test_migration_is_idempotent(tmp_path):
    db = str(tmp_path / "d.db")
    _make_db(db)
    assert migrate_sqlite(db) is True
    assert migrate_sqlite(db) is True
    assert _columns(db).count("lang") == 1


def test_migration_without_table_is_noop(tmp_path):
    db = str(tmp_path / "d.db")
    _make_db(db, with_table=False)
    assert migrate_sqlite(db) is True
    assert _columns(db) == []


def test_migration_missing_file_returns_false(tmp_path):
    assert migrate_sqlite(str(tmp_path / "missing.db")) is False


def test_model_has_nullable_lang_column():
    col = Admin_users.__table__.c.lang
    assert col.nullable is True
    assert col.default is None or col.default.arg is None
