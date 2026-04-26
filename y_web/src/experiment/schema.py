import os
import sqlite3

from sqlalchemy import create_engine, text

_SQLITE_TABLES = {
    "image_posts": """
        CREATE TABLE IF NOT EXISTS image_posts (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL,
            source_url TEXT,
            title TEXT,
            subreddit TEXT,
            description TEXT,
            fetched_on TEXT,
            used INTEGER DEFAULT 0,
            local_path TEXT,
            high_res_url TEXT
        )
    """,
    "reply_inbox_state": """
        CREATE TABLE IF NOT EXISTS reply_inbox_state (
            user_id INTEGER PRIMARY KEY REFERENCES user_mgmt(id),
            last_seen_reply_id INTEGER NOT NULL DEFAULT 0
        )
    """,
    "forum_chat_sessions": """
        CREATE TABLE IF NOT EXISTS forum_chat_sessions (
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "forum_chat_messages": """
        CREATE TABLE IF NOT EXISTS forum_chat_messages (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL REFERENCES forum_chat_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            meta_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "stress_reward": """
        CREATE TABLE IF NOT EXISTS stress_reward (
            id TEXT PRIMARY KEY,
            uid INTEGER NOT NULL REFERENCES user_mgmt(id),
            variable TEXT NOT NULL CHECK (variable IN ('stress', 'reward')),
            value REAL NOT NULL CHECK (
                (type = 'aggregate' AND value >= 0 AND value <= 1)
                OR (type = 'variation' AND value >= -1 AND value <= 1)
            ),
            type TEXT NOT NULL CHECK (type IN ('aggregate', 'variation')),
            action TEXT,
            tid INTEGER NOT NULL REFERENCES rounds(id)
        )
    """,
}

_SQLITE_COLUMNS = {
    "user_mgmt": {
        "cover_image": "VARCHAR(400) DEFAULT ''",
    },
    "post": {
        "image_post_id": "INTEGER",
        "dedupe_key": "VARCHAR(64)",
        "client_action_id": "VARCHAR(96)",
        "created_at": "DATETIME",
    },
    "images": {
        "remote_article_id": "INTEGER",
    },
    "websites": {
        "fetch_images_from_url": "BOOLEAN DEFAULT 0",
        "fetch_images_timeout": "INTEGER DEFAULT 10",
    },
}

_POSTGRES_TABLES = {
    "image_posts": """
        CREATE TABLE IF NOT EXISTS image_posts (
            id SERIAL PRIMARY KEY,
            url VARCHAR(500) NOT NULL,
            source_url VARCHAR(500),
            title VARCHAR(300),
            subreddit VARCHAR(100),
            description TEXT,
            fetched_on VARCHAR(20),
            used BOOLEAN DEFAULT FALSE,
            local_path VARCHAR(500),
            high_res_url VARCHAR(500)
        )
    """,
    "reply_inbox_state": """
        CREATE TABLE IF NOT EXISTS reply_inbox_state (
            user_id INTEGER PRIMARY KEY REFERENCES user_mgmt(id) ON DELETE CASCADE,
            last_seen_reply_id INTEGER NOT NULL DEFAULT 0
        )
    """,
    "forum_chat_sessions": """
        CREATE TABLE IF NOT EXISTS forum_chat_sessions (
            id SERIAL PRIMARY KEY,
            owner_user_id TEXT NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
            owner_username VARCHAR(50) NOT NULL,
            target_user_id TEXT NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
            target_username VARCHAR(50) NOT NULL,
            target_profile_pic TEXT,
            run_id TEXT,
            llm_model VARCHAR(200),
            llm_base_url VARCHAR(300),
            persona_snapshot TEXT,
            memory_snapshot_json TEXT,
            last_message_preview TEXT,
            last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "forum_chat_messages": """
        CREATE TABLE IF NOT EXISTS forum_chat_messages (
            id SERIAL PRIMARY KEY,
            session_id INTEGER NOT NULL REFERENCES forum_chat_sessions(id) ON DELETE CASCADE,
            role VARCHAR(12) NOT NULL,
            content TEXT NOT NULL,
            meta_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "stress_reward": """
        CREATE TABLE IF NOT EXISTS stress_reward (
            id VARCHAR(36) PRIMARY KEY,
            uid INTEGER NOT NULL REFERENCES user_mgmt(id) ON DELETE CASCADE,
            variable VARCHAR(16) NOT NULL CHECK (variable IN ('stress', 'reward')),
            value DOUBLE PRECISION NOT NULL CHECK (
                (type = 'aggregate' AND value >= 0 AND value <= 1)
                OR (type = 'variation' AND value >= -1 AND value <= 1)
            ),
            type VARCHAR(16) NOT NULL CHECK (type IN ('aggregate', 'variation')),
            action VARCHAR(64),
            tid INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE
        )
    """,
}

_POSTGRES_COLUMNS = {
    "user_mgmt": {
        "cover_image": "VARCHAR(400) DEFAULT ''",
    },
    "post": {
        "image_post_id": "INTEGER",
        "dedupe_key": "VARCHAR(64)",
        "client_action_id": "VARCHAR(96)",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    },
    "images": {
        "remote_article_id": "INTEGER",
    },
    "websites": {
        "fetch_images_from_url": "BOOLEAN DEFAULT FALSE",
        "fetch_images_timeout": "INTEGER DEFAULT 10",
    },
}


def _sqlite_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def ensure_sqlite_experiment_schema(db_path: str) -> None:
    if not db_path or not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        for ddl in _SQLITE_TABLES.values():
            conn.execute(ddl)

        for table, columns in _SQLITE_COLUMNS.items():
            existing = _sqlite_existing_columns(conn, table)
            if not existing:
                continue  # table doesn't exist in this DB; skip
            for column_name, column_def in columns.items():
                if column_name not in existing:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}"
                    )

        stress_reward_columns = _sqlite_existing_columns(conn, "stress_reward")
        if stress_reward_columns and "action" not in stress_reward_columns:
            conn.execute("ALTER TABLE stress_reward ADD COLUMN action TEXT")

        if "created_at" in _sqlite_existing_columns(conn, "post"):
            conn.execute(
                "UPDATE post SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
            )

        conn.commit()
    finally:
        conn.close()


