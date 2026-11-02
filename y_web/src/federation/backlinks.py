"""Back-links of cross-posted content in a World Simulation: where a post, photo or message was copied from, and where it
was copied to.

Every runtime keeps, for each content it materialised from a cross-post, a row of ``federation_ref`` (``local_kind``,
``local_id``, ``source_ref``); ``source_ref`` is ``ysocial://<federation id>/<member>/<kind>/<origin id>``. This module
reads those tables, read-only, from the database of each experiment (the file the quotes and the analytics read too) and
answers, for a content of an experiment:

* ``origin_for(exp_id, local_id)``  where it comes from: platform label and icon, origin experiment, origin author and the
  address of the origin content in the web interface (no address when the interface of that experiment is not active, the
  content was removed or the platform has no page for it);
* ``copies_for(exp_id, local_id)``  the reverse: the copies of an origin content on the other platforms, with a link each.

A page asks for one content at a time but the answer is computed once per request and experiment, for all the cross-posted
contents of that experiment (one read of ``federation_ref`` and one lookup per platform involved, never one per post);
the number of rows read is bounded. Outside a World Simulation (or without the optional YFederation plugin) the answer is
``None`` / ``[]`` without touching any experiment database, and nothing here may break a page: every error is swallowed."""

from __future__ import annotations

import re
import sqlite3
from typing import Dict, List, Optional

from y_web import db

MAX_ROWS = 2000  # cross-posted contents of one experiment that are resolved per request
MAX_COPIES = 10  # copies listed for one origin content
SQL_CHUNK = 400

PLATFORM_LABELS = {
    "microblogging": "Microblogging",
    "forum": "Forum",
    "photo_sharing": "Photo sharing",
    "instant_messaging": "Instant messaging",
    "dating": "Dating",
}
# name of the icon of the platform (drawn by the partial)
ICONS = {
    "microblogging": "message-circle",
    "forum": "message-square",
    "photo_sharing": "camera",
    "instant_messaging": "send",
    "dating": "heart",
}
# kind of content of each platform in ``federation_ref`` / in the ``source_ref`` (dating has no post card)
LOCAL_KIND = {"microblogging": "post", "forum": "post", "photo_sharing": "photo", "instant_messaging": "message"}
# where to read the author of a content: (id, author name, author id) of the contents asked
AUTHOR_SQL = {
    "microblogging": "SELECT p.id, u.username, p.user_id FROM post p LEFT JOIN user_mgmt u ON u.id = p.user_id WHERE p.id IN ({q})",
    "forum": "SELECT p.id, u.username, p.user_id FROM post p LEFT JOIN user_mgmt u ON u.id = p.user_id WHERE p.id IN ({q})",
    "photo_sharing": "SELECT p.id, u.username, p.user_id FROM photos p LEFT JOIN user_mgmt u ON u.id = p.user_id WHERE p.id IN ({q})",
    "instant_messaging": "SELECT m.id, a.username, m.sender_account_id FROM messages m LEFT JOIN accounts a ON a.id = m.sender_account_id WHERE m.id IN ({q})",
}
# the page of a content in the web interface (same conventions as ``profile_badges.PROFILE_PATHS``)
CONTENT_PATHS = {
    "microblogging": "/{exp}/thread/{id}",
    "forum": "/{exp}/rthread/{id}",
    "instant_messaging": "/{exp}/im/thread/{id}",
    # a photo has no page of its own: the profile of the author shows it, the anchor is the card of the photo
    "photo_sharing": "/{exp}/photo/profile/{author}/recent/1#feed-post-{id}",
}
_REF = re.compile(r"^ysocial://[^/]+/([^/]+)/([a-z_]+)/(.+)$")


def parse_ref(source_ref) -> Optional[tuple]:
    """``(member, kind, origin id)`` of a ``source_ref``, or ``None`` when it does not have the expected shape."""
    match = _REF.match(str(source_ref or ""))
    return match.groups() if match else None


def content_href(platform_type: str, exp_id, local_id, author_id=None) -> Optional[str]:
    path = CONTENT_PATHS.get(platform_type)
    if not path or (platform_type == "photo_sharing" and author_id in (None, "")):
        return None
    return path.format(exp=int(exp_id), id=local_id, author=author_id)


def _db_path(exp) -> Optional[str]:
    from y_web.src.federation.service import experiment_dir

    return str(experiment_dir(exp) / "database_server.db")


