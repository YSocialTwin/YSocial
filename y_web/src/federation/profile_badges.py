"""Profile badges of a World Simulation: where else an account takes part, with a link to its profile there.

On the profile page of an account (an agent or a person enrolled in the World Simulation) every platform page shows one
badge for each *other* member where the same identity has an account, linking to the profile on that platform. The
identity is the ``global_agent_id`` of ``federation_identity_link``; the state of each membership is read, read-only, from
the coordinator's ``federation.db`` when it exists (an agent that is dormant or left on a platform is not shown there);
before the first run every account is shown. Nothing here writes, and for an account outside a World Simulation the answer
is an empty list (the pages render exactly as before)."""

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


def badges_for(exp_id, account_id) -> List[dict]:
    """``[{member, platform_type, label, href}]`` for the other platforms of the identity behind ``account_id`` on the
    experiment ``exp_id``; ``[]`` when the experiment is not a member of a World Simulation or the account has no identity."""
    from y_web.src.federation.humans import members_state
    from y_web.src.models.admin import Federation, FederationHuman, FederationIdentityLink, FederationMember

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
    for name in sorted(accounts):
        account, state = accounts[name]
        member = members.get(name)
        if member is None or name == own.member or name in pending or state != "active":
            continue
        href = profile_href(member.platform_type, member.exp_id, account)
        if href:
            # the label is the name of the experiment (several experiments can have the same platform type); the type is the icon
            out.append({"member": name, "platform_type": member.platform_type, "exp_id": member.exp_id,
                        "label": label_of(names, name), "icon": ICONS.get(member.platform_type, "link"), "href": href})
    return out
