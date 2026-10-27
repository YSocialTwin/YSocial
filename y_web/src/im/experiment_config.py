"""Experiment-level settings of instant messaging (IM) experiments.

The experiment page of every platform has the same switches (annotations, opinion dynamics, stress/reward,
memory) and the same "update configuration" action. Their state lives in the experiment's server configuration
file at the top level, where the page reads it. IM reads its own keys, so the functions here write both: the
mirror that YWeb reads and the keys IM acts on. They are pure (no Flask, no database) so they can be tested alone.

IM keys written (see ``schemas/config/server_config.json`` and ``client_config.json`` of YInstantMessaging):

* server: ``simulation.enable_toxicity``, ``simulation.enable_sentiment``, ``simulation.memory_enabled`` and
  ``telegram.stress_reward`` (the same structure as YSocial's stress/reward ``system`` block, without the
  events IM does not have);
* client: ``simulation.emotion_annotation``, ``opinion_dynamics.enabled``, ``stress_reward.enabled`` and
  ``agents.memory_enabled``.
"""

import copy
import datetime
from typing import Any, Dict, Optional

# the stress/reward blocks YSocial and IM have in common, and the events IM implements
_SHARED_BLOCKS = ("coupling", "churn", "activity_impact")
_IM_EVENTS = {"reaction": ("like", "dislike"), "comment": ("positive", "neutral", "critical", "hostile", "supportive")}


def _flag(value) -> bool:
    return bool(value)


def stress_reward_to_im(config: Optional[dict]) -> Dict[str, Any]:
    """YSocial's normalized stress/reward settings (``enabled``, ``backward_rounds``, ``system``) as IM's block."""
    config = config or {}
    system = config.get("system") or {}
    out: Dict[str, Any] = {
        "enabled": _flag(config.get("enabled")),
        "backward_rounds": int(config.get("backward_rounds") or 24),
    }
    for block in _SHARED_BLOCKS:
        if isinstance(system.get(block), dict):
            out[block] = copy.deepcopy(system[block])
    events = system.get("events")
    if isinstance(events, dict):
        kept: Dict[str, Any] = {}
        for family, subtypes in _IM_EVENTS.items():
            if isinstance(events.get(family), dict):
                kept[family] = {s: copy.deepcopy(events[family][s]) for s in subtypes if s in events[family]}
        if kept:
            out["events"] = kept
    return out


def stress_reward_from_im(block: Optional[dict]) -> Dict[str, Any]:
    """IM's ``telegram.stress_reward`` as the shape the settings page edits (missing parts are filled by the caller)."""
    block = block or {}
    system = {k: copy.deepcopy(block[k]) for k in (*_SHARED_BLOCKS, "events") if isinstance(block.get(k), dict)}
    return {"enabled": _flag(block.get("enabled")), "backward_rounds": int(block.get("backward_rounds") or 24), "system": system}


def apply_experiment_switches(
    config: dict,
    *,
    toxicity: Optional[bool] = None,
    sentiment: Optional[bool] = None,
    emotion: Optional[bool] = None,
    opinion: Optional[bool] = None,
    stress_reward: Optional[bool] = None,
    memory: Optional[bool] = None,
    stress_reward_config: Optional[dict] = None,
) -> dict:
    """Set the experiment switches in a server configuration (mutated and returned).

    ``None`` leaves a switch as it is. ``stress_reward_config`` is YSocial's normalized block; when given it
    also replaces the detail settings.
    """
    simulation = config.setdefault("simulation", {})
    if toxicity is not None:
        config["toxicity_annotation"] = bool(toxicity)
        simulation["enable_toxicity"] = bool(toxicity)
    elif "toxicity_annotation" not in config:
        config["toxicity_annotation"] = bool(simulation.get("enable_toxicity", False))
    if sentiment is not None:
        config["sentiment_annotation"] = bool(sentiment)
        simulation["enable_sentiment"] = bool(sentiment)
    elif "sentiment_annotation" not in config:
        config["sentiment_annotation"] = bool(simulation.get("enable_sentiment", False))
    if emotion is not None:
        config["emotion_annotation"] = bool(emotion)
    config.setdefault("emotion_annotation", False)
    if opinion is not None:
        config["opinion_dynamics_enabled"] = bool(opinion)
    config.setdefault("opinion_dynamics_enabled", False)
    if memory is not None:
        memory_block = config.get("memory") if isinstance(config.get("memory"), dict) else {}
        memory_block["enabled"] = bool(memory)
        config["memory"] = memory_block
        simulation["memory_enabled"] = bool(memory)
    else:
        config.setdefault("memory", {"enabled": bool(simulation.get("memory_enabled", False))})

    telegram = config.setdefault("telegram", {})
    if stress_reward_config is not None:
        mirror = copy.deepcopy(stress_reward_config)
        if stress_reward is not None:
            mirror["enabled"] = bool(stress_reward)
        config["stress_reward"] = mirror
        config["stress_reward_enabled"] = bool(mirror.get("enabled"))
        telegram["stress_reward"] = stress_reward_to_im(mirror)
    elif stress_reward is not None:
        mirror = config.get("stress_reward") if isinstance(config.get("stress_reward"), dict) else {}
        mirror["enabled"] = bool(stress_reward)
        config["stress_reward"] = mirror
        config["stress_reward_enabled"] = bool(stress_reward)
        im_block = telegram.get("stress_reward") if isinstance(telegram.get("stress_reward"), dict) else {}
        im_block["enabled"] = bool(stress_reward)
        telegram["stress_reward"] = im_block
    else:
        config.setdefault("stress_reward_enabled", bool((telegram.get("stress_reward") or {}).get("enabled", False)))
    return config


