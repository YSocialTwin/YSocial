"""The recommender catalogue is completed in databases whose ``enabled`` values are empty."""

import shutil
import sqlite3
from pathlib import Path

from y_web.migrations.sync_recsys_catalog import migrate_sqlite

TEMPLATE = Path(__file__).resolve().parents[2] / "data_schema" / "database_dashboard.db"


def _rows(db, table):
    conn = sqlite3.connect(db)
    try:
        return {
            n: e
            for n, e in conn.execute(f"SELECT name, enabled FROM {table}").fetchall()
        }
    finally:
        conn.close()


def _stale_copy(tmp_path):
    """A database like the ones upgraded from old releases: empty `enabled`, fewer rows."""
    db = tmp_path / "dashboard.db"
    shutil.copyfile(TEMPLATE, db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE content_recsys SET enabled = NULL")
    conn.execute("UPDATE follow_recsys SET enabled = ''")
    conn.execute("DELETE FROM content_recsys WHERE id > 10")
    conn.execute("DELETE FROM follow_recsys WHERE id > 5")
    conn.execute(
        "INSERT INTO content_recsys (name, value, category, enabled) "
        "VALUES ('FilterBubble', 'Personalized Feed', 'Personalization', 'HumanOnly')"
    )
    conn.commit()
    conn.close()
    return db


def test_empty_enabled_values_and_missing_recommenders_are_restored(tmp_path):
    db = _stale_copy(tmp_path)
    assert migrate_sqlite(str(db), str(TEMPLATE)) > 0
    content = _rows(db, "content_recsys")
    follow = _rows(db, "follow_recsys")
    assert content["ReverseChrono"] == "HPC,Standard"
    assert content["CollaborativeUserUser"] == "HPC"  # HPC-only, was missing
    assert follow["Jaccard"] == "HPC,Standard"
    assert follow["RandomWalkRestart"] == "HPC"
    # the HPC and Standard client pages filter on this column
    assert [n for n, e in content.items() if e and "hpc" in e.lower()]
    assert [n for n, e in follow.items() if e and "standard" in e.lower()]


def test_existing_values_and_extra_rows_are_left_alone(tmp_path):
    db = _stale_copy(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE content_recsys SET enabled = 'Standard' WHERE name = 'Jaccard'")
    conn.execute(
        "UPDATE content_recsys SET enabled = 'Standard' WHERE name = 'ReverseChrono'"
    )
    conn.commit()
    conn.close()
    migrate_sqlite(str(db), str(TEMPLATE))
    content = _rows(db, "content_recsys")
    assert content["ReverseChrono"] == "Standard"  # chosen by the user, kept
    assert content["FilterBubble"] == "HumanOnly"  # not in the template, kept


def test_migration_is_idempotent(tmp_path):
    db = _stale_copy(tmp_path)
    migrate_sqlite(str(db), str(TEMPLATE))
    assert migrate_sqlite(str(db), str(TEMPLATE)) == 0
