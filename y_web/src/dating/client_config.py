"""Client configuration of dating experiments (plan S3, IR-D-06).

The advanced settings of a client are generated from ``schemas/config/client_config.json`` of YDating
(:mod:`y_web.src.dating.schema_forms`). The few keys YWeb sets itself are listed in :data:`INTERNAL`, each with
the reason; ``tests/test_dating_settings.py`` checks that every other key of the schema has a control.
"""

import importlib.util
import os
import re
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
    "profile_generation.images.folder": "the web interface shows the files of the media folder of the experiment",
    "memory.enabled": "the Memory switch of the experiment configuration",
    "memory.package_path": "managed by the runtime",
    "memory.run_id": "managed by the runtime",
    "activity.profiles": "derived from the activity profiles of the population (hours of each profile)",
}

# The OpenAI-compatible servers are reached through the base address (the runtime adds /v1/chat/completions),
# while the other platforms ask for the address with /v1: both are accepted.
LLM_URL_DEFAULT = "http://127.0.0.1:11434/v1"

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


DEFAULT_DAYS = 30


def days_from_form(form: Any) -> int:
    """Duration of the form: the number of days (30 by default) or -1 when "Run until stopped" is checked.

    The controls are the ones of the clients of the other platforms (``days`` and ``infinite_duration``).
    """
    if str(form.get("infinite_duration", "")).strip().lower() in ("on", "true", "1"):
        return -1
    raw = form.get("days")
    if raw is None or str(raw).strip() == "":
        raw = form.get("num_days", DEFAULT_DAYS)
    return parse_days(raw)


def images_available() -> bool:
    """The optional packages of the image generation (``requirements-images.txt``) can be imported."""
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "diffusers"))


def mode_defaults(llm_enabled: bool, images_ok: bool = False) -> Dict[str, Any]:
    """Defaults that depend on the experiment: language models for everything, or rules for everything.

    With LLM agents on, the agents decide the swipes, write the messages and the profile texts with the model, and
    the photos are drawn with the image model (when its packages are installed). With LLM agents off nothing calls a
    model: swipes follow the utility rules, messages come from the canned phrases and the texts are not generated.
    """
    if llm_enabled:
        return {
            "llm": {"backend": "openai", "url": LLM_URL_DEFAULT},
            "swipe": {"mode": "llm"},
            "conversation": {"enabled": True, "text_source": "llm"},
            "profile_generation": {
                "enabled": True,
                "images": {
                    "enabled": bool(images_ok),
                    "generator": "diffusion" if images_ok else "stub",
                },
            },
            "stress_reward": {"tone_source": "llm"},
        }
    return {
        "llm": {"backend": "stub"},
        "swipe": {"mode": "rule", "llm_vision": False},
        "conversation": {"text_source": "template"},
        "profile_generation": {"enabled": False, "images": {"enabled": False}},
        "stress_reward": {"tone_source": "neutral"},
    }


def rule_settings() -> Dict[str, Any]:
    """The settings that a client without language models always has (the image generation is its own choice)."""
    return {
        "llm": {"backend": "stub"},
        "swipe": {"mode": "rule", "llm_vision": False},
        "conversation": {"text_source": "template"},
        "profile_generation": {"enabled": False},
        "stress_reward": {"tone_source": "neutral"},
    }


def _normalise_llm(config: Dict[str, Any], llm_enabled: bool) -> List[str]:
    """Clean the language model settings (address without /v1) and return what is missing."""
    llm = config.get("llm") or {}
    url = str(llm.get("url") or "").strip().rstrip("/")
    llm["url"] = (
        re.sub(r"/v1(/.*)?$", "", url) if llm.get("backend") == "openai" else url
    )
    problems: List[str] = []
    if llm_enabled and llm.get("backend") != "stub" and not llm.get("model"):
        problems.append(
            "llm.model: select a model (fetch the models of the server first)"
        )
    if (config.get("swipe") or {}).get("llm_vision") and not llm.get("vision_model"):
        problems.append(
            "swipe.llm_vision: select a vision model to show the photos to the model"
        )
    config["llm"] = llm
    return problems


def profile_weights(hours_by_name: Dict[str, str]) -> Dict[str, List[float]]:
    """``activity.profiles`` from the activity profiles of the population (name -> comma separated active hours).

    An agent with a profile is active in the hours of the profile (weight 1) and not in the others (weight 0), as
    in the other platforms. A profile that covers the 24 hours (Always On) is left out: its agents keep the hourly
    activity curve of the client.
    """
    out: Dict[str, List[float]] = {}
    for name, hours in (hours_by_name or {}).items():
        active = {
            int(h)
            for h in str(hours or "").split(",")
            if h.strip().isdigit() and 0 <= int(h) <= 23
        }
        if active and len(active) < 24:
            out[str(name).strip().lower()] = [
                1.0 if h in active else 0.0 for h in range(24)
            ]
    return out


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
    llm_enabled: bool = False,
    images_ok: bool = False,
    activity_hours: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """The ``client_config`` of a client: schema defaults, the defaults of the mode, the form, then the keys YWeb sets.

    ``llm_enabled`` is the LLM switch of the experiment: with it off the settings that need a model are not on the
    form and keep their rule-based value. Raises :class:`DatingClientFormError` for an out-of-range value or when the
    result does not satisfy the schema of the runtime.
    """
    sch = schema(repo_dir)
    form = form or {}
    try:
        values = sf.parse_form(form, sf.fields(sch, INTERNAL), label_of)
    except sf.SettingsError as exc:
        raise DatingClientFormError(exc.problems) from None
    base = sf.merge(sf.defaults(sch), mode_defaults(llm_enabled, images_ok))
    config = sf.merge(base, values)
    if not llm_enabled:  # nothing of the form can switch a model on
        config = sf.merge(config, rule_settings())
    if activity_hours:
        config["activity"]["profiles"] = profile_weights(activity_hours)
    config["client_name"] = name
    config["num_days"] = days
    config["population_file"] = population_file
    config["num_slots_per_day"] = int(
        sf.get_path(server_config, "simulation.num_slots_per_day", 24)
    )
    config["seed"] = int(server_config.get("seed", 0) or 0)
    config["language"] = language or "en"
    sf.set_path(config, "memory.enabled", bool(memory_enabled))
    problems = _normalise_llm(config, llm_enabled) + sf.schema_problems(sch, config)
    if problems:
        raise DatingClientFormError(problems)
    return config


def values_for_form(
    repo_dir: str,
    config: Optional[Dict[str, Any]] = None,
    llm_enabled: bool = False,
    images_ok: bool = False,
) -> Dict[str, str]:
    """Text of every control: from a stored client configuration, else the defaults of the mode."""
    sch = schema(repo_dir)
    base = sf.merge(sf.defaults(sch), mode_defaults(llm_enabled, images_ok))
    base = sf.merge(base, config or {})
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
    problems = _normalise_llm(merged, True) + sf.schema_problems(sch, merged)
    if problems:
        raise DatingClientFormError(problems)
    return merged
