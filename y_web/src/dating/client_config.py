"""Client configuration of dating experiments (plan S3, IR-D-06).

The advanced settings of a client are generated from ``schemas/config/client_config.json`` of YDating
(:mod:`y_web.src.dating.schema_forms`). The few keys YWeb sets itself are listed in :data:`INTERNAL`, each with
the reason; ``tests/test_dating_settings.py`` checks that every other key of the schema has a control.
"""

import os
from typing import Any, Dict, List, Optional

from y_web.src.dating import schema_forms as sf

SCHEMA = os.path.join("config", "client_config.json")

# keys YWeb writes itself, and why they are not on the form
INTERNAL: Dict[str, str] = {
    "client_name": "the name field of the form",
    "num_days": "the duration field of the form",
    "num_slots_per_day": "an experiment setting (server configuration): all clients agree on the slot length",
    "seed": "derived from the experiment seed, so that one seed reproduces the whole run",
    "namespace": "found by the client in the marker the server writes",
    "ray_address": "found by the client in the marker the server writes",
    "population_file": "the population chosen on the form (a file of the experiment folder)",
    "language": "the prompt language of the client (prompt settings)",
    "memory.enabled": "the Memory switch of the experiment configuration",
    "memory.package_path": "managed by the runtime",
    "memory.run_id": "managed by the runtime",
}

MAX_DAYS = 3650


class DatingClientFormError(ValueError):
    """The client form is not valid (``problems`` carry the reasons)."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def schema(repo_dir: str) -> Dict[str, Any]:
    return sf.load_schema(repo_dir, SCHEMA)


def form_fields(repo_dir: str) -> List[sf.Field]:
    return sf.fields(schema(repo_dir), INTERNAL)


def grouped(fields: List[sf.Field]) -> Dict[str, List[sf.Field]]:
    out: Dict[str, List[sf.Field]] = {}
    for f in fields:
        out.setdefault(f.group, []).append(f)
    return out


def parse_days(raw: Any) -> int:
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        raise DatingClientFormError(["num_days: must be an integer"]) from None
    if days != -1 and not 1 <= days <= MAX_DAYS:
        raise DatingClientFormError([f"num_days: must be between 1 and {MAX_DAYS}"])
    return days


def build_client_config(
    repo_dir: str,
    *,
    name: str,
    population_file: str,
    days: int,
    server_config: Dict[str, Any],
    memory_enabled: bool,
    language: str,
    form: Any = None,
    label_of=lambda s: s,
) -> Dict[str, Any]:
    """The ``client_config`` of a client: schema defaults, the values of the form, then the keys YWeb sets.

    Raises :class:`DatingClientFormError` for an out-of-range value or when the result does not satisfy the
    schema of the runtime.
    """
    sch = schema(repo_dir)
    try:
        values = sf.parse_form(form or {}, sf.fields(sch, INTERNAL), label_of)
    except sf.SettingsError as exc:
        raise DatingClientFormError(exc.problems) from None
    config = sf.merge(sf.defaults(sch), values)
    config["client_name"] = name
    config["num_days"] = days
    config["population_file"] = population_file
    config["num_slots_per_day"] = int(
        sf.get_path(server_config, "simulation.num_slots_per_day", 24)
    )
    config["seed"] = int(server_config.get("seed", 0) or 0)
    config["language"] = language or "en"
    sf.set_path(config, "memory.enabled", bool(memory_enabled))
    problems = sf.schema_problems(sch, config)
    if problems:
        raise DatingClientFormError(problems)
    return config


def values_for_form(
    repo_dir: str, config: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    """Text of every control: from a stored client configuration, else the schema defaults."""
    sch = schema(repo_dir)
    base = sf.merge(sf.defaults(sch), config or {})
    return {
        f.path: sf.to_form_text(sf.get_path(base, f.path, f.default), f)
        for f in sf.fields(sch, INTERNAL)
    }


def remaining_days(
    total_days: int, last_day: int, last_slot: int, slots_per_day: int
) -> int:
    """Days the runtime must run when the client (re)starts so that the client ends after ``total_days`` in all.

    The runtime counts ``num_days`` from the day it registers (days and slots start at 1). A client that never ran
    (``last_day`` < 1) runs the whole total; one stopped inside a day runs that day again; ``-1`` means until
    stopped. A result of 0 means that nothing is left (the runtime would read 0 as "unlimited": the caller refuses).
    """
    if int(total_days) <= 0:
        return -1
    if int(last_day) < 1:
        start = 1
    else:
        start = int(last_day) + (1 if int(last_slot) >= int(slots_per_day) else 0)
    return max(0, 1 + int(total_days) - start)


def set_duration(config: Dict[str, Any], days: int) -> Dict[str, Any]:
    """The client configuration with the number of days the runtime runs from now."""
    updated = dict(config)
    updated["num_days"] = int(days)
    return updated


def apply_form(
    repo_dir: str, config: Dict[str, Any], form: Any, label_of=lambda s: s
) -> Dict[str, Any]:
    """``config`` with the values of the form of the client page; raises :class:`DatingClientFormError`."""
    sch = schema(repo_dir)
    try:
        values = sf.parse_form(form, sf.fields(sch, INTERNAL), label_of)
    except sf.SettingsError as exc:
        raise DatingClientFormError(exc.problems) from None
    merged = sf.merge(config, values)
    problems = sf.schema_problems(sch, merged)
    if problems:
        raise DatingClientFormError(problems)
    return merged
