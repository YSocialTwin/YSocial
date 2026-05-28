"""
Database migration script to add agent archetype fields to client table.

This script adds fields to store:
- Agent archetype percentages (Validator, Broadcaster, Explorer)
- Transition probabilities between archetypes (9 values for 3x3 matrix)

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
    Add agent archetype columns to client table in SQLite database.

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
        cursor.execute("PRAGMA table_info(client)")
        columns = [column[1] for column in cursor.fetchall()]

        columns_to_add = []
        if "archetype_validator" not in columns:
            columns_to_add.append(("archetype_validator", "REAL DEFAULT 0.52"))
        if "archetype_broadcaster" not in columns:
            columns_to_add.append(("archetype_broadcaster", "REAL DEFAULT 0.20"))
        if "archetype_explorer" not in columns:
            columns_to_add.append(("archetype_explorer", "REAL DEFAULT 0.28"))

        # Transition probabilities (3x3 matrix)
        # From Validator
        if "trans_val_val" not in columns:
            columns_to_add.append(("trans_val_val", "REAL DEFAULT 0.853"))
        if "trans_val_broad" not in columns:
            columns_to_add.append(("trans_val_broad", "REAL DEFAULT 0.081"))
        if "trans_val_expl" not in columns:
            columns_to_add.append(("trans_val_expl", "REAL DEFAULT 0.066"))

        # From Broadcaster
        if "trans_broad_broad" not in columns:
            columns_to_add.append(("trans_broad_broad", "REAL DEFAULT 0.729"))
        if "trans_broad_val" not in columns:
            columns_to_add.append(("trans_broad_val", "REAL DEFAULT 0.195"))
        if "trans_broad_expl" not in columns:
            columns_to_add.append(("trans_broad_expl", "REAL DEFAULT 0.075"))

        # From Explorer
        if "trans_expl_expl" not in columns:
            columns_to_add.append(("trans_expl_expl", "REAL DEFAULT 0.490"))
        if "trans_expl_val" not in columns:
            columns_to_add.append(("trans_expl_val", "REAL DEFAULT 0.364"))
        if "trans_expl_broad" not in columns:
            columns_to_add.append(("trans_expl_broad", "REAL DEFAULT 0.146"))

        if columns_to_add:
            for column_name, column_type in columns_to_add:
                cursor.execute(
                    f"ALTER TABLE client ADD COLUMN {column_name} {column_type}"
                )
                print(f"✓ Added column '{column_name}' to client table")
        else:
            print("○ All agent archetype columns already exist in client table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add agent archetype columns to client table in PostgreSQL database.

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
            WHERE table_schema = 'public' 
              AND table_name = 'client'
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]

        columns_to_add = []
        if "archetype_validator" not in existing_columns:
            columns_to_add.append(("archetype_validator", "REAL DEFAULT 0.52"))
        if "archetype_broadcaster" not in existing_columns:
            columns_to_add.append(("archetype_broadcaster", "REAL DEFAULT 0.20"))
        if "archetype_explorer" not in existing_columns:
            columns_to_add.append(("archetype_explorer", "REAL DEFAULT 0.28"))

        # Transition probabilities (3x3 matrix)
        # From Validator
        if "trans_val_val" not in existing_columns:
            columns_to_add.append(("trans_val_val", "REAL DEFAULT 0.853"))
        if "trans_val_broad" not in existing_columns:
            columns_to_add.append(("trans_val_broad", "REAL DEFAULT 0.081"))
        if "trans_val_expl" not in existing_columns:
            columns_to_add.append(("trans_val_expl", "REAL DEFAULT 0.066"))

        # From Broadcaster
        if "trans_broad_broad" not in existing_columns:
            columns_to_add.append(("trans_broad_broad", "REAL DEFAULT 0.729"))
        if "trans_broad_val" not in existing_columns:
            columns_to_add.append(("trans_broad_val", "REAL DEFAULT 0.195"))
        if "trans_broad_expl" not in existing_columns:
            columns_to_add.append(("trans_broad_expl", "REAL DEFAULT 0.075"))

        # From Explorer
        if "trans_expl_expl" not in existing_columns:
            columns_to_add.append(("trans_expl_expl", "REAL DEFAULT 0.490"))
        if "trans_expl_val" not in existing_columns:
            columns_to_add.append(("trans_expl_val", "REAL DEFAULT 0.364"))
        if "trans_expl_broad" not in existing_columns:
            columns_to_add.append(("trans_expl_broad", "REAL DEFAULT 0.146"))

        if columns_to_add:
            for column_name, column_type in columns_to_add:
                cursor.execute(
                    f"ALTER TABLE client ADD COLUMN {column_name} {column_type}"
                )
                print(f"✓ Added column '{column_name}' to client table")
        else:
            print("○ All agent archetype columns already exist in client table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Agent Archetype Fields")
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