def _postgres_existing_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            """),
        {"table_name": table},
    ).fetchall()
    return {str(row[0]) for row in rows}


def ensure_postgresql_experiment_schema(db_uri: str) -> None:
    if not db_uri:
        return

    engine = create_engine(db_uri)
    try:
        with engine.begin() as conn:
            for ddl in _POSTGRES_TABLES.values():
                conn.execute(text(ddl))

            for table, columns in _POSTGRES_COLUMNS.items():
                existing = _postgres_existing_columns(conn, table)
                if not existing:
                    continue  # table doesn't exist in this DB; skip
                for column_name, column_def in columns.items():
                    if column_name not in existing:
                        conn.execute(
                            text(
                                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_name} {column_def}"
                            )
                        )

            stress_reward_columns = _postgres_existing_columns(conn, "stress_reward")
            if stress_reward_columns and "action" not in stress_reward_columns:
                conn.execute(
                    text(
                        "ALTER TABLE stress_reward ADD COLUMN IF NOT EXISTS action VARCHAR(64)"
                    )
                )

            existing = _postgres_existing_columns(conn, "post")
            if "created_at" in existing:
                conn.execute(
                    text(
                        "UPDATE post SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
                    )
                )
    finally:
        engine.dispose()


def ensure_experiment_schema_for_uri(db_uri: str) -> None:
    if not db_uri:
        return
    if db_uri.startswith("sqlite:///"):
        ensure_sqlite_experiment_schema(db_uri.replace("sqlite:///", "", 1))
    elif db_uri.startswith("postgresql"):
        ensure_postgresql_experiment_schema(db_uri)
