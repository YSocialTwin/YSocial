"""Add structured agent custom features table to the dashboard database."""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """Create agents_custom_features in SQLite if missing."""
    if not db_path or not os.path.exists(db_path):
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents_custom_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                feature_type VARCHAR(20) NOT NULL,
                key VARCHAR(200) NOT NULL,
                value TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
            )
            """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_agents_custom_features_agent_id ON agents_custom_features(agent_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_agents_custom_features_type ON agents_custom_features(feature_type)"
        )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"✗ Error migrating SQLite agents_custom_features: {exc}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Create agents_custom_features in PostgreSQL if missing."""
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
            CREATE TABLE IF NOT EXISTS agents_custom_features (
                id SERIAL PRIMARY KEY,
                agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                feature_type VARCHAR(20) NOT NULL,
                key VARCHAR(200) NOT NULL,
                value TEXT
            )
            """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_agents_custom_features_agent_id ON agents_custom_features(agent_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_agents_custom_features_type ON agents_custom_features(feature_type)"
        )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"✗ Error migrating PostgreSQL agents_custom_features: {exc}")
        return False
