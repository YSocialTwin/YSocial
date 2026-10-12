"""add plugin_state table (enable/disable switch for external plugin suites)

One row per external plugin suite (``repo_key``). A missing row means
"enabled", so no data migration is needed for already-installed plugins.
Idempotent: on databases where ``db.create_all()`` already built the table
this is a no-op.

Revision ID: 0006_add_plugin_state_table
Revises: 0005_rename_educatyon_to_frontend_adds_on
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0006_add_plugin_state_table"
down_revision: Union[str, None] = "0005_rename_educatyon_to_frontend_adds_on"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "plugin_state"


def upgrade() -> None:
    if _TABLE in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("repo_key", sa.String(64), primary_key=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    if _TABLE in inspect(op.get_bind()).get_table_names():
        op.drop_table(_TABLE)
