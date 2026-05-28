"""
Database migration script to add download_notifications table.

Stores async archive generation notifications and downloadable resource metadata
for admin users.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """Add download_notifications table to SQLite dashboard database."""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='download_notifications'"
        )
        if cursor.fetchone():
            print("○ download_notifications table already exists in SQLite database")
            conn.close()
            return True

        cursor.execute("""
            CREATE TABLE download_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                message VARCHAR(500) NOT NULL DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'processing',
                resource_path VARCHAR(500),
                resource_name VARCHAR(255),
                error_message VARCHAR(500),
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES admin_users(id)
            )
            """)
        cursor.execute(
            "CREATE INDEX idx_download_notifications_user_created ON download_notifications(user_id, created_at)"
        )

        conn.commit()
        conn.close()
        print("✓ Created download_notifications table in SQLite database")
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Add download_notifications table to PostgreSQL dashboard database."""
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'download_notifications'
            """)
        if cursor.fetchone():
            print(
                "○ download_notifications table already exists in PostgreSQL database"
            )
            conn.close()
            return True

        cursor.execute("""
            CREATE TABLE download_notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES admin_users(id),
                title VARCHAR(200) NOT NULL,
                message VARCHAR(500) NOT NULL DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'processing',
                resource_path VARCHAR(500),
                resource_name VARCHAR(255),
                error_message VARCHAR(500),
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        cursor.execute(
            "CREATE INDEX idx_download_notifications_user_created ON download_notifications(user_id, created_at)"
        )

        conn.commit()
        conn.close()
        print("✓ Created download_notifications table in PostgreSQL database")
        return True
    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False
