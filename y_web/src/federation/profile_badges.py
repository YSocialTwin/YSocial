"""Profile badges of a World Simulation: where else an account takes part, with a link to its profile there.

On the profile page of an account (an agent or a person enrolled in the World Simulation) every platform page shows one
chip for each *other* member where the same identity has an account, labelled with the name of its experiment (the platform
type is only the icon) and linking to the profile there. The identity is the ``global_agent_id`` of
``federation_identity_link``; the state of each membership (``active``, ``dormant``, ``left``, ``ineligible``) is read,
read-only, from the coordinator's ``federation.db`` when it exists, and a chip of an agent that is not active there is
muted; before the first run every account is shown as active. A chip carries the handle of the account there when it differs
from this one and, when the coordinator knows it, how many of the agent's contents were cross-posted there. The link exists
only while the web interface of that experiment is active. Everything is read in one batch per page (one query on the
coordinator, one small query per platform, one grouped statistics query), the number of chips is bounded, and nothing here
writes. For an account outside a World Simulation the answer is an empty list (the pages render exactly as before)."""

from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Optional

from y_web import db
from y_web.src.federation.backlinks import ICONS  # icon of each platform type (``shared/world_simulation_icon.html``)
from y_web.src.federation.names import label_of, names_of

# the profile page of an account on each platform (see the routes of ``y_web/routes/social``)
PROFILE_PATHS = {
    "microblogging": "/{exp}/profile/{account}/recent/1",
    "forum": "/{exp}/profile/{account}/recent/1",
    "photo_sharing": "/{exp}/photo/profile/{account}/recent/1",
    "instant_messaging": "/{exp}/im/profile/{account}",
    "dating": "/{exp}/dating/profile/{account}",
}


def profile_href(platform_type: str, exp_id, account_id) -> Optional[str]:
    path = PROFILE_PATHS.get(platform_type)
    return path.format(exp=int(exp_id), account=str(account_id)) if path else None


