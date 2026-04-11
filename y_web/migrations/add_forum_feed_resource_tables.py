"""Add reusable forum feed resource tables to the dashboard database."""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """Create reusable forum feed resource tables in SQLite."""
    if not db_path or not os.path.exists(db_path):
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forum_rss_feed_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                feed_url VARCHAR(500) NOT NULL UNIQUE,
                url_site VARCHAR(500) NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_forum_rss_feed_resources_name ON forum_rss_feed_resources(name)"
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forum_image_feed_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subreddit VARCHAR(200) NOT NULL UNIQUE,
                interests TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_forum_image_feed_resources_subreddit ON forum_image_feed_resources(subreddit)"
        )

        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"✗ Error migrating SQLite forum feed resources: {exc}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Create reusable forum feed resource tables in PostgreSQL."""
    if not PSYCOPG2_AVAILABLE:
        return False

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forum_rss_feed_resources (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                feed_url VARCHAR(500) NOT NULL UNIQUE,
                url_site VARCHAR(500) NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_forum_rss_feed_resources_name ON forum_rss_feed_resources(name)"
        )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS forum_image_feed_resources (
                id SERIAL PRIMARY KEY,
                subreddit VARCHAR(200) NOT NULL UNIQUE,
                interests TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_forum_image_feed_resources_subreddit ON forum_image_feed_resources(subreddit)"
        )

        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"✗ Error migrating PostgreSQL forum feed resources: {exc}")
        return False
