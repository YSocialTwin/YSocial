"""Who is active where in a World Simulation: one row per identity, one state per platform (read-only).

The state of each account comes from the coordinator's ``federation.db`` (``federation_identity``: ``active``, ``dormant``,
``left`` or ``ineligible``, with the ticks of joining and leaving); before the first run the file does not exist and every
account is listed as ``not started``. Names come from the YWeb agents and from the enrolled people. Nothing is written."""

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
        return {(g, m): {"state": s, "joined": j, "left": l}
                for g, m, s, j, l in conn.execute("SELECT global_agent_id, member, state, joined_tick, left_tick FROM federation_identity")}
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
            return dict(conn.execute("SELECT global_agent_id, kind FROM federation_identity_kind"))
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def table(fed) -> dict:
    """``{"members": [member], "source": "coordinator"|"links", "rows": [{id, name, kind, states: {member: {...}}}]}`` sorted by
    kind (agents first) and name."""
    from y_web.src.federation import service
    from y_web.src.models.admin import Admin_users, Agent, FederationIdentityLink

    members = [row.member for row, _exp in service.members_of(fed)]
    live = _coordinator(fed.folder)
    kinds = _kinds(fed.folder)
    rows: Dict[str, dict] = {}
    for link in db.session.query(FederationIdentityLink).filter_by(federation_pk=fed.id).order_by(FederationIdentityLink.id):
        gid = link.global_agent_id
        entry = rows.setdefault(gid, {"id": gid, "name": "", "kind": "human" if gid.startswith("human:") else kinds.get(gid, "agent"), "states": {}})
        info = (live or {}).get((gid, link.member)) if live is not None else None
        entry["states"][link.member] = {"state": info["state"] if info else "not started", "account": link.local_account_id,
                                        "joined": info["joined"] if info else None, "left": info["left"] if info else None}
    agent_ids = [int(g) for g in rows if g.isdigit()]
    names = {str(a.id): a.name for a in db.session.query(Agent).filter(Agent.id.in_(agent_ids)).all()} if agent_ids else {}
    for gid, entry in rows.items():
        if gid.startswith("human:") and gid[6:].isdigit():
            user = db.session.get(Admin_users, int(gid[6:]))
            entry["name"] = user.username if user else gid
        else:
            entry["name"] = names.get(gid, gid)
    ordered = sorted(rows.values(), key=lambda r: (r["kind"] != "agent", r["name"].lower(), r["id"]))
    return {"members": members, "source": "coordinator" if live is not None else "links", "rows": ordered}


def filtered(data: dict, member: str = "", state: str = "", query: str = "", kind: str = "") -> List[dict]:
    """The rows with at least one account that matches ``member`` and ``state`` (both empty: all), a name containing
    ``query`` and the ``kind`` (agent or human)."""
    query = (query or "").strip().lower()
    out = []
    for row in data["rows"]:
        if kind and row["kind"] != kind:
            continue
        if query and query not in row["name"].lower() and query not in row["id"].lower():
            continue
        if member or state:
            cells = [row["states"].get(member)] if member else list(row["states"].values())
            if not any(c and (not state or c["state"] == state) for c in cells):
                continue
        out.append(row)
    return out


def counts(data: dict) -> Dict[str, Dict[str, int]]:
    """``{member: {state: n}}`` over all the identities."""
    out = {m: {} for m in data["members"]}
    for row in data["rows"]:
        for m, cell in row["states"].items():
            out.setdefault(m, {})[cell["state"]] = out.setdefault(m, {}).get(cell["state"], 0) + 1
    return out
