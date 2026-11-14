"""Checks of the client files of the platforms that write their own (dating, forum) and run length of their clients.

Platform-owned: the providers call them from ``normalize_hpc_client_config``; ``y_web.src.hpc.client`` re-exports them.
"""

import json
import os

from sqlalchemy import select

from y_web import db


def _normalize_dating_client_config(
    exp_folder: str, client_name: str, population_name: str, client_config_path: str
) -> None:
    """Check that a dating client file still matches its client and its population file.

    Nothing is rewritten (the file is the one the form wrote, and its content is part of what a resumed
    run is compared with); a mismatch stops the start with a clear message.
    """
    with open(client_config_path, "r", encoding="utf-8") as handle:
        client_config = json.load(handle)
    if client_config.get("client_name") != client_name:
        raise ValueError(
            f"{os.path.basename(client_config_path)} is for client "
            f"{client_config.get('client_name')!r}, not {client_name!r}"
        )
    population_file = client_config.get("population_file") or ""
    if not population_file or not os.path.isfile(
        os.path.join(exp_folder, population_file)
    ):
        raise FileNotFoundError(
            f"population file {population_file!r} of client {client_name!r} not found"
        )


def _normalize_forum_client_config(
    exp_folder: str, client_name: str, population_name: str, client_config_path: str
) -> None:
    """Check that a forum client file still matches its client and its population file.

    Nothing is rewritten (the file is the one the form wrote); a mismatch stops the start with a clear message.
    """
    with open(client_config_path, "r", encoding="utf-8") as handle:
        client_config = json.load(handle)
    if client_config.get("client_name") != client_name:
        raise ValueError(
            f"{os.path.basename(client_config_path)} is for client "
            f"{client_config.get('client_name')!r}, not {client_name!r}"
        )
    population_file = (client_config.get("population") or {}).get("file") or ""
    if not population_file or not os.path.isfile(
        os.path.join(exp_folder, population_file)
    ):
        raise FileNotFoundError(
            f"population file {population_file!r} of client {client_name!r} not found"
        )


def _set_dating_run_length(
    client_config_path: str, cli, unlimited_value: int = -1
) -> None:
    """Write in the client file how many days the dating or forum runtime runs from this start.

    The database holds the total length of the client (``Client.days``); the runtime counts the days from the
    moment it registers, so a restarted client gets what is left of the total.
    """
    from y_web.src.hpc.run_length import remaining_days, set_duration
    from y_web.src.models import Client_Execution

    with open(client_config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    slots = int(config.get("num_slots_per_day") or 24)
    execution = db.session.scalars(
        select(Client_Execution).filter_by(client_id=cli.id)
    ).first()
    last_day = getattr(execution, "last_active_day", -1) if execution else -1
    last_slot = getattr(execution, "last_active_hour", -1) if execution else -1
    days = remaining_days(cli.days, last_day or -1, last_slot or -1, slots)
    if days == 0:
        raise RuntimeError(
            f"Client '{cli.name}' has already run all its days: extend the simulation to run it further."
        )
    if days == -1:
        days = unlimited_value  # YForum reads 0 as "until stopped"
    stale = False
    if unlimited_value == 0 and isinstance(config.get("simulation"), dict):
        # forum schema is strict: drop the duration keys an older extension wrote under "simulation"
        for key in ("days", "num_days"):
            stale = config["simulation"].pop(key, None) is not None or stale
    if stale or config.get("num_days") != days:
        with open(client_config_path, "w", encoding="utf-8") as handle:
            json.dump(set_duration(config, days), handle, indent=2)
