"""
Database migration script to add cover_image to experiment user_mgmt tables.

This keeps per-user profile header images in the experiment database so the
visual customization path works for any user type, not only admin-backed ones.
"""

import os
import sqlite3

from y_web.src.content.cover_images import random_cover_image_url

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite_server(db_path, quiet=False):
    """
    Add cover_image column to user_mgmt table in a SQLite experiment database.

    Args:
        db_path: Path to experiment SQLite database
        quiet: Suppress status output when True

    Returns:
        bool: True if migration succeeded, False otherwise
    """
    if not os.path.exists(db_path):
        if not quiet:
            print(f"Server database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user_mgmt)")
        columns = [column[1] for column in cursor.fetchall()]

        if "cover_image" not in columns:
            if not quiet:
                print("Adding 'cover_image' column to user_mgmt table...")
            cursor.execute(
                "ALTER TABLE user_mgmt ADD COLUMN cover_image VARCHAR(400) DEFAULT ''"
            )
            conn.commit()
            if not quiet:
                print("✓ Successfully added 'cover_image' column to user_mgmt table")
        elif not quiet:
            print("✓ Column 'cover_image' already exists in user_mgmt table")

        cursor.execute(
            "SELECT id FROM user_mgmt WHERE cover_image IS NULL OR TRIM(cover_image) = ''"
        )
        missing_ids = [row[0] for row in cursor.fetchall()]
        for user_id in missing_ids:
            cursor.execute(
                "UPDATE user_mgmt SET cover_image = ? WHERE id = ?",
                (random_cover_image_url(), user_id),
            )
        if missing_ids:
            conn.commit()

        conn.close()
        return True
    except sqlite3.Error as exc:
        if not quiet:
            print(f"Error migrating server database: {exc}")
        return False


def migrate_experiment_databases(experiments_dir, quiet=False):
    """
    Migrate all experiment SQLite databases under the experiments directory.

    Returns:
        tuple: (success_count, total_count)
    """
    if not os.path.exists(experiments_dir):
        if not quiet:
            print(f"Experiments directory not found: {experiments_dir}")
        return (0, 0)

    success_count = 0
    total_count = 0

    for root, _dirs, files in os.walk(experiments_dir):
        for file in files:
            if file == "database_server.db":
                total_count += 1
                db_path = os.path.join(root, file)
                if not quiet:
                    print(f"Migrating experiment database: {db_path}")
                if migrate_sqlite_server(db_path, quiet=True):
                    success_count += 1

    if not quiet and total_count > 0:
        print(f"✓ Migrated {success_count}/{total_count} experiment databases")

    return (success_count, total_count)


def migrate_postgresql_server(db_config):
    """
    Add cover_image column to user_mgmt table in a PostgreSQL experiment database.
    """
    if not PSYCOPG2_AVAILABLE:
        print("psycopg2 not available, skipping PostgreSQL migration")
        return False

    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'user_mgmt' AND column_name = 'cover_image'
            """
        )

        if cursor.fetchone() is None:
            print("Adding 'cover_image' column to user_mgmt table in PostgreSQL...")
            cursor.execute(
                "ALTER TABLE user_mgmt ADD COLUMN cover_image VARCHAR(400) DEFAULT ''"
            )
            conn.commit()
            print("✓ Successfully added 'cover_image' column to user_mgmt table")
        else:
            print("✓ Column 'cover_image' already exists in user_mgmt table")

        cursor.execute(
            "SELECT id FROM user_mgmt WHERE cover_image IS NULL OR BTRIM(cover_image) = ''"
        )
        missing_ids = [row[0] for row in cursor.fetchall()]
        for user_id in missing_ids:
            cursor.execute(
                "UPDATE user_mgmt SET cover_image = %s WHERE id = %s",
                (random_cover_image_url(), user_id),
            )
        if missing_ids:
            conn.commit()

        conn.close()
        return True
    except Exception as exc:
        print(f"Error migrating PostgreSQL server database: {exc}")
        return False