def _query(path, sql, params=()) -> list:
    """Rows of a read-only query on a server database; ``[]`` when the file or a table does not exist."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    except Exception:  # noqa: BLE001
        return []
    try:
        conn.execute("PRAGMA query_only = ON")
        return conn.execute(sql, params).fetchall()
    except Exception:  # noqa: BLE001 - no back-link rather than a broken page
        return []
    finally:
        conn.close()


def _contents(path, platform_type, ids) -> Dict[str, tuple]:
    """``{id (str): (author name, author id)}`` of the contents that exist among ``ids`` (removed ones are absent)."""
    sql = AUTHOR_SQL.get(platform_type)
    ids = sorted({str(i) for i in ids})
    out: Dict[str, tuple] = {}
    if not sql:
        return out
    for start in range(0, len(ids), SQL_CHUNK):
        chunk = ids[start:start + SQL_CHUNK]
        for cid, name, author_id in _query(path, sql.format(q=",".join("?" * len(chunk))), chunk):
            out[str(cid)] = (name or "", "" if author_id is None else str(author_id))
    return out


def _world(exp_id) -> Optional[dict]:
    """The members of the World Simulation of ``exp_id``: ``{"own": member name, "members": {name: info}}``."""
    from y_web.src.models.admin import Exps, FederationMember

    own = db.session.query(FederationMember).filter_by(exp_id=int(exp_id)).first()
    if own is None:
        return None
    members = {}
    for m in db.session.query(FederationMember).filter_by(federation_pk=own.federation_pk):
        exp = db.session.get(Exps, m.exp_id)
        if exp is None:
            continue
        members[m.member] = {"member": m.member, "platform_type": m.platform_type, "exp_id": m.exp_id,
                             "exp_name": exp.exp_name, "active": exp.status == 1, "exp": exp}
    if own.member not in members:
        return None
    return {"own": own.member, "members": members}


def _info(member, kind, found, local_id) -> dict:
    """What the partial shows for the content ``local_id`` of ``member``; ``found`` is ``(author, author id)`` or None."""
    ptype = member["platform_type"]
    author, author_id = found if found else ("", "")
    href = content_href(ptype, member["exp_id"], local_id, author_id) if found and member["active"] else None
    # ``label`` is the name of the experiment (never the platform type: a World Simulation can hold several experiments of the
    # same type); ``type_label`` and ``icon`` describe the type
    return {"member": member["member"], "platform_type": ptype,
            "label": member["exp_name"] or member["member"].replace("_", " ").capitalize(),
            "type_label": PLATFORM_LABELS.get(ptype, member["member"].replace("_", " ").capitalize()),
            "icon": ICONS.get(ptype, "link"), "exp_id": member["exp_id"], "exp_name": member["exp_name"],
            "kind": kind, "id": str(local_id), "author": author or None, "available": bool(found), "href": href}


def _origins(world) -> Dict[str, dict]:
    """``{local id: origin}`` for every cross-posted content of the experiment (one read of its ``federation_ref``)."""
    me = world["members"][world["own"]]
    kind = LOCAL_KIND.get(me["platform_type"])
    if kind is None:
        return {}
    rows = _query(_db_path(me["exp"]),
                  "SELECT local_id, source_ref FROM federation_ref WHERE local_kind = ? ORDER BY rowid DESC LIMIT ?",
                  (kind, MAX_ROWS))
    wanted: Dict[str, List[tuple]] = {}  # origin member -> [(local id, origin kind, origin id)]
    for local_id, ref in rows:
        parsed = parse_ref(ref)
        if parsed and parsed[0] in world["members"] and parsed[0] != world["own"]:
            wanted.setdefault(parsed[0], []).append((str(local_id), parsed[1], parsed[2]))
    out: Dict[str, dict] = {}
    for name, items in wanted.items():
        member = world["members"][name]
        known = LOCAL_KIND.get(member["platform_type"])
        found = _contents(_db_path(member["exp"]), member["platform_type"], [i for _l, k, i in items if k == known])
        for local_id, okind, oid in items:
            out[local_id] = _info(member, okind, found.get(oid) if okind == known else None, oid)
    return out


def _copies(world) -> Dict[str, List[dict]]:
    """``{origin content id: [copy, ...]}``: where the contents of the experiment were cross-posted on the other platforms."""
    me = world["members"][world["own"]]
    kind = LOCAL_KIND.get(me["platform_type"])
    if kind is None:
        return {}
    out: Dict[str, List[dict]] = {}
    pattern = f"ysocial://%/{world['own']}/{kind}/%"
    for name in sorted(world["members"]):
        if name == world["own"]:
            continue
        member = world["members"][name]
        path = _db_path(member["exp"])
        rows = _query(path, "SELECT local_kind, local_id, source_ref FROM federation_ref WHERE source_ref LIKE ? "
                            "ORDER BY rowid LIMIT ?", (pattern, MAX_ROWS))
        mine = [(str(lid), parse_ref(ref)) for _k, lid, ref in rows]
        mine = [(lid, p) for lid, p in mine if p and p[0] == world["own"] and p[1] == kind]
        known = LOCAL_KIND.get(member["platform_type"])
        found = _contents(path, member["platform_type"], [lid for lid, _p in mine]) if known else {}
        for lid, parsed in mine:
            copies = out.setdefault(parsed[2], [])
            if len(copies) < MAX_COPIES:
                copies.append(_info(member, known or "", found.get(lid) if known else None, lid))
    return out


def _cached(exp_id) -> dict:
    """``{"origins": ..., "copies": ...}`` of an experiment, computed once per request."""
    from flask import g, has_request_context

    from y_web.src.federation.availability import sdk_available

    empty = {"origins": {}, "copies": {}}
    if exp_id is None or not sdk_available():
        return empty
    cache = g.setdefault("_ws_backlinks", {}) if has_request_context() else None
    if cache is not None and exp_id in cache:
        return cache[exp_id]
    try:
        world = _world(exp_id)
        value = {"origins": _origins(world), "copies": _copies(world)} if world else empty
    except Exception:  # noqa: BLE001 - a page never fails because of the federation
        value = empty
    if cache is not None:
        cache[exp_id] = value
    return value


def origin_for(exp_id, local_id) -> Optional[dict]:
    """Where a cross-posted content comes from, or ``None`` (not a cross-post, not in a World Simulation, no plugin)."""
    try:
        if local_id is None:
            return None
        return _cached(exp_id)["origins"].get(str(local_id))
    except Exception:  # noqa: BLE001
        return None


def copies_for(exp_id, local_id) -> List[dict]:
    """The copies of a content on the other platforms of its World Simulation; ``[]`` when there are none."""
    try:
        if local_id is None:
            return []
        return list(_cached(exp_id)["copies"].get(str(local_id), []))
    except Exception:  # noqa: BLE001
        return []
