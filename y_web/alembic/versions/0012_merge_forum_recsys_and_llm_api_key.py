"""Merge the forum recsys columns and the stored LLM API key.

Two branches added a revision after 0010: ``0011_add_forum_recsys_rows`` (YForum) and
``0011_add_admin_users_llm_api_key`` (API key of the LLM server). They touch different tables, so
this revision only joins the two heads.

Revision ID: 0012_merge_forum_recsys_and_llm_api_key
Revises: 0011_add_forum_recsys_rows, 0011_add_admin_users_llm_api_key
"""

from typing import Sequence, Union

revision: str = "0012_merge_forum_recsys_and_llm_api_key"
down_revision: Union[str, Sequence[str], None] = (
    "0011_add_forum_recsys_rows",
    "0011_add_admin_users_llm_api_key",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
