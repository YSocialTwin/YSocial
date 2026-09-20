"""rename educatyon_exp_module_settings to frontend_adds_on_exp_module_settings

The EducatYon frontend-plugin suite was renamed to Frontend Adds-on. This
renames the table in place (SQLite/PostgreSQL both support ALTER TABLE
RENAME TO without a data copy) so every already-collected row of
per-experiment module configuration survives untouched. The historical
revision 0004 that created the table is left exactly as it was applied --
this migration only renames what 0004 already built.

Revision ID: 0005_rename_educatyon_to_frontend_adds_on
Revises: 0004_add_educatyon_exp_module_settings
Create Date: 2026-09-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0005_rename_educatyon_to_frontend_adds_on"
down_revision: Union[str, None] = "0004_add_educatyon_exp_module_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_NAME = "educatyon_exp_module_settings"
_NEW_NAME = "frontend_adds_on_exp_module_settings"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    # Idempotent and order-independent with respect to the legacy manual
    # migration runner (y_web/migrations/add_frontend_adds_on_module_settings.py),
    # which performs the exact same rename when Alembic isn't the active
    # migration path -- whichever one runs first on a given database wins,
    # the other becomes a no-op.
    if _OLD_NAME in existing_tables and _NEW_NAME not in existing_tables:
        op.rename_table(_OLD_NAME, _NEW_NAME)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if _NEW_NAME in existing_tables and _OLD_NAME not in existing_tables:
        op.rename_table(_NEW_NAME, _OLD_NAME)
