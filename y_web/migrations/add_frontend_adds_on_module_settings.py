"""
Database migration script to add frontend_adds_on_exp_module_settings table.

This table stores per-experiment, per-module configuration for the
Frontend Adds-on frontend plugin suite (see
``y_web/src/external_runtime/frontend_plugins.py`` and
``y_web/src/external_runtime/plugin_loader.py``).

This is the legacy/manual fallback runner (``run_migrations()``), applied
only when neither Flask-Migrate nor standalone Alembic is importable — see
``y_web/__init__.py``. The primary migration path for this table is the
Alembic revision ``0004_add_educatyon_exp_module_settings`` (kept under its
original historical name -- see ``y_web/alembic/versions/0004_...py`` --
since Alembic tracks already-applied databases by that exact revision
string; the table itself is renamed forward by revision
``0005_rename_educatyon_to_frontend_adds_on``).
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """Add frontend_adds_on_exp_module_settings table to the SQLite database."""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Rename-in-place for a database that already has the old
        # (pre-rename) table with real, already-collected config rows --
        # never drop/recreate, that would silently orphan existing data.
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='educatyon_exp_module_settings'"
        )
        old_table_exists = cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='frontend_adds_on_exp_module_settings'"
        )
        table_exists = cursor.fetchone() is not None
        if old_table_exists and not table_exists:
            cursor.execute(
                "ALTER TABLE educatyon_exp_module_settings RENAME TO frontend_adds_on_exp_module_settings"
            )
            conn.commit()
            print("✓ Renamed educatyon_exp_module_settings to frontend_adds_on_exp_module_settings (data preserved)")
            table_exists = True

        if not table_exists:
            cursor.execute("""
                CREATE TABLE frontend_adds_on_exp_module_settings (
                    exp_id       INTEGER NOT NULL REFERENCES exps(idexp),
                    module_id    TEXT NOT NULL,
                    enabled      INTEGER NOT NULL DEFAULT 0,
                    config_json  TEXT NOT NULL DEFAULT '{}',
                    updated_at   TEXT,
                    PRIMARY KEY (exp_id, module_id)
                )
            """)
            print("✓ Created frontend_adds_on_exp_module_settings table in SQLite database")
        else:
            print("○ frontend_adds_on_exp_module_settings table already exists in SQLite database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Add frontend_adds_on_exp_module_settings table to the PostgreSQL database."""
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        print("  Install with: pip install psycopg2-binary")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'educatyon_exp_module_settings'
        """)
        old_table_exists = cursor.fetchone() is not None
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'frontend_adds_on_exp_module_settings'
        """)
        table_exists = cursor.fetchone() is not None
        if old_table_exists and not table_exists:
            cursor.execute(
                "ALTER TABLE educatyon_exp_module_settings RENAME TO frontend_adds_on_exp_module_settings"
            )
            conn.commit()
            print("✓ Renamed educatyon_exp_module_settings to frontend_adds_on_exp_module_settings (data preserved)")
            table_exists = True

        if not table_exists:
            cursor.execute("""
                CREATE TABLE frontend_adds_on_exp_module_settings (
                    exp_id       INTEGER NOT NULL REFERENCES exps(idexp),
                    module_id    TEXT NOT NULL,
                    enabled      BOOLEAN NOT NULL DEFAULT FALSE,
                    config_json  TEXT NOT NULL DEFAULT '{}',
                    updated_at   TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (exp_id, module_id)
                )
            """)
            print("✓ Created frontend_adds_on_exp_module_settings table in PostgreSQL database")
        else:
            print("○ frontend_adds_on_exp_module_settings table already exists in PostgreSQL database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False
