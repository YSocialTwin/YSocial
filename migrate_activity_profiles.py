#!/usr/bin/env python3
"""
Migration script to add the id column to the activity_profiles table.

This script updates existing SQLite and PostgreSQL databases to add the missing
id column to the activity_profiles table. Run this if you get an error:
"no such column: activity_profiles.id"

Usage:
    python migrate_activity_profiles.py [--db-type sqlite|postgresql]
"""

import argparse
import os
import sys


def migrate_sqlite():
    """Migrate SQLite database to add id column to activity_profiles table."""
    import sqlite3

    db_path = os.path.join(os.path.dirname(__file__), "y_web", "db", "dashboard.db")

    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        print("The database will be created automatically when you start the app.")
        return True

    print(f"Migrating SQLite database at {db_path}...")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_profiles'"
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            print("Table 'activity_profiles' does not exist yet. Creating it...")
            cursor.execute(
                """
                CREATE TABLE activity_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(120) NOT NULL UNIQUE,
                    hours VARCHAR(100) NOT NULL
                )
                """
            )
            conn.commit()
            print("✓ Table 'activity_profiles' created successfully")
            return True

        # Check if id column exists
        cursor.execute("PRAGMA table_info(activity_profiles)")
        columns = [col[1] for col in cursor.fetchall()]

        if "id" in columns:
            print("✓ Column 'id' already exists in activity_profiles table")
            return True

        print("Column 'id' is missing. Recreating table...")

        # Backup existing data
        cursor.execute("SELECT name, hours FROM activity_profiles")
        existing_data = cursor.fetchall()

        # Drop old table and create new one
        cursor.execute("DROP TABLE activity_profiles")
        cursor.execute(
            """
            CREATE TABLE activity_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(120) NOT NULL UNIQUE,
                hours VARCHAR(100) NOT NULL
            )
            """
        )

        # Restore data
        if existing_data:
            cursor.executemany(
                "INSERT INTO activity_profiles (name, hours) VALUES (?, ?)",
                existing_data,
            )
            print(f"✓ Restored {len(existing_data)} existing activity profiles")

        conn.commit()
        conn.close()
        print("✓ Migration completed successfully")
        return True

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return False


def migrate_postgresql():
    """Migrate PostgreSQL database to add id column to activity_profiles table."""
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("✗ sqlalchemy is required for PostgreSQL migration")
        return False

    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "password")
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    dbname = os.getenv("PG_DBNAME", "dashboard")

    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    print(f"Connecting to PostgreSQL at {host}:{port}/{dbname}...")

    try:
        engine = create_engine(connection_string)
        with engine.connect() as conn:
            # Check if table exists
            result = conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'activity_profiles'
                    )
                    """
                )
            )
            table_exists = result.scalar()

            if not table_exists:
                print("Table 'activity_profiles' does not exist yet. Creating it...")
                conn.execute(
                    text(
                        """
                        CREATE TABLE activity_profiles (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(120) NOT NULL UNIQUE,
                            hours VARCHAR(100) NOT NULL
                        )
                        """
                    )
                )
                conn.commit()
                print("✓ Table 'activity_profiles' created successfully")
                return True

            # Check if id column exists
            result = conn.execute(
                text(
                    """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'activity_profiles' AND column_name = 'id'
                    """
                )
            )
            id_exists = result.scalar() is not None

            if id_exists:
                print("✓ Column 'id' already exists in activity_profiles table")
                return True

            print("Column 'id' is missing. Adding it...")

            # For PostgreSQL, we need to handle this differently
            # First, backup data
            result = conn.execute(text("SELECT name, hours FROM activity_profiles"))
            existing_data = result.fetchall()

            # Drop and recreate table
            conn.execute(text("DROP TABLE activity_profiles"))
            conn.execute(
                text(
                    """
                    CREATE TABLE activity_profiles (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(120) NOT NULL UNIQUE,
                        hours VARCHAR(100) NOT NULL
                    )
                    """
                )
            )

            # Restore data
            if existing_data:
                for name, hours in existing_data:
                    conn.execute(
                        text(
                            "INSERT INTO activity_profiles (name, hours) VALUES (:name, :hours)"
                        ),
                        {"name": name, "hours": hours},
                    )
                print(f"✓ Restored {len(existing_data)} existing activity profiles")

            conn.commit()
            print("✓ Migration completed successfully")
            return True

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return False


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description="Migrate activity_profiles table to add id column"
    )
    parser.add_argument(
        "--db-type",
        choices=["sqlite", "postgresql"],
        default="sqlite",
        help="Database type (default: sqlite)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Activity Profiles Table Migration")
    print("=" * 60)

    if args.db_type == "sqlite":
        success = migrate_sqlite()
    else:
        success = migrate_postgresql()

    if success:
        print("\n✓ Migration completed successfully!")
        print("You can now start the YSocial application.")
        sys.exit(0)
    else:
        print("\n✗ Migration failed. Please check the error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
