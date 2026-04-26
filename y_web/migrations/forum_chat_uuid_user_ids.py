"""
Migrate forum/private chat session user ids to TEXT.

HPC experiments use UUID-backed user ids. Existing SQLite experiment databases
may already contain the chat tables with INTEGER user id columns, which accepts
some text values but is misleading and brittle across DB backends.
"""

import os
import sqlite3


def migrate_sqlite_server(db_path, quiet=False):
    if not os.path.exists(db_path):
        if not quiet:
            print(f"Server database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='forum_chat_sessions'"
        )
        if cursor.fetchone() is None:
            conn.close()
            return True

        cursor.execute("PRAGMA table_info(forum_chat_sessions)")
        columns = {row[1]: str(row[2] or "").upper() for row in cursor.fetchall()}
        if columns.get("owner_user_id") == "TEXT" and columns.get("target_user_id") == "TEXT":
            conn.close()
            return True

        if not quiet:
            print("Migrating forum_chat_sessions user id columns to TEXT...")

        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("ALTER TABLE forum_chat_sessions RENAME TO forum_chat_sessions_old")
        cursor.execute(
            """
            CREATE TABLE forum_chat_sessions (
                id INTEGER PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES user_mgmt(id),
                owner_username TEXT NOT NULL,
                target_user_id TEXT NOT NULL REFERENCES user_mgmt(id),
                target_username TEXT NOT NULL,
                target_profile_pic TEXT,
                run_id TEXT,
                llm_model TEXT,
                llm_base_url TEXT,
                persona_snapshot TEXT,
                memory_snapshot_json TEXT,
                last_message_preview TEXT,
                last_message_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO forum_chat_sessions (
                id, owner_user_id, owner_username, target_user_id, target_username,
                target_profile_pic, run_id, llm_model, llm_base_url, persona_snapshot,
                memory_snapshot_json, last_message_preview, last_message_at,
                created_at, updated_at
            )
            SELECT
                id, CAST(owner_user_id AS TEXT), owner_username,
                CAST(target_user_id AS TEXT), target_username,
                target_profile_pic, run_id, llm_model, llm_base_url, persona_snapshot,
                memory_snapshot_json, last_message_preview, last_message_at,
                created_at, updated_at
            FROM forum_chat_sessions_old
            """
        )
        cursor.execute("DROP TABLE forum_chat_sessions_old")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_forum_chat_sessions_owner_user_id "
            "ON forum_chat_sessions(owner_user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_forum_chat_sessions_target_user_id "
            "ON forum_chat_sessions(target_user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_forum_chat_sessions_owner_username "
            "ON forum_chat_sessions(owner_username)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_forum_chat_sessions_target_username "
            "ON forum_chat_sessions(target_username)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_forum_chat_sessions_run_id "
            "ON forum_chat_sessions(run_id)"
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as exc:
        if not quiet:
            print(f"Error migrating forum chat session user ids: {exc}")
        return False


def migrate_experiment_databases(experiments_dir, quiet=False):
    if not os.path.exists(experiments_dir):
        if not quiet:
            print(f"Experiments directory not found: {experiments_dir}")
        return (0, 0)

    success_count = 0
    total_count = 0
    for root, _dirs, files in os.walk(experiments_dir):
        for file in files:
            if file != "database_server.db":
                continue
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
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not available, skipping PostgreSQL migration")
        return False

    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'forum_chat_sessions'
            )
            """
        )
        if not cursor.fetchone()[0]:
            cursor.close()
            conn.close()
            return True

        cursor.execute(
            """
            ALTER TABLE forum_chat_sessions
            ALTER COLUMN owner_user_id TYPE TEXT USING owner_user_id::text,
            ALTER COLUMN target_user_id TYPE TEXT USING target_user_id::text
            """
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as exc:
        print(f"Error migrating forum chat session user ids in PostgreSQL: {exc}")
        return False
