"""add the forum-only content recommenders (Hot, Top, Most commented)

Revision ID: 0011_add_forum_recsys_rows
Revises: 0010_add_prompt_language
Create Date: 2026-10-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_add_forum_recsys_rows"
down_revision: Union[str, None] = "0010_add_prompt_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATEGORY = "Reddit-style Ranking"
_ENABLED = "Forum"
_ROWS = (
    ("HotRanking", "(HOT) Hot Ranking"),
    ("TopRanking", "(TOP) Top Ranking"),
    ("MostCommented", "(MC) Most Commented"),
)


def _has_table(bind) -> bool:
    return "content_recsys" in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        # Tables created later by ``create_all`` are seeded from the template.
        return
    existing = {c["name"] for c in sa.inspect(bind).get_columns("content_recsys")}
    for column in ("category", "enabled"):
        if column not in existing:
            op.add_column("content_recsys", sa.Column(column, sa.Text(), nullable=True))

    for name, value in _ROWS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM content_recsys WHERE name = :name"), {"name": name}
        ).fetchone()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO content_recsys (name, value, category, enabled) "
                "VALUES (:name, :value, :category, :enabled)"
            ),
            {
                "name": name,
                "value": value,
                "category": _CATEGORY,
                "enabled": _ENABLED,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        return
    for name, _ in _ROWS:
        bind.execute(
            sa.text("DELETE FROM content_recsys WHERE name = :name"), {"name": name}
        )
