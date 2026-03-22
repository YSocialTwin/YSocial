"""
Canonical location for execution backend helpers.
"""

import sys

from y_web.src.hpc.client import start_hpc_client, stop_hpc_client
from y_web.src.hpc.population_backup import backup_population_for_hpc_client
from y_web.src.hpc.server import start_hpc_server, stop_hpc_server
from y_web.src.simulation.client import start_client, terminate_client
from y_web.src.simulation.port_manager import terminate_process_on_port
from y_web.src.simulation.server import start_server, terminate_server_process


def _legacy_override(name, default):
    """Allow legacy shim monkeypatches to keep affecting canonical helpers."""
    legacy_module = sys.modules.get("y_web.utils.execution_backend")
    if legacy_module is None:
        return default
    return getattr(legacy_module, name, default)


def uses_hpc_backend(experiment) -> bool:
    """Return whether the experiment runs on the HPC backend."""
    return getattr(experiment, "simulator_type", None) == "HPC"


def start_server_for_experiment(experiment):
    """Start the server for the given experiment using the correct backend."""
    if uses_hpc_backend(experiment):
        return _legacy_override("start_hpc_server", start_hpc_server)(experiment)
    return _legacy_override("start_server", start_server)(experiment)


def start_client_for_experiment(experiment, client, population, *, resume=True):
    """Start a client using the backend associated with the experiment."""
    if uses_hpc_backend(experiment):
        _legacy_override(
            "backup_population_for_hpc_client", backup_population_for_hpc_client
        )(experiment, client, population)
        return _legacy_override("start_hpc_client", start_hpc_client)(
            experiment, client, population
        )
    return _legacy_override("start_client", start_client)(
        experiment, client, population, resume=resume
    )


def stop_client_for_experiment(experiment, client, *, pause=False):
    """Stop or pause a client using the backend associated with the experiment."""
    if uses_hpc_backend(experiment):
        return _legacy_override("stop_hpc_client", stop_hpc_client)(client)
    return _legacy_override("terminate_client", terminate_client)(client, pause=pause)


def stop_server_for_experiment(experiment):
    """Stop the server for the given experiment using the correct backend."""
    if uses_hpc_backend(experiment):
        return _legacy_override("stop_hpc_server", stop_hpc_server)(experiment.idexp)
    terminated = _legacy_override("terminate_server_process", terminate_server_process)(
        experiment.idexp
    )
    if not terminated:
        _legacy_override("terminate_process_on_port", terminate_process_on_port)(
            experiment.port
        )
    return terminated
