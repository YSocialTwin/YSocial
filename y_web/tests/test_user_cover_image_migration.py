import sqlite3

from y_web.migrations.add_user_cover_image_field import migrate_sqlite_server
from y_web.src.experiment.schema import ensure_sqlite_experiment_schema


def test_migrate_sqlite_server_adds_cover_image_column(tmp_path):
    db_path = tmp_path / "experiment.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE user_mgmt (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        )
        """
    )
    cursor.execute("INSERT INTO user_mgmt (id, username) VALUES (1, 'alice')")
    conn.commit()
    conn.close()

    assert migrate_sqlite_server(str(db_path), quiet=True) is True

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user_mgmt)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "cover_image" in columns
    cursor.execute("SELECT cover_image FROM user_mgmt WHERE id = 1")
    assert cursor.fetchone()[0].startswith("/static/assets/img/demo/bg/")
    conn.close()


def test_ensure_sqlite_experiment_schema_adds_cover_image_column(tmp_path):
    db_path = tmp_path / "experiment_schema.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE user_mgmt (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL
        )
        """
    )
    cursor.execute("INSERT INTO user_mgmt (id, username) VALUES (1, 'alice')")
    conn.commit()
    conn.close()

    ensure_sqlite_experiment_schema(str(db_path))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user_mgmt)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "cover_image" in columns
    cursor.execute("SELECT cover_image FROM user_mgmt WHERE id = 1")
    assert cursor.fetchone()[0] == ""
    conn.close()
