#!/usr/bin/env python3
"""
Runner for file-backed ad hoc plugin clients.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path

from sqlalchemy.exc import OperationalError

ROOT = Path(__file__).resolve().parents[3]
PLUGIN_SRC = ROOT / "external" / "y_agents_plugins" / "src"
for candidate in (ROOT, PLUGIN_SRC):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

try:
    from y_agents_plugins.config import AppConfig  # noqa: E402
    from y_agents_plugins.core import AgentContext, AgentSpec  # noqa: E402
    from y_agents_plugins.db import ExperimentDatabase  # noqa: E402
    from y_agents_plugins.llm import LangChainTextGenerator  # noqa: E402
    from y_agents_plugins.runtime.app import build_default_registry  # noqa: E402
    from y_agents_plugins.runtime.execution_logger import ExecutionLogger  # noqa: E402
    from y_agents_plugins.runtime.executor import ActionExecutor  # noqa: E402
    from y_agents_plugins.runtime.loader import AgentSpecLoader  # noqa: E402
    from y_agents_plugins.runtime.manifest import load_agent_type_manifest  # noqa: E402
    from y_agents_plugins.runtime.scheduler import (  # noqa: E402
        ActivityProfileScheduler,
    )
except ModuleNotFoundError:
    # External plugin runtime is optional in base installations and in CI test jobs.
    AppConfig = None
    AgentContext = None
    AgentSpec = None
    ExperimentDatabase = None
    LangChainTextGenerator = None
    build_default_registry = None
    ExecutionLogger = None
    ActionExecutor = None
    AgentSpecLoader = None
    load_agent_type_manifest = None
    ActivityProfileScheduler = None

TERMINATE = False
SQLITE_LOCK_MAX_RETRIES = 6
SQLITE_LOCK_RETRY_DELAY_SECONDS = 0.5


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _write_state(state_path: Path, payload: dict) -> None:
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    tmp_path.replace(state_path)


def _load_state(state_path: Path) -> dict:
    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def _install_signal_handlers():
    def _handler(signum, frame):
        del signum, frame
        global TERMINATE
        TERMINATE = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def _update_tick_state(
    state_path: Path,
    state: dict,
    *,
    ticks: int,
    current_round,
    infinite: bool,
    expected_rounds: int,
):
    state.update(
        {
            "status": 1,
            "elapsed_time": ticks,
            "last_active_day": int(current_round.day),
            "last_active_hour": int(current_round.slot),
            "infinite": infinite,
            "expected_duration_rounds": -1 if infinite else expected_rounds,
            "progress": (
                0
                if infinite or expected_rounds <= 0
                else min(100, max(0, int(100 * ticks / expected_rounds)))
            ),
            "updated_at": _now_iso(),
        }
    )
    _write_state(state_path, state)


def _config_mtime(config_path: Path) -> float:
    try:
        return config_path.stat().st_mtime
    except OSError:
        return -1.0


def _client_field(config, field_name: str, default=None):
    client = getattr(config, "client", None)
    if isinstance(client, dict):
        return client.get(field_name, default)
    return getattr(client, field_name, default)


def _build_client_agent_spec(config) -> AgentSpec:
    client_id = _client_field(config, "client_id", "") or ""
    agent_type = _client_field(config, "agent_type", "") or ""
    agent_settings = _client_field(config, "agent_settings", {}) or {}
    email = str(_client_field(config, "email", "") or f"{client_id}@example.org")
    password = str(_client_field(config, "password", "") or client_id or "secret")
    activity_profile = str(_client_field(config, "activity_profile", "") or "Always On")
    daily_budget = float(_client_field(config, "daily_budget", 1) or 1)
    return AgentSpec(
        name=str(
            _client_field(config, "name", "") or client_id or agent_type or "client"
        ),
        username=client_id or agent_type or "client",
        email=email,
        password=password,
        agent_type=agent_type,
        activity_profile=activity_profile,
        daily_budget=daily_budget,
        owner=str(_client_field(config, "owner", "") or "experiment"),
        parameters=dict(agent_settings) if isinstance(agent_settings, dict) else {},
    )


def _apply_config_metadata_to_state(state: dict, config) -> dict:
    metadata = _client_field(config, "metadata", {}) or {}
    client_id = _client_field(config, "client_id", "") or ""
    agent_type = _client_field(config, "agent_type", "") or ""
    state["name"] = str(metadata.get("name") or client_id or state.get("name") or "")
    state["description"] = str(metadata.get("description") or "")
    state["population_id"] = metadata.get("population_id")
    state["population_name"] = str(
        metadata.get("population_name")
        or metadata.get("population")
        or state.get("population_name")
        or ""
    )
    state["agent_type_slug"] = str(
        metadata.get("agent_type_slug") or state.get("agent_type_slug") or ""
    )
    state["agent_type_display"] = str(
        metadata.get("agent_type_display")
        or agent_type
        or state.get("agent_type_display")
        or ""
    )
    state["agent_type_runtime"] = str(
        agent_type or state.get("agent_type_runtime") or ""
    )
    return state


def _is_sqlite_lock_error(exc: Exception) -> bool:
    if not isinstance(exc, OperationalError):
        return False
    return "database is locked" in str(exc).lower()


def _run_with_sqlite_retry(logger, connection, label: str, fn):
    delay = SQLITE_LOCK_RETRY_DELAY_SECONDS
    last_error = None
    for attempt in range(1, SQLITE_LOCK_MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as exc:
            if not _is_sqlite_lock_error(exc) or attempt == SQLITE_LOCK_MAX_RETRIES:
                raise
            last_error = exc
            try:
                connection.rollback()
            except Exception:
                logger.warning(
                    "Rollback failed after transient SQLite lock",
                    extra={"operation": label},
                    exc_info=True,
                )
            logger.warning(
                "Retrying SQLite-locked ad hoc operation",
                extra={
                    "operation": label,
                    "attempt": attempt,
                    "max_retries": SQLITE_LOCK_MAX_RETRIES,
                    "delay_seconds": delay,
                },
            )
            time.sleep(delay)
            delay *= 2
    if last_error is not None:
        raise last_error


def run(config_path: Path, state_path: Path) -> int:
    if AppConfig is None:
        raise RuntimeError(
            "y_agents_plugins is not installed. Ad hoc plugin runner is unavailable."
        )
    logger = logging.getLogger("adhoc_client_runner")
    execution_logger = ExecutionLogger()
    config = AppConfig.from_file(config_path)
    config_mtime = _config_mtime(config_path)
    state = _load_state(state_path)
    state["status"] = 1
    state["pid"] = state.get("pid") or None
    state["updated_at"] = _now_iso()
    state["error"] = None
    state = _apply_config_metadata_to_state(state, config)
    _write_state(state_path, state)

    manifest = load_agent_type_manifest()
    manifest.require_known_agent_type(config.client.agent_type)
    registry = build_default_registry()
    llm = LangChainTextGenerator.from_client_config(config.client)
    agent = registry.create(
        config.client.agent_type,
        settings=config.client.agent_settings,
        llm_client=llm,
    )
    sqlite_path = config.database.sqlite_path
    if sqlite_path is not None:
        sqlite_path = Path(sqlite_path)
        while not TERMINATE and not sqlite_path.exists():
            time.sleep(config.database.poll_interval_seconds)
        if TERMINATE:
            return 0

    database = ExperimentDatabase(config.database.url)
    executor = ActionExecutor(database)
    scheduler = ActivityProfileScheduler(config.client.simulation)
    loader = AgentSpecLoader()
    managed_agents = loader.load(
        config.client.agents_json_path,
        expected_agent_type=config.client.agent_type,
    )
    for managed_agent in managed_agents:
        config.client.simulation.is_agent_active(managed_agent.activity_profile, 0)

    expected_rounds = int(config.client.max_ticks or 0)
    infinite = config.client.max_ticks is None or bool(
        config.client.simulation.raw.get("run_until_stopped")
    )
    last_seen_round_id = None
    previous_round = None
    ticks = int(state.get("elapsed_time") or 0)

    connection = database.connect()
    try:
        while not TERMINATE:
            try:
                current_round = database.get_current_round(connection)
                break
            except RuntimeError as exc:
                if "No rows found in rounds table" not in str(exc):
                    raise
                time.sleep(config.database.poll_interval_seconds)
        else:
            return 0

        agent.setup_database(database, connection)
        client_agent = _build_client_agent_spec(config)
        combined_agents = tuple(managed_agents) + (client_agent,)
        _run_with_sqlite_retry(
            logger,
            connection,
            "register_agents",
            lambda: database.register_agents(
                connection, combined_agents, joined_on=current_round.id
            ),
        )

        while not TERMINATE and (infinite or ticks < expected_rounds):
            latest_config_mtime = _config_mtime(config_path)
            if latest_config_mtime != config_mtime:
                config = AppConfig.from_file(config_path)
                config_mtime = latest_config_mtime
                llm = LangChainTextGenerator.from_client_config(config.client)
                agent = registry.create(
                    config.client.agent_type,
                    settings=config.client.agent_settings,
                    llm_client=llm,
                )
                agent.setup_database(database, connection)
                scheduler = ActivityProfileScheduler(config.client.simulation)
                expected_rounds = int(config.client.max_ticks or 0)
                infinite = config.client.max_ticks is None or bool(
                    config.client.simulation.raw.get("run_until_stopped")
                )
                state = _load_state(state_path)
                state = _apply_config_metadata_to_state(state, config)
                state["infinite"] = infinite
                state["expected_duration_rounds"] = -1 if infinite else expected_rounds
                state["updated_at"] = _now_iso()
                _write_state(state_path, state)
                logger.info(
                    "Reloaded ad hoc client config",
                    extra={
                        "client_id": config.client.client_id,
                        "config_path": str(config_path),
                    },
                )

            pending_rounds = database.get_rounds_after(connection, last_seen_round_id)
            if not pending_rounds:
                time.sleep(config.database.poll_interval_seconds)
                continue

            for current_round in pending_rounds:
                if TERMINATE or (not infinite and ticks >= expected_rounds):
                    break

                context = AgentContext(
                    client_id=config.client.client_id,
                    current_round=current_round,
                    previous_round=previous_round,
                    users=database.get_users(connection),
                    recent_posts=database.get_recent_posts(
                        connection,
                        round_id=current_round.id,
                        limit=config.client.recent_posts_limit,
                    ),
                    managed_agents=managed_agents,
                    connection=connection,
                )

                logger.info(
                    "Executing synchronized plugin tick",
                    extra={
                        "client_id": config.client.client_id,
                        "round_id": current_round.id,
                        "day": current_round.day,
                        "slot": current_round.slot,
                    },
                )
                for managed_agent in managed_agents:
                    if not scheduler.is_active(managed_agent, current_round):
                        continue
                    tick_started = time.perf_counter()
                    success = True
                    error = None
                    try:
                        actions = agent.on_tick(context, managed_agent)
                        for action in actions:
                            _run_with_sqlite_retry(
                                logger,
                                connection,
                                f"execute:{action.action_type}",
                                lambda action=action: executor.execute(
                                    connection,
                                    context=context,
                                    agent=managed_agent,
                                    action=action,
                                ),
                            )
                    except Exception as exc:
                        success = False
                        error = str(exc)
                        raise
                    finally:
                        execution_logger.log_execution(
                            agent_name=managed_agent.username,
                            method_name="plugin_tick",
                            execution_time=time.perf_counter() - tick_started,
                            tid=current_round.id,
                            day=current_round.day,
                            hour=current_round.slot,
                            success=success,
                            error=error,
                        )

                previous_round = current_round
                last_seen_round_id = current_round.id
                ticks += 1
                _update_tick_state(
                    state_path,
                    state,
                    ticks=ticks,
                    current_round=current_round,
                    infinite=infinite,
                    expected_rounds=expected_rounds,
                )

        state = _load_state(state_path)
        state.update(
            {
                "status": 0,
                "pid": None,
                "completed": (
                    not infinite and ticks >= expected_rounds and not TERMINATE
                ),
                "progress": (
                    state.get("progress", 0)
                    if infinite
                    else (
                        100
                        if ticks >= expected_rounds
                        else int(state.get("progress", 0) or 0)
                    )
                ),
                "updated_at": _now_iso(),
            }
        )
        _write_state(state_path, state)
        return 0
    except Exception as exc:
        state = _load_state(state_path)
        state.update(
            {
                "status": 0,
                "pid": None,
                "error": str(exc),
                "updated_at": _now_iso(),
            }
        )
        _write_state(state_path, state)
        raise
    finally:
        execution_logger.close()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a file-backed YSocial plugin client."
    )
    parser.add_argument(
        "--config", required=True, help="Path to the ad hoc client config."
    )
    parser.add_argument(
        "--state", required=True, help="Path to the ad hoc client state file."
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    _install_signal_handlers()
    return run(Path(args.config), Path(args.state))


if __name__ == "__main__":
    raise SystemExit(main())
