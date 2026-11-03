"""Who is active where in a World Simulation: one row per identity, one state per platform (read-only).

The state of each account comes from the coordinator's ``federation.db`` (``federation_identity``: ``active``, ``dormant``,
``left`` or ``ineligible``, with the ticks of joining and leaving); before the first run the file does not exist and every
account is listed as ``not started``. Names come from the YWeb agents and from the enrolled people. Nothing is written.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Optional

from y_web import db

STATES = ("active", "dormant", "left", "ineligible", "not started")
PAGE_SIZE = 100


def _coordinator(folder) -> Optional[Dict[tuple, dict]]:
    path = os.path.join(str(folder or ""), "federation.db")
    if not folder or not os.path.isfile(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None
    try:
        conn.execute("PRAGMA query_only = ON")
        return {
            (g, m): {"state": s, "joined": j, "left": l}
            for g, m, s, j, l in conn.execute(
                "SELECT global_agent_id, member, state, joined_tick, left_tick FROM federation_identity"
            )
        }
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _kinds(folder) -> Dict[str, str]:
    path = os.path.join(str(folder or ""), "federation.db")
    if not folder or not os.path.isfile(path):
        return {}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            return dict(
                conn.execute(
                    "SELECT global_agent_id, kind FROM federation_identity_kind"
                )
            )
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def _stats(folder) -> Optional[Dict[str, dict]]:
    """Cross-posting statistics per ``global_agent_id`` from the ``crosspost.v1`` messages of the coordinator (read-only), or
    ``None`` when the database or the tables cannot be read.

    * ``made_own``: cross-posts the agent made of its OWN content (messages whose author, ``global_agent_id``, is the agent,
      without ``quoted``; one per destination);
    * ``made_others``: cross-posts it made of OTHER agents' content (the same, with ``quoted``: shares);
    * ``times``: delivered copies of its own content (those messages with a row in ``federation_delivery``), and ``by_dest``
      the same per destination member.

    One grouped query per metric; the rows of the agents that cross-posted nothing are absent.
    """
    path = os.path.join(str(folder or ""), "federation.db")
    if not folder or not os.path.isfile(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None
    out: Dict[str, dict] = {}
    cell = lambda g: out.setdefault(
        g, {"made_own": 0, "made_others": 0, "times": 0, "by_dest": {}}
    )  # noqa: E731
    try:
        conn.execute("PRAGMA query_only = ON")
        for gid, shared, n in conn.execute(
            "SELECT json_extract(payload_json, '$.global_agent_id'), json_type(payload_json, '$.quoted') IS NOT NULL, COUNT(*) "
            "FROM federation_message WHERE payload_type = 'crosspost.v1' GROUP BY 1, 2"
        ):
            if gid:
                cell(str(gid))["made_others" if shared else "made_own"] += n
        for gid, target, n in conn.execute(
            "SELECT json_extract(m.payload_json, '$.global_agent_id'), m.target_member, COUNT(*) FROM federation_message m "
            "JOIN federation_delivery d ON d.fed_msg_id = m.fed_msg_id AND d.target_member = m.target_member "
            "WHERE m.payload_type = 'crosspost.v1' AND json_type(m.payload_json, '$.quoted') IS NULL GROUP BY 1, 2"
        ):
            if gid:
                c = cell(str(gid))
                c["times"] += n
                c["by_dest"][target] = n
        return out
    except sqlite3.Error:
        return None
    finally:
        conn.close()


NO_STATS = {"made_own": 0, "made_others": 0, "times": 0, "by_dest": {}}
SORTS = ("name", "made_own", "made_others", "times")
ACTIVITIES = ("made", "crossposted", "none")


def table(fed) -> dict:
    """``{"members": [member], "source": "coordinator"|"links", "rows": [{id, name, kind, states: {member: {...}}}]}`` sorted by
    kind (agents first) and name."""
    from y_web.src.federation import service
    from y_web.src.models.admin import Admin_users, Agent, FederationIdentityLink

    members = [row.member for row, _exp in service.members_of(fed)]
    names_of_members = {
        row.member: (exp.exp_name if exp is not None and exp.exp_name else row.member)
        for row, exp in service.members_of(fed)
    }
    stats = _stats(fed.folder)
    live = _coordinator(fed.folder)
    kinds = _kinds(fed.folder)
    rows: Dict[str, dict] = {}
    for link in (
        db.session.query(FederationIdentityLink)
        .filter_by(federation_pk=fed.id)
        .order_by(FederationIdentityLink.id)
    ):
        gid = link.global_agent_id
        entry = rows.setdefault(
            gid,
            {
                "id": gid,
                "name": "",
                "kind": (
                    "human" if gid.startswith("human:") else kinds.get(gid, "agent")
                ),
                "states": {},
            },
        )
        info = (live or {}).get((gid, link.member)) if live is not None else None
        entry["states"][link.member] = {
            "state": info["state"] if info else "not started",
            "account": link.local_account_id,
            "joined": info["joined"] if info else None,
            "left": info["left"] if info else None,
        }
    agent_ids = [int(g) for g in rows if g.isdigit()]
    names = (
        {
            str(a.id): a.name
            for a in db.session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
        }
        if agent_ids
        else {}
    )
    for gid, entry in rows.items():
        if gid.startswith("human:") and gid[6:].isdigit():
            user = db.session.get(Admin_users, int(gid[6:]))
            entry["name"] = user.username if user else gid
        else:
            entry["name"] = names.get(gid, gid)
    for gid, entry in rows.items():
        entry["stats"] = (stats or {}).get(gid, NO_STATS)
    ordered = sorted(
        rows.values(), key=lambda r: (r["kind"] != "agent", r["name"].lower(), r["id"])
    )
    return {
        "members": members,
        "source": "coordinator" if live is not None else "links",
        "rows": ordered,
        "names": names_of_members,
        "stats_available": stats is not None,
    }


def filtered(
    data: dict,
    member: str = "",
    state: str = "",
    query: str = "",
    kind: str = "",
    activity: str = "",
) -> List[dict]:
    """The rows with at least one account that matches ``member`` and ``state`` (both empty: all), a name containing
    ``query``, the ``kind`` (agent or human) and the ``activity`` (``made``: made cross-posts, ``crossposted``: its content was
    cross-posted, ``none``: neither)."""
    query = (query or "").strip().lower()
    out = []
    for row in data["rows"]:
        if kind and row["kind"] != kind:
            continue
        if (
            query
            and query not in row["name"].lower()
            and query not in row["id"].lower()
        ):
            continue
        st = row.get("stats") or NO_STATS
        if activity == "made" and not (st["made_own"] or st["made_others"]):
            continue
        if activity == "crossposted" and not st["times"]:
            continue
        if activity == "none" and (st["made_own"] or st["made_others"] or st["times"]):
            continue
        if member or state:
            cells = (
                [row["states"].get(member)] if member else list(row["states"].values())
            )
            if not any(c and (not state or c["state"] == state) for c in cells):
                continue
        out.append(row)
    return out


def default_direction(sort: str) -> str:
    return "asc" if sort == "name" else "desc"


def sorted_rows(
    rows: List[dict], sort: str = "name", direction: str = ""
) -> List[dict]:
    """``rows`` sorted by ``sort`` (``name``, ``made_own``, ``made_others`` or ``times``) in ``direction`` (``asc``/``desc``; the
    default is A-Z for the name and the largest first for the numbers); ties by name. The default (name, ascending) keeps the order
    of :func:`table`: agents first, then by name."""
    if sort not in SORTS:
        sort = "name"
    descending = (direction or default_direction(sort)) == "desc"
    if sort == "name":
        return (
            rows
            if not descending
            else sorted(
                rows,
                key=lambda r: (r["kind"] == "agent", r["name"].lower(), r["id"]),
                reverse=True,
            )
        )
    out = sorted(rows, key=lambda r: (r["name"].lower(), r["id"]))
    return sorted(out, key=lambda r: r["stats"][sort], reverse=descending)


def counts(data: dict) -> Dict[str, Dict[str, int]]:
    """``{member: {state: n}}`` over all the identities."""
    out = {m: {} for m in data["members"]}
    for row in data["rows"]:
        for m, cell in row["states"].items():
            out.setdefault(m, {})[cell["state"]] = (
                out.setdefault(m, {}).get(cell["state"], 0) + 1
            )
    return out
