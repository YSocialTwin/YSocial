"""
Database migration script to store admin interview agent ids as text.

HPC experiments use UUID-backed `user_mgmt.id` values, so the dashboard-side
`admin_interview_sessions.agent_user_id` column must not remain integer-only.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    if not db_path or not os.path.exists(db_path):
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(admin_interview_sessions)")
        columns = cursor.fetchall()
        if not columns:
            conn.close()
            return True

        agent_column = next(
            (column for column in columns if column[1] == "agent_user_id"),
            None,
        )
        if agent_column is None:
            conn.close()
            return True

        declared_type = str(agent_column[2] or "").strip().upper()
        if declared_type in {"TEXT", "VARCHAR", "VARCHAR(64)"}:
            conn.close()
            return True

        cursor.execute(
            "ALTER TABLE admin_interview_sessions RENAME TO admin_interview_sessions_old"
        )
        cursor.execute("""
            CREATE TABLE admin_interview_sessions (
                id INTEGER PRIMARY KEY,
                exp_id INTEGER NOT NULL,
                admin_username VARCHAR(50) NOT NULL,
                agent_user_id VARCHAR(64) NOT NULL,
                agent_username VARCHAR(50) NOT NULL,
                run_id TEXT,
                backend_mode VARCHAR(20) NOT NULL DEFAULT 'agent_runtime',
                llm_model VARCHAR(200),
                llm_base_url VARCHAR(300),
                persona_snapshot TEXT,
                interests_snapshot_json TEXT,
                memory_snapshot_json TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        cursor.execute("""
            INSERT INTO admin_interview_sessions (
                id, exp_id, admin_username, agent_user_id, agent_username, run_id,
                backend_mode, llm_model, llm_base_url, persona_snapshot,
                interests_snapshot_json, memory_snapshot_json, created_at, updated_at
            )
            SELECT
                id, exp_id, admin_username, CAST(agent_user_id AS TEXT), agent_username, run_id,
                backend_mode, llm_model, llm_base_url, persona_snapshot,
                interests_snapshot_json, memory_snapshot_json, created_at, updated_at
            FROM admin_interview_sessions_old
            """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_interview_sessions_exp_id ON admin_interview_sessions(exp_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_interview_sessions_admin_username ON admin_interview_sessions(admin_username)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_interview_sessions_run_id ON admin_interview_sessions(run_id)"
        )
        cursor.execute("DROP TABLE admin_interview_sessions_old")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def migrate_postgresql(host, port, database, user, password):
    if not PSYCOPG2_AVAILABLE:
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()
        cursor.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'admin_interview_sessions'
              AND column_name = 'agent_user_id'
            """)
        row = cursor.fetchone()
        if row is None:
            conn.close()
            return True

        data_type = str(row[0] or "").strip().lower()
        if data_type in {"character varying", "text"}:
            conn.close()
            return True

        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ALTER COLUMN agent_user_id TYPE VARCHAR(64)
            USING agent_user_id::text
            """)
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False
