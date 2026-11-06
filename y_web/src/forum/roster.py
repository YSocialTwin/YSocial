"""The roster file a forum client (YForum) keeps, and when the initial opinions may still change.

YForum saves the agents it registered in ``agents_<client>.json`` (or ``population.agents_file``) next to the client
configuration, and a client that finds the file resumes from it instead of reading the population file again. The
initial opinions set on the opinion page live in the population file, so after the first start of a client a roster
that is already there would hide every later change of them.

A client that has never run (``Client_Execution`` without progress) has nothing to resume: its roster, left by an
aborted or earlier start, is removed so the population file is read again. A client that did run keeps its roster
(a resume must not lose its agents); the caller is told so it can say that the new opinions apply to a restart from
scratch.
"""

from __future__ import annotations

import json
import os
from typing import Optional

REMOVED = "removed"
ABSENT = "absent"
KEPT_STARTED = "kept_started"


def roster_path(client_config_path: str, client_name: str) -> str:
    """The roster file of a forum client, in the folder of its configuration file."""
    folder = os.path.dirname(client_config_path)
    name = None
    try:
        with open(client_config_path, "r", encoding="utf-8") as handle:
            name = (
                (json.load(handle).get("population") or {}).get("agents_file")
            ) or None
    except (OSError, ValueError):
        name = None
    return os.path.join(folder, name or f"agents_{client_name}.json")


def client_has_started(execution) -> bool:
    """True when the client has made progress (a ``Client_Execution`` with a day or an hour done)."""
    if execution is None:
        return False
    day = getattr(execution, "last_active_day", None)
    hour = getattr(execution, "last_active_hour", None)
    return (day is not None and day >= 0) or (hour is not None and hour >= 0)


def reset_unstarted_roster(
    client_config_path: str, client_name: str, execution=None
) -> str:
    """Remove the roster of a client that never ran; keep it when the client already has progress."""
    path = roster_path(client_config_path, client_name)
    if not os.path.exists(path):
        return ABSENT
    if client_has_started(execution):
        return KEPT_STARTED
    os.remove(path)
    return REMOVED