def apply_switches_to_client(
    client_config: dict,
    *,
    emotion: Optional[bool] = None,
    opinion: Optional[bool] = None,
    stress_reward: Optional[bool] = None,
    memory: Optional[bool] = None,
) -> dict:
    """Set the experiment switches in a client configuration (mutated and returned).

    Turning a switch on never overrides a parameter the researcher already chose: only ``enabled`` changes.
    """
    if emotion is not None:
        client_config.setdefault("simulation", {})["emotion_annotation"] = bool(emotion)
    if opinion is not None:
        block = client_config.get("opinion_dynamics") if isinstance(client_config.get("opinion_dynamics"), dict) else {}
        block["enabled"] = bool(opinion)
        if opinion:
            block.setdefault("model_name", "bounded_confidence")
        client_config["opinion_dynamics"] = block
    if stress_reward is not None:
        block = client_config.get("stress_reward") if isinstance(client_config.get("stress_reward"), dict) else {}
        block["enabled"] = bool(stress_reward)
        client_config["stress_reward"] = block
    if memory is not None:
        client_config.setdefault("agents", {})["memory_enabled"] = bool(memory)
    return client_config


def read_switches(config: dict) -> Dict[str, bool]:
    """The switches as the experiment page shows them (the YWeb mirror first, IM's own keys as fallback)."""
    simulation = config.get("simulation") or {}
    telegram_stress = (config.get("telegram") or {}).get("stress_reward") or {}
    memory = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    return {
        "toxicity": bool(config.get("toxicity_annotation", simulation.get("enable_toxicity", False))),
        "sentiment": bool(config.get("sentiment_annotation", simulation.get("enable_sentiment", False))),
        "emotion": bool(config.get("emotion_annotation", False)),
        "opinion": bool(config.get("opinion_dynamics_enabled", False)),
        "stress_reward": bool(config.get("stress_reward_enabled", telegram_stress.get("enabled", False))),
        "memory": bool(memory.get("enabled", simulation.get("memory_enabled", False))),
    }


class TimeParameterError(ValueError):
    """The run length, start date or round length conflicts with what is already fixed."""


