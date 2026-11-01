"""Human participants of a World Simulation (F8, H3): enrolment of a YWeb user in the members of a federation.

A person is one identity ``human:<Admin_users.id>`` (D1) with at most one account per platform (INV-14), enrolled
explicitly, platform by platform (D2), also while the federation runs (D3: the coordinator learns the identity
through ``POST /v1/identity``). Humans are outside attention, discovery, leave and the affective report (D7, INV-15):
that is the coordinator's and the runtimes' business, YWeb only records who is enrolled and where.

The accounts are created through the gateways of the runtimes, never by YWeb (instant messaging, dating and, since
H5, microblogging, forum and photo sharing). Dating asks the person for a profile, so its account exists only after
the person joined: the enrolment there is *pending* (``created`` false) and its id is the derived one.
Unenrolling never deletes an account: it only marks the person inactive in YWeb.
"""

from __future__ import annotations

import json
from typing import Callable, Optional

from y_web import db
from y_web.src.federation import service
from y_web.src.federation.service import WorldSimulationError

HUMAN_PREFIX = "human:"
GATEWAY_PLATFORMS = ("microblogging", "forum", "photo_sharing", "instant_messaging", "dating")
RUNNING_STATES = ("running", "paused", "starting")


def human_id_of(user_id) -> str:
    """``human:<Admin_users.id>``: one person, one identity in every World Simulation (D1)."""
    return f"{HUMAN_PREFIX}{int(user_id)}"


def is_human_id(global_agent_id) -> bool:
    return str(global_agent_id).startswith(HUMAN_PREFIX)


class HumanEnrolmentError(WorldSimulationError):
    pass


def _err(code: str, message: str):
    raise HumanEnrolmentError([{"code": code, "message": message}])


# -- the account of a person on each platform ----------------------------------------------------------
def _ensure_micro_like(platform_type, exp, user, hid, session=None, offline=None):
    from y_web.src.federation.human_gateways import GatewayUnavailable, RuntimeGateway

    folder = service.experiment_dir(exp)
    config = service.server_config_path(exp)
    # photo sharing derives the identity from the key (``human:<key>``): the key is the user id
    key = str(int(user.id)) if platform_type == "photo_sharing" else f"u{int(user.id)}"
    gateway = RuntimeGateway(platform_type, folder, server_config=config, database=folder / "database_server.db",
                             session=session, offline=offline)
    try:
        status, payload = gateway.ensure(key, str(user.username)[:15], hid, getattr(exp, "prompt_language", None))
    except GatewayUnavailable as exc:
        _err("gateway_unavailable", f"{platform_type}: {exc}")
    if status not in (200, 201) or "account_id" not in (payload or {}):
        _err("gateway_refused", f"{platform_type}: the gateway answered {status}")
    return str(payload["account_id"]), True


def _ensure_im(platform_type, exp, user, hid, session=None, offline=None):
    from y_web.src.im import human_identity
    from y_web.src.im.gateway_client import GatewayClient, GatewayUnavailable

    folder = str(service.experiment_dir(exp))
    uid = human_identity.experiment_uid(exp)
    key = human_identity.human_key(uid, user.id)
    try:
        status, _payload = GatewayClient(folder, session=session).ensure(key, str(user.username)[:15], getattr(exp, "prompt_language", None))
    except GatewayUnavailable as exc:
        _err("gateway_unavailable", f"{platform_type}: {exc}")
    if status not in (200, 201):
        _err("gateway_refused", f"{platform_type}: the gateway answered {status}")
    return human_identity.human_account_id(uid, user.id), True


def _ensure_dating(platform_type, exp, user, hid, session=None, offline=None):
    from y_web.src.dating import human as dating_human

    # the profile is filled by the person when they join (photos, preferences): the account is pending until then
    return dating_human.human_account_id(dating_human.experiment_uid(exp), user.id), False


ENSURERS = {
    "microblogging": _ensure_micro_like,
    "forum": _ensure_micro_like,
    "photo_sharing": _ensure_micro_like,
    "instant_messaging": _ensure_im,
    "dating": _ensure_dating,
}


def supported(row, exp) -> bool:
    """HPC microblogging (YSimulator) has no human gateway."""
    if row.platform_type not in ENSURERS:
        return False
    return not (row.platform_type == "microblogging" and (getattr(exp, "simulator_type", None) or "Standard") == "HPC")


# -- records -------------------------------------------------------------------------------------------
def _models():
    from y_web.src.models.admin import FederationHuman, FederationIdentityLink

    return FederationHuman, FederationIdentityLink


