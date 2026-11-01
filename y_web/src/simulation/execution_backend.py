"""
Backend routing helpers for experiment execution.

This module selects between the standard local-process execution path and the
HPC execution path based on ``experiment.simulator_type``. Standard experiments
use ``src.simulation`` server/client lifecycle helpers; HPC experiments use the
``src.hpc`` server/client helpers plus population backup handling.
"""

from y_web.src.hpc.client import start_hpc_client, stop_hpc_client
from y_web.src.hpc.population_backup import backup_population_for_hpc_client
from y_web.src.hpc.server import start_hpc_server, stop_hpc_server
from y_web.src.simulation.adhoc_client import stop_all_adhoc_clients
from y_web.src.simulation.client import start_client, terminate_client
from y_web.src.simulation.port_manager import terminate_process_on_port
from y_web.src.simulation.server import start_server, terminate_server_process


def uses_hpc_backend(experiment) -> bool:
    """Return whether the experiment runs on the HPC backend."""
    return getattr(experiment, "simulator_type", None) == "HPC"


def start_server_for_experiment(experiment):
    """Start the server for the given experiment using the correct backend."""
    if uses_hpc_backend(experiment):
        return start_hpc_server(experiment)
    return start_server(experiment)


def start_client_for_experiment(experiment, client, population, *, resume=True):
    """Start a client using the backend associated with the experiment."""
    if uses_hpc_backend(experiment):
        backup_population_for_hpc_client(experiment, client, population)
        return start_hpc_client(experiment, client, population)
    return start_client(experiment, client, population, resume=resume)


def stop_client_for_experiment(experiment, client, *, pause=False):
    """Stop or pause a client using the backend associated with the experiment."""
    if uses_hpc_backend(experiment):
        terminal_state = "paused" if pause else "manual_stop"
        return stop_hpc_client(client, terminal_state=terminal_state)
    return terminate_client(client, pause=pause)


def stop_server_for_experiment(experiment):
    """Stop the server for the given experiment using the correct backend."""
    stop_all_adhoc_clients(experiment, pause=False)
    if uses_hpc_backend(experiment):
        return stop_hpc_server(experiment.idexp)
    terminated = terminate_server_process(experiment.idexp)
    if not terminated:
        terminate_process_on_port(experiment.port)
    return terminated


# --------------------------------------------------------------------------------------------------------------
# World Simulation lifecycle (federation). New functions only: the experiment functions above are unchanged.
# Order: coordinator -> servers (the instant messaging gateway comes up with its server) -> clients; stop in reverse.
# --------------------------------------------------------------------------------------------------------------
FEDERATION_ACTIVE_STATES = ("starting", "running", "paused", "stopping")


def _federation_clients(exp):
    from y_web import db
    from y_web.src.models import Client

    return db.session.query(Client).filter_by(id_exp=exp.idexp).order_by(Client.id).all()


def _start_federation_clients(exp, *, resume=True):
    from y_web import db
    from y_web.src.models import Population

    started = []
    for client in _federation_clients(exp):
        if client.status == 1:
            continue
        population = db.session.get(Population, client.population_id)
        if population is None:
            raise RuntimeError(f"no population for client '{client.name}' of '{exp.exp_name}'")
        start_client_for_experiment(exp, client, population, resume=resume)
        client.status = 1
        db.session.commit()
        _register_gate_probe(exp, client)
        started.append(client.id)
    return started


def _register_gate_probe(exp, client):
    """Tell the watchdog how to recognise that this client is waiting at the gate (no database access in the probe)."""
    from types import SimpleNamespace

    from y_web.src.federation import coordinator_process as cp
    from y_web.src.federation import service
    from y_web.src.simulation.watchdog import register_gate_wait_probe

    fed = cp.federation_of_experiment(exp.idexp)
    if fed is None:
        return
    member = next((row.member for row, e in service.members_of(fed) if e.idexp == exp.idexp), None)
    snapshot = SimpleNamespace(folder=fed.folder, token=fed.token)
    register_gate_wait_probe(
        f"client_{client.id}", lambda: member in cp.waiting_members(cp.coordinator_status(snapshot, timeout=2.0))
    )


