"""Ids and ``seq`` of the rows a person (YWeb) writes into a database that does not number them itself.

A YForum database has UUID string ids and a server-assigned ``seq`` (NOT NULL, UNIQUE) on 14 tables, and no database
default for either. The ORM models of YWeb were written for integer autoincrement ids, so an insert of a forum action
(post, comment, vote, follow, report...) would omit both. Two hooks fix that, and only for the tables of such a
database:

* ``fill_insert`` (mapper ``before_insert``): a new UUID as ``id`` when the table has a text id and none was set;
* ``number_inserts`` (engine ``before_execute``): the insert gets ``seq = MAX(seq) + 1`` computed by the statement
  itself (the YForum server continues after it, see ``SequenceAllocator``), when the table has the column.

``seq`` is declared on the Core table only (``add_seq_columns``), never on the models and never created by
``create_all``, so queries and inserts of every other database are unchanged.
"""

import uuid

from sqlalchemy import Column, Integer, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import CreateColumn
from sqlalchemy.sql.dml import Insert

from y_web import db

# the tables of a YForum database that carry ``seq`` (YForum ``models.SEQ_TABLES``)
SEQ_TABLES = (
    "user_mgmt",
    "rounds",
    "post",
    "follow",
    "reactions",
    "mentions",
    "interests",
    "articles",
    "images",
    "post_sentiment",
    "agent_opinion",
    "memory_interaction_events",
    "memory_items",
    "memory_community_digests",
)


@compiles(CreateColumn)
def _skip_mapped_seq(element, compiler, **kw):
    """The mapped ``seq`` is never part of the tables YWeb creates: only the databases that have it use it."""
    if element.element.info.get("yweb_forum_seq"):
        return None
    return compiler.visit_create_column(element, **kw)


def add_seq_columns() -> None:
    """Declare ``seq`` on the tables of the ``SEQ_TABLES`` without mapping it on the models.

    The column is only known to the Core table: it is never selected by the ORM, never created by ``create_all``
    (see ``_skip_mapped_seq``) and never part of an ORM insert; ``number_inserts`` adds it to the inserts that go to
    a database which has it.
    """
    for mapper in list(db.Model.registry.mappers):
        cls = mapper.class_
        table = getattr(cls, "__table__", None)
        if (
            getattr(cls, "__bind_key__", None) != "db_exp"
            or table is None
            or table.name not in SEQ_TABLES
            or "seq" in table.c
        ):
            continue
        table.append_column(
            Column("seq", Integer, nullable=True, info={"yweb_forum_seq": True})
        )


def number_inserts(conn, clauseelement, multiparams, params, execution_options):
    """Give the ``seq`` of the table to an insert that goes to a database with that column.

    The number is computed by the insert itself (``MAX(seq) + 1`` of the table, in the same statement), so rows
    inserted one after the other, or by the YForum server at the same time, never take the same value.
    """
    if not isinstance(clauseelement, Insert):
        return clauseelement, multiparams, params
    table = clauseelement.table
    if (
        table.name not in SEQ_TABLES
        or "seq" not in table.c
        or not table.c.seq.info.get("yweb_forum_seq")
    ):
        return clauseelement, multiparams, params
    from y_web.src.forum.ordering import (  # lazy: the forum package imports the models
        table_layout,
    )

    if not table_layout(conn.engine, table.name)[1]:
        return (
            clauseelement,
            multiparams,
            params,
        )  # this database has no seq (every other platform)
    next_number = (
        select(func.coalesce(func.max(table.c.seq), 0) + 1)
        .select_from(table)
        .scalar_subquery()
    )
    return clauseelement.values(seq=next_number), multiparams, params


def fill_insert(mapper, connection, target) -> None:
    cls = mapper.class_
    if getattr(cls, "__bind_key__", None) != "db_exp":
        return
    table = mapper.local_table.name
    from y_web.src.forum.ordering import (  # lazy: the forum package imports the models
        table_layout,
    )

    id_is_text, _has_seq = table_layout(connection.engine, table)
    if id_is_text and hasattr(target, "id") and getattr(target, "id", None) is None:
        target.id = str(uuid.uuid4())


def install() -> None:
    add_seq_columns()
    if not event.contains(Engine, "before_execute", number_inserts):
        event.listen(Engine, "before_execute", number_inserts, retval=True)
    if not event.contains(db.Model, "before_insert", fill_insert):
        event.listen(db.Model, "before_insert", fill_insert, propagate=True)
