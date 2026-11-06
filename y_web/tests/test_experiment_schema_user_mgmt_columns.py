"""Experiment DBs created by other runtimes (YForum) get the YWeb-only user_mgmt columns."""

import sqlite3

from y_web.src.experiment.schema import ensure_sqlite_experiment_schema


def test_activity_profile_and_archetype_added(tmp_path):
    db = tmp_path / "forum.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE user_mgmt (id VARCHAR(36) PRIMARY KEY, username TEXT, seq INTEGER)"
    )
    conn.execute(
        "CREATE TABLE rounds (id VARCHAR(36) PRIMARY KEY, day INTEGER, hour INTEGER)"
    )
    conn.commit()
    conn.close()

    assert ensure_sqlite_experiment_schema(str(db)) is True

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_mgmt)")}
    conn.close()
    assert {"activity_profile", "archetype", "cover_image"} <= cols
