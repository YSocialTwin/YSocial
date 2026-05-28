"""
Migration script to add opinion_evolution_cache and opinion_evolution_sampled_agents tables.

This migration adds performance optimization tables for opinion evolution visualization:
- opinion_evolution_cache: Caches pre-computed statistics with incremental state support
- opinion_evolution_sampled_agents: Stores sampled agent IDs for stable visualization
"""

import os
import sqlite3
import sys


def migrate_sqlite(dashboard_db_path):
    """
    Add opinion evolution cache tables to SQLite dashboard database.

    Args:
        dashboard_db_path: Path to the dashboard.db SQLite database

    Returns:
        bool: True if migration succeeded, False otherwise
    """
    if not os.path.exists(dashboard_db_path):
        print(f"Database not found at {dashboard_db_path}")
        return False

    try:
        conn = sqlite3.connect(dashboard_db_path)
        cursor = conn.cursor()

        # Migration 1: Add opinion_evolution_cache table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='opinion_evolution_cache'"
        )
        if not cursor.fetchone():
            print("Creating opinion_evolution_cache table...")
            cursor.execute("""
                CREATE TABLE opinion_evolution_cache (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    exp_id               INTEGER NOT NULL,
                    day                  INTEGER NOT NULL,
                    hour                 INTEGER NOT NULL,
                    topic_id             INTEGER,
                    total_opinions       INTEGER NOT NULL,
                    social_interactions  INTEGER NOT NULL,
                    unique_agents        INTEGER NOT NULL,
                    binned_data          TEXT NOT NULL,
                    latest_opinions_state TEXT,
                    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX idx_cache_lookup ON opinion_evolution_cache(exp_id, day, hour, topic_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_cache_created ON opinion_evolution_cache(created_at)
            """)
            print("✓ opinion_evolution_cache table created")
        else:
            print("opinion_evolution_cache table already exists")

            # Check if latest_opinions_state column exists, add if missing
            cursor.execute("PRAGMA table_info(opinion_evolution_cache)")
            columns = [column[1] for column in cursor.fetchall()]
            if "latest_opinions_state" not in columns:
                print(
                    "Adding latest_opinions_state column to opinion_evolution_cache..."
                )
                cursor.execute("""
                    ALTER TABLE opinion_evolution_cache 
                    ADD COLUMN latest_opinions_state TEXT
                """)
                print("✓ latest_opinions_state column added")

        # Migration 2: Add opinion_evolution_sampled_agents table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='opinion_evolution_sampled_agents'"
        )
        if not cursor.fetchone():
            print("Creating opinion_evolution_sampled_agents table...")
            cursor.execute("""
                CREATE TABLE opinion_evolution_sampled_agents (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    exp_id               INTEGER NOT NULL,
                    topic_id             TEXT,
                    sample_percentage    INTEGER NOT NULL,
                    sampled_agent_ids    TEXT NOT NULL,
                    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX idx_sampled_agents_lookup ON opinion_evolution_sampled_agents(exp_id, topic_id, sample_percentage)
            """)
            cursor.execute("""
                CREATE INDEX idx_sampled_agents_created ON opinion_evolution_sampled_agents(created_at)
            """)
            print("✓ opinion_evolution_sampled_agents table created")
        else:
            print("opinion_evolution_sampled_agents table already exists")

        conn.commit()
        conn.close()
        print("✓ Opinion evolution cache migration completed successfully")
        return True

    except Exception as e:
        print(f"Error migrating database: {e}")
        return False


def migrate_postgresql(user, password, host, port, dbname):
    """
    Add opinion evolution cache tables to PostgreSQL dashboard database.

    Args:
        user: PostgreSQL username
        password: PostgreSQL password
        host: PostgreSQL host
        port: PostgreSQL port
        dbname: Database name

    Returns:
        bool: True if migration succeeded, False otherwise
    """
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(f"postgresql://{user}:{password}@{host}:{port}/{dbname}")

        with engine.connect() as conn:
            # Migration 1: Add opinion_evolution_cache table
            result = conn.execute(
                text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = 'opinion_evolution_cache')"
                )
            )
            if not result.scalar():
                print("Creating opinion_evolution_cache table...")
                conn.execute(text("""
                    CREATE TABLE opinion_evolution_cache (
                        id                   SERIAL PRIMARY KEY,
                        exp_id               INTEGER NOT NULL,
                        day                  INTEGER NOT NULL,
                        hour                 INTEGER NOT NULL,
                        topic_id             INTEGER,
                        total_opinions       INTEGER NOT NULL,
                        social_interactions  INTEGER NOT NULL,
                        unique_agents        INTEGER NOT NULL,
                        binned_data          TEXT NOT NULL,
                        latest_opinions_state TEXT,
                        created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT fk_opinion_cache_exp FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE
                    )
                """))

                # Create indexes
                conn.execute(text("""
                    CREATE INDEX idx_cache_lookup ON opinion_evolution_cache(exp_id, day, hour, topic_id)
                """))
                conn.execute(text("""
                    CREATE INDEX idx_cache_created ON opinion_evolution_cache(created_at)
                """))
                conn.commit()
                print("✓ opinion_evolution_cache table created")
            else:
                print("opinion_evolution_cache table already exists")

                # Check if latest_opinions_state column exists, add if missing
                result = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT FROM information_schema.columns "
                        "WHERE table_name = 'opinion_evolution_cache' "
                        "AND column_name = 'latest_opinions_state')"
                    )
                )
                if not result.scalar():
                    print(
                        "Adding latest_opinions_state column to opinion_evolution_cache..."
                    )
                    conn.execute(text("""
                        ALTER TABLE opinion_evolution_cache 
                        ADD COLUMN latest_opinions_state TEXT
                    """))
                    conn.commit()
                    print("✓ latest_opinions_state column added")

            # Migration 2: Add opinion_evolution_sampled_agents table
            result = conn.execute(
                text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = 'opinion_evolution_sampled_agents')"
                )
            )
            if not result.scalar():
                print("Creating opinion_evolution_sampled_agents table...")
                conn.execute(text("""
                    CREATE TABLE opinion_evolution_sampled_agents (
                        id                   SERIAL PRIMARY KEY,
                        exp_id               INTEGER NOT NULL,
                        topic_id             VARCHAR(50),
                        sample_percentage    INTEGER NOT NULL,
                        sampled_agent_ids    TEXT NOT NULL,
                        created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT fk_sampled_agents_exp FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE
                    )
                """))

                # Create indexes
                conn.execute(text("""
                    CREATE INDEX idx_sampled_agents_lookup ON opinion_evolution_sampled_agents(exp_id, topic_id, sample_percentage)
                """))
                conn.execute(text("""
                    CREATE INDEX idx_sampled_agents_created ON opinion_evolution_sampled_agents(created_at)
                """))
                conn.commit()
                print("✓ opinion_evolution_sampled_agents table created")
            else:
                print("opinion_evolution_sampled_agents table already exists")

        engine.dispose()
        print("✓ Opinion evolution cache migration completed successfully")
        return True

    except Exception as e:
        print(f"Error migrating PostgreSQL database: {e}")
        return False


if __name__ == "__main__":
    # For testing SQLite migration
    import sys

    if len(sys.argv) > 1:
        migrate_sqlite(sys.argv[1])
    else:
        print("Usage: python add_opinion_evolution_cache.py <path_to_dashboard.db>")
