"""Human participants of a World Simulation (F8, H3): enrolment of a YWeb user in the members of a federation.

A person is one identity ``human:<Admin_users.id>`` (D1) with at most one account per platform (INV-14), enrolled
explicitly, platform by platform (D2), also while the federation runs (D3: the coordinator learns the identity
through ``POST /v1/identity``). Humans are outside attention, discovery, leave and the affective report (D7, INV-15):
that is the coordinator's and the runtimes' business, YWeb only records who is enrolled and where.

The accounts are created through the gateways of the runtimes, never by YWeb (each platform declares its gateway,
``human_gateway``). A platform whose account needs the person (a profile, say) has it only after the person joined: the
enrolment there is *pending* (``created`` false) and its id is the derived one.
Unenrolling never deletes an account: it only marks the person inactive in YWeb.
"""

from __future__ import annotations

import json
from typing import Callable, Optional

from y_web import db
from y_web.platforms import registry
from y_web.src.federation import service
from y_web.src.federation.service import WorldSimulationError

HUMAN_PREFIX = "human:"
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
def _gateway(platform_type, exp):
    from y_web.src.federation import traits

    return traits.human_gateway(platform_type, getattr(exp, "simulator_type", None))


def _ensure_account(platform_type, exp, user, hid, session=None, offline=None):
    """``(account id, created)`` of the person on the member; the platform's own ``enrol`` when it has one, otherwise
    the account request of its gateway."""
    from y_web.platforms.base import GatewayPaths, HumanGatewayError
    from y_web.src.federation import human_gateways as hg
    from y_web.src.federation.human_gateways import GatewayUnavailable, RuntimeGateway

    spec = _gateway(platform_type, exp)
    folder = service.experiment_dir(exp)
    config = service.server_config_path(exp)
    try:
        if spec is not None and spec.enrol is not None:
            return spec.enrol(
                exp,
                user,
                hid,
                GatewayPaths(folder, config, folder / "database_server.db"),
                session,
                offline,
            )
        key = spec.key_template.format(user_id=int(user.id))
        gateway = RuntimeGateway(
            platform_type,
            folder,
            server_config=config,
            database=folder / "database_server.db",
            session=session,
            offline=offline,
            hpc=hg.is_hpc(exp),
        )
        status, payload = gateway.ensure(
            key, str(user.username)[:15], hid, getattr(exp, "prompt_language", None)
        )
    except HumanGatewayError as exc:
        _err(exc.code, f"{platform_type}: {exc}")
    except GatewayUnavailable as exc:
        _err("gateway_unavailable", f"{platform_type}: {exc}")
    if status not in (200, 201) or "account_id" not in (payload or {}):
        _err("gateway_refused", f"{platform_type}: the gateway answered {status}")
    return str(payload["account_id"]), True


def supported(row, exp) -> bool:
    """Every platform of a World Simulation has a human gateway (a platform without one cannot enrol people)."""
    return _gateway(row.platform_type, exp) is not None


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
    return (
        db.session.query(FederationHuman)
        .filter_by(federation_pk=fed.id)
        .order_by(FederationHuman.id)
        .all()
    )


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
    return CoordinatorClient.from_files(
        folder / "federation_coordinator.json",
        folder / "federation.token",
        "yweb",
        retry_budget=1.0,
    )


def _refresh_files(fed) -> None:
    """federation.json always; the member configurations only while the federation runs (they are installed at start
    and removed at stop so that a member started alone never waits for a coordinator).
    """
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
    except (
        Exception
    ) as exc:  # noqa: BLE001 - the coordinator's refusal is shown, the enrolment is not kept half-way
        _err(
            "coordinator_refused",
            f"the coordinator did not accept {human.human_id}: {exc}",
        )


