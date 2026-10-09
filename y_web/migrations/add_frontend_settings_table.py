"""
Database migration script to add exp_frontend_settings table.

This table stores per-experiment frontend UI settings (interactions,
annotations, notification menu visibility) for microblogging experiments.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """
    Add exp_frontend_settings table to the SQLite database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        bool: True if successful, False otherwise
    """
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='exp_frontend_settings'"
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            cursor.execute("""
                CREATE TABLE exp_frontend_settings (
                    exp_id       INTEGER PRIMARY KEY REFERENCES exps(idexp),
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    updated_at   TEXT
                )
            """)
            print("✓ Created exp_frontend_settings table in SQLite database")
        else:
            print("○ exp_frontend_settings table already exists in SQLite database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add exp_frontend_settings table to the PostgreSQL database.

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        bool: True if successful, False otherwise
    """
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
              AND table_name = 'exp_frontend_settings'
        """)
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            cursor.execute("""
                CREATE TABLE exp_frontend_settings (
                    exp_id        INTEGER PRIMARY KEY REFERENCES exps(idexp),
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    updated_at    TIMESTAMP DEFAULT NOW()
                )
            """)
            print("✓ Created exp_frontend_settings table in PostgreSQL database")
        else:
            print("○ exp_frontend_settings table already exists in PostgreSQL database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False
