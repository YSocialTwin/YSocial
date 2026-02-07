"""
Database migration script to fix idexp primary key autoincrement in exps table.

This script fixes the idexp column to be a proper autoincrementing primary key.
The issue was that idexp was defined as INT without PRIMARY KEY AUTOINCREMENT,
causing NULL values to be inserted instead of auto-generated IDs.

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
    Fix idexp primary key autoincrement in SQLite database.

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

        # Check current table structure
        cursor.execute("PRAGMA table_info(exps)")
        columns_info = cursor.fetchall()
        
        # Check if idexp is already a primary key with autoincrement
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='exps'")
        table_sql = cursor.fetchone()
        
        if table_sql and "PRIMARY KEY AUTOINCREMENT" in table_sql[0].upper():
            print("○ idexp column already has AUTOINCREMENT in SQLite database")
            conn.close()
            return True

        print("Fixing idexp column to be PRIMARY KEY AUTOINCREMENT...")
        
        # Get all data from the current table
        cursor.execute("SELECT * FROM exps")
        existing_data = cursor.fetchall()
        
        # Get column names
        column_names = [col[1] for col in columns_info]
        
        # Check if exp_group exists in the original table
        has_exp_group = 'exp_group' in column_names
        
        # Create new table with proper primary key
        # Include exp_group only if it exists in the original table
        exp_group_column = "exp_group TEXT DEFAULT ''" if has_exp_group else ""
        exp_group_comma = "," if has_exp_group else ""
        
        create_table_sql = f"""
            CREATE TABLE exps_new (
                idexp INTEGER PRIMARY KEY AUTOINCREMENT,
                platform_type TEXT,
                exp_name TEXT,
                db_name TEXT,
                owner TEXT,
                exp_descr TEXT,
                status INT,
                running INT,
                port INT,
                server TEXT,
                annotations TEXT,
                server_pid INT,
                llm_agents_enabled INT,
                exp_status TEXT,
                simulator_type TEXT,
                is_remote INT{exp_group_comma}
                {exp_group_column}
            )
        """
        cursor.execute(create_table_sql)
        
        # Copy data from old table to new table
        # All rows will be migrated with new auto-generated IDs
        if existing_data:
            # Prepare insert statement (excluding idexp for auto-generation)
            insert_cols = [col for col in column_names if col != 'idexp']
            placeholders = ','.join(['?' for _ in insert_cols])
            insert_sql = f"INSERT INTO exps_new ({','.join(insert_cols)}) VALUES ({placeholders})"
            
            migrated_count = 0
            for row in existing_data:
                # Create data tuple excluding idexp (let it auto-generate)
                row_dict = dict(zip(column_names, row))
                data_tuple = tuple(row_dict[col] for col in insert_cols)
                cursor.execute(insert_sql, data_tuple)
                migrated_count += 1
            
            print(f"  Migrated {migrated_count} experiment(s) with new auto-generated IDs")
        
        # Drop old table and rename new table
        cursor.execute("DROP TABLE exps")
        cursor.execute("ALTER TABLE exps_new RENAME TO exps")
        
        print("✓ Fixed idexp column to be PRIMARY KEY AUTOINCREMENT in SQLite database")
        
        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        import traceback
        traceback.print_exc()
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Fix idexp primary key in PostgreSQL database.

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

        # Check if idexp has a sequence (autoincrement equivalent in PostgreSQL)
        cursor.execute("""
            SELECT column_default 
            FROM information_schema.columns 
            WHERE table_name = 'exps' AND column_name = 'idexp'
        """)
        result = cursor.fetchone()
        
        if result and result[0] and 'nextval' in str(result[0]):
            print("○ idexp column already has sequence (autoincrement) in PostgreSQL database")
            conn.close()
            return True

        print("Adding sequence to idexp column in PostgreSQL...")
        
        # Create sequence if it doesn't exist
        cursor.execute("""
            CREATE SEQUENCE IF NOT EXISTS exps_idexp_seq
        """)
        
        # Set the sequence to start from the max existing ID + 1
        cursor.execute("""
            SELECT COALESCE(MAX(idexp), 0) + 1 FROM exps WHERE idexp IS NOT NULL
        """)
        next_id = cursor.fetchone()[0]
        
        cursor.execute(f"""
            ALTER SEQUENCE exps_idexp_seq RESTART WITH {next_id}
        """)
        
        # Set the default value for idexp to use the sequence
        cursor.execute("""
            ALTER TABLE exps 
            ALTER COLUMN idexp SET DEFAULT nextval('exps_idexp_seq')
        """)
        
        # Update NULL idexp values with sequence values
        cursor.execute("""
            UPDATE exps 
            SET idexp = nextval('exps_idexp_seq') 
            WHERE idexp IS NULL
        """)
        
        print("✓ Fixed idexp column to use sequence in PostgreSQL database")
        
        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Fix idexp Primary Key Autoincrement")
    print("=" * 70)
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
    pg_host = os.environ.get("PG_HOST", "localhost")
    pg_port = os.environ.get("PG_PORT", "5432")
    pg_database = os.environ.get("PG_DBNAME", "dashboard")
    pg_user = os.environ.get("PG_USER", "postgres")
    pg_password = os.environ.get("PG_PASSWORD", "")

    if pg_password:
        postgresql_success = migrate_postgresql(
            pg_host, pg_port, pg_database, pg_user, pg_password
        )
    else:
        print("○ PostgreSQL not configured (no password found in environment)")
        print("  To migrate PostgreSQL, set the following environment variables:")
        print("  - PG_HOST (default: localhost)")
        print("  - PG_PORT (default: 5432)")
        print("  - PG_DBNAME (default: dashboard)")
        print("  - PG_USER (default: postgres)")
        print("  - PG_PASSWORD (required)")
        postgresql_success = None

    print()
    print("=" * 70)
    print("Migration Summary:")
    print(f"  SQLite:     {'✓ Success' if sqlite_success else '✗ Failed'}")
    if postgresql_success is not None:
        print(f"  PostgreSQL: {'✓ Success' if postgresql_success else '✗ Failed'}")
    else:
        print("  PostgreSQL: ○ Skipped (not configured)")
    print("=" * 70)

    return 0 if sqlite_success else 1


if __name__ == "__main__":
    sys.exit(main())
