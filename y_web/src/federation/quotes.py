"""Attribution of shared content in the views of the members of a World Simulation (P4, E3).

When a cross-post that shares the content of another agent reaches a platform, the runtime writes the post with an
attribution line and keeps the structured reference (original author, platform, excerpt) in its own table
``federation_quoted`` (keyed by the local post, photo or message id). This module reads that table, read-only, from the
database of the experiment (the file the analytics read too), so the pages can show a small attribution block.

Nothing here may break a page: an experiment that is not in a World Simulation costs no query at all (NFR-01), a missing
table or database gives no attribution, and every error is swallowed."""

from __future__ import annotations

import sqlite3

# Local id column of federation_quoted in each runtime (YServer/YServerReddit: post_id, YPhotoSharing: photo_id,
# YInstantMessaging: message_id, YDating: local_id).
ID_COLUMNS = ("post_id", "photo_id", "message_id", "local_id")
PLATFORM_LABELS = {
    "microblogging": "Microblogging",
    "forum": "Forum",
    "photo_sharing": "Photo sharing",
    "instant_messaging": "Instant messaging",
    "dating": "Dating",
}
MAX_ROWS = 5000


def platform_label(member, names=None) -> str:
    """Display name of the platform where the shared content was seen: the name of its experiment when ``names`` knows the
    member, otherwise the member name (spelled as a platform type when it is one)."""
    if names and names.get(str(member)):
        return names[str(member)]
    return PLATFORM_LABELS.get(str(member), str(member))


def read_quotes(path, names=None) -> dict:
    """``{local id (str): {author_name, member, platform, excerpt, source_ref}}`` of one server database, read only.

    ``platform`` is the name of the experiment the content was seen on (``names``: ``{member: experiment name}``), the platform
    type is never shown. Empty when the file or the table does not exist or cannot be read."""
    out: dict = {}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    except Exception:  # noqa: BLE001
        return out
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(federation_quoted)")]
        key = next((c for c in ID_COLUMNS if c in cols), None)
        if key is None or "author_name" not in cols:
            return out
        for row in conn.execute(
            f"SELECT {key}, author_name, member, text_excerpt, source_ref FROM federation_quoted LIMIT {MAX_ROWS}"
        ):
            out[str(row[0])] = {
                "author_name": row[1] or "",
                "member": row[2] or "",
                "platform": platform_label(row[2], names),
                "excerpt": row[3] or "",
                "source_ref": row[4],
            }
    except Exception:  # noqa: BLE001 - no attribution rather than a broken page
        return {}
    finally:
        conn.close()
    return out


def _database_path(exp_id):
    from y_web.src.federation.service import experiment_dir
    from y_web.src.models.admin import Exps
    from y_web import db

    exp = db.session.get(Exps, exp_id)
    return str(experiment_dir(exp) / "database_server.db") if exp is not None else None


def quotes_for(exp_id, ids=None) -> dict:
    """The attributions of an experiment, for the local ids asked (all of them when ``ids`` is None).

    ``{}`` when the experiment is not a member of a World Simulation, without touching its database."""
    try:
        from y_web.src.federation.service import world_simulation_of

        if exp_id is None or world_simulation_of(exp_id) is None:
            return {}
        from y_web.src.federation.names import world_names

        path = _database_path(exp_id)
        rows = read_quotes(path, world_names(exp_id)) if path else {}
        if ids is None:
            return rows
        wanted = {str(i) for i in ids}
        return {k: v for k, v in rows.items() if k in wanted}
    except Exception:  # noqa: BLE001
        return {}


def federation_quote(exp_id, local_id):
    """Template helper: the attribution of one post, photo or message (None when it has none). One read of the table per
    request and experiment; nothing at all outside a World Simulation."""
    try:
        from flask import g, has_request_context

        if local_id is None or exp_id is None:
            return None
        cache = None
        if has_request_context():
            cache = g.setdefault("_federation_quotes", {})
        if cache is not None and exp_id in cache:
            rows = cache[exp_id]
        else:
            rows = quotes_for(exp_id)
            if cache is not None:
                cache[exp_id] = rows
        return rows.get(str(local_id))
    except Exception:  # noqa: BLE001
        return None
