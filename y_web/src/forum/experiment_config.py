"""Configuration of YForum experiments and the experiment switches of the experiment page (plan F12).

The experiment page offers the same switches on every platform (toxicity, sentiment and emotion annotation, opinion
dynamics, stress/reward, memory). The page reads and writes top-level mirrors in ``server_config.json``; YForum acts on
other keys, and its schemas are strict, so a switch only does something when the runtime key is written as well:

* server: ``toxicity_annotation``, ``sentiment_annotation``, ``emotion_annotation``, ``perspective_api`` and
  ``stress_reward.enabled`` are the runtime keys themselves;
* client: ``simulation.emotion_annotation``, ``simulation.opinion_dynamics.enabled``, ``stress_reward`` and
  ``agents.memory_enabled``.

The module is pure: no Flask, no database.
"""

import copy
import secrets
from typing import Any, Dict, Iterable, Optional

FORUM_SERVER_NAME = "orchestrator_server"
FORUM_NAMESPACE = "forum_sim"
FORUM_DEFAULT_SLOTS_PER_DAY = 24
FORUM_MAX_SEED = 2**31 - 1


class ForumConfigError(ValueError):
    """A form value for a forum experiment is out of range."""


def _int_in_range(value, name: str, lo: int, hi: int, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ForumConfigError(f"{name} must be an integer") from None
    if not lo <= number <= hi:
        raise ForumConfigError(f"{name} must be between {lo} and {hi}")
    return number


def generate_forum_server_config(
    exp_name: str,
    db_uri: str,
    data_path: str,
    is_remote: bool = False,
    seed: Optional[int] = None,
    slots_per_day: Optional[int] = None,
    topics: Iterable[str] = (),
    toxicity_annotation: bool = False,
    sentiment_annotation: bool = False,
    emotion_annotation: bool = False,
    opinion_dynamics_enabled: bool = False,
    stress_reward_enabled: bool = False,
    memory_enabled: bool = False,
    perspective_api: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the ``server_config.json`` of a forum experiment on YForum.

    The seed is stored in the file so that a run can be repeated: when the form gives none, a random one is drawn once,
    at creation. SQLite only in this version (the server creates the database on first start). Federation and human
    participants stay off (they are opt-in in YForum).
    """
    config: Dict[str, Any] = {
        "server_name": FORUM_SERVER_NAME,
        "experiment_name": exp_name,
        "namespace": FORUM_NAMESPACE,
        "min_to_start": 1,
        "seed": _int_in_range(
            seed, "seed", 0, FORUM_MAX_SEED, secrets.randbelow(FORUM_MAX_SEED)
        ),
        "database": {"type": "sqlite", "sqlite": {"filename": "database_server.db"}},
        "simulation": {
            "num_slots_per_day": _int_in_range(
                slots_per_day,
                "slots_per_day",
                1,
                96,
                FORUM_DEFAULT_SLOTS_PER_DAY,
            )
        },
        "logging": {
            "enable_server_log": True,
            "enable_console_log": True,
            "enable_actor_log": True,
            "enable_request_log": True,
        },
        # host metadata read by the experiment pages (accepted by the schema, ignored by the runtime)
        "platform_type": "forum",
        "database_uri": db_uri,
        "data_path": data_path,
        "is_remote": bool(is_remote),
        "topics": [str(t).strip() for t in topics if str(t).strip()],
        # workflows stay locked until the researcher confirms the configuration, as on the other platforms
        "experiment_configuration_confirmed": False,
    }
    apply_experiment_switches(
        config,
        toxicity=toxicity_annotation,
        sentiment=sentiment_annotation,
        emotion=emotion_annotation,
        opinion=opinion_dynamics_enabled,
        stress_reward=stress_reward_enabled,
        memory=memory_enabled,
        perspective_api=perspective_api,
    )
    return config


def apply_experiment_switches(
    config: Dict[str, Any],
    *,
    toxicity: Optional[bool] = None,
    sentiment: Optional[bool] = None,
    emotion: Optional[bool] = None,
    opinion: Optional[bool] = None,
    stress_reward: Optional[bool] = None,
    memory: Optional[bool] = None,
    perspective_api: Optional[str] = None,
) -> Dict[str, Any]:
    """Set the experiment switches in a forum server configuration (mutated and returned).

    ``None`` leaves a switch as it is. The runtime keys and the mirrors the experiment page reads are written
    together. The server block ``stress_reward`` carries only ``enabled`` (its schema is strict): the details of
    stress/reward belong to the client configuration. Opinion dynamics and memory act in the client
    (:func:`apply_switches_to_client`); on the server they only have the mirror.
    """
    for key, value in (
        ("toxicity_annotation", toxicity),
        ("sentiment_annotation", sentiment),
        ("emotion_annotation", emotion),
    ):
        if value is not None:
            config[key] = bool(value)
        else:
            config.setdefault(key, False)

    if opinion is not None:
        config["opinion_dynamics_enabled"] = bool(opinion)
    else:
        config.setdefault("opinion_dynamics_enabled", False)

    block = config.get("stress_reward")
    enabled = (
        bool(stress_reward)
        if stress_reward is not None
        else bool((block or {}).get("enabled", config.get("stress_reward_enabled")))
    )
    config["stress_reward"] = {"enabled": enabled}
    config["stress_reward_enabled"] = enabled

    memory_block = config.get("memory")
    memory_block = dict(memory_block) if isinstance(memory_block, dict) else {}
    if memory is not None:
        memory_block["enabled"] = bool(memory)
    else:
        memory_block.setdefault("enabled", False)
    config["memory"] = {"enabled": bool(memory_block["enabled"])}

    # the scoring key is the runtime's: only when toxicity is on and a key is given
    if toxicity is not None or perspective_api is not None:
        on = bool(config.get("toxicity_annotation"))
        config["perspective_api"] = (
            perspective_api if (on and perspective_api) else None
        )
    return config


def apply_switches_to_client(
    client_config: Dict[str, Any],
    *,
    emotion: Optional[bool] = None,
    opinion: Optional[bool] = None,
    stress_reward: Optional[bool] = None,
    memory: Optional[bool] = None,
    stress_reward_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Set the experiment switches in the client configuration of a forum experiment (mutated and returned).

    Only keys of the client schema are written. A ``stress_reward`` under ``simulation`` wins over the top-level one in
    YForum, so when it exists it is kept in step.
    """
    simulation = client_config.get("simulation")
    if not isinstance(simulation, dict):
        simulation = {}
        client_config["simulation"] = simulation

    if emotion is not None:
        simulation["emotion_annotation"] = bool(emotion)

    if opinion is not None:
        opinions = simulation.get("opinion_dynamics")
        if not isinstance(opinions, dict):
            opinions = {}
        opinions["enabled"] = bool(opinion)
        simulation["opinion_dynamics"] = opinions

    if stress_reward is not None or stress_reward_config is not None:
        details = copy.deepcopy(stress_reward_config or {})
        block = client_config.get("stress_reward")
        block = dict(block) if isinstance(block, dict) else {}
        if "backward_rounds" in details:
            block["backward_rounds"] = int(details["backward_rounds"])
        if isinstance(details.get("system"), dict):
            block["system"] = details["system"]
        if stress_reward is not None:
            block["enabled"] = bool(stress_reward)
        elif "enabled" in details:
            block["enabled"] = bool(details["enabled"])
        client_config["stress_reward"] = block
        inner = simulation.get("stress_reward")
        if isinstance(inner, dict) and "enabled" in block:
            inner["enabled"] = block["enabled"]

    if memory is not None:
        agents = client_config.get("agents")
        if not isinstance(agents, dict):
            agents = {}
        agents["memory_enabled"] = bool(memory)
        client_config["agents"] = agents
    return client_config


def read_switches(config: Dict[str, Any]) -> Dict[str, bool]:
    """The switches as the experiment page shows them (the runtime keys first, the mirrors as fallback)."""
    stress = config.get("stress_reward")
    stress = stress if isinstance(stress, dict) else {}
    memory = config.get("memory")
    memory = memory if isinstance(memory, dict) else {}
    return {
        "toxicity": bool(config.get("toxicity_annotation", False)),
        "sentiment": bool(config.get("sentiment_annotation", False)),
        "emotion": bool(config.get("emotion_annotation", False)),
        "opinion": bool(config.get("opinion_dynamics_enabled", False)),
        "stress_reward": bool(
            stress.get("enabled", config.get("stress_reward_enabled", False))
        ),
        "memory": bool(memory.get("enabled", False)),
    }
