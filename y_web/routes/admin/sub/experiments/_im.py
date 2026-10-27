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


def generate_im_server_config(
    exp_name,
    db_uri,
    data_path,
    is_remote=False,
    num_days=None,
    start_date=None,
    ticks_per_round=None,
):
    """Build the ``server_config.json`` of an IM experiment (plan, table in 5.2).

    The database is not pre-created: IM creates ``database_server.db`` on first start (SQLite only in v1).
    """
    return {
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
        "logging": {"enable_server_log": True, "enable_console_log": True},
        "platform_type": "instant_messaging",
        "database_uri": db_uri,
        "data_path": data_path,
        "is_remote": is_remote,
        "experiment_name": exp_name,
    }
