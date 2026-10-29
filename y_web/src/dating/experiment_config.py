"""Server configuration of YDating experiments (plan S1, IR-D-04).

The ``server_config.json`` of a dating experiment must satisfy the strict JSON Schema of YDating
(``schemas/config/server_config.json``). Besides the runtime keys it carries the host metadata the experiment
pages of YSocial read at the top level, as on the other platforms (``platform_type``, ``experiment_name``, the
annotation mirrors, the confirmation flag). The module is pure: no Flask, no database.
"""

import secrets
from typing import Any, Dict, Optional

DATING_SERVER_NAME = "orchestrator_server"
DATING_NAMESPACE = "dating_sim"
DATING_DEFAULT_SLOTS_PER_DAY = 24
DATING_MAX_SEED = 2**31 - 1


class DatingConfigError(ValueError):
    """A form value for a dating experiment is out of range."""


def _int_in_range(value, name: str, lo: int, hi: int, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise DatingConfigError(f"{name} must be an integer") from None
    if not lo <= number <= hi:
        raise DatingConfigError(f"{name} must be between {lo} and {hi}")
    return number


def generate_dating_server_config(
    exp_name: str,
    db_uri: str,
    data_path: str,
    is_remote: bool = False,
    seed: Optional[int] = None,
    slots_per_day: Optional[int] = None,
    toxicity_annotation: bool = False,
    sentiment_annotation: bool = False,
    emotion_annotation: bool = False,
    stress_reward_enabled: bool = False,
    memory_enabled: bool = False,
) -> Dict[str, Any]:
    """Build the ``server_config.json`` of a dating experiment.

    The experiment seed is stored in the file, so that a run can be repeated: when the form gives none a random
    one is drawn once, at creation. SQLite only in v1 (the database is created by the server on first start).
    Opinion dynamics do not exist in dating and are always off.
    """
    config: Dict[str, Any] = {
        "server_name": DATING_SERVER_NAME,
        "namespace": DATING_NAMESPACE,
        "min_to_start": 1,
        "seed": _int_in_range(
            seed, "seed", 0, DATING_MAX_SEED, secrets.randbelow(DATING_MAX_SEED)
        ),
        "database": {"type": "sqlite", "sqlite": {"filename": "database_server.db"}},
        "simulation": {
            "num_slots_per_day": _int_in_range(
                slots_per_day,
                "slots_per_day",
                1,
                96,
                DATING_DEFAULT_SLOTS_PER_DAY,
            )
        },
        "logging": {
            "enable_server_log": True,
            "enable_console_log": True,
            "enable_actor_log": True,
            "enable_request_log": True,
        },
        "annotations": {
            "sentiment": bool(sentiment_annotation),
            "toxicity": bool(toxicity_annotation),
            "emotions": bool(emotion_annotation),
        },
        "stress_reward": {"enabled": bool(stress_reward_enabled)},
        # host metadata read by the experiment pages (accepted by the schema, ignored by the runtime)
        "platform_type": "dating",
        "experiment_name": exp_name,
        "database_uri": db_uri,
        "data_path": data_path,
        "is_remote": bool(is_remote),
        "toxicity_annotation": bool(toxicity_annotation),
        "sentiment_annotation": bool(sentiment_annotation),
        "emotion_annotation": bool(emotion_annotation),
        "opinion_dynamics_enabled": False,
        "stress_reward_enabled": bool(stress_reward_enabled),
        "memory": {"enabled": bool(memory_enabled)},
        # like the other platforms: workflows stay locked until the researcher confirms the configuration
        "experiment_configuration_confirmed": False,
    }
    return config


def apply_experiment_switches(
    config: Dict[str, Any],
    *,
    toxicity: Optional[bool] = None,
    sentiment: Optional[bool] = None,
    emotion: Optional[bool] = None,
    stress_reward: Optional[bool] = None,
    memory: Optional[bool] = None,
) -> Dict[str, Any]:
    """Set the experiment switches in a dating server configuration (mutated and returned).

    The experiment page reads the top-level mirrors, the runtime the ``annotations`` and ``stress_reward``
    blocks: both are written. ``None`` leaves a switch as it is. Only ``stress_reward.enabled`` changes: the
    detail settings the researcher chose stay. Opinion dynamics do not exist in dating (always off).
    """
    annotations = config.get("annotations")
    annotations = dict(annotations) if isinstance(annotations, dict) else {}
    for name, key, mirror, value in (
        ("sentiment", "sentiment", "sentiment_annotation", sentiment),
        ("toxicity", "toxicity", "toxicity_annotation", toxicity),
        ("emotions", "emotions", "emotion_annotation", emotion),
    ):
        if value is not None:
            annotations[key] = bool(value)
        else:
            annotations.setdefault(key, bool(config.get(mirror, False)))
        config[mirror] = bool(annotations[key])
    config["annotations"] = annotations

    block = config.get("stress_reward")
    block = dict(block) if isinstance(block, dict) else {}
    if stress_reward is not None:
        block["enabled"] = bool(stress_reward)
    else:
        block.setdefault("enabled", bool(config.get("stress_reward_enabled", False)))
    config["stress_reward"] = block
    config["stress_reward_enabled"] = bool(block["enabled"])

    memory_block = config.get("memory")
    memory_block = dict(memory_block) if isinstance(memory_block, dict) else {}
    if memory is not None:
        memory_block["enabled"] = bool(memory)
    else:
        memory_block.setdefault("enabled", False)
    config["memory"] = memory_block

    config["opinion_dynamics_enabled"] = False
    config.pop("perspective_api", None)
    return config


def read_switches(config: Dict[str, Any]) -> Dict[str, bool]:
    """The switches as the experiment page shows them (the runtime blocks first, the mirrors as fallback)."""
    annotations = (
        config.get("annotations") if isinstance(config.get("annotations"), dict) else {}
    )
    stress = (
        config.get("stress_reward")
        if isinstance(config.get("stress_reward"), dict)
        else {}
    )
    memory = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    return {
        "toxicity": bool(
            annotations.get("toxicity", config.get("toxicity_annotation", False))
        ),
        "sentiment": bool(
            annotations.get("sentiment", config.get("sentiment_annotation", False))
        ),
        "emotion": bool(
            annotations.get("emotions", config.get("emotion_annotation", False))
        ),
        "opinion": False,
        "stress_reward": bool(
            stress.get("enabled", config.get("stress_reward_enabled", False))
        ),
        "memory": bool(memory.get("enabled", False)),
    }
