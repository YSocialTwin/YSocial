"""World Simulation service (guide F5.2): creation, validation and configuration files of a federation.

A World Simulation groups two to five stopped experiments, one per platform type, that share the same population and run
on one simulated 24-slot clock. In the interface the feature is always called "World Simulation"; in code and files it is
"federation" (guide 6, F5).

Rules checked at creation (each one has its own error code):
    member_count        2 to 5 experiments
    experiment_running  every experiment is stopped
    remote              no remote experiment
    population          every experiment uses the same, non-empty set of populations
    duplicate_platform  one experiment per platform type (D-05)
    platform            the platform supports federation
    simulator_type      forum runs on Standard, photo sharing / instant messaging / dating on HPC, microblogging on either (D-06)
    clock               clock mode "simulated" with hourly feed refresh (24 slots a day)
    already_member      the experiment is not a member of another World Simulation
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from y_web import db
from y_web.src.hpc.platforms import find_hpc_platform

MIN_MEMBERS, MAX_MEMBERS = 2, 5
PROTOCOL = "1.0"
SLOTS_PER_DAY = 24
GRANULARITIES = ("slot", "day")
OPTION_BLOCKS = ("attention", "crosspost", "discovery", "leave", "membership", "topics", "pseudonyms")
# platform_type -> simulator types allowed (D-06); None = decided by supports_federation of the HPC table
ALLOWED_SIMULATORS = {
    "microblogging": ("Standard", "HPC"),
    "forum": ("Standard",),
    "photo_sharing": ("HPC",),
    "instant_messaging": ("HPC",),
    "dating": ("HPC",),
}
SERVER_CONFIG_NAMES = ("config_server.json", "server_config.json")
FEDERATION_FOLDER_NAME = "federations"


class WorldSimulationError(ValueError):
    """Validation or consistency error; ``errors`` is a list of ``{"code", "message"}``."""

    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, dict) else list(errors)
        super().__init__("; ".join(f"{e['code']}: {e['message']}" for e in self.errors))

    @property
    def codes(self):
        return [e["code"] for e in self.errors]


@dataclass
class MemberInfo:
    """What the validation needs to know about one candidate experiment (no database access in the rules)."""

    exp_id: int
    exp_name: str
    platform_type: str
    simulator_type: str = "Standard"
    running: bool = False
    is_remote: bool = False
    population_ids: frozenset = frozenset()
    clock_mode: str = "simulated"
    feed_refresh: str = "hourly"
    other_federation: Optional[str] = None
    extra: dict = field(default_factory=dict)


def supports_federation(platform_type: str, simulator_type: str) -> bool:
    spec = find_hpc_platform(platform_type)
    if simulator_type == "HPC":
        return bool(spec and spec.supports_federation)
    return platform_type in ("microblogging", "forum")  # Standard path: YServer and YServerReddit


def validate_members(infos) -> list:
    """Return the list of errors (empty when the group is valid). Pure function."""
    infos = list(infos)
    errors = []

    def err(code, message):
        errors.append({"code": code, "message": message})

    if not MIN_MEMBERS <= len(infos) <= MAX_MEMBERS:
        err("member_count", f"A World Simulation needs {MIN_MEMBERS} to {MAX_MEMBERS} experiments, got {len(infos)}.")
    seen = {}
    for i in infos:
        if i.platform_type in seen:
            err("duplicate_platform", f"'{i.exp_name}' and '{seen[i.platform_type]}' are both {i.platform_type} experiments.")
        seen.setdefault(i.platform_type, i.exp_name)
    for i in infos:
        if i.running:
            err("experiment_running", f"'{i.exp_name}' is running: stop it first.")
        if i.is_remote:
            err("remote", f"'{i.exp_name}' is a remote experiment.")
        allowed = ALLOWED_SIMULATORS.get(i.platform_type)
        if allowed is None:
            err("platform", f"The {i.platform_type} platform of '{i.exp_name}' cannot take part in a World Simulation.")
        elif i.simulator_type not in allowed:
            err("simulator_type", f"'{i.exp_name}': {i.platform_type} runs on {' or '.join(allowed)}, not {i.simulator_type}.")
        elif not supports_federation(i.platform_type, i.simulator_type):
            err("platform", f"The {i.platform_type} platform of '{i.exp_name}' cannot take part in a World Simulation.")
        if str(i.clock_mode) != "simulated" or str(i.feed_refresh) != "hourly":
            err("clock", f"'{i.exp_name}' must use the simulated clock with hourly slots ({SLOTS_PER_DAY} a day).")
        if i.other_federation:
            err("already_member", f"'{i.exp_name}' already belongs to the World Simulation '{i.other_federation}'.")
    # Populations may be disjoint or partly overlapping (INV-17): an agent takes part on the members whose populations
    # contain it. A member may even start without agents (clients can be added later), but not all of them.
    if not any(i.population_ids for i in infos):
        err("population", "At least one experiment needs a population.")
    return errors


def username_of(agent) -> str:
    """The username an agent has on every platform: its name (the runtime registers the account under it, INV-17)."""
    return str(agent.name)


# --------------------------------------------------------------------------------------------- database access
def federations_root() -> Path:
    from y_web.src.experiment.helpers import BASE_DIR

    return Path(BASE_DIR) / "experiments" / FEDERATION_FOLDER_NAME


def experiment_dir(exp) -> Path:
    from y_web.src.experiment.helpers import get_experiment_dir

    return get_experiment_dir(exp)


def experiment_db_uri(exp) -> Optional[str]:
    from y_web.src.experiment.helpers import get_experiment_engine_uri

    return get_experiment_engine_uri(exp)


def server_config_path(exp) -> Optional[Path]:
    folder = experiment_dir(exp)
    for name in SERVER_CONFIG_NAMES:
        if (folder / name).is_file():
            return folder / name
    return None


def client_config_paths(exp) -> list:
    """Per-client configuration files in the experiment folder (not backups, not summaries)."""
    folder = experiment_dir(exp)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("client*.json") if not p.name.startswith("client_summary"))


def _clock_of(exp) -> tuple:
    path = server_config_path(exp)
    clock = {}
    if path is not None:
        try:
            clock = json.loads(path.read_text()).get("clock") or {}
        except (OSError, ValueError):
            clock = {}
    return str(clock.get("mode", "simulated")), str(clock.get("feed_refresh", "hourly"))


def collect_member_info(exp) -> MemberInfo:
    from y_web.src.models.admin import Federation, FederationMember, Population_Experiment

    pops = frozenset(r.id_population for r in Population_Experiment.query.filter_by(id_exp=exp.idexp).all())
    link = (
        db.session.query(Federation)
        .join(FederationMember, FederationMember.federation_pk == Federation.id)
        .filter(FederationMember.exp_id == exp.idexp)
        .first()
    )
    mode, refresh = _clock_of(exp)
    return MemberInfo(
        exp_id=exp.idexp,
        exp_name=exp.exp_name,
        platform_type=exp.platform_type,
        simulator_type=exp.simulator_type or "Standard",
        running=bool(exp.running) or str(exp.exp_status) in ("active", "scheduled"),
        is_remote=bool(exp.is_remote),
        population_ids=pops,
        clock_mode=mode,
        feed_refresh=refresh,
        other_federation=link.name if link else None,
    )


def _population_agents(population_ids) -> list:
    from y_web.src.models.admin import Agent, Agent_Population

    return (
        db.session.query(Agent)
        .join(Agent_Population, Agent_Population.agent_id == Agent.id)
        .filter(Agent_Population.population_id.in_(list(population_ids)))
        .order_by(Agent.id)
        .all()
    )


def _check_usernames(exp, agents) -> None:
    """Agents are matched to their accounts by username: two agents of one member must not share it."""
    seen = {}
    for agent in agents:
        name = username_of(agent)
        if name in seen and seen[name] != agent.id:
            raise WorldSimulationError(
                [{"code": "username", "message": f"'{exp.exp_name}': the agents {seen[name]} and {agent.id} have the same name '{name}': "
                  "a World Simulation identifies the accounts of a platform by name."}]
            )
        seen[name] = agent.id


def _clean_options(options) -> dict:
    options = dict(options or {})
    unknown = set(options) - set(OPTION_BLOCKS)
    if unknown:
        raise WorldSimulationError({"code": "options", "message": f"Unknown parameter blocks: {sorted(unknown)}."})
    for key, value in options.items():
        if not isinstance(value, dict):
            raise WorldSimulationError({"code": "options", "message": f"'{key}' must be an object."})
    return options


def create_federation(name, exp_ids, owner="", seed=None, granularity="slot", options=None, exposures=False):
    """Validate and create a World Simulation; writes its folder, token and federation.json. Returns the model row.

    The member configurations are not touched until the World Simulation starts (see write_member_configs)."""
    from y_web.src.models.admin import Exps, Federation, FederationIdentityLink, FederationMember

    name = (name or "").strip()
    if not name:
        raise WorldSimulationError({"code": "name", "message": "The World Simulation needs a name."})
    if granularity not in GRANULARITIES:
        raise WorldSimulationError({"code": "granularity", "message": f"Granularity must be one of {GRANULARITIES}."})
    options = _clean_options(options)
    exp_ids = list(dict.fromkeys(int(i) for i in exp_ids))
    exps = [db.session.get(Exps, i) for i in exp_ids]
    if any(e is None for e in exps):
        raise WorldSimulationError({"code": "experiment", "message": "Unknown experiment."})
    infos = [collect_member_info(e) for e in exps]
    errors = validate_members(infos)
    if errors:
        raise WorldSimulationError(errors)
    seed = secrets.randbelow(2**31) if seed is None else int(seed)

    fed = Federation(
        federation_id=uuid.uuid4().hex,
        name=name,
        owner=owner or "",
        seed=seed,
        granularity=granularity,
        status="stopped",
        config_json=json.dumps({**options, "exposures": bool(exposures)}),
    )
    db.session.add(fed)
    db.session.flush()
    fed.federation_id = str(fed.id)  # numeric: the runtimes put it into source_ref and read it as an integer
    folder = federations_root() / f"federation_{fed.id}_{uuid.uuid4().hex[:8]}"
    fed.folder = str(folder)
    for position, exp in enumerate(sorted(exps, key=lambda e: e.platform_type)):
        db.session.add(
            FederationMember(
                federation_pk=fed.id, exp_id=exp.idexp, member=exp.platform_type, platform_type=exp.platform_type, position=position
            )
        )
    member_agents = {}
    for exp, info in sorted(zip(exps, infos), key=lambda pair: pair[0].platform_type):  # the same order whatever the selection
        agents = _population_agents(info.population_ids) if info.population_ids else []
        _check_usernames(exp, agents)
        member_agents[exp.platform_type] = agents
        for agent in agents:
            db.session.add(
                FederationIdentityLink(
                    federation_pk=fed.id,
                    global_agent_id=str(agent.id),
                    member=exp.platform_type,
                    local_account_id="",
                    username=username_of(agent),
                )
            )
    try:
        write_federation_files(fed)
    except Exception:
        db.session.rollback()
        shutil.rmtree(folder, ignore_errors=True)
        raise
    db.session.commit()
    return fed


def members_of(fed) -> list:
    from y_web.src.models.admin import Exps, FederationMember

    rows = db.session.query(FederationMember).filter_by(federation_pk=fed.id).order_by(FederationMember.position).all()
    return [(row, db.session.get(Exps, row.exp_id)) for row in rows]


def member_databases(fed) -> dict:
    """``{member: path of the server database}`` of the members of a World Simulation, for the analytics (read-only use)."""
    out = {}
    for row, exp in members_of(fed):
        try:
            out[row.member] = str(experiment_dir(exp) / "database_server.db")
        except Exception:  # noqa: BLE001 - an experiment without a folder simply has no database to read
            continue
    return out


def _legacy_names(links) -> dict:
    """{global_agent_id: name} for the agents of links written by older releases (no username stored)."""
    from y_web.src.models.admin import Agent

    ids = {int(l.global_agent_id) for l in links if l.username is None and l.global_agent_id.isdigit()}
    if not ids:
        return {}
    return {str(a.id): username_of(a) for a in db.session.query(Agent).filter(Agent.id.in_(ids)).all()}


def build_federation_config(fed) -> dict:
    """The content of federation.json (coordinator configuration, guide 4.8)."""
    from y_web.src.models.admin import FederationIdentityLink

    options = json.loads(fed.config_json or "{}")
    members = [
        {"member": row.member, "exp_id": row.exp_id, "platform": row.platform_type, "db_uri": experiment_db_uri(exp)}
        for row, exp in members_of(fed)
    ]
    links = db.session.query(FederationIdentityLink).filter_by(federation_pk=fed.id).order_by(FederationIdentityLink.id).all()
    names = _legacy_names(links)
    identity = []
    for l in links:
        username = None if l.global_agent_id.startswith("human:") else (l.username or names.get(l.global_agent_id))
        if username:
            # an agent: the coordinator learns the account from the runtime (INV-17); links of older releases carried a local
            # id equal to the agent id, which no runtime ever guaranteed
            identity.append({"global_agent_id": l.global_agent_id, "member": l.member, "username": username, "eligible": True})
        else:
            identity.append({"global_agent_id": l.global_agent_id, "member": l.member, "local_account_id": l.local_account_id, "eligible": True})
    config = {
        "federation_id": int(fed.federation_id),
        "seed": fed.seed,
        "granularity": fed.granularity,
        "protocol": PROTOCOL,
        "members": members,
        "identity": identity,
    }
    for block in OPTION_BLOCKS:
        if block in options:
            config[block] = options[block]
    if options.get("exposures") and "quoted" not in config:
        # members send exposures: a quoted cross-post is kept only if its author saw the content (P3, INV-16)
        config["quoted"] = {"require_exposure": True}
    return config


def write_federation_files(fed) -> None:
    """federation.json and the token file (mode 0600) in the folder of the World Simulation."""
    folder = Path(fed.folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "federation.json").write_text(json.dumps(build_federation_config(fed), indent=1))
    token_path = folder / "federation.token"
    if not token_path.exists():
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(16))
    fed.token = token_path.read_text().strip()


def member_section(fed, row, exp, enabled=True) -> dict:
    """The ``federation`` section of the configuration of a member (server and clients)."""
    folder = Path(fed.folder)
    options = json.loads(fed.config_json or "{}")
    crosspost = options.get("crosspost") or {}
    section = {
        "enabled": bool(enabled),
        "member": row.member,
        "federation_id": int(fed.federation_id),
        "exp_id": str(exp.idexp),
        "coordinator_file": str(folder / "federation_coordinator.json"),
        "token_file": str(folder / "federation.token"),
        "protocol": PROTOCOL,
        "exposures": bool(options.get("exposures", False)),
        # F6.2: who decides the cross-posts (coordinator rule or the agent itself) and how often an agent tries
        "crosspost_mode": str(crosspost.get("mode") or "coordinator_rule"),
    }
    # Topic migration: content that crosses platforms brings its topics and a missing one is created (default on).
    # Written only under the key each runtime reads: the forum server `topic_migration`, YSimulator `create_topics`;
    # the other runtimes migrate topics by default and have no switch.
    migrate = bool((options.get("topics") or {}).get("migration", True))
    if row.platform_type == "forum":
        section["topic_migration"] = migrate
    elif row.platform_type == "microblogging" and (getattr(exp, "simulator_type", None) or "Standard") == "HPC":
        section["create_topics"] = migrate
    elif row.platform_type == "microblogging" and not migrate:
        section["topic_migration"] = False  # YServer reads it; absent means on (its default)
    # F8: the people enrolled in this member (``human:<id>`` -> local account); the runtimes keep them out of the agent rules
    from y_web.src.federation.humans import accounts_by_member

    humans = accounts_by_member(fed).get(row.member)
    if humans:
        section["accounts"] = humans
    if "propensity" in crosspost:
        section["crosspost_propensity"] = float(crosspost["propensity"])
        section["seed"] = int(fed.seed)
    return section


def _update_json(path: Path, section: Optional[dict]) -> None:
    data = json.loads(path.read_text())
    if section is None:
        data.pop("federation", None)
    else:
        data["federation"] = section
    path.write_text(json.dumps(data, indent=2))


def write_member_configs(fed) -> list:
    """Install the federation section in the server and client configuration files of every member (idempotent).

    Done when the World Simulation starts and undone when it stops, so that a member experiment started on its own
    never waits for a coordinator."""
    written = []
    for row, exp in members_of(fed):
        section = member_section(fed, row, exp)
        paths = ([server_config_path(exp)] if server_config_path(exp) else []) + client_config_paths(exp)
        for path in paths:
            _update_json(path, section)
            written.append(str(path))
    return written


def remove_member_configs(fed) -> list:
    """Take the federation section out of the configuration files of every member (the experiments run alone again)."""
    removed = []
    for row, exp in members_of(fed):
        paths = ([server_config_path(exp)] if server_config_path(exp) else []) + client_config_paths(exp)
        for path in paths:
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if "federation" in data:
                _update_json(path, None)
                removed.append(str(path))
    return removed


def delete_federation(fed) -> None:
    """Delete a stopped World Simulation: configuration sections, rows and folder. The experiments are untouched otherwise."""
    from y_web.src.models.admin import FederationIdentityLink, FederationMember

    if fed.status not in ("stopped", "completed", "failed"):
        raise WorldSimulationError({"code": "running", "message": "Stop the World Simulation before deleting it."})
    remove_member_configs(fed)
    from y_web.src.models.admin import FederationHuman

    db.session.query(FederationIdentityLink).filter_by(federation_pk=fed.id).delete()
    db.session.query(FederationHuman).filter_by(federation_pk=fed.id).delete()  # F8: the enrolments go with the World Simulation
    db.session.query(FederationMember).filter_by(federation_pk=fed.id).delete()
    folder = fed.folder
    db.session.delete(fed)
    db.session.commit()
    if folder:
        shutil.rmtree(folder, ignore_errors=True)


def world_simulation_map(exp_ids=None) -> dict:
    """{experiment id: {"id", "name", "status"}} of the experiments that belong to a World Simulation (one query)."""
    from y_web.src.models.admin import Federation, FederationMember

    query = db.session.query(FederationMember.exp_id, Federation.id, Federation.name, Federation.status).join(
        Federation, FederationMember.federation_pk == Federation.id
    )
    if exp_ids is not None:
        query = query.filter(FederationMember.exp_id.in_(list(exp_ids)))
    # "locked": the World Simulation is starting, running, paused or stopping, so the member cannot be started or stopped alone
    return {
        e: {"id": i, "name": n, "status": s, "locked": s in ("starting", "running", "paused", "stopping")}
        for e, i, n, s in query.all()
    }


def world_simulation_of(exp_id):
    """The World Simulation ({"id", "name", "status"}) an experiment belongs to, or None."""
    try:
        return world_simulation_map([exp_id]).get(exp_id)
    except Exception:  # noqa: BLE001 - a page or a command must work even where the federation tables cannot be read
        return None