def _stop_federation_clients(exp, *, pause=False):
    from y_web import db

    errors = []
    for client in _federation_clients(exp):
        if client.status != 1:
            continue
        from y_web.src.simulation.watchdog import unregister_gate_wait_probe

        unregister_gate_wait_probe(f"client_{client.id}")
        try:
            stop_client_for_experiment(exp, client, pause=pause)
        except Exception as exc:  # keep stopping the others
            errors.append(f"client '{client.name}': {exc}")
        client.status = 0
        db.session.commit()
    return errors


def start_federation(fed, *, resume=True):
    """Start a World Simulation: coordinator, then the server of every member, then their clients.

    On any failure what was started is stopped again, the state becomes "failed" and the error is raised."""
    from y_web import db
    from y_web.src.federation import coordinator_process as cp
    from y_web.src.federation import service

    if fed.status in FEDERATION_ACTIVE_STATES:
        raise service.WorldSimulationError({"code": "state", "message": f"The World Simulation is {fed.status}."})
    members = service.members_of(fed)
    busy = [exp.exp_name for _, exp in members if exp.running or str(exp.exp_status) in ("active", "scheduled")]
    if busy:
        raise service.WorldSimulationError(
            {"code": "experiment_running", "message": "Member experiments are running: " + ", ".join(busy)}
        )
    fed.status = "starting"
    db.session.commit()
    try:
        service.write_federation_files(fed)  # federation.json is regenerated from the saved parameters at every (re)start
        cp.start_coordinator(fed)
        service.write_member_configs(fed)
        db.session.commit()
        from y_web.src.federation import humans as _humans

        for _, exp in members:
            exp.running = 1
            exp.exp_status = "active"
            db.session.commit()
            _humans.prepare_member(fed, exp)  # token of the microblogging human gateway, before its server starts
            start_server_for_experiment(exp)
            _humans.after_server_started(fed, exp)  # forum and photo sharing: their gateway processes
        for _, exp in members:
            _start_federation_clients(exp, resume=resume)
        fed.status = "running"
        db.session.commit()
    except Exception as exc:
        from y_web.src.federation.notifications import notify_failure

        _stop_federation_processes(fed, members)
        fed.status = "failed"
        db.session.commit()
        notify_failure(fed, "start", str(exc))
        raise
    return fed


def _stop_federation_processes(fed, members=None):
    from y_web import db
    from y_web.src.federation import coordinator_process as cp
    from y_web.src.federation import service

    members = members if members is not None else service.members_of(fed)
    errors = []
    for _, exp in reversed(members):
        errors += _stop_federation_clients(exp, pause=False)
    for _, exp in reversed(members):
        try:
            from y_web.src.federation import humans as _humans

            _humans.after_server_stopped(exp)
        except Exception as exc:  # a gateway that does not stop never blocks the stop
            errors.append(f"human gateway '{exp.exp_name}': {exc}")
        try:
            stop_server_for_experiment(exp)
        except Exception as exc:
            errors.append(f"server '{exp.exp_name}': {exc}")
        exp.running = 0
        exp.exp_status = "stopped"
        db.session.commit()
    service.remove_member_configs(fed)
    if not cp.stop_coordinator(fed):
        errors.append("the coordinator did not stop")
    db.session.commit()
    return errors


def stop_federation(fed):
    """Stop a World Simulation: clients, servers, coordinator (reverse of the start). Returns the list of errors met."""
    from y_web import db

    fed.status = "stopping"
    db.session.commit()
    errors = _stop_federation_processes(fed)
    fed.status = "stopped"
    db.session.commit()
    return errors


def pause_federation(fed):
    """Pause: the clients stop (paused), servers and coordinator stay up and keep the clock."""
    from y_web import db
    from y_web.src.federation import service

    if fed.status != "running":
        raise service.WorldSimulationError({"code": "state", "message": f"Cannot pause: the World Simulation is {fed.status}."})
    errors = []
    for _, exp in reversed(service.members_of(fed)):
        errors += _stop_federation_clients(exp, pause=True)
    fed.status = "paused"
    db.session.commit()
    return errors


def resume_federation(fed):
    """Resume a paused World Simulation: the clients start again from where they stopped."""
    from y_web import db
    from y_web.src.federation import service

    if fed.status != "paused":
        raise service.WorldSimulationError({"code": "state", "message": f"Cannot resume: the World Simulation is {fed.status}."})
    for _, exp in service.members_of(fed):
        _start_federation_clients(exp, resume=True)
    fed.status = "running"
    db.session.commit()
    return fed
