"""What the core offers a platform at run time, kept apart from the provider contract.

A platform never imports core internals: it asks for these services. Each one forwards to the core when called
(the core modules are not loaded when a provider is imported), so the core can move its internals without
touching a platform, as long as the service keeps its meaning.
"""

from __future__ import annotations

from typing import Any, Optional


def writable_path(relative_path: str = "") -> str:
    """Absolute path in the data folder the application writes to."""
    from y_web.src.system.path_utils import get_writable_path

    return get_writable_path(relative_path)


def db_session() -> Any:
    """The database session of the application (``db.session``)."""
    from y_web import db

    return db.session


def client_execution(client: Any) -> Any:
    """The execution record of a client (its progress), or ``None`` when it never ran."""
    from sqlalchemy import select

    from y_web import db
    from y_web.src.models import Client_Execution

    return db.session.scalars(
        select(Client_Execution).filter_by(client_id=client.id)
    ).first()


def database_type() -> str:
    """Backend of the admin database: ``"sqlite"`` or ``"postgresql"`` (needs an application context)."""
    from y_web.routes.admin.sub.experiments._helpers import _get_database_type

    return _get_database_type()


def experiment_folder(experiment: Any) -> str:
    """Folder that holds the files of an experiment (needs an application context)."""
    from y_web.routes.admin.sub.experiments._helpers import _get_experiment_folder

    return _get_experiment_folder(writable_path(), experiment, database_type())


def hpc_experiment_folder(experiment: Any) -> str:
    """Folder of an experiment as the HPC runtime lays it out."""
    from y_web.src.hpc.client import _resolve_hpc_experiment_folder

    return _resolve_hpc_experiment_folder(experiment)


def set_client_run_length(
    client_config: str, client: Any, unlimited_value: int = -1
) -> None:
    """Write in the client file how many days the client runs from this start (what is left of ``Client.days``)."""
    from y_web.src.hpc.client import _set_dating_run_length

    _set_dating_run_length(client_config, client, unlimited_value=unlimited_value)


def sync_client_duration(client_config: str, client: Any) -> Optional[int]:
    """Make the client file say how long the client runs, as ``Client.days`` does."""
    from y_web.src.hpc.client import _sync_hpc_client_duration_from_config

    return _sync_hpc_client_duration_from_config(client_config, client)


def generate_hpc_server_config(**options: Any) -> dict:
    """Server configuration of a new experiment on the HPC runtime (the keyword arguments of the core generator)."""
    from y_web.routes.admin.sub.experiments._crud import generate_hpc_config

    return generate_hpc_config(**options)


def write_prompt_pack(
    name: str, destination: Any, language: Optional[str] = None
) -> None:
    """Write the prompt file a new experiment or client starts from (English as is, other languages merged)."""
    from y_web.src.system import prompt_packs

    prompt_packs.write_pack(name, destination, language)