def apply_time_parameters(
    config: dict,
    *,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    ticks_per_round: Optional[int] = None,
    other_clients: int = 0,
    run_started: bool = False,
) -> dict:
    """Carry the time parameters of a client form into the server configuration (mutated and returned).

    In IM the clock belongs to the server, but the researcher sets the run in the client form like on the other
    platforms. The server runs as long as its longest client, so ``days`` only grows the run. The start date and
    the round length are the experiment's: the first client sets them, a later client must agree (the form
    pre-fills them), and once a run has started none of them can change without a reset, because the server
    keeps a hash of its configuration.
    """
    simulation = config.setdefault("simulation", {})
    telegram_time = config.setdefault("telegram", {}).setdefault("time", {})
    if run_started:
        if days is not None and int(days) > int(simulation.get("num_days", 0)):
            raise TimeParameterError("the run already started: reset the experiment to make it longer")
        if start_date is not None and str(start_date) != str(simulation.get("start_date")):
            raise TimeParameterError("the run already started: the start date cannot change")
        if ticks_per_round is not None and int(ticks_per_round) != int(telegram_time.get("ticks_per_round", 12)):
            raise TimeParameterError("the run already started: the round length cannot change")
        return config
    if days is not None:
        current = int(simulation.get("num_days", 0)) if other_clients else 0
        simulation["num_days"] = max(int(days), current)
    if other_clients:
        if start_date is not None and str(start_date) != str(simulation.get("start_date")):
            raise TimeParameterError("the start date is the experiment's: use the one of the existing clients")
        if ticks_per_round is not None and int(ticks_per_round) != int(telegram_time.get("ticks_per_round", 12)):
            raise TimeParameterError("the round length is the experiment's: use the one of the existing clients")
    else:
        if start_date:
            simulation["start_date"] = datetime.date.fromisoformat(str(start_date)).isoformat()
        if ticks_per_round is not None:
            telegram_time["ticks_per_round"] = int(ticks_per_round)
    return config


class AdvancedSettingsError(ValueError):
    """A server-level setting is out of range or cannot change any more."""


def _server_config_path(exp_folder: str) -> str:
    import os

    return os.path.join(exp_folder, "server_config.json")


def run_started(exp_folder: str) -> bool:
    """Whether the server already created its database (its configuration hash is then fixed)."""
    import os

    return os.path.isfile(os.path.join(exp_folder, "database_server.db"))


def read_advanced_settings(exp_folder: str) -> Dict[str, Any]:
    """The server-level settings the experiment page offers under *Advanced Settings*."""
    import json
    import os

    path = _server_config_path(exp_folder)
    config: Dict[str, Any] = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            config = json.load(handle) or {}
    human = config.get("human") if isinstance(config.get("human"), dict) else {}
    return {
        "min_round_seconds": float((human.get("pace") or {}).get("min_round_seconds", 0) or 0),
        "max_humans": int(human.get("max_humans", 50) or 50),
        "locked": run_started(exp_folder),
    }


def write_advanced_settings(exp_folder: str, *, min_round_seconds=None, max_humans=None) -> Dict[str, Any]:
    """Validate and write the advanced settings into ``server_config.json``.

    The server keeps a hash of its configuration, so nothing changes once a run has started (reset it first).
    """
    import json

    if run_started(exp_folder):
        raise AdvancedSettingsError("the run already started: reset the experiment to change these settings")
    try:
        seconds = float(min_round_seconds) if min_round_seconds not in (None, "") else 0.0
        humans = int(max_humans) if max_humans not in (None, "") else 50
    except (TypeError, ValueError):
        raise AdvancedSettingsError("the values must be numbers") from None
    if not 0 <= seconds <= 3600:
        raise AdvancedSettingsError("minimum round duration must be between 0 and 3600 seconds")
    if not 1 <= humans <= 1000:
        raise AdvancedSettingsError("maximum number of participants must be between 1 and 1000")
    path = _server_config_path(exp_folder)
    with open(path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    human = config.get("human") if isinstance(config.get("human"), dict) else {"enabled": True}
    human["enabled"] = True
    human["max_humans"] = humans
    human.setdefault("pace", {})["min_round_seconds"] = seconds
    config["human"] = human
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=4)
    return config


def load_server_config(exp_folder: str) -> Dict[str, Any]:
    """The experiment's ``server_config.json`` (an empty dict when it does not exist yet)."""
    import json
    import os

    path = _server_config_path(exp_folder)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle) or {}


def save_server_config(exp_folder: str, config: Dict[str, Any]) -> None:
    import json

    with open(_server_config_path(exp_folder), "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=4)


def time_parameters(config: Dict[str, Any]) -> Dict[str, Any]:
    """The run length, start date and round length a server configuration holds (what the client form pre-fills)."""
    simulation = config.get("simulation") or {}
    return {
        "days": int(simulation.get("num_days", 7) or 7),
        "start_date": str(simulation.get("start_date") or ""),
        "ticks_per_round": int(((config.get("telegram") or {}).get("time") or {}).get("ticks_per_round", 12) or 12),
    }
