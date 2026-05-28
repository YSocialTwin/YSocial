"""
Database migration script to add category and enabled columns to recsys tables.

This script adds:
- category: TEXT column for categorizing recommendation systems
- enabled: TEXT column containing comma-separated list of clients (e.g., "HPC,Standard")

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
    Add category and enabled columns to recsys tables in SQLite database.

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

        # Check if columns already exist in content_recsys
        cursor.execute("PRAGMA table_info(content_recsys)")
        content_columns = [row[1] for row in cursor.fetchall()]

        # Add category column to content_recsys if it doesn't exist (check for both old 'group' name and new 'category' name)
        if "category" not in content_columns:
            # Check if old 'group' column exists and needs to be renamed
            if "group" in content_columns:
                # SQLite doesn't support column rename directly, need to recreate table
                print(
                    "○ Renaming 'group' column to 'category' in content_recsys (requires table recreation)"
                )
                # This is complex, so for now just add category column if group exists
                # In production, data would need to be copied over
                cursor.execute("ALTER TABLE content_recsys ADD COLUMN category TEXT")
                cursor.execute('UPDATE content_recsys SET category = "group"')
                print(
                    "✓ Added category column and copied data from group column in content_recsys"
                )
            else:
                cursor.execute("ALTER TABLE content_recsys ADD COLUMN category TEXT")
                print("✓ Added category column to content_recsys in SQLite database")
        else:
            print("○ category column already exists in content_recsys SQLite table")

        # Add enabled column to content_recsys if it doesn't exist
        if "enabled" not in content_columns:
            cursor.execute("ALTER TABLE content_recsys ADD COLUMN enabled TEXT")
            print("✓ Added enabled column to content_recsys in SQLite database")
            # Update existing records
            cursor.execute("UPDATE content_recsys SET enabled = 'HPC,Standard'")
            print("✓ Updated existing content_recsys records with 'HPC,Standard'")
        else:
            print("○ enabled column already exists in content_recsys SQLite table")

        # Check if columns already exist in follow_recsys
        cursor.execute("PRAGMA table_info(follow_recsys)")
        follow_columns = [row[1] for row in cursor.fetchall()]

        # Add category column to follow_recsys if it doesn't exist
        if "category" not in follow_columns:
            # Check if old 'group' column exists and needs to be renamed
            if "group" in follow_columns:
                print(
                    "○ Renaming 'group' column to 'category' in follow_recsys (requires table recreation)"
                )
                cursor.execute("ALTER TABLE follow_recsys ADD COLUMN category TEXT")
                cursor.execute('UPDATE follow_recsys SET category = "group"')
                print(
                    "✓ Added category column and copied data from group column in follow_recsys"
                )
            else:
                cursor.execute("ALTER TABLE follow_recsys ADD COLUMN category TEXT")
                print("✓ Added category column to follow_recsys in SQLite database")
        else:
            print("○ category column already exists in follow_recsys SQLite table")

        # Add enabled column to follow_recsys if it doesn't exist
        if "enabled" not in follow_columns:
            cursor.execute("ALTER TABLE follow_recsys ADD COLUMN enabled TEXT")
            print("✓ Added enabled column to follow_recsys in SQLite database")
            # Update existing records
            cursor.execute("UPDATE follow_recsys SET enabled = 'HPC,Standard'")
            print("✓ Updated existing follow_recsys records with 'HPC,Standard'")
        else:
            print("○ enabled column already exists in follow_recsys SQLite table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add category and enabled columns to recsys tables in PostgreSQL database.

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

        # Check if columns already exist in content_recsys
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'content_recsys'
        """)
        content_columns = [row[0] for row in cursor.fetchall()]

        # Add category column to content_recsys if it doesn't exist (or rename from group)
        if "category" not in content_columns:
            if "group" in content_columns:
                # Rename group to category
                cursor.execute("""
                    ALTER TABLE content_recsys 
                    RENAME COLUMN "group" TO category
                """)
                print(
                    "✓ Renamed 'group' column to 'category' in content_recsys PostgreSQL table"
                )
            else:
                cursor.execute("""
                    ALTER TABLE content_recsys 
                    ADD COLUMN category TEXT
                """)
                print(
                    "✓ Added category column to content_recsys in PostgreSQL database"
                )
        else:
            print("○ category column already exists in content_recsys PostgreSQL table")

        # Add enabled column to content_recsys if it doesn't exist
        if "enabled" not in content_columns:
            cursor.execute("""
                ALTER TABLE content_recsys 
                ADD COLUMN enabled TEXT
            """)
            print("✓ Added enabled column to content_recsys in PostgreSQL database")
            # Update existing records
            cursor.execute("UPDATE content_recsys SET enabled = 'HPC,Standard'")
            print("✓ Updated existing content_recsys records with 'HPC,Standard'")
        else:
            print("○ enabled column already exists in content_recsys PostgreSQL table")

        # Check if columns already exist in follow_recsys
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'follow_recsys'
        """)
        follow_columns = [row[0] for row in cursor.fetchall()]

        # Add category column to follow_recsys if it doesn't exist (or rename from group)
        if "category" not in follow_columns:
            if "group" in follow_columns:
                # Rename group to category
                cursor.execute("""
                    ALTER TABLE follow_recsys 
                    RENAME COLUMN "group" TO category
                """)
                print(
                    "✓ Renamed 'group' column to 'category' in follow_recsys PostgreSQL table"
                )
            else:
                cursor.execute("""
                    ALTER TABLE follow_recsys 
                    ADD COLUMN category TEXT
                """)
                print("✓ Added category column to follow_recsys in PostgreSQL database")
        else:
            print("○ category column already exists in follow_recsys PostgreSQL table")

        # Add enabled column to follow_recsys if it doesn't exist
        if "enabled" not in follow_columns:
            cursor.execute("""
                ALTER TABLE follow_recsys 
                ADD COLUMN enabled TEXT
            """)
            print("✓ Added enabled column to follow_recsys in PostgreSQL database")
            # Update existing records
            cursor.execute("UPDATE follow_recsys SET enabled = 'HPC,Standard'")
            print("✓ Updated existing follow_recsys records with 'HPC,Standard'")
        else:
            print("○ enabled column already exists in follow_recsys PostgreSQL table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Recsys Columns")
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
        print(f"  PostgreSQL: ○ Skipped (not configured)")
    print("=" * 60)

    return 0 if sqlite_success else 1


if __name__ == "__main__":
    sys.exit(main())
