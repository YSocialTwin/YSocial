"""add signup_settings and signup_target (self-registration of participants)

Idempotent: databases where ``db.create_all()`` already built the tables are left untouched.

Revision ID: 0009_add_signup_tables
Revises: 0008_add_admin_users_lang
Create Date: 2026-10-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0009_add_signup_tables"
down_revision: Union[str, None] = "0008_add_admin_users_lang"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "signup_settings" not in tables:
        op.create_table(
            "signup_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "enabled", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    if "signup_target" not in tables:
        op.create_table(
            "signup_target",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("ref", sa.String(64), nullable=False),
            sa.UniqueConstraint("kind", "ref", name="uq_signup_target"),
        )


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    for name in ("signup_target", "signup_settings"):
        if name in tables:
            op.drop_table(name)
