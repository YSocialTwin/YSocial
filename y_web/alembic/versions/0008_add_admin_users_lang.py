"""add admin_users.lang (dashboard language chosen by each admin user)

NULL means "automatic": the ``ys_lang`` cookie, then the browser language, then
English. Idempotent: databases that already have the column are left untouched.

Revision ID: 0008_add_admin_users_lang
Revises: 0007_sync_legacy_dashboard_schema
Create Date: 2026-10-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0008_add_admin_users_lang"
down_revision: Union[str, None] = "0007_sync_legacy_dashboard_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "admin_users" not in inspector.get_table_names():
        return
    if "lang" in {c["name"] for c in inspector.get_columns("admin_users")}:
        return
    op.execute("ALTER TABLE admin_users ADD COLUMN lang VARCHAR(10)")


def downgrade() -> None:
    # Additive and idempotent: nothing to undo.
    pass
