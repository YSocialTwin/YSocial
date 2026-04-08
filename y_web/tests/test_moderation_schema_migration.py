import sqlite3

from y_web.migrations.add_moderation_schema import migrate_sqlite_server


def test_migrate_sqlite_server_adds_moderation_schema(tmp_path):
    db_path = tmp_path / "experiment.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE user_mgmt (id INTEGER PRIMARY KEY, username TEXT NOT NULL)"
    )
    cursor.execute(
        "CREATE TABLE rounds (id INTEGER PRIMARY KEY, day INTEGER, hour INTEGER)"
    )
    cursor.execute("""
        CREATE TABLE post (
            id INTEGER PRIMARY KEY,
            tweet TEXT NOT NULL,
            round INTEGER NOT NULL,
            user_id INTEGER NOT NULL
        )
        """)
    conn.commit()
    conn.close()

    assert migrate_sqlite_server(str(db_path), quiet=True) is True

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(post)")
    post_columns = {row[1] for row in cursor.fetchall()}
    assert "moderated" in post_columns
    assert "is_moderation_comment" in post_columns

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "sys_messages" in tables
    assert "reported" in tables
    cursor.execute("PRAGMA table_info(sys_messages)")
    sys_message_columns = {row[1] for row in cursor.fetchall()}
    assert "duration" in sys_message_columns
    assert "to_round" not in sys_message_columns
    conn.close()
