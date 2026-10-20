"""add exps.prompt_language and client.prompt_language (language of the LLM prompts)

The default is ``en`` so existing experiments and clients keep the prompts they already have. Idempotent:
databases that already have the columns are left untouched.

Revision ID: 0010_add_prompt_language
Revises: 0009_add_signup_tables
Create Date: 2026-10-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0010_add_prompt_language"
down_revision: Union[str, None] = "0009_add_signup_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("exps", "client")


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for table in TABLES:
        if table not in existing:
            continue
        if "prompt_language" in {c["name"] for c in inspector.get_columns(table)}:
            continue
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN prompt_language VARCHAR(10) NOT NULL DEFAULT 'en'"
        )


def downgrade() -> None:
    # Additive and idempotent: nothing to undo.
    pass