def enrol(
    fed,
    user,
    members,
    *,
    coordinator=None,
    session=None,
    offline=None,
    write_files: bool = True,
):
    """Enrol ``user`` in the given members of ``fed`` (names of members, the names the federation gives them).

    Idempotent: a member already enrolled keeps its account. All the gateways are asked before anything is recorded,
    so a failure leaves nothing half-way (an account already created stays: asking again finds it).
    """
    FederationHuman, FederationIdentityLink = _models()
    rows = {row.member: (row, exp) for row, exp in service.members_of(fed)}
    wanted = sorted({str(m) for m in members or []})
    if not wanted:
        _err("no_member", "Pick at least one platform.")
    for name in wanted:
        if name not in rows:
            _err("unknown_member", f"{name} is not a member of this World Simulation.")
        if not supported(*rows[name]):
            _err(
                "platform_not_supported",
                f"The {name} platform of this World Simulation has no human gateway.",
            )
    hid = human_id_of(user.id)
    human = (
        db.session.query(FederationHuman)
        .filter_by(federation_pk=fed.id, user_id=int(user.id))
        .first()
    )
    state = members_state(human) if human else {}
    results = {}
    for name in wanted:
        if name in state and human.status == "active":
            results[name] = (
                str(state[name]["account_id"]),
                bool(state[name].get("created", True)),
            )
            continue
        row, exp = rows[name]
        results[name] = _ensure_account(
            row.platform_type, exp, user, hid, session=session, offline=offline
        )
    if human is None:
        human = FederationHuman(
            federation_pk=fed.id,
            user_id=int(user.id),
            human_id=hid,
            members_json="{}",
            status="active",
        )
        db.session.add(human)
    human.status = "active"
    for name, (account, created) in results.items():
        state[name] = {"account_id": account, "created": created}
        link = (
            db.session.query(FederationIdentityLink)
            .filter_by(federation_pk=fed.id, global_agent_id=hid, member=name)
            .first()
        )
        if link is None:
            db.session.add(
                FederationIdentityLink(
                    federation_pk=fed.id,
                    global_agent_id=hid,
                    member=name,
                    local_account_id=account,
                )
            )
        else:
            link.local_account_id = account
    human.members_json = json.dumps(state, sort_keys=True)
    try:
        db.session.flush()
        _announce(
            fed,
            human,
            [
                {"member": m, "local_account_id": str(i["account_id"])}
                for m, i in sorted(state.items())
            ],
            coordinator,
        )
    except HumanEnrolmentError:
        db.session.rollback()
        raise
    db.session.commit()
    if write_files:
        _refresh_files(fed)
    return human


def confirm_account(fed, user_id, member) -> bool:
    """A pending account now exists: the person joined. True when the record changed."""
    FederationHuman, _ = _models()
    human = (
        db.session.query(FederationHuman)
        .filter_by(federation_pk=fed.id, user_id=int(user_id))
        .first()
    )
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
    human = (
        db.session.query(FederationHuman)
        .filter_by(federation_pk=fed.id, user_id=int(user_id))
        .first()
    )
    if human is None or human.status == "inactive":
        return False
    human.status = "inactive"
    db.session.commit()
    if write_files:
        _refresh_files(fed)
    return True


# -- the gateways with the run of a member (called by the World Simulation lifecycle) --------------------
def _has_humans(fed, member) -> bool:
    return bool(accounts_by_member(fed).get(member))


def _member_name(fed, exp):
    return next(
        (row.member for row, e in service.members_of(fed) if e.idexp == exp.idexp), None
    )


def prepare_member(fed, exp) -> None:
    """Before the server of a member starts: the token of a gateway that is part of the server goes in its server
    configuration (the gateways that are processes have their own token, written when they start).
    """
    from y_web.src.federation.human_gateways import set_server_token

    member = _member_name(fed, exp)
    row = next((r for r, e in service.members_of(fed) if e.idexp == exp.idexp), None)
    if member is None or row is None or not _has_humans(fed, member):
        return
    spec = _gateway(row.platform_type, exp)
    if spec is None or not spec.token_in_server_config or not spec.http:
        return
    path = service.server_config_path(exp)
    if path is not None:
        set_server_token(path)


def after_server_started(fed, exp):
    """After the server of a member is up: start its human gateway when that is a process of its own (a failure is only a
    warning in the log: the person can still act offline through the runtime script when the server is stopped).
    """
    from y_web.src.federation import human_gateways as hg

    member = _member_name(fed, exp)
    row = next((r for r, e in service.members_of(fed) if e.idexp == exp.idexp), None)
    if member is None or row is None or not _has_humans(fed, member):
        return None
    spec = _gateway(row.platform_type, exp)
    if spec is None or spec.start_process is None:
        return None
    from y_web.src.simulation.server import detect_env_handler
    from y_web.src.system.path_utils import get_external_repo_dir

    config = (
        hg._load_json(service.server_config_path(exp))
        if service.server_config_path(exp)
        else {}
    )
    url = f"http://{config.get('host') or '127.0.0.1'}:{int(config.get('port') or getattr(exp, 'port', 0) or 0)}"
    return hg.start_gateway(
        row.platform_type,
        service.experiment_dir(exp),
        get_external_repo_dir(spec.repo),
        python_cmd=detect_env_handler() or None,
        server_url=url,
    )


def after_server_stopped(exp) -> bool:
    """The server of a member stopped: so does its human gateway process (nothing to do for the other platforms)."""
    from y_web.src.federation import human_gateways as hg

    folder = service.experiment_dir(exp)
    return hg.stop_gateway(folder) if hg.is_running(folder) else False
