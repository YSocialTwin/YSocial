"""
Migration script to add blog_posts table to SQLite database.

This migration adds the blog_posts table for storing blog post announcements
similar to the release_info table.
"""

import os
import sqlite3
import sys


def migrate_dashboard_db():
    """Add blog_posts table to the dashboard database if it doesn't exist."""
    # Determine the database path based on execution mode
    if getattr(sys, "frozen", False):
        # Running from PyInstaller - use writable location
        from y_web.utils.path_utils import get_writable_path

        db_dir = os.path.join(get_writable_path(), "y_web", "db")
    else:
        # Running from source
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_dir = os.path.join(base_dir, "db")

    db_path = os.path.join(db_dir, "dashboard.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if blog_posts table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blog_posts'"
        )
        if cursor.fetchone():
            print("blog_posts table already exists")
            conn.close()
            return True

        # Create the blog_posts table
        cursor.execute(
            """
            CREATE TABLE blog_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                published_at TEXT,
                link TEXT,
                is_read INTEGER DEFAULT 0,
                latest_check_on TEXT
            )
        """
        )

        conn.commit()
        conn.close()
        print("Successfully created blog_posts table")
        return True

    except Exception as e:
        print(f"Error migrating database: {e}")
        return False


if __name__ == "__main__":
    migrate_dashboard_db()
