"""Instant messaging (IM) experiments: server configuration generator and form validation."""

import datetime

IM_SERVER_NAME = "orchestrator_server"
IM_NAMESPACE = "yinstantmessaging"
IM_DEFAULT_DAYS = 7
IM_DEFAULT_TICKS_PER_ROUND = 12
IM_READY_TIMEOUT_SECONDS = 180


class ImConfigError(ValueError):
    """A form value for an IM experiment is out of range."""


def _int_in_range(value, name, lo, hi, default):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ImConfigError(f"{name} must be an integer") from None
    if not lo <= number <= hi:
        raise ImConfigError(f"{name} must be between {lo} and {hi}")
    return number


def _start_date(value):
    if value in (None, ""):
        return datetime.date.today().isoformat()
    try:
        return datetime.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ImConfigError("start_date must be an ISO date (YYYY-MM-DD)") from None


def _float_in_range(value, name, lo, hi, default):
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ImConfigError(f"{name} must be a number") from None
    if not lo <= number <= hi:
        raise ImConfigError(f"{name} must be between {lo} and {hi}")
    return number


def human_section(enabled=True, min_round_seconds=None, max_humans=None):
    """The ``human`` block of ``server_config.json`` (plan 5.8).

    Humans can register at any time, as on the other platforms, so YWeb always writes the block for the
    experiments it creates: the gateway is a non-blocking client and never holds a round. ``None`` (key
    absent) only when a caller explicitly turns it off, which keeps the configuration of older experiments.
    """
    if not enabled:
        return None
    return {
        "enabled": True,
        "max_humans": _int_in_range(max_humans, "max_humans", 1, 1000, 50),
        "pace": {
            "min_round_seconds": _float_in_range(
                min_round_seconds, "min_round_seconds", 0, 3600, 0
            )
        },
    }


def generate_im_server_config(
    exp_name,
    db_uri,
    data_path,
    is_remote=False,
    num_days=None,
    start_date=None,
    ticks_per_round=None,
    human_enabled=True,
    human_min_round_seconds=None,
    human_max_humans=None,
    toxicity_annotation=False,
    sentiment_annotation=False,
    emotion_annotation=False,
    opinion_dynamics_enabled=False,
    stress_reward_enabled=False,
    memory_enabled=False,
):
    """Build the ``server_config.json`` of an IM experiment (plan, table in 5.2).

    The structure follows the other platforms: the experiment-level switches (annotations, opinion dynamics,
    stress/reward, memory) sit at the top level, where the experiment page reads them, and are mirrored into the
    keys IM itself reads (``simulation.enable_*``, ``telegram.stress_reward``) by
    :func:`y_web.src.im.experiment_config.apply_experiment_switches`. The run length, start date and round
    length are set from the client form (see :func:`y_web.src.im.experiment_config.apply_time_parameters`);
    the defaults below apply until a client is created.

    The database is not pre-created: IM creates ``database_server.db`` on first start (SQLite only in v1).
    """
    config = {
        "server_name": IM_SERVER_NAME,
        "namespace": IM_NAMESPACE,
        "min_to_start": 1,
        "timeout_seconds": IM_READY_TIMEOUT_SECONDS,
        "ready_timeout_seconds": IM_READY_TIMEOUT_SECONDS,
        "database": {"type": "sqlite"},
        "simulation": {
            "num_days": _int_in_range(num_days, "num_days", 1, 3650, IM_DEFAULT_DAYS),
            "start_date": _start_date(start_date),
        },
        "telegram": {
            "time": {
                "ticks_per_round": _int_in_range(
                    ticks_per_round, "ticks_per_round", 1, 60, IM_DEFAULT_TICKS_PER_ROUND
                )
            }
        },
        "logging": {"enable_server_log": True, "enable_console_log": True, "compress_rotated": False},
        "platform_type": "instant_messaging",
        "database_uri": db_uri,
        "data_path": data_path,
        "is_remote": is_remote,
        "experiment_name": exp_name,
        # like the other platforms: workflows stay locked until the researcher confirms the configuration
        "experiment_configuration_confirmed": False,
    }
    from y_web.src.im.experiment_config import apply_experiment_switches

    apply_experiment_switches(
        config,
        toxicity=toxicity_annotation,
        sentiment=sentiment_annotation,
        emotion=emotion_annotation,
        opinion=opinion_dynamics_enabled,
        stress_reward=stress_reward_enabled,
        memory=memory_enabled,
    )
    human = human_section(human_enabled, human_min_round_seconds, human_max_humans)
    if human is not None:
        config["human"] = human
    return config
