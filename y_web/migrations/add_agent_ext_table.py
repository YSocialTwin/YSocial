"""
Database migration script to add the agent_ext table.

Stores plugin-specific agent fields that are not part of the standard
dashboard agents schema.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """Add agent_ext table to the SQLite dashboard database."""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_ext'"
        )
        if cursor.fetchone():
            print("○ agent_ext table already exists in SQLite database")
            conn.close()
            return True

        cursor.execute("""
            CREATE TABLE agent_ext (
                agent_id INTEGER NOT NULL,
                feature_name VARCHAR(100) NOT NULL,
                feature_value TEXT,
                PRIMARY KEY (agent_id, feature_name),
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            )
            """)
        cursor.execute(
            "CREATE INDEX idx_agent_ext_feature_name ON agent_ext(feature_name)"
        )

        conn.commit()
        conn.close()
        print("✓ Created agent_ext table in SQLite database")
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Add agent_ext table to the PostgreSQL dashboard database."""
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
            WHERE table_schema = 'public' AND table_name = 'agent_ext'
            """)
        if cursor.fetchone():
            print("○ agent_ext table already exists in PostgreSQL database")
            conn.close()
            return True

        cursor.execute("""
            CREATE TABLE agent_ext (
                agent_id INTEGER NOT NULL REFERENCES agents(id),
                feature_name VARCHAR(100) NOT NULL,
                feature_value TEXT,
                PRIMARY KEY (agent_id, feature_name)
            )
            """)
        cursor.execute(
            "CREATE INDEX idx_agent_ext_feature_name ON agent_ext(feature_name)"
        )

        conn.commit()
        conn.close()
        print("✓ Created agent_ext table in PostgreSQL database")
        return True
    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False
