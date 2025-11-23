"""
Database migration script to add log metrics tables for incremental log reading.

This script adds three new tables:
- log_file_offsets: Tracks the last read position in log files
- server_log_metrics: Stores aggregated server log metrics
- client_log_metrics: Stores aggregated client log metrics

Run this script to update existing YSocial installations.
"""

import os
import sqlite3
import sys

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """
    Add log metrics tables to SQLite database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        bool: True if successful, False otherwise
    """
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if tables already exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('log_file_offsets', 'server_log_metrics', 'client_log_metrics')"
        )
        existing_tables = [row[0] for row in cursor.fetchall()]

        # Create log_file_offsets table if it doesn't exist
        if "log_file_offsets" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE log_file_offsets (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    exp_id        INTEGER NOT NULL,
                    log_file_type VARCHAR(50) NOT NULL,
                    client_id     INTEGER,
                    file_path     VARCHAR(500) NOT NULL,
                    last_offset   INTEGER NOT NULL DEFAULT 0,
                    last_updated  TEXT NOT NULL,
                    FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE,
                    FOREIGN KEY (client_id) REFERENCES client(id) ON DELETE CASCADE
                )
            """
            )
            cursor.execute(
                "CREATE INDEX idx_log_file_offset_lookup ON log_file_offsets(exp_id, log_file_type, client_id)"
            )
            print("✓ Created log_file_offsets table in SQLite database")
        else:
            print("○ log_file_offsets table already exists in SQLite database")

        # Create server_log_metrics table if it doesn't exist
        if "server_log_metrics" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE server_log_metrics (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    exp_id            INTEGER NOT NULL,
                    aggregation_level VARCHAR(10) NOT NULL,
                    day               INTEGER NOT NULL,
                    hour              INTEGER,
                    path              VARCHAR(200) NOT NULL,
                    call_count        INTEGER NOT NULL DEFAULT 0,
                    total_duration    REAL NOT NULL DEFAULT 0.0,
                    min_time          TEXT,
                    max_time          TEXT,
                    FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE
                )
            """
            )
            cursor.execute(
                "CREATE INDEX idx_server_log_metrics_lookup ON server_log_metrics(exp_id, aggregation_level, day, hour, path)"
            )
            print("✓ Created server_log_metrics table in SQLite database")
        else:
            print("○ server_log_metrics table already exists in SQLite database")

        # Create client_log_metrics table if it doesn't exist
        if "client_log_metrics" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE client_log_metrics (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    exp_id               INTEGER NOT NULL,
                    client_id            INTEGER NOT NULL,
                    aggregation_level    VARCHAR(10) NOT NULL,
                    day                  INTEGER NOT NULL,
                    hour                 INTEGER,
                    method_name          VARCHAR(200) NOT NULL,
                    call_count           INTEGER NOT NULL DEFAULT 0,
                    total_execution_time REAL NOT NULL DEFAULT 0.0,
                    FOREIGN KEY (exp_id) REFERENCES exps(idexp) ON DELETE CASCADE,
                    FOREIGN KEY (client_id) REFERENCES client(id) ON DELETE CASCADE
                )
            """
            )
            cursor.execute(
                "CREATE INDEX idx_client_log_metrics_lookup ON client_log_metrics(exp_id, client_id, aggregation_level, day, hour, method_name)"
            )
            print("✓ Created client_log_metrics table in SQLite database")
        else:
            print("○ client_log_metrics table already exists in SQLite database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add log metrics tables to PostgreSQL database.

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        bool: True if successful, False otherwise
    """
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        print("  Install with: pip install psycopg2-binary")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        # Check if tables already exist
        cursor.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name IN ('log_file_offsets', 'server_log_metrics', 'client_log_metrics')
        """
        )
        existing_tables = [row[0] for row in cursor.fetchall()]

        # Create log_file_offsets table if it doesn't exist
        if "log_file_offsets" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE log_file_offsets (
                    id            SERIAL PRIMARY KEY,
                    exp_id        INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
                    log_file_type VARCHAR(50) NOT NULL,
                    client_id     INTEGER REFERENCES client(id) ON DELETE CASCADE,
                    file_path     VARCHAR(500) NOT NULL,
                    last_offset   BIGINT NOT NULL DEFAULT 0,
                    last_updated  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            cursor.execute(
                "CREATE INDEX idx_log_file_offset_lookup ON log_file_offsets(exp_id, log_file_type, client_id)"
            )
            print("✓ Created log_file_offsets table in PostgreSQL database")
        else:
            print("○ log_file_offsets table already exists in PostgreSQL database")

        # Create server_log_metrics table if it doesn't exist
        if "server_log_metrics" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE server_log_metrics (
                    id                SERIAL PRIMARY KEY,
                    exp_id            INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
                    aggregation_level VARCHAR(10) NOT NULL,
                    day               INTEGER NOT NULL,
                    hour              INTEGER,
                    path              VARCHAR(200) NOT NULL,
                    call_count        INTEGER NOT NULL DEFAULT 0,
                    total_duration    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    min_time          TIMESTAMP,
                    max_time          TIMESTAMP
                )
            """
            )
            cursor.execute(
                "CREATE INDEX idx_server_log_metrics_lookup ON server_log_metrics(exp_id, aggregation_level, day, hour, path)"
            )
            print("✓ Created server_log_metrics table in PostgreSQL database")
        else:
            print("○ server_log_metrics table already exists in PostgreSQL database")

        # Create client_log_metrics table if it doesn't exist
        if "client_log_metrics" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE client_log_metrics (
                    id                   SERIAL PRIMARY KEY,
                    exp_id               INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
                    client_id            INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
                    aggregation_level    VARCHAR(10) NOT NULL,
                    day                  INTEGER NOT NULL,
                    hour                 INTEGER,
                    method_name          VARCHAR(200) NOT NULL,
                    call_count           INTEGER NOT NULL DEFAULT 0,
                    total_execution_time DOUBLE PRECISION NOT NULL DEFAULT 0.0
                )
            """
            )
            cursor.execute(
                "CREATE INDEX idx_client_log_metrics_lookup ON client_log_metrics(exp_id, client_id, aggregation_level, day, hour, method_name)"
            )
            print("✓ Created client_log_metrics table in PostgreSQL database")
        else:
            print("○ client_log_metrics table already exists in PostgreSQL database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Log Metrics Tables")
    print("=" * 60)
    print()

    # Migrate SQLite database
    print("Migrating SQLite database...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    sqlite_db_path = os.path.join(project_root, "data_schema", "database_dashboard.db")

    sqlite_success = migrate_sqlite(sqlite_db_path)
    print()

    # Migrate PostgreSQL database (if configured)
    print("Migrating PostgreSQL database...")

    # Try to read PostgreSQL configuration from environment variables
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_database = os.environ.get("POSTGRES_DB", "ysocial")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")

    if pg_password:
        postgresql_success = migrate_postgresql(
            pg_host, pg_port, pg_database, pg_user, pg_password
        )
    else:
        print("○ PostgreSQL not configured (no password found in environment)")
        print("  To migrate PostgreSQL, set the following environment variables:")
        print("  - POSTGRES_HOST (default: localhost)")
        print("  - POSTGRES_PORT (default: 5432)")
        print("  - POSTGRES_DB (default: ysocial)")
        print("  - POSTGRES_USER (default: postgres)")
        print("  - POSTGRES_PASSWORD (required)")
        postgresql_success = None

    print()
    print("=" * 60)
    print("Migration Summary:")
    print(f"  SQLite:     {'✓ Success' if sqlite_success else '✗ Failed'}")
    if postgresql_success is not None:
        print(f"  PostgreSQL: {'✓ Success' if postgresql_success else '✗ Failed'}")
    else:
        print(f"  PostgreSQL: ○ Skipped (not configured)")
    print("=" * 60)

    return 0 if sqlite_success else 1


if __name__ == "__main__":
    sys.exit(main())
