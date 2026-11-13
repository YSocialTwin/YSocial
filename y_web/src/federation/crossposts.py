"""Cross-posted contents of a World Simulation, searchable (admin: Cross-posts tab).

One row per ``crosspost.v1`` message of the coordinator's ``federation.db`` (one content copied to one destination), read
read-only and paged on the server: free-text search (text excerpt, author), filters by origin experiment, destination
experiment, agent, state (delivered / pending), mode and tick range, sort by tick, GET parameters only (the address keeps the
query), and the same filters for the CSV export. Everything is keyed by the MEMBER of the World Simulation; the name shown to the
person is the experiment name and the platform type is only the icon.

Each row of a page is then resolved against the databases of the two experiments (one query per experiment and chunk of the
page, never one per row): the origin content from the ``source_ref`` (``ysocial://<fid>/<member>/<kind>/<id>``), its author, and
the copy on the destination, found in the ``federation_ref`` of the destination by ``fed_msg_id`` (or by ``source_ref``).
A content gets an address (the same builders of :mod:`y_web.src.federation.backlinks`) only when the web interface of its
experiment is active (``Exps.status == 1``); otherwise the icon is shown inactive.

Bounds: the page size is 25, 50 or 100, the offset is capped, the total is counted up to ``COUNT_CAP`` and the export stops at
``EXPORT_MAX`` rows. The coordinator owns ``federation.db`` (no index is created by YWeb: it is opened read-only); the queries
filter on ``payload_type`` and order by ``tick_emitted``. A missing file or table gives an empty result, never an error.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Dict, List, Optional

from y_web.src.federation import backlinks
from y_web.src.federation.analytics_etl import SLOTS_PER_DAY
from y_web.src.federation.profile_badges import profile_href

PAGE_SIZES = (25, 50, 100)
DEFAULT_SIZE = 25
MAX_OFFSET = 20000
COUNT_CAP = 100000
EXPORT_MAX = 20000
MAX_GIDS = 400  # identities matched by the name typed in the search box
STATUSES = ("delivered", "pending")
MODES = ("agent_action", "coordinator_rule")
SORTS = ("tick_desc", "tick_asc")
COORDINATOR = "coordinator"  # source_member of the cross-posts the coordinator materialises (crosspost.mode = coordinator_rule)
# where to read the username behind an account id, per platform type
USER_SQL = {
    "instant_messaging": "SELECT id FROM accounts WHERE username LIKE ? ESCAPE '\\' LIMIT ?",
}
DEFAULT_USER_SQL = "SELECT id FROM user_mgmt WHERE username LIKE ? ESCAPE '\\' LIMIT ?"
_TICK = re.compile(r"^\d{1,9}$")

SELECT = (
    "SELECT m.fed_msg_id, m.source_member, m.target_member, m.tick_emitted, "
    "json_extract(m.payload_json, '$.global_agent_id'), json_extract(m.payload_json, '$.source_ref'), "
    "json_extract(m.payload_json, '$.text_excerpt'), json_extract(m.payload_json, '$.kind'), "
    "json_extract(m.payload_json, '$.quoted.author_name'), json_type(m.payload_json, '$.quoted'), d.acked_tick "
    "FROM federation_message m LEFT JOIN federation_delivery d ON d.fed_msg_id = m.fed_msg_id AND d.target_member = m.target_member "
    "WHERE m.payload_type = 'crosspost.v1'"
)


def db_path(fed) -> str:
    return os.path.join(str(getattr(fed, "folder", "") or ""), "federation.db")


def _open(path):
    if not os.path.isfile(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        conn.execute("PRAGMA query_only = ON")
        return conn
    except sqlite3.Error:
        return None


def _like(text: str) -> str:
    return (
        "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    )


def _tick(value) -> Optional[int]:
    value = str(value or "").strip()
    return int(value) if _TICK.match(value) else None


def parse_filters(args, members) -> dict:
    """The filters of a request (``args``: query string), cleaned: unknown members, states and sorts are dropped, the page size
    is one of ``PAGE_SIZES``. ``members``: the member names of the World Simulation."""
    get = (
        (lambda k: str(args.get(k, "") or "").strip())
        if args is not None
        else (lambda k: "")
    )
    members = set(members)
    try:
        size = int(get("size"))
    except ValueError:
        size = DEFAULT_SIZE
    try:
        page = max(1, int(get("page") or 1))
    except ValueError:
        page = 1
    return {
        "q": get("q")[:200],
        "source": get("source") if get("source") in members else "",
        "destination": get("destination") if get("destination") in members else "",
        "agent": get("agent")[:80],
        "status": get("status") if get("status") in STATUSES else "",
        "mode": get("mode") if get("mode") in MODES else "",
        "tick_from": _tick(get("tick_from")),
        "tick_to": _tick(get("tick_to")),
        "ref": get("ref")[:200],
        "sort": get("sort") if get("sort") in SORTS else "tick_desc",
        "size": size if size in PAGE_SIZES else DEFAULT_SIZE,
        "page": page,
    }


def query_args(f: dict, **over) -> dict:
    """The filters as GET parameters (only what is set), for the links of the pager, the sort and the export."""
    out = {k: v for k, v in f.items() if v not in ("", None) and k != "page"}
    if out.get("sort") == "tick_desc":
        del out["sort"]
    if out.get("size") == DEFAULT_SIZE:
        del out["size"]
    out.update(over)
    return {k: v for k, v in out.items() if v not in ("", None)}


def _gids_matching(conn, text: str, members: Dict[str, dict]) -> List[str]:
    """Global ids of the agents whose name or username contains ``text`` (bounded)."""
    like, found = _like(text), []
    found.append(text)  # the identity itself
    try:
        found += [
            r[0]
            for r in conn.execute(
                "SELECT global_agent_id FROM federation_agent_name WHERE name LIKE ? ESCAPE '\\' LIMIT ?",
                (like, MAX_GIDS),
            )
        ]
    except sqlite3.Error:
        pass
    for name, member in members.items():
        if len(found) >= MAX_GIDS:
            break
        ids = [
            str(r[0])
            for r in backlinks._query(
                backlinks._db_path(member["exp"]),
                USER_SQL.get(member["platform_type"], DEFAULT_USER_SQL),
                (like, 200),
            )
        ]
        for start in range(0, len(ids), 300):
            chunk = ids[start : start + 300]
            try:
                found += [
                    r[0]
                    for r in conn.execute(
                        "SELECT global_agent_id FROM federation_identity WHERE member = ? AND local_account_id IN (%s) LIMIT ?"
                        % ",".join("?" * len(chunk)),
                        [name] + chunk + [MAX_GIDS],
                    )
                ]
            except sqlite3.Error:
                pass
    return list(dict.fromkeys(found))[:MAX_GIDS]


def _where(conn, f: dict, members: Dict[str, dict]):
    sql, args = "", []
    if f["source"]:
        sql += " AND json_extract(m.payload_json, '$.source_ref') LIKE ?"
        args.append(f"ysocial://%/{f['source']}/%")
    if f["destination"]:
        sql += " AND m.target_member = ?"
        args.append(f["destination"])
    if f["agent"]:
        sql += " AND json_extract(m.payload_json, '$.global_agent_id') = ?"
        args.append(f["agent"])
    if f["ref"]:
        sql += " AND json_extract(m.payload_json, '$.source_ref') = ?"
        args.append(f["ref"])
    if f["status"] == "delivered":
        sql += " AND d.acked_tick IS NOT NULL"
    elif f["status"] == "pending":
        sql += " AND d.acked_tick IS NULL"
    if f["mode"] == "coordinator_rule":
        sql += " AND m.source_member = ?"
        args.append(COORDINATOR)
    elif f["mode"] == "agent_action":
        sql += " AND m.source_member != ?"
        args.append(COORDINATOR)
    if f["tick_from"] is not None:
        sql += " AND m.tick_emitted >= ?"
        args.append(f["tick_from"])
    if f["tick_to"] is not None:
        sql += " AND m.tick_emitted <= ?"
        args.append(f["tick_to"])
    if f["q"]:
        gids = _gids_matching(conn, f["q"], members)
        sql += " AND (json_extract(m.payload_json, '$.text_excerpt') LIKE ? ESCAPE '\\'"
        args.append(_like(f["q"]))
        if gids:
            sql += (
                " OR json_extract(m.payload_json, '$.global_agent_id') IN (%s)"
                % ",".join("?" * len(gids))
            )
            args += gids
        sql += ")"
    return sql, args


def _members(fed) -> Dict[str, dict]:
    """``{member: {member, platform_type, exp_id, exp_name, active, exp}}`` of the World Simulation."""
    from y_web.src.federation import service

    out = {}
    for row, exp in service.members_of(fed):
        if exp is not None:
            out[row.member] = {
                "member": row.member,
                "platform_type": row.platform_type,
                "exp_id": row.exp_id,
                "exp_name": exp.exp_name,
                "active": exp.status == 1,
                "exp": exp,
            }
    return out


def _icon(member: Optional[dict], name: str) -> dict:
    """The part of a row that draws one platform: icon (type), tooltip name (experiment) and activity of its frontend."""
    if member is None:
        return {
            "member": name,
            "platform_type": "",
            "icon": "link",
            "exp_name": name.replace("_", " ").capitalize(),
            "exp_id": None,
            "active": False,
        }
    return {
        "member": name,
        "platform_type": member["platform_type"],
        "icon": backlinks.ICONS.get(member["platform_type"], "link"),
        "exp_name": member["exp_name"] or name,
        "exp_id": member["exp_id"],
        "active": member["active"],
    }


def _copies(member: dict, rows) -> Dict[str, tuple]:
    """``{fed_msg_id: (local kind, local id)}`` of the copies on the destination, by ``fed_msg_id`` and, for those not found,
    by ``source_ref`` (one chunked query each; ``rows``: ``[(fed_msg_id, source_ref)]``).
    """
    path, out = backlinks._db_path(member["exp"]), {}
    ids = sorted({r[0] for r in rows})
    for start in range(0, len(ids), backlinks.SQL_CHUNK):
        chunk = ids[start : start + backlinks.SQL_CHUNK]
        for fid, kind, lid in backlinks._query(
            path,
            "SELECT fed_msg_id, local_kind, local_id FROM federation_ref WHERE fed_msg_id IN (%s)"
            % ",".join("?" * len(chunk)),
            chunk,
        ):
            out[fid] = (kind, lid)
    missing = {fid: ref for fid, ref in rows if fid not in out}
    refs = sorted(set(missing.values()))
    by_ref: Dict[str, tuple] = {}
    for start in range(0, len(refs), backlinks.SQL_CHUNK):
        chunk = refs[start : start + backlinks.SQL_CHUNK]
        for ref, kind, lid in backlinks._query(
            path,
            "SELECT source_ref, local_kind, local_id FROM federation_ref WHERE source_ref IN (%s)"
            % ",".join("?" * len(chunk)),
            chunk,
        ):
            by_ref.setdefault(ref, (kind, lid))
    for fid, ref in missing.items():
        if ref in by_ref:
            out[fid] = by_ref[ref]
    return out


def _resolve(conn, raw: list, members: Dict[str, dict]) -> List[dict]:
    """Rows of the page: the raw message rows plus origin, destination, author and delivery, in the order of ``raw``."""
    parsed = [backlinks.parse_ref(r[5]) for r in raw]
    # origin contents, per member: one query for the authors of the contents of the page
    wanted: Dict[str, set] = {}
    for p in parsed:
        if (
            p
            and p[0] in members
            and backlinks.LOCAL_KIND.get(members[p[0]]["platform_type"]) == p[1]
        ):
            wanted.setdefault(p[0], set()).add(p[2])
    found = {
        m: backlinks._contents(
            backlinks._db_path(members[m]["exp"]), members[m]["platform_type"], ids
        )
        for m, ids in wanted.items()
    }
    # copies on the destinations, per destination member
    asked: Dict[str, list] = {}
    for r in raw:
        if r[2] in members and r[10] is not None:  # a copy exists only once delivered
            asked.setdefault(r[2], []).append((r[0], r[5]))
    copies = {m: _copies(members[m], rows) for m, rows in asked.items()}
    copy_authors = {}
    for m, by in copies.items():
        known = backlinks.LOCAL_KIND.get(members[m]["platform_type"])
        ids = [lid for kind, lid in by.values() if kind == known]
        copy_authors[m] = (
            backlinks._contents(
                backlinks._db_path(members[m]["exp"]), members[m]["platform_type"], ids
            )
            if known
            else {}
        )
    gids = sorted({r[4] for r in raw if r[4]})
    names, accounts = {}, {}
    if gids:
        try:
            for start in range(0, len(gids), 400):
                chunk = gids[start : start + 400]
                marks = ",".join("?" * len(chunk))
                names.update(
                    conn.execute(
                        "SELECT global_agent_id, name FROM federation_agent_name WHERE global_agent_id IN (%s)"
                        % marks,
                        chunk,
                    )
                )
                accounts.update(
                    {
                        (g, m): a
                        for g, m, a in conn.execute(
                            "SELECT global_agent_id, member, local_account_id FROM federation_identity WHERE global_agent_id IN (%s)"
                            % marks,
                            chunk,
                        )
                    }
                )
        except sqlite3.Error:
            pass
    out = []
    for r, p in zip(raw, parsed):
        (
            fid,
            source_member,
            target,
            tick,
            gid,
            ref,
            text,
            kind,
            quoted_author,
            quoted_type,
            acked,
        ) = r
        origin_member = (
            p[0] if p else (source_member if source_member != COORDINATOR else "")
        )
        origin_info = members.get(origin_member)
        origin = _icon(origin_info, origin_member)
        author, author_id, href = "", "", None
        origin_known = origin_info is not None and backlinks.LOCAL_KIND.get(
            origin_info["platform_type"]
        ) == (p[1] if p else None)
        hit = found.get(origin_member, {}).get(p[2]) if p and origin_known else None
        if hit:
            author, author_id = hit
        author = author or names.get(gid) or (gid or "")
        author_id = author_id or accounts.get((gid, origin_member)) or ""
        origin["id"] = p[2] if p else ""
        origin["available"] = bool(hit)
        origin["href"] = (
            backlinks.content_href(
                origin_info["platform_type"], origin_info["exp_id"], p[2], author_id
            )
            if hit and origin_info["active"]
            else None
        )
        author_href = (
            profile_href(origin_info["platform_type"], origin_info["exp_id"], author_id)
            if origin_info and origin_info["active"] and author_id
            else None
        )
        dest_info = members.get(target)
        dest = _icon(dest_info, target)
        copy = copies.get(target, {}).get(fid)
        dest["delivered"] = acked is not None
        dest["id"] = str(copy[1]) if copy else ""
        dest["available"] = bool(copy)
        dest["href"] = None
        if copy and dest_info is not None and dest_info["active"]:
            who = copy_authors.get(target, {}).get(str(copy[1]))
            dest["href"] = backlinks.content_href(
                dest_info["platform_type"],
                dest_info["exp_id"],
                copy[1],
                who[1] if who else None,
            )
        out.append(
            {
                "fed_msg_id": fid,
                "tick": tick,
                "day": tick // SLOTS_PER_DAY,
                "slot": tick % SLOTS_PER_DAY,
                "global_agent_id": gid or "",
                "author": author,
                "author_id": author_id,
                "author_href": author_href,
                "text": text or "",
                "kind": kind or "",
                "shared": quoted_type is not None,
                "shared_from": quoted_author or "",
                "origin": origin,
                "destination": dest,
                "mode": (
                    "coordinator_rule"
                    if source_member == COORDINATOR
                    else "agent_action"
                ),
                "delivered": acked is not None,
                "delivered_tick": acked,
                "source_ref": ref or "",
            }
        )
    return out


def search(
    fed, f: dict, *, limit: Optional[int] = None, offset: Optional[int] = None
) -> dict:
    """``{"rows", "total", "capped", "available"}`` of the filters ``f`` (see :func:`parse_filters`). ``total`` stops at
    ``COUNT_CAP`` (``capped``). Without ``limit`` the page of ``f`` is returned."""
    result = {"rows": [], "total": 0, "capped": False, "available": False}
    conn = _open(db_path(fed))
    if conn is None:
        return result
    try:
        members = _members(fed)
        result["available"] = True
        where, args = _where(conn, f, members)
        base = SELECT + where
        total = conn.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM federation_message m LEFT JOIN federation_delivery d ON "
            "d.fed_msg_id = m.fed_msg_id AND d.target_member = m.target_member WHERE m.payload_type = 'crosspost.v1'"
            + where
            + " LIMIT ?)",
            args + [COUNT_CAP],
        ).fetchone()[0]
        result["total"], result["capped"] = total, total >= COUNT_CAP
        limit = f["size"] if limit is None else limit
        offset = (
            min(MAX_OFFSET, (f["page"] - 1) * f["size"]) if offset is None else offset
        )
        order = "ASC" if f["sort"] == "tick_asc" else "DESC"
        raw = conn.execute(
            f"{base} ORDER BY m.tick_emitted {order}, m.fed_msg_id LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
        result["rows"] = _resolve(conn, raw, members)
    except sqlite3.Error:
        result["rows"], result["total"] = [], 0  # no table yet: an empty list
    finally:
        conn.close()
    return result


def export_rows(fed, f: dict) -> List[dict]:
    """Every row of the filters (at most ``EXPORT_MAX``), resolved in chunks of 100."""
    out: List[dict] = []
    for offset in range(0, EXPORT_MAX, 100):
        page = search(fed, f, limit=min(100, EXPORT_MAX - offset), offset=offset)[
            "rows"
        ]
        out += page
        if len(page) < 100:
            break
    return out


CSV_COLUMNS = [
    "tick",
    "day",
    "slot",
    "author",
    "global_agent_id",
    "origin_experiment",
    "origin_platform",
    "origin_content_id",
    "origin_url",
    "destination_experiment",
    "destination_platform",
    "destination_content_id",
    "destination_url",
    "text",
    "mode",
    "delivered",
    "delivered_tick",
    "shared_content_of",
    "fed_msg_id",
]


def csv_row(r: dict) -> list:
    o, d = r["origin"], r["destination"]
    return [
        r["tick"],
        r["day"],
        r["slot"],
        r["author"],
        r["global_agent_id"],
        o["exp_name"],
        o["platform_type"],
        o["id"],
        o["href"] or "",
        d["exp_name"],
        d["platform_type"],
        d["id"],
        d["href"] or "",
        r["text"],
        r["mode"],
        "yes" if r["delivered"] else "no",
        "" if r["delivered_tick"] is None else r["delivered_tick"],
        r["shared_from"],
        r["fed_msg_id"],
    ]
