"""
Canonical location for execution backend helpers.
"""

from y_web.src.hpc.client import start_hpc_client, stop_hpc_client
from y_web.src.hpc.population_backup import backup_population_for_hpc_client
from y_web.src.hpc.server import start_hpc_server, stop_hpc_server
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
        return stop_hpc_client(client)
    return terminate_client(client, pause=pause)


def stop_server_for_experiment(experiment):
    """Stop the server for the given experiment using the correct backend."""
    if uses_hpc_backend(experiment):
        return stop_hpc_server(experiment.idexp)
    terminated = terminate_server_process(experiment.idexp)
    if not terminated:
        terminate_process_on_port(experiment.port)
    return terminated
