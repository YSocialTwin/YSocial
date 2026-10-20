"""
Database migration: add the ``lang`` column to the admin_users table.

``lang`` stores the dashboard language chosen by each admin user (NULL means
"automatic": cookie, then the browser language, then English). The migration
is idempotent and can be run on SQLite and PostgreSQL.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """Add admin_users.lang to a SQLite database; return True on success."""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(admin_users)")
        columns = [row[1] for row in cursor.fetchall()]
        if not columns:
            conn.close()
            return True  # table not created yet: create_all adds the column
        if "lang" not in columns:
            cursor.execute("ALTER TABLE admin_users ADD COLUMN lang VARCHAR(10)")
            print("✓ Added lang column to SQLite database")
        else:
            print("○ lang column already exists in SQLite database")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Add admin_users.lang to a PostgreSQL database; return True on success."""
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'admin_users'"
        )
        columns = [row[0] for row in cursor.fetchall()]
        if not columns:
            conn.close()
            return True
        if "lang" not in columns:
            cursor.execute("ALTER TABLE admin_users ADD COLUMN lang VARCHAR(10)")
            print("✓ Added lang column to PostgreSQL database")
        else:
            print("○ lang column already exists in PostgreSQL database")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False
