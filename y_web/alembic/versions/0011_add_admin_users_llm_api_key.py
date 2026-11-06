"""add admin_users.llm_api_key (API key of the LLM server of each admin user)

Empty means "no key" (a local Ollama or vLLM needs none). Idempotent: databases that already
have the column are left untouched.

Revision ID: 0011_add_admin_users_llm_api_key
Revises: 0010_add_prompt_language
Create Date: 2026-11-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0011_add_admin_users_llm_api_key"
down_revision: Union[str, None] = "0010_add_prompt_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "admin_users" not in inspector.get_table_names():
        return
    if "llm_api_key" in {c["name"] for c in inspector.get_columns("admin_users")}:
        return
    op.execute("ALTER TABLE admin_users ADD COLUMN llm_api_key VARCHAR(300) DEFAULT ''")


def downgrade() -> None:
    # Additive and idempotent: nothing to undo.
    pass
