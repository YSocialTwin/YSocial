"""add educatyon_exp_module_settings table

Revision ID: 0004_add_educatyon_exp_module_settings
Revises: 0003_add_filter_bubble_recsys_row
Create Date: 2026-09-17
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_educatyon_exp_module_settings"
down_revision: Union[str, None] = "0003_add_filter_bubble_recsys_row"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "educatyon_exp_module_settings",
        sa.Column("exp_id", sa.Integer(), sa.ForeignKey("exps.idexp"), primary_key=True, nullable=False),
        sa.Column("module_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("educatyon_exp_module_settings")