def members_state(human) -> dict:
    try:
        data = json.loads(human.members_json or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def list_humans(fed) -> list:
    FederationHuman, _ = _models()
    return db.session.query(FederationHuman).filter_by(federation_pk=fed.id).order_by(FederationHuman.id).all()


def accounts_by_member(fed) -> dict:
    """``{member: {human_id: local_account_id}}`` of the active humans: what member configurations carry."""
    out: dict = {}
    for h in list_humans(fed):
        if h.status != "active":
            continue
        for member, info in sorted(members_state(h).items()):
            out.setdefault(member, {})[h.human_id] = str(info["account_id"])
    return out


def _coordinator_client(fed):
    from pathlib import Path

    from ysocial_federation.client import CoordinatorClient

    folder = Path(fed.folder)
    return CoordinatorClient.from_files(folder / "federation_coordinator.json", folder / "federation.token", "yweb", retry_budget=1.0)


def _refresh_files(fed) -> None:
    """federation.json always; the member configurations only while the federation runs (they are installed at start
    and removed at stop so that a member started alone never waits for a coordinator)."""
    service.write_federation_files(fed)
    if fed.status in RUNNING_STATES:
        service.write_member_configs(fed)


def _announce(fed, human, accounts: list, coordinator=None) -> None:
    """Tell a running coordinator about the identity (idempotent); stopped federations read it from federation.json."""
    if fed.status not in RUNNING_STATES:
        return
    client = coordinator if coordinator is not None else _coordinator_client(fed)
    try:
        client.add_identity(human.human_id, "human", accounts)
    except Exception as exc:  # noqa: BLE001 - the coordinator's refusal is shown, the enrolment is not kept half-way
        _err("coordinator_refused", f"the coordinator did not accept {human.human_id}: {exc}")


def enrol(fed, user, members, *, coordinator=None, session=None, offline=None, write_files: bool = True):
    """Enrol ``user`` in the given members of ``fed`` (names of members, e.g. ``["forum", "dating"]``).

    Idempotent: a member already enrolled keeps its account. All the gateways are asked before anything is recorded,
    so a failure leaves nothing half-way (an account already created stays: asking again finds it)."""
    FederationHuman, FederationIdentityLink = _models()
    rows = {row.member: (row, exp) for row, exp in service.members_of(fed)}
    wanted = sorted({str(m) for m in members or []})
    if not wanted:
        _err("no_member", "Pick at least one platform.")
    for name in wanted:
        if name not in rows:
            _err("unknown_member", f"{name} is not a member of this World Simulation.")
        if not supported(*rows[name]):
            _err("platform_not_supported", f"The {name} platform of this World Simulation has no human gateway.")
    hid = human_id_of(user.id)
    human = db.session.query(FederationHuman).filter_by(federation_pk=fed.id, user_id=int(user.id)).first()
    state = members_state(human) if human else {}
    results = {}
    for name in wanted:
        if name in state and human.status == "active":
            results[name] = (str(state[name]["account_id"]), bool(state[name].get("created", True)))
            continue
        row, exp = rows[name]
        results[name] = ENSURERS[row.platform_type](row.platform_type, exp, user, hid, session=session, offline=offline)
    if human is None:
        human = FederationHuman(federation_pk=fed.id, user_id=int(user.id), human_id=hid, members_json="{}", status="active")
        db.session.add(human)
    human.status = "active"
    for name, (account, created) in results.items():
        state[name] = {"account_id": account, "created": created}
        link = db.session.query(FederationIdentityLink).filter_by(federation_pk=fed.id, global_agent_id=hid, member=name).first()
        if link is None:
            db.session.add(FederationIdentityLink(federation_pk=fed.id, global_agent_id=hid, member=name, local_account_id=account))
        else:
            link.local_account_id = account
    human.members_json = json.dumps(state, sort_keys=True)
    try:
        db.session.flush()
        _announce(fed, human, [{"member": m, "local_account_id": str(i["account_id"])} for m, i in sorted(state.items())], coordinator)
    except HumanEnrolmentError:
        db.session.rollback()
        raise
    db.session.commit()
    if write_files:
        _refresh_files(fed)
    return human


def confirm_account(fed, user_id, member) -> bool:
    """A pending account (dating) now exists: the person joined. True when the record changed."""
    FederationHuman, _ = _models()
    human = db.session.query(FederationHuman).filter_by(federation_pk=fed.id, user_id=int(user_id)).first()
    state = members_state(human) if human else {}
    if member not in state or state[member].get("created", True):
        return False
    state[member]["created"] = True
    human.members_json = json.dumps(state, sort_keys=True)
    db.session.commit()
    return True


def unenrol(fed, user_id, *, write_files: bool = True) -> bool:
    """The person stops being offered the destinations; accounts and identity links stay (nothing is deleted)."""
    FederationHuman, _ = _models()
    human = db.session.query(FederationHuman).filter_by(federation_pk=fed.id, user_id=int(user_id)).first()
    if human is None or human.status == "inactive":
        return False
    human.status = "inactive"
    db.session.commit()
    if write_files:
        _refresh_files(fed)
    return True
