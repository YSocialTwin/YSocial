"""
Database migration script to add archetype field to agents table (dashboard db)
and user_mgmt table (server db).

This script adds the 'archetype' field with NULL as default value to:
- agents table in dashboard database
- user_mgmt table in server database

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


def migrate_sqlite_dashboard(db_path):
    """
    Add archetype column to agents table in SQLite dashboard database.

    Args:
        db_path: Path to the SQLite dashboard database file

    Returns:
        bool: True if successful, False otherwise
    """
    if not os.path.exists(db_path):
        print(f"Dashboard database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists in agents table
        cursor.execute("PRAGMA table_info(agents)")
        columns = [column[1] for column in cursor.fetchall()]

        if "archetype" not in columns:
            print("Adding 'archetype' column to agents table in dashboard database...")
            cursor.execute("ALTER TABLE agents ADD COLUMN archetype TEXT DEFAULT NULL")
            conn.commit()
            print("✓ Successfully added 'archetype' column to agents table")
        else:
            print("✓ Column 'archetype' already exists in agents table")

        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"Error migrating dashboard database: {e}")
        return False


def migrate_sqlite_server(db_path, quiet=False):
    """
    Add archetype column to user_mgmt table in SQLite server database.

    Args:
        db_path: Path to the SQLite server database file
        quiet: If True, suppress output messages

    Returns:
        bool: True if successful, False otherwise
    """
    if not os.path.exists(db_path):
        if not quiet:
            print(f"Server database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists in user_mgmt table
        cursor.execute("PRAGMA table_info(user_mgmt)")
        columns = [column[1] for column in cursor.fetchall()]

        if "archetype" not in columns:
            if not quiet:
                print(
                    "Adding 'archetype' column to user_mgmt table in server database..."
                )
            cursor.execute(
                "ALTER TABLE user_mgmt ADD COLUMN archetype TEXT DEFAULT NULL"
            )
            conn.commit()
            if not quiet:
                print("✓ Successfully added 'archetype' column to user_mgmt table")
        else:
            if not quiet:
                print("✓ Column 'archetype' already exists in user_mgmt table")

        conn.close()
        return True

    except sqlite3.Error as e:
        if not quiet:
            print(f"Error migrating server database: {e}")
        return False


def migrate_experiment_databases(experiments_dir, quiet=False):
    """
    Migrate all experiment databases in the experiments directory.

    Args:
        experiments_dir: Path to the experiments directory
        quiet: If True, suppress output messages

    Returns:
        tuple: (success_count, total_count)
    """
    if not os.path.exists(experiments_dir):
        if not quiet:
            print(f"Experiments directory not found: {experiments_dir}")
        return (0, 0)

    success_count = 0
    total_count = 0

    # Find all experiment databases
    for root, dirs, files in os.walk(experiments_dir):
        for file in files:
            if file == "database_server.db":
                db_path = os.path.join(root, file)
                total_count += 1
                if not quiet:
                    print(f"Migrating experiment database: {db_path}")
                if migrate_sqlite_server(db_path, quiet=True):
                    success_count += 1

    if not quiet and total_count > 0:
        print(f"✓ Migrated {success_count}/{total_count} experiment databases")

    return (success_count, total_count)


def migrate_postgresql_dashboard(db_config):
    """
    Add archetype column to agents table in PostgreSQL dashboard database.

    Args:
        db_config: Dictionary with keys 'host', 'port', 'database', 'user', 'password'

    Returns:
        bool: True if successful, False otherwise
    """
    if not PSYCOPG2_AVAILABLE:
        print("psycopg2 not available, skipping PostgreSQL migration")
        return False

    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'agents' AND column_name = 'archetype'
        """)

        if cursor.fetchone() is None:
            print(
                "Adding 'archetype' column to agents table in PostgreSQL dashboard..."
            )
            cursor.execute("ALTER TABLE agents ADD COLUMN archetype TEXT DEFAULT NULL")
            conn.commit()
            print("✓ Successfully added 'archetype' column to agents table")
        else:
            print("✓ Column 'archetype' already exists in agents table")

        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"Error migrating PostgreSQL dashboard database: {e}")
        return False


def migrate_postgresql_server(db_config):
    """
    Add archetype column to user_mgmt table in PostgreSQL server database.

    Args:
        db_config: Dictionary with keys 'host', 'port', 'database', 'user', 'password'

    Returns:
        bool: True if successful, False otherwise
    """
    if not PSYCOPG2_AVAILABLE:
        print("psycopg2 not available, skipping PostgreSQL migration")
        return False

    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'user_mgmt' AND column_name = 'archetype'
        """)

        if cursor.fetchone() is None:
            print(
                "Adding 'archetype' column to user_mgmt table in PostgreSQL server..."
            )
            cursor.execute(
                "ALTER TABLE user_mgmt ADD COLUMN archetype TEXT DEFAULT NULL"
            )
            conn.commit()
            print("✓ Successfully added 'archetype' column to user_mgmt table")
        else:
            print("✓ Column 'archetype' already exists in user_mgmt table")

        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"Error migrating PostgreSQL server database: {e}")
        return False


def run_migration(
    dashboard_db_path=None,
    server_db_path=None,
    pg_dashboard_config=None,
    pg_server_config=None,
):
    """
    Run the migration on all specified databases.

    Args:
        dashboard_db_path: Path to SQLite dashboard database
        server_db_path: Path to SQLite server database
        pg_dashboard_config: PostgreSQL dashboard database config dict
        pg_server_config: PostgreSQL server database config dict

    Returns:
        bool: True if all migrations succeeded, False otherwise
    """
    success = True

    print("\n" + "=" * 60)
    print("Running Agent Archetype Field Migration")
    print("=" * 60 + "\n")

    # Migrate SQLite dashboard database
    if dashboard_db_path:
        print("--- SQLite Dashboard Database ---")
        if not migrate_sqlite_dashboard(dashboard_db_path):
            success = False
        print()

    # Migrate SQLite server database
    if server_db_path:
        print("--- SQLite Server Database ---")
        if not migrate_sqlite_server(server_db_path):
            success = False
        print()

    # Migrate PostgreSQL dashboard database
    if pg_dashboard_config:
        print("--- PostgreSQL Dashboard Database ---")
        if not migrate_postgresql_dashboard(pg_dashboard_config):
            success = False
        print()

    # Migrate PostgreSQL server database
    if pg_server_config:
        print("--- PostgreSQL Server Database ---")
        if not migrate_postgresql_server(pg_server_config):
            success = False
        print()

    if success:
        print("=" * 60)
        print("✓ All migrations completed successfully!")
        print("=" * 60 + "\n")
    else:
        print("=" * 60)
        print("✗ Some migrations failed")
        print("=" * 60 + "\n")

    return success


if __name__ == "__main__":
    # This script can be run standalone for manual migration
    if len(sys.argv) < 2:
        print(
            "Usage: python add_agent_archetype_field.py <dashboard_db_path> [server_db_path]"
        )
        print(
            "Example: python add_agent_archetype_field.py data_schema/database_dashboard.db data_schema/database_clean_server.db"
        )
        sys.exit(1)

    dashboard_path = sys.argv[1] if len(sys.argv) > 1 else None
    server_path = sys.argv[2] if len(sys.argv) > 2 else None

    success = run_migration(
        dashboard_db_path=dashboard_path, server_db_path=server_path
    )

    sys.exit(0 if success else 1)
