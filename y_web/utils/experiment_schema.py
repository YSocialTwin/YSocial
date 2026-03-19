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
}

_SQLITE_COLUMNS = {
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
}

_POSTGRES_COLUMNS = {
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
            for column_name, column_def in columns.items():
                if column_name not in existing:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}"
                    )

        if "created_at" in _sqlite_existing_columns(conn, "post"):
            conn.execute(
                "UPDATE post SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
            )

        conn.commit()
    finally:
        conn.close()


def _postgres_existing_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            """
        ),
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
                for column_name, column_def in columns.items():
                    if column_name not in existing:
                        conn.execute(
                            text(
                                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_name} {column_def}"
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
