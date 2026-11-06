"""Chronological ordering key of forum rows, independent of the id type.

Rows of a YForum database carry a server-assigned, monotonic ``seq`` column while ids are UUIDs
(random, so they say nothing about the order). Standard experiment databases have no ``seq`` and
their integer ids are already monotonic: ``seq_or_id`` returns ``seq`` when the table has it and
the ``id`` column otherwise, so the same query serves both.
"""

from typing import Dict, Tuple

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import Integer, column

from y_web import db

_HAS_SEQ: Dict[Tuple[str, str], bool] = {}
_LAYOUT: Dict[Tuple[str, str], Tuple[bool, bool]] = {}


def _table_has_seq(table_name: str) -> bool:
    try:
        engine = db.engines["db_exp"]
        key = (str(engine.url), table_name)
        if key not in _HAS_SEQ:
            columns = {c["name"] for c in sa_inspect(engine).get_columns(table_name)}
            _HAS_SEQ[key] = "seq" in columns
        return _HAS_SEQ[key]
    except Exception:
        return False


def table_layout(engine, table_name: str) -> Tuple[bool, bool]:
    """``(id_is_text, has_seq)`` of ``table_name`` in the database behind ``engine`` (cached)."""
    key = (str(engine.url), "layout:" + table_name)
    if key not in _LAYOUT:
        try:
            columns = {
                c["name"]: c["type"] for c in sa_inspect(engine).get_columns(table_name)
            }
            id_type = columns.get("id")
            _LAYOUT[key] = (
                id_type is not None and not isinstance(id_type, Integer),
                "seq" in columns,
            )
        except Exception:
            return (False, False)  # not cached: the table may appear later
    return _LAYOUT[key]


def forget_cached_schema() -> None:
    """Drop what was learnt about the tables (after a schema change or an experiment switch)."""
    _HAS_SEQ.clear()
    _LAYOUT.clear()


def seq_or_id(entity):
    """SQL expression ordering ``entity`` (a model or an ``aliased`` model) in insertion order."""
    selectable = sa_inspect(entity).selectable
    base = getattr(sa_inspect(entity), "mapper", None)
    table = base.local_table.name if base is not None else getattr(selectable, "name", "")
    if _table_has_seq(table):
        # a column of the very selectable the query uses (the table itself, or the alias of it)
        return column("seq", Integer, _selectable=selectable)
    return entity.id
