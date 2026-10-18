"""Merge hashtags that differ only by a leading ``#`` or by case, and store them in canonical form.

Older experiments hold the same hashtag several times (``#Sustainability``, ``Sustainability``,
``sustainability``): trending lists and hashtag pages then count them apart. This brings an experiment
database to the canonical form of :mod:`y_web.hashtag_text` (no ``#``; first spelling kept; identity
ignores case). It is idempotent, works on Standard (integer ids) and HPC/photo (uuid ids) databases, and
re-points the link tables to the surviving row. Texts that were cut when stored (``#c`` for
``#c'e...``) cannot be recovered and are left as they are.
"""

import logging
from collections import OrderedDict

from sqlalchemy import create_engine, inspect, text

from y_web.hashtag_text import hashtag_key, normalize_hashtag

logger = logging.getLogger(__name__)

# link table -> column that identifies the owner of the tag
_LINK_TABLES = {"post_hashtags": "post_id", "photo_hashtags": "photo_id"}


def merge_duplicate_hashtags(engine):
    """Normalize and merge the hashtags of one experiment database; returns ``{"merged": n, "renamed": m}``."""
    result = {"merged": 0, "renamed": 0}
    tables = set(inspect(engine).get_table_names())
    if "hashtags" not in tables:
        return result
    links = {
        table: owner
        for table, owner in _LINK_TABLES.items()
        if table in tables
        and {"hashtag_id", owner} <= {c["name"] for c in inspect(engine).get_columns(table)}
    }
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, hashtag FROM hashtags ORDER BY id")).fetchall()
        groups = OrderedDict()
        for row in rows:
            key = hashtag_key(row[1])
            if key:
                groups.setdefault(key, []).append(row)
        for members in groups.values():
            keeper = members[0]
            canonical = normalize_hashtag(keeper[1])
            if canonical != keeper[1]:
                conn.execute(
                    text("UPDATE hashtags SET hashtag = :h WHERE id = :i"),
                    {"h": canonical, "i": keeper[0]},
                )
                result["renamed"] += 1
            for dup in members[1:]:
                for table, owner in links.items():
                    conn.execute(
                        text(
                            f"UPDATE {table} SET hashtag_id = :k WHERE hashtag_id = :d AND NOT EXISTS "
                            f"(SELECT 1 FROM (SELECT {owner} AS o FROM {table} WHERE hashtag_id = :k) AS t "
                            f"WHERE t.o = {table}.{owner})"
                        ),
                        {"k": keeper[0], "d": dup[0]},
                    )
                    conn.execute(text(f"DELETE FROM {table} WHERE hashtag_id = :d"), {"d": dup[0]})
                conn.execute(text("DELETE FROM hashtags WHERE id = :d"), {"d": dup[0]})
                result["merged"] += 1
    return result


def merge_duplicate_hashtags_for_uri(db_uri):
    """Same as :func:`merge_duplicate_hashtags` for a database URI; never raises."""
    try:
        engine = create_engine(db_uri)
        try:
            result = merge_duplicate_hashtags(engine)
        finally:
            engine.dispose()
        if result["merged"] or result["renamed"]:
            logger.info("hashtags normalized in %s: %s", db_uri, result)
        return result
    except Exception as exc:  # pragma: no cover - best effort, retried at the next start
        logger.warning("hashtag normalization skipped for %s: %s", db_uri, exc)
        return None
