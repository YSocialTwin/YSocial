"""add exp_frontend_settings table

Revision ID: 0002_add_frontend_settings_table
Revises: 0001_baseline
Create Date: 2026-09-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_frontend_settings_table"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exp_frontend_settings",
        sa.Column(
            "exp_id",
            sa.Integer(),
            sa.ForeignKey("exps.idexp"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("exp_frontend_settings")
