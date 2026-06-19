"""
Database migration script to add terminal_state to client_execution table.

This column distinguishes:
- running: the client is active or resumable
- paused: the client was paused intentionally
- manual_stop: the client was stopped manually
- completed: the client reached natural completion
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
    """Add terminal_state column to SQLite databases."""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(client_execution)")
        columns = [row[1] for row in cursor.fetchall()]

        if "terminal_state" not in columns:
            cursor.execute(
                "ALTER TABLE client_execution ADD COLUMN terminal_state TEXT DEFAULT 'running'"
            )
            print("✓ Added terminal_state column to SQLite client_execution table")
            cursor.execute(
                "UPDATE client_execution SET terminal_state = 'running' "
                "WHERE terminal_state IS NULL OR terminal_state = ''"
            )
            print("✓ Normalized existing client_execution terminal_state values")
        else:
            print(
                "○ terminal_state column already exists in SQLite client_execution table"
            )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite client_execution table: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Add terminal_state column to PostgreSQL databases."""
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
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'client_execution'
        """)
        columns = [row[0] for row in cursor.fetchall()]

        if "terminal_state" not in columns:
            cursor.execute("""
                ALTER TABLE client_execution
                ADD COLUMN terminal_state VARCHAR(20) DEFAULT 'running'
            """)
            print("✓ Added terminal_state column to PostgreSQL client_execution table")
            cursor.execute(
                "UPDATE client_execution SET terminal_state = 'running' "
                "WHERE terminal_state IS NULL OR terminal_state = ''"
            )
            print("✓ Normalized existing client_execution terminal_state values")
        else:
            print(
                "○ terminal_state column already exists in PostgreSQL client_execution table"
            )

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating PostgreSQL client_execution table: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Client Execution Terminal State")
    print("=" * 60)
    print()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    sqlite_db_path = os.path.join(project_root, "data_schema", "database_dashboard.db")

    sqlite_success = migrate_sqlite(sqlite_db_path)
    print()

    print("Migrating PostgreSQL database...")
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
