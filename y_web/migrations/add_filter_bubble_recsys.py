"""
Database migration: add FilterBubble (Personalized Feed) to content_recsys.

This is a human-only content recommender (enabled='HumanOnly') that builds
a filter bubble around a human user's interests and opinions gathered during
the onboarding phase.
"""

import os
import sqlite3

try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

_NAME = "FilterBubble"
_VALUE = "Personalized Feed"
_CATEGORY = "Personalization"
_ENABLED = "HumanOnly"


def migrate_sqlite(db_path):
    """Add FilterBubble row to content_recsys in the SQLite dashboard DB."""
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT enabled, category FROM content_recsys WHERE name = ?", (_NAME,)
        ).fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO content_recsys (name, value, category, enabled) "
                "VALUES (?, ?, ?, ?)",
                (_NAME, _VALUE, _CATEGORY, _ENABLED),
            )
            print(f"✓ Inserted {_NAME} into content_recsys (SQLite)")
        elif row[0] != _ENABLED or row[1] != _CATEGORY:
            cursor.execute(
                "UPDATE content_recsys SET enabled = ?, category = ? WHERE name = ?",
                (_ENABLED, _CATEGORY, _NAME),
            )
            print(f"✓ Fixed {_NAME} columns in content_recsys (SQLite)")
        else:
            print(f"○ {_NAME} already correct in content_recsys (SQLite)")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite (FilterBubble recsys): {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """Add FilterBubble row to content_recsys in the PostgreSQL dashboard DB."""
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        return False
    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()
        cursor.execute(
            "SELECT enabled, category FROM content_recsys WHERE name = %s", (_NAME,)
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO content_recsys (name, value, category, enabled) "
                "VALUES (%s, %s, %s, %s)",
                (_NAME, _VALUE, _CATEGORY, _ENABLED),
            )
            print(f"✓ Inserted {_NAME} into content_recsys (PostgreSQL)")
        elif row[0] != _ENABLED or row[1] != _CATEGORY:
            cursor.execute(
                "UPDATE content_recsys SET enabled = %s, category = %s WHERE name = %s",
                (_ENABLED, _CATEGORY, _NAME),
            )
            print(f"✓ Fixed {_NAME} columns in content_recsys (PostgreSQL)")
        else:
            print(f"○ {_NAME} already correct in content_recsys (PostgreSQL)")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating PostgreSQL (FilterBubble recsys): {e}")
        return False
