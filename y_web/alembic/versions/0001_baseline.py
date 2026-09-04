"""baseline: stato schema post-migrazione-manuale

This is a no-op migration. It marks the database as being at the baseline
state — i.e., the schema that results from applying all 31 manual migrations
in y_web/migrations/ (which were in use before Flask-Migrate was adopted).

For any existing YSocial database, stamp this revision manually to tell
Alembic that no schema changes are needed:

    flask --app y_social.py db stamp 0001_baseline

For brand-new databases, running ``flask db upgrade`` will apply this
baseline (a no-op), after which future migrations will be applied normally.

Revision ID: 0001_baseline
Revises: (none — this is the root revision)
Create Date: 2026-09-04
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op: the schema is managed by SQLAlchemy's db.create_all() on first
    # run, and by the 31 manual migrations in y_web/migrations/ for upgrades.
    # Future schema changes go in new migration files generated with:
    #   flask --app y_social.py db migrate -m "description"
    pass


def downgrade() -> None:
    # Downgrading past the baseline is not supported.
    pass
