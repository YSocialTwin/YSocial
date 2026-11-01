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


def _states(folder) -> Optional[Dict[tuple, str]]:
    """``{(global_agent_id, member): state}`` from the coordinator database, or ``None`` when it cannot be read."""
    path = os.path.join(str(folder or ""), "federation.db")
    if not folder or not os.path.isfile(path):
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None
    try:
        conn.execute("PRAGMA query_only = ON")
        return {(g, m): s for g, m, s in conn.execute("SELECT global_agent_id, member, state FROM federation_identity")}
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
    link = db.session.query(FederationIdentityLink).filter_by(
        federation_pk=own.federation_pk, member=own.member, local_account_id=str(account_id)).first()
    if link is None:
        return []
    fed = db.session.get(Federation, own.federation_pk)
    members = {m.member: m for m in db.session.query(FederationMember).filter_by(federation_pk=own.federation_pk)}
    states = _states(getattr(fed, "folder", None))
    pending = set()
    if str(link.global_agent_id).startswith("human:"):  # an account that does not exist yet has no profile to open
        human = db.session.query(FederationHuman).filter_by(federation_pk=own.federation_pk, human_id=link.global_agent_id,
                                                            status="active").first()
        if human is None:
            return []
        pending = {m for m, info in members_state(human).items() if not info.get("created", True)}
    out = []
    for other in db.session.query(FederationIdentityLink).filter_by(
            federation_pk=own.federation_pk, global_agent_id=link.global_agent_id).order_by(FederationIdentityLink.member):
        member = members.get(other.member)
        if member is None or other.member == own.member or other.member in pending:
            continue
        if states is not None and states.get((other.global_agent_id, other.member), "active") != "active":
            continue
        href = profile_href(member.platform_type, member.exp_id, other.local_account_id)
        if href:
            out.append({"member": other.member, "platform_type": member.platform_type,
                        "label": other.member.replace("_", " ").capitalize(), "href": href})
    return out
