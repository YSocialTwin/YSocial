"""
Database migration script to add experiment schedule tables.

This script adds:
- experiment_schedule_groups: Groups for batch experiment execution
- experiment_schedule_items: Links experiments to groups
- experiment_schedule_status: Tracks schedule execution state

Run this script to update existing YSocial installations.
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
    Add experiment schedule tables to SQLite database.

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

        # Check if tables already exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='experiment_schedule_groups'"
        )
        if cursor.fetchone() is None:
            # Create experiment_schedule_groups table
            cursor.execute(
                """
                CREATE TABLE experiment_schedule_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            print("✓ Created experiment_schedule_groups table")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='experiment_schedule_items'"
        )
        if cursor.fetchone() is None:
            # Create experiment_schedule_items table
            cursor.execute(
                """
                CREATE TABLE experiment_schedule_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    experiment_id INTEGER NOT NULL,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (group_id) REFERENCES experiment_schedule_groups(id),
                    FOREIGN KEY (experiment_id) REFERENCES exps(idexp)
                )
            """
            )
            print("✓ Created experiment_schedule_items table")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='experiment_schedule_status'"
        )
        if cursor.fetchone() is None:
            # Create experiment_schedule_status table
            cursor.execute(
                """
                CREATE TABLE experiment_schedule_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    is_running INTEGER NOT NULL DEFAULT 0,
                    current_group_id INTEGER,
                    started_at DATETIME
                )
            """
            )
            # Insert initial status row
            cursor.execute(
                "INSERT INTO experiment_schedule_status (is_running) VALUES (0)"
            )
            print("✓ Created experiment_schedule_status table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add experiment schedule tables to PostgreSQL database.

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

        # Check and create experiment_schedule_groups table
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'experiment_schedule_groups'
            )
        """
        )
        if not cursor.fetchone()[0]:
            cursor.execute(
                """
                CREATE TABLE experiment_schedule_groups (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            print("✓ Created experiment_schedule_groups table")

        # Check and create experiment_schedule_items table
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'experiment_schedule_items'
            )
        """
        )
        if not cursor.fetchone()[0]:
            cursor.execute(
                """
                CREATE TABLE experiment_schedule_items (
                    id SERIAL PRIMARY KEY,
                    group_id INTEGER NOT NULL REFERENCES experiment_schedule_groups(id),
                    experiment_id INTEGER NOT NULL REFERENCES exps(idexp),
                    order_index INTEGER NOT NULL DEFAULT 0
                )
            """
            )
            print("✓ Created experiment_schedule_items table")

        # Check and create experiment_schedule_status table
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'experiment_schedule_status'
            )
        """
        )
        if not cursor.fetchone()[0]:
            cursor.execute(
                """
                CREATE TABLE experiment_schedule_status (
                    id SERIAL PRIMARY KEY,
                    is_running INTEGER NOT NULL DEFAULT 0,
                    current_group_id INTEGER,
                    started_at TIMESTAMP
                )
            """
            )
            # Insert initial status row
            cursor.execute(
                "INSERT INTO experiment_schedule_status (is_running) VALUES (0)"
            )
            print("✓ Created experiment_schedule_status table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False
