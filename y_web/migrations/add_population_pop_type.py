"""
Database migration script to add the pop_type column to the population table.

The field stores a population-level specialization such as ``hword`` while
leaving legacy standard populations as ``NULL``.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """Add pop_type column to the SQLite dashboard population table."""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(population)")
        columns = [row[1] for row in cursor.fetchall()]

        if "pop_type" not in columns:
            cursor.execute(
                "ALTER TABLE population ADD COLUMN pop_type TEXT DEFAULT NULL"
            )
            print("✓ Added pop_type column to SQLite population table")
        else:
            print("○ pop_type column already exists in SQLite population table")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Add pop_type column to the PostgreSQL dashboard population table."""
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'population'
            """)
        columns = [row[0] for row in cursor.fetchall()]

        if "pop_type" not in columns:
            cursor.execute(
                "ALTER TABLE population ADD COLUMN pop_type VARCHAR(50) DEFAULT NULL"
            )
            print("✓ Added pop_type column to PostgreSQL population table")
        else:
            print("○ pop_type column already exists in PostgreSQL population table")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False
