"""Run length of a client written into its client file (platforms that count the days from the client's start)."""

import json

from sqlalchemy import select

from y_web import db


def _write_client_run_length(
    client_config_path: str, cli, unlimited_value: int = -1
) -> None:
    """Write in the client file how many days the runtime runs from this start.

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
        days = unlimited_value  # some runtimes read 0 as "until stopped"
    stale = False
    if unlimited_value == 0 and isinstance(config.get("simulation"), dict):
        # a strict client schema: drop the duration keys an older extension wrote under "simulation"
        for key in ("days", "num_days"):
            stale = config["simulation"].pop(key, None) is not None or stale
    if stale or config.get("num_days") != days:
        with open(client_config_path, "w", encoding="utf-8") as handle:
            json.dump(set_duration(config, days), handle, indent=2)
