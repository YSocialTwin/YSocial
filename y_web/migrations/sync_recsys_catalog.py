"""
Database migration: complete the recommender catalogue (content_recsys / follow_recsys).

The client creation pages list the recommenders whose ``enabled`` column names the simulator
in use (``HPC``, ``Standard``). Databases created by older releases, or upgraded through a
path that added the column without filling it, have NULL/empty ``enabled`` values and miss
the HPC-only recommenders: the selectors then come out empty or incomplete.

This migration reads the shipped template (``data_schema/database_dashboard.db``) and, by
name:

* inserts the recommenders that are missing;
* fills ``enabled`` (and ``category``) only where they are NULL or empty.

A value that is already set is never overwritten, and rows that are not in the template
(for example ``FilterBubble``) are left alone. It is idempotent.
"""

import os
import sqlite3

_TABLES = ("content_recsys", "follow_recsys")


def _template_path():
    from y_web.src.system.path_utils import get_resource_path

    return get_resource_path(os.path.join("data_schema", "database_dashboard.db"))


def _read_template(template_path, table):
    conn = sqlite3.connect(f"file:{template_path}?mode=ro", uri=True)
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        if not {"name", "value", "category", "enabled"} <= set(cols):
            return []
        return conn.execute(
            f"SELECT name, value, category, enabled FROM {table} ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def migrate_sqlite(db_path, template_path=None):
    """Return the number of rows inserted or completed (0 when nothing was needed)."""
    template_path = template_path or _template_path()
    if not template_path or not os.path.exists(template_path):
        return 0
    if os.path.abspath(template_path) == os.path.abspath(db_path):
        return 0
    changed = 0
    conn = sqlite3.connect(db_path)
    try:
        for table in _TABLES:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if not cols:
                continue
            for column in ("category", "enabled"):
                if column not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
            for name, value, category, enabled in _read_template(template_path, table):
                row = conn.execute(
                    f"SELECT id, category, enabled FROM {table} WHERE name = ?",
                    (name,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        f"INSERT INTO {table} (name, value, category, enabled) "
                        "VALUES (?, ?, ?, ?)",
                        (name, value, category, enabled),
                    )
                    changed += 1
                    continue
                row_id, cur_category, cur_enabled = row
                updates, params = [], []
                if not (cur_enabled or "").strip() and enabled:
                    updates.append("enabled = ?")
                    params.append(enabled)
                if not (cur_category or "").strip() and category:
                    updates.append("category = ?")
                    params.append(category)
                if updates:
                    conn.execute(
                        f"UPDATE {table} SET {', '.join(updates)} WHERE id = ?",
                        (*params, row_id),
                    )
                    changed += 1
        conn.commit()
    finally:
        conn.close()
    if changed:
        print(f"✓ Recommender catalogue completed ({changed} rows)")
    return changed
