"""
Database migration script to add opinion dynamics tables.

This script adds two tables for opinion dynamics simulations:
- opinion_groups: Define opinion groups with name and value ranges [lower_bound, upper_bound]
- opinion_distributions: Store distribution configurations (type and parameters as JSON)

Run this script to update existing YSocial installations.
"""

import json
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
    Add opinion dynamics tables to SQLite database.

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

        # Check if opinion_groups table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='opinion_groups'"
        )
        groups_exists = cursor.fetchone() is not None

        if not groups_exists:
            cursor.execute("""
                CREATE TABLE opinion_groups (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        VARCHAR(100) NOT NULL,
                    lower_bound REAL NOT NULL,
                    upper_bound REAL NOT NULL
                )
            """)
            print("✓ Created opinion_groups table in SQLite database")
        else:
            print("○ opinion_groups table already exists in SQLite database")

        # Check if opinion_distributions table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='opinion_distributions'"
        )
        distributions_exists = cursor.fetchone() is not None

        distributions_created = False
        if not distributions_exists:
            cursor.execute("""
                CREATE TABLE opinion_distributions (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    name              VARCHAR(100) NOT NULL,
                    distribution_type VARCHAR(50) NOT NULL,
                    parameters        TEXT NOT NULL
                )
            """)
            print("✓ Created opinion_distributions table in SQLite database")
            distributions_created = True
        else:
            print("○ opinion_distributions table already exists in SQLite database")

        # Populate default distributions if table was just created
        if distributions_created:
            default_distributions = [
                ("Uniform", "uniform", json.dumps({"low": 0, "high": 1})),
                (
                    "Normal (μ=0.5, σ=0.25)",
                    "normal",
                    json.dumps({"loc": 0.5, "scale": 0.25}),
                ),
                ("U-shaped", "beta", json.dumps({"a": 0.5, "b": 0.5})),
                ("Left-skewed (μ=0.3)", "beta", json.dumps({"a": 0.5, "b": 2})),
                ("Right-skewed (μ=0.7)", "beta", json.dumps({"a": 2, "b": 0.5})),
            ]

            for name, dist_type, params in default_distributions:
                cursor.execute(
                    "INSERT INTO opinion_distributions (name, distribution_type, parameters) VALUES (?, ?, ?)",
                    (name, dist_type, params),
                )
            print(
                f"✓ Populated {len(default_distributions)} default distributions in SQLite database"
            )

        # Populate default opinion groups if tables were just created
        if not groups_exists:
            default_groups = [
                ("Strongly against", 0.0, 0.2),
                ("Against", 0.2, 0.4),
                ("Neutral", 0.4, 0.6),
                ("In favor", 0.6, 0.8),
                ("Strongly in favor", 0.8, 1.0),
            ]

            for name, lower, upper in default_groups:
                cursor.execute(
                    "INSERT INTO opinion_groups (name, lower_bound, upper_bound) VALUES (?, ?, ?)",
                    (name, lower, upper),
                )
            print(
                f"✓ Populated {len(default_groups)} default opinion groups in SQLite database"
            )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add opinion dynamics tables to PostgreSQL database.

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

        # Check if opinion_groups table already exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name = 'opinion_groups'
        """)
        groups_exists = cursor.fetchone() is not None

        if not groups_exists:
            cursor.execute("""
                CREATE TABLE opinion_groups (
                    id          SERIAL PRIMARY KEY,
                    name        VARCHAR(100) NOT NULL,
                    lower_bound DOUBLE PRECISION NOT NULL,
                    upper_bound DOUBLE PRECISION NOT NULL
                )
            """)
            print("✓ Created opinion_groups table in PostgreSQL database")
        else:
            print("○ opinion_groups table already exists in PostgreSQL database")

        # Check if opinion_distributions table already exists
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name = 'opinion_distributions'
        """)
        distributions_exists = cursor.fetchone() is not None

        distributions_created = False
        if not distributions_exists:
            cursor.execute("""
                CREATE TABLE opinion_distributions (
                    id                SERIAL PRIMARY KEY,
                    name              VARCHAR(100) NOT NULL,
                    distribution_type VARCHAR(50) NOT NULL,
                    parameters        TEXT NOT NULL
                )
            """)
            print("✓ Created opinion_distributions table in PostgreSQL database")
            distributions_created = True
        else:
            print("○ opinion_distributions table already exists in PostgreSQL database")

        # Populate default distributions if table was just created
        if distributions_created:
            default_distributions = [
                ("Uniform", "uniform", json.dumps({"low": 0, "high": 1})),
                (
                    "Normal (μ=0.5, σ=0.25)",
                    "normal",
                    json.dumps({"loc": 0.5, "scale": 0.25}),
                ),
                ("U-shaped", "beta", json.dumps({"a": 0.5, "b": 0.5})),
                ("Left-skewed (μ=0.3)", "beta", json.dumps({"a": 0.5, "b": 2})),
                ("Right-skewed (μ=0.7)", "beta", json.dumps({"a": 2, "b": 0.5})),
            ]

            for name, dist_type, params in default_distributions:
                cursor.execute(
                    "INSERT INTO opinion_distributions (name, distribution_type, parameters) VALUES (%s, %s, %s)",
                    (name, dist_type, params),
                )
            print(
                f"✓ Populated {len(default_distributions)} default distributions in PostgreSQL database"
            )

        # Populate default opinion groups if tables were just created
        if not groups_exists:
            default_groups = [
                ("Strongly against", 0.0, 0.2),
                ("Against", 0.2, 0.4),
                ("Neutral", 0.4, 0.6),
                ("In favor", 0.6, 0.8),
                ("Strongly in favor", 0.8, 1.0),
            ]

            for name, lower, upper in default_groups:
                cursor.execute(
                    "INSERT INTO opinion_groups (name, lower_bound, upper_bound) VALUES (%s, %s, %s)",
                    (name, lower, upper),
                )
            print(
                f"✓ Populated {len(default_groups)} default opinion groups in PostgreSQL database"
            )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Opinion Dynamics Tables")
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
        print("  PostgreSQL: ○ Skipped (not configured)")
    print("=" * 60)

    return 0 if sqlite_success else 1


if __name__ == "__main__":
    sys.exit(main())
