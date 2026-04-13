"""
Add moderation-related experiment schema to legacy server databases.
"""

from __future__ import annotations

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite_server(db_path, quiet=False):
    if not os.path.exists(db_path):
        if not quiet:
            print(f"Server database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(post)")
        post_columns = [column[1] for column in cursor.fetchall()]
        if "moderated" not in post_columns:
            cursor.execute("ALTER TABLE post ADD COLUMN moderated INTEGER DEFAULT 0")
        if "is_moderation_comment" not in post_columns:
            cursor.execute(
                "ALTER TABLE post ADD COLUMN is_moderation_comment INTEGER DEFAULT 0"
            )

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sys_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                to_uid INTEGER,
                message TEXT NOT NULL,
                from_round INTEGER,
                duration INTEGER,
                FOREIGN KEY(to_uid) REFERENCES user_mgmt(id),
                FOREIGN KEY(from_round) REFERENCES rounds(id)
            )
            """)
        cursor.execute("PRAGMA table_info(sys_messages)")
        sys_message_columns = [column[1] for column in cursor.fetchall()]
        if "to_round" in sys_message_columns:
            cursor.execute("""
                CREATE TABLE sys_messages__new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    to_uid INTEGER,
                    message TEXT NOT NULL,
                    from_round INTEGER,
                    duration INTEGER,
                    FOREIGN KEY(to_uid) REFERENCES user_mgmt(id),
                    FOREIGN KEY(from_round) REFERENCES rounds(id)
                )
                """)
            cursor.execute("""
                INSERT INTO sys_messages__new (id, type, to_uid, message, from_round, duration)
                SELECT
                    id,
                    type,
                    to_uid,
                    message,
                    from_round,
                    CASE
                        WHEN from_round IS NOT NULL AND to_round IS NOT NULL AND to_round >= from_round
                            THEN to_round - from_round
                        ELSE NULL
                    END
                FROM sys_messages
                """)
            cursor.execute("DROP TABLE sys_messages")
            cursor.execute("ALTER TABLE sys_messages__new RENAME TO sys_messages")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reported (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                to_uid INTEGER,
                to_post INTEGER,
                from_uid INTEGER NOT NULL,
                tid INTEGER NOT NULL,
                FOREIGN KEY(to_uid) REFERENCES user_mgmt(id),
                FOREIGN KEY(to_post) REFERENCES post(id),
                FOREIGN KEY(from_uid) REFERENCES user_mgmt(id),
                FOREIGN KEY(tid) REFERENCES rounds(id)
            )
            """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stress_reward (
                id TEXT PRIMARY KEY,
                uid INTEGER NOT NULL,
                variable TEXT NOT NULL CHECK (variable IN ('stress', 'reward')),
                value REAL NOT NULL CHECK (value >= 0 AND value <= 1),
                type TEXT NOT NULL CHECK (type IN ('aggregate', 'variation')),
                tid INTEGER NOT NULL,
                FOREIGN KEY(uid) REFERENCES user_mgmt(id),
                FOREIGN KEY(tid) REFERENCES rounds(id)
            )
            """)
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as exc:
        if not quiet:
            print(f"Error migrating server database: {exc}")
        return False


def migrate_experiment_databases(experiments_dir, quiet=False):
    if not os.path.exists(experiments_dir):
        if not quiet:
            print(f"Experiments directory not found: {experiments_dir}")
        return (0, 0)

    success_count = 0
    total_count = 0

    for root, _, files in os.walk(experiments_dir):
        for file in files:
            if file == "database_server.db":
                total_count += 1
                if migrate_sqlite_server(os.path.join(root, file), quiet=True):
                    success_count += 1

    if not quiet and total_count > 0:
        print(f"✓ Migrated {success_count}/{total_count} experiment databases")

    return (success_count, total_count)


def migrate_postgresql_server(host, port, database, user, password):
    if not PSYCOPG2_AVAILABLE:
        print("psycopg2 not available, skipping PostgreSQL migration")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()
        cursor.execute(
            "ALTER TABLE post ADD COLUMN IF NOT EXISTS moderated INTEGER DEFAULT 0"
        )
        cursor.execute(
            "ALTER TABLE post ADD COLUMN IF NOT EXISTS is_moderation_comment INTEGER DEFAULT 0"
        )
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sys_messages (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                to_uid INTEGER REFERENCES user_mgmt(id),
                message TEXT NOT NULL,
                from_round INTEGER REFERENCES rounds(id),
                duration INTEGER
            )
            """)
        cursor.execute(
            "ALTER TABLE sys_messages ADD COLUMN IF NOT EXISTS duration INTEGER"
        )
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='sys_messages' AND column_name='to_round'
                ) THEN
                    UPDATE sys_messages
                    SET duration = CASE
                        WHEN duration IS NOT NULL THEN duration
                        WHEN from_round IS NOT NULL AND to_round IS NOT NULL AND to_round >= from_round
                            THEN to_round - from_round
                        ELSE NULL
                    END;
                    ALTER TABLE sys_messages DROP COLUMN to_round;
                END IF;
            END $$;
            """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reported (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                to_uid INTEGER REFERENCES user_mgmt(id),
                to_post INTEGER REFERENCES post(id),
                from_uid INTEGER NOT NULL REFERENCES user_mgmt(id),
                tid INTEGER NOT NULL REFERENCES rounds(id)
            )
            """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stress_reward (
                id VARCHAR(36) PRIMARY KEY,
                uid INTEGER NOT NULL REFERENCES user_mgmt(id),
                variable VARCHAR(16) NOT NULL CHECK (variable IN ('stress', 'reward')),
                value DOUBLE PRECISION NOT NULL CHECK (value >= 0 AND value <= 1),
                type VARCHAR(16) NOT NULL CHECK (type IN ('aggregate', 'variation')),
                tid INTEGER NOT NULL REFERENCES rounds(id)
            )
            """)
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"Error migrating PostgreSQL server database: {exc}")
        return False
