"""
Database migration script to add exp_details_tutorial_shown column to admin_users table.

This script adds:
- exp_details_tutorial_shown: Boolean column (default False)

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
    Add exp_details_tutorial_shown column to SQLite database.

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

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(admin_users)")
        columns = [row[1] for row in cursor.fetchall()]

        # Add exp_details_tutorial_shown column if it doesn't exist
        if "exp_details_tutorial_shown" not in columns:
            cursor.execute(
                "ALTER TABLE admin_users ADD COLUMN exp_details_tutorial_shown INTEGER DEFAULT 0"
            )
            print("✓ Added exp_details_tutorial_shown column to SQLite database")
        else:
            print(
                "○ exp_details_tutorial_shown column already exists in SQLite database"
            )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add exp_details_tutorial_shown column to PostgreSQL database.

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

        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'admin_users'
        """)
        columns = [row[0] for row in cursor.fetchall()]

        # Add exp_details_tutorial_shown column if it doesn't exist
        if "exp_details_tutorial_shown" not in columns:
            cursor.execute("""
                ALTER TABLE admin_users 
                ADD COLUMN exp_details_tutorial_shown BOOLEAN DEFAULT FALSE
            """)
            print("✓ Added exp_details_tutorial_shown column to PostgreSQL database")
        else:
            print(
                "○ exp_details_tutorial_shown column already exists in PostgreSQL database"
            )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Experiment Details Tutorial Column")
    print("=" * 70)
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

    # Try to read PostgreSQL configuration from environment variables (same as create_postgresql_db)
    pg_host = os.environ.get("PG_HOST", "localhost")
    pg_port = os.environ.get("PG_PORT", "5432")
    pg_database = os.environ.get("PG_DBNAME", "dashboard")
    pg_user = os.environ.get("PG_USER", "postgres")
    pg_password = os.environ.get("PG_PASSWORD", "")

    if pg_password:
        postgresql_success = migrate_postgresql(
            pg_host, pg_port, pg_database, pg_user, pg_password
        )
    else:
        print("○ PostgreSQL not configured (no password found in environment)")
        print("  To migrate PostgreSQL, set the following environment variables:")
        print("  - PG_HOST (default: localhost)")
        print("  - PG_PORT (default: 5432)")
        print("  - PG_DBNAME (default: dashboard)")
        print("  - PG_USER (default: postgres)")
        print("  - PG_PASSWORD (required)")
        postgresql_success = None

    print()
    print("=" * 70)
    print("Migration Summary:")
    print(f"  SQLite:     {'✓ Success' if sqlite_success else '✗ Failed'}")
    if postgresql_success is not None:
        print(f"  PostgreSQL: {'✓ Success' if postgresql_success else '✗ Failed'}")
    else:
        print("  PostgreSQL: ○ Skipped (not configured)")
    print("=" * 70)

    return 0 if sqlite_success else 1


if __name__ == "__main__":
    sys.exit(main())
