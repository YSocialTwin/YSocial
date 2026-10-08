"""add FilterBubble (Personalized Feed) row to content_recsys

Revision ID: 0003_add_filter_bubble_recsys_row
Revises: 0002_add_frontend_settings_table
Create Date: 2026-09-16
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_add_filter_bubble_recsys_row"
down_revision: Union[str, None] = "0002_add_frontend_settings_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME     = "FilterBubble"
_VALUE    = "Personalized Feed"
_CATEGORY = "Personalization"
_ENABLED  = "HumanOnly"


def upgrade() -> None:
    bind = op.get_bind()
    # Check whether the row already exists (migration may have been applied
    # via the legacy run_migrations() path or a manual SQL seed).
    exists = bind.execute(
        sa.text("SELECT 1 FROM content_recsys WHERE name = :name"),
        {"name": _NAME},
    ).fetchone()

    if exists:
        # Row present but enabled/category may be swapped from an earlier
        # incorrect SQL seed — normalise both columns in place.
        bind.execute(
            sa.text(
                "UPDATE content_recsys "
                "SET enabled = :enabled, category = :category "
                "WHERE name = :name"
            ),
            {"enabled": _ENABLED, "category": _CATEGORY, "name": _NAME},
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO content_recsys (name, value, category, enabled) "
                "VALUES (:name, :value, :category, :enabled)"
            ),
            {"name": _NAME, "value": _VALUE, "category": _CATEGORY, "enabled": _ENABLED},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM content_recsys WHERE name = :name"),
        {"name": _NAME},
    )
