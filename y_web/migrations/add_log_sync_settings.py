"""
Database migration script to add log_sync_settings table for automatic log sync.

This script adds the log_sync_settings table which stores:
- enabled: Whether automatic log sync is enabled
- sync_interval_minutes: Frequency of sync in minutes (default 10)
- last_sync: Timestamp of the last sync operation

Run this script to update existing YSocial installations.
"""

import os
import sqlite3
import sys

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """
    Add log_sync_settings table to SQLite database.

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

        # Check if table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='log_sync_settings'"
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            cursor.execute(
                """
                CREATE TABLE log_sync_settings (
                    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                    enabled               INTEGER NOT NULL DEFAULT 1,
                    sync_interval_minutes INTEGER NOT NULL DEFAULT 10,
                    last_sync             TEXT
                )
            """
            )
            # Insert default settings row
            cursor.execute(
                """
                INSERT INTO log_sync_settings (enabled, sync_interval_minutes)
                VALUES (1, 10)
            """
            )
            print("✓ Created log_sync_settings table in SQLite database")
        else:
            print("○ log_sync_settings table already exists in SQLite database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add log_sync_settings table to PostgreSQL database.

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

        # Check if table already exists
        cursor.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name = 'log_sync_settings'
        """
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            cursor.execute(
                """
                CREATE TABLE log_sync_settings (
                    id                    SERIAL PRIMARY KEY,
                    enabled               BOOLEAN NOT NULL DEFAULT TRUE,
                    sync_interval_minutes INTEGER NOT NULL DEFAULT 10,
                    last_sync             TIMESTAMP
                )
            """
            )
            # Insert default settings row
            cursor.execute(
                """
                INSERT INTO log_sync_settings (enabled, sync_interval_minutes)
                VALUES (TRUE, 10)
            """
            )
            print("✓ Created log_sync_settings table in PostgreSQL database")
        else:
            print("○ log_sync_settings table already exists in PostgreSQL database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Log Sync Settings Table")
    print("=" * 60)
    print()

    # Migrate SQLite database
    print("Migrating SQLite database...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    sqlite_db_path = os.path.join(project_root, "data_schema", "database_dashboard.db")

    sqlite_success = migrate_sqlite(sqlite_db_path)
    print()

    # Migrate PostgreSQL database (if configured)
    print("Migrating PostgreSQL database...")

    # Try to read PostgreSQL configuration from environment variables
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_database = os.environ.get("POSTGRES_DB", "ysocial")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")

    if pg_password:
        postgresql_success = migrate_postgresql(
            pg_host, pg_port, pg_database, pg_user, pg_password
        )
    else:
        print("○ PostgreSQL not configured (no password found in environment)")
        print("  To migrate PostgreSQL, set the following environment variables:")
        print("  - POSTGRES_HOST (default: localhost)")
        print("  - POSTGRES_PORT (default: 5432)")
        print("  - POSTGRES_DB (default: ysocial)")
        print("  - POSTGRES_USER (default: postgres)")
        print("  - POSTGRES_PASSWORD (required)")
        postgresql_success = None

    print()
    print("=" * 60)
    print("Migration Summary:")
    print(f"  SQLite:     {'✓ Success' if sqlite_success else '✗ Failed'}")
    if postgresql_success is not None:
        print(f"  PostgreSQL: {'✓ Success' if postgresql_success else '✗ Failed'}")
    else:
        print("  PostgreSQL: ○ Skipped (not configured)")
    print("=" * 60)

    return 0 if sqlite_success else 1


if __name__ == "__main__":
    sys.exit(main())
