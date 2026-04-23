"""
Database migration script to add cover_image column to agents table.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    if not db_path or not os.path.exists(db_path):
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(agents)")
        columns = [column[1] for column in cursor.fetchall()]

        if "cover_image" not in columns:
            cursor.execute("ALTER TABLE agents ADD COLUMN cover_image VARCHAR(400) DEFAULT ''")
            conn.commit()

        conn.close()
        return True
    except sqlite3.Error:
        return False


def migrate_postgresql(host, port, database, user, password):
    if not PSYCOPG2_AVAILABLE:
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, dbname=database, user=user, password=password
        )
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'agents' AND column_name = 'cover_image'
            """
        )
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE agents ADD COLUMN cover_image VARCHAR(400) DEFAULT ''")
            conn.commit()
        conn.close()
        return True
    except Exception:
        return False