def _rows(folder) -> Optional[List[tuple]]:
    """``[(global_agent_id, member, local_account_id, state)]`` of the accounts the coordinator knows (INV-17: the runtime
    reported them), from its database, or ``None`` when it cannot be read."""
    path = os.path.join(str(folder or ""), "federation.db")
    if not folder or not os.path.isfile(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None
    try:
        conn.execute("PRAGMA query_only = ON")
        return [(str(g), m, str(a), s) for g, m, a, s in conn.execute(
            "SELECT global_agent_id, member, local_account_id, state FROM federation_identity WHERE local_account_id IS NOT NULL")]
    except sqlite3.Error:
        return None
    finally:
        conn.close()


MAX_BADGES = 24  # chips of one profile page
# where each platform keeps the username of an account (read to show the handle of the other platforms)
USERNAME_SQL = {
    "microblogging": "SELECT id, username FROM user_mgmt WHERE id = ?",
    "forum": "SELECT id, username FROM user_mgmt WHERE id = ?",
    "photo_sharing": "SELECT id, username FROM user_mgmt WHERE id = ?",
    "dating": "SELECT id, username FROM user_mgmt WHERE id = ?",
    "instant_messaging": "SELECT id, username FROM accounts WHERE id = ?",
}


def _handle(exp, platform_type, account) -> Optional[str]:
    """The username of ``account`` on the experiment ``exp`` (read-only), or ``None`` when it cannot be read."""
    sql = USERNAME_SQL.get(platform_type)
    if not sql or exp is None:
        return None
    from y_web.src.federation.backlinks import _db_path, _query

    try:
        rows = _query(_db_path(exp), sql, (account,))
    except Exception:  # noqa: BLE001
        return None
    return str(rows[0][1]) if rows and rows[0][1] else None


def _crossposts(folder, gid) -> Dict[str, int]:
    """``{member: contents of the agent cross-posted there}`` (delivered copies), ``{}`` when the coordinator has no figures.
    The grouped statistics of the Agents tab, computed once per request."""
    try:
        from flask import g, has_request_context

        from y_web.src.federation import agent_states

        cache = g.setdefault("_ws_badge_stats", {}) if has_request_context() else {}
        if str(folder) not in cache:
            cache[str(folder)] = agent_states._stats(folder) or {}
        return dict((cache[str(folder)].get(str(gid)) or {}).get("by_dest") or {})
    except Exception:  # noqa: BLE001 - the figure is optional
        return {}


def badges_for(exp_id, account_id) -> List[dict]:
    """The other platforms of the identity behind ``account_id`` on the experiment ``exp_id``, one dict each
    ``{member, platform_type, exp_id, label, icon, href, state, active, handle, crossposts}``: ``label`` is the experiment
    name, ``state`` the membership state, ``active`` whether the agent is active there, ``href`` the profile (``None`` when
    the interface of that experiment is not active), ``handle`` the username there when it differs from this one (else
    ``None``) and ``crossposts`` the contents cross-posted there (``None`` when unknown). Active platforms come first.
    ``[]`` when the experiment is not a member of a World Simulation or the account has no identity."""
    from y_web.src.federation.humans import members_state
    from y_web.src.models.admin import Exps, Federation, FederationHuman, FederationIdentityLink, FederationMember

    if exp_id is None or account_id in (None, ""):
        return []
    own = db.session.query(FederationMember).filter_by(exp_id=int(exp_id)).first()
    if own is None:
        return []
    fed = db.session.get(Federation, own.federation_pk)
    rows = _rows(getattr(fed, "folder", None))
    gid = None
    for g, m, a, _state in rows or ():
        if m == own.member and a == str(account_id):
            gid = g
            break
    link = None
    if gid is None:  # people (accounts known to YWeb) and links of older releases
        link = db.session.query(FederationIdentityLink).filter_by(
            federation_pk=own.federation_pk, member=own.member, local_account_id=str(account_id)).first()
        if link is None:
            return []
        gid = link.global_agent_id
    members = {m.member: m for m in db.session.query(FederationMember).filter_by(federation_pk=own.federation_pk)}
    names = names_of(own.federation_pk)
    pending = set()
    if str(gid).startswith("human:"):  # an account that does not exist yet has no profile to open
        human = db.session.query(FederationHuman).filter_by(federation_pk=own.federation_pk, human_id=gid,
                                                            status="active").first()
        if human is None:
            return []
        pending = {m for m, info in members_state(human).items() if not info.get("created", True)}
    out = []
    accounts = {}  # {member: (account, state)}: what the coordinator reports first, then what YWeb knows (people)
    for other in db.session.query(FederationIdentityLink).filter_by(
            federation_pk=own.federation_pk, global_agent_id=gid).order_by(FederationIdentityLink.member):
        if other.local_account_id:
            accounts[other.member] = (other.local_account_id, "active")
    for g, m, a, state in rows or ():
        if g == gid:
            accounts[m] = (a, state)
    here = _handle(db.session.get(Exps, own.exp_id), own.platform_type, str(account_id))
    stats = None
    for name in sorted(accounts):
        if len(out) >= MAX_BADGES:
            break
        account, state = accounts[name]
        member = members.get(name)
        if member is None or name == own.member or name in pending:
            continue
        exp = db.session.get(Exps, member.exp_id)
        path = profile_href(member.platform_type, member.exp_id, account)
        if not path:
            continue
        if stats is None:
            stats = _crossposts(getattr(fed, "folder", None), gid) if rows is not None else {}
        handle = _handle(exp, member.platform_type, account)
        # the label is the name of the experiment (several experiments can have the same platform type); the type is the icon
        out.append({"member": name, "platform_type": member.platform_type, "exp_id": member.exp_id,
                    "label": label_of(names, name), "icon": ICONS.get(member.platform_type, "link"),
                    "href": path if exp is not None and exp.status == 1 else None, "state": state, "active": state == "active",
                    "handle": handle if handle and (not here or handle.lower() != here.lower()) else None,
                    "crossposts": stats.get(name)})
    out.sort(key=lambda b: (not b["active"], b["label"].lower(), b["member"]))
    return out
