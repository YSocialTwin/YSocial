"""The recommender systems a platform adds to the catalogue the selectors of the pages list.

A platform declares them in ``PlatformProvider.recsys_catalog`` (one dict per recommender: ``kind`` is ``content`` or
``follow``, then ``name``, ``label``, ``category`` and ``enabled``, the runtime the algorithm is offered for:
``Standard``, ``HPC`` or ``HumanOnly``). :func:`ensure_catalog` adds the ones the tables do not have yet, by name.
A row that exists keeps what it has: only an empty ``enabled`` or ``category`` (databases of older releases) is filled
from the declaration, so what an administrator edited stays. The tables ship empty: every row comes from a platform.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select


def _models():
    from y_web.src.models import Content_Recsys, Follow_Recsys

    return {"content": Content_Recsys, "follow": Follow_Recsys}


def ensure_catalog(session: Optional[Any] = None) -> int:
    """Insert the declared recommenders that are missing and fill what a row left empty; return how many changes."""
    from y_web import db
    from y_web.platforms import registry

    session = session or db.session
    models = _models()
    inserted = 0
    existing = {
        kind: {
            str(row.name).lower(): row for row in session.scalars(select(model)).all()
        }
        for kind, model in models.items()
    }
    for provider in registry.all_providers():
        for row in provider.recsys_catalog:
            kind = row.get("kind", "content")
            model = models.get(kind)
            name = str(row.get("name", "")).strip()
            if model is None or not name:
                continue
            current = existing[kind].get(name.lower())
            if current is not None:
                # only what an older release left empty
                for column, value in (
                    ("enabled", row.get("enabled", "Standard")),
                    ("category", row.get("category")),
                ):
                    if value and not (getattr(current, column) or "").strip():
                        setattr(current, column, value)
                        inserted += 1
                continue
            record = model(
                name=name,
                value=row.get("label", name),
                category=row.get("category"),
                enabled=row.get("enabled", "Standard"),
            )
            session.add(record)
            existing[kind][name.lower()] = record
            inserted += 1
    if inserted:
        session.commit()
    return inserted
