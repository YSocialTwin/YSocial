"""The recommender systems a platform adds to the catalogue the selectors of the pages list.

A platform declares them in ``PlatformProvider.recsys_catalog`` (one dict per recommender: ``kind`` is ``content`` or
``follow``, then ``name``, ``label``, ``category`` and ``enabled``, the runtime the algorithm is offered for:
``Standard``, ``HPC`` or ``HumanOnly``). :func:`ensure_catalog` adds the ones the tables do not have yet, by name; a
row that exists is never changed, so what an administrator edited stays.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select


def _models():
    from y_web.src.models import Content_Recsys, Follow_Recsys

    return {"content": Content_Recsys, "follow": Follow_Recsys}


def ensure_catalog(session: Optional[Any] = None) -> int:
    """Insert the declared recommenders that are missing; return how many were inserted."""
    from y_web import db
    from y_web.platforms import registry

    session = session or db.session
    models = _models()
    inserted = 0
    known = {
        kind: {str(name).lower() for name in session.scalars(select(model.name)).all()}
        for kind, model in models.items()
    }
    for provider in registry.all_providers():
        for row in provider.recsys_catalog:
            kind = row.get("kind", "content")
            model = models.get(kind)
            name = str(row.get("name", "")).strip()
            if model is None or not name or name.lower() in known[kind]:
                continue
            session.add(
                model(
                    name=name,
                    value=row.get("label", name),
                    category=row.get("category"),
                    enabled=row.get("enabled", "Standard"),
                )
            )
            known[kind].add(name.lower())
            inserted += 1
    if inserted:
        session.commit()
    return inserted
