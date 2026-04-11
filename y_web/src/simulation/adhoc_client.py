"""
File-backed execution helpers for plugin-managed ad hoc clients.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

from y_web.src.simulation.process_registry import _register_process, _unregister_process
from y_web.src.simulation.server import detect_env_handler
from y_web.src.simulation.subprocess_env import build_subprocess_env
from y_web.src.system.path_utils import get_resource_path, get_writable_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _experiment_folder_name(experiment) -> str:
    db_uri = current_app.config.get("SQLALCHEMY_BINDS", {}).get("db_exp", "")
    if db_uri.startswith("sqlite"):
        return experiment.db_name.split(os.sep)[1]
    return experiment.db_name.removeprefix("experiments_")


def experiment_folder(experiment) -> Path:
    return (
        Path(get_writable_path())
        / "y_web"
        / "experiments"
        / _experiment_folder_name(experiment)
    )


def _config_paths(experiment) -> list[Path]:
    folder = experiment_folder(experiment)
    if not folder.exists():
        return []
    return sorted(
        path
        for path in folder.glob("adhoc_client_*.json")
        if not path.name.endswith(".state.json")
    )


def client_key_from_config_path(config_path: Path) -> str:
    stem = config_path.stem
    prefix = "adhoc_client_"
    return stem[len(prefix) :] if stem.startswith(prefix) else stem


def config_path_for_client(experiment, client_key: str) -> Path:
    safe_key = os.path.basename((client_key or "").strip())
    path = experiment_folder(experiment) / f"adhoc_client_{safe_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"Ad hoc client config not found for key '{safe_key}'")
    return path


def state_path_for_config(config_path: Path) -> Path:
    return config_path.with_suffix(".state.json")


def stdout_log_path_for_config(config_path: Path) -> Path:
    return config_path.with_suffix(".stdout.log")


def stderr_log_path_for_config(config_path: Path) -> Path:
    return config_path.with_suffix(".stderr.log")


def client_log_path_for_config(config_path: Path) -> Path:
    return config_path.with_name(
        f"{client_key_from_config_path(config_path)}_client.log"
    )


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(tmp_path, path)


def _initial_state_from_config(config_path: Path, config: dict) -> dict:
    client = config.get("client", {}) if isinstance(config, dict) else {}
    metadata = client.get("metadata", {}) if isinstance(client, dict) else {}
    simulation = client.get("simulation", {}) if isinstance(client, dict) else {}
    max_ticks = client.get("max_ticks")
    run_until_stopped = bool(simulation.get("run_until_stopped")) or max_ticks is None
    expected_rounds = -1 if run_until_stopped else int(max_ticks)

    return {
        "version": 1,
        "client_key": client_key_from_config_path(config_path),
        "config_path": str(config_path),
        "agents_path": str(client.get("agents_json_path") or ""),
        "name": str(
            metadata.get("name") or client.get("client_id") or config_path.stem
        ),
        "description": str(metadata.get("description") or ""),
        "population_id": metadata.get("population_id"),
        "population_name": str(
            metadata.get("population_name") or metadata.get("population") or ""
        ),
        "agent_type_slug": str(metadata.get("agent_type_slug") or ""),
        "agent_type_display": str(
            metadata.get("agent_type_display") or client.get("agent_type") or ""
        ),
        "agent_type_runtime": str(client.get("agent_type") or ""),
        "status": 0,
        "pid": None,
        "progress": 0,
        "infinite": run_until_stopped,
        "elapsed_time": 0,
        "expected_duration_rounds": expected_rounds,
        "last_active_day": -1,
        "last_active_hour": -1,
        "completed": False,
        "error": None,
        "stdout_log": str(stdout_log_path_for_config(config_path)),
        "stderr_log": str(stderr_log_path_for_config(config_path)),
        "client_log": str(client_log_path_for_config(config_path)),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def _refresh_static_state_fields(state: dict, config_path: Path, config: dict) -> dict:
    refreshed = dict(state)
    baseline = _initial_state_from_config(config_path, config)
    for key in (
        "client_key",
        "config_path",
        "agents_path",
        "name",
        "description",
        "population_id",
        "population_name",
        "agent_type_slug",
        "agent_type_display",
        "agent_type_runtime",
        "infinite",
        "expected_duration_rounds",
        "stdout_log",
        "stderr_log",
        "client_log",
    ):
        refreshed[key] = baseline.get(key)
    return refreshed


def ensure_state_for_config(config_path: Path) -> dict:
    config = read_json(config_path) or {}
    state_path = state_path_for_config(config_path)
    state = read_json(state_path)
    if not isinstance(state, dict):
        state = _initial_state_from_config(config_path, config)
        write_json(state_path, state)
        return state

    merged = _initial_state_from_config(config_path, config)
    merged.update(state)
    merged = _refresh_static_state_fields(merged, config_path, config)
    merged["config_path"] = str(config_path)
    merged["agents_path"] = str(
        (config.get("client", {}) or {}).get("agents_json_path")
        or merged.get("agents_path")
        or ""
    )
    merged["updated_at"] = merged.get("updated_at") or _now_iso()

    pid = merged.get("pid")
    if merged.get("status") == 1 and (
        not pid or not _is_running_adhoc_process(int(pid))
    ):
        merged["status"] = 0
        merged["pid"] = None
        merged["updated_at"] = _now_iso()
        if not merged.get("completed"):
            merged["error"] = merged.get("error") or "Process not running"

    write_json(state_path, merged)
    return merged


def list_adhoc_clients(experiment) -> list[dict]:
    clients = []
    for config_path in _config_paths(experiment):
        state = ensure_state_for_config(config_path)
        state["client_key"] = client_key_from_config_path(config_path)
        clients.append(state)
    return clients


def initialize_state_for_config(config_path: str | Path) -> dict:
    return ensure_state_for_config(Path(config_path))


def _is_running_adhoc_process(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil

        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        cmdline = " ".join(proc.cmdline()).lower()
        return (
            "adhoc_client_runner.py" in cmdline
            or "--run-adhoc-client-subprocess" in cmdline
        )
    except psutil.ZombieProcess:
        return False
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return False
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _find_matching_adhoc_pids(config_path: Path) -> list[int]:
    try:
        import psutil
    except Exception:
        return []

    target = str(config_path)
    matches: list[int] = []
    for proc in psutil.process_iter(["pid", "cmdline", "status"]):
        try:
            if proc.info.get("status") == psutil.STATUS_ZOMBIE:
                continue
            cmdline = proc.info.get("cmdline") or []
            if not cmdline:
                continue
            joined = " ".join(cmdline)
            if (
                "adhoc_client_runner.py" not in joined
                and "--run-adhoc-client-subprocess" not in joined
            ):
                continue
            if target not in joined:
                continue
            matches.append(int(proc.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    return matches


def _terminate_pid(pid: int, *, timeout_seconds: float = 3.0) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _is_running_adhoc_process(pid):
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass

    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not _is_running_adhoc_process(pid):
            return True
        time.sleep(0.05)
    return not _is_running_adhoc_process(pid)


def _runner_command(config_path: Path, state_path: Path) -> tuple[list[str], str]:
    runner_script = get_resource_path(
        os.path.join("y_web", "src", "simulation", "adhoc_client_runner.py")
    )

    if getattr(sys, "frozen", False):
        return (
            [
                sys.executable,
                "--run-adhoc-client-subprocess",
                "--config",
                str(config_path),
                "--state",
                str(state_path),
            ],
            os.getcwd(),
        )

    python_cmd = detect_env_handler()
    workspace_root = str(Path(__file__).resolve().parents[3])
    if (
        isinstance(python_cmd, str)
        and " " in python_cmd
        and not os.path.isabs(python_cmd)
    ):
        cmd = python_cmd.split() + [
            runner_script,
            "--config",
            str(config_path),
            "--state",
            str(state_path),
        ]
    else:
        cmd = [
            python_cmd,
            runner_script,
            "--config",
            str(config_path),
            "--state",
            str(state_path),
        ]
    return cmd, workspace_root


def start_adhoc_client(experiment, client_key: str):
    config_path = config_path_for_client(experiment, client_key)
    state_path = state_path_for_config(config_path)
    state = ensure_state_for_config(config_path)
    if state.get("status") == 1 and state.get("pid"):
        if _is_running_adhoc_process(int(state["pid"])):
            return None

    cmd, cwd = _runner_command(config_path, state_path)
    out_path = stdout_log_path_for_config(config_path)
    err_path = stderr_log_path_for_config(config_path)
    client_log_path = client_log_path_for_config(config_path)

    out_file = open(out_path, "a", encoding="utf-8", buffering=1)
    err_file = open(err_path, "a", encoding="utf-8", buffering=1)

    env = build_subprocess_env(
        {
            "Y_ADHOC_CLIENT_SUBPROCESS": "1",
            "PYTHONUNBUFFERED": "1",
            "YAGENTS_CLIENT_LOG_FILE": str(client_log_path),
        }
    )

    if not getattr(sys, "frozen", False):
        workspace_root = str(Path(__file__).resolve().parents[3])
        plugin_src = str(Path(workspace_root) / "external" / "y_agents_plugins" / "src")
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in [workspace_root, plugin_src, existing_path] if part
        )

    if sys.platform.startswith("win"):
        process = subprocess.Popen(
            cmd,
            stdout=out_file,
            stderr=err_file,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            env=env,
            cwd=cwd,
        )
    else:
        process = subprocess.Popen(
            cmd,
            stdout=out_file,
            stderr=err_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
            cwd=cwd,
        )

    state.update(
        {
            "status": 1,
            "pid": process.pid,
            "error": None,
            "stdout_log": str(out_path),
            "stderr_log": str(err_path),
            "client_log": str(client_log_path),
            "updated_at": _now_iso(),
        }
    )
    write_json(state_path, state)
    _register_process(
        f"adhoc_client_{experiment.idexp}_{client_key}", process, out_file, err_file
    )
    return process


def stop_adhoc_client(experiment, client_key: str, *, pause: bool = True) -> bool:
    config_path = config_path_for_client(experiment, client_key)
    state_path = state_path_for_config(config_path)
    state = ensure_state_for_config(config_path)
    _unregister_process(f"adhoc_client_{experiment.idexp}_{client_key}")

    candidate_pids = set()
    pid = state.get("pid")
    if pid:
        candidate_pids.add(int(pid))
    candidate_pids.update(_find_matching_adhoc_pids(config_path))

    for candidate_pid in sorted(candidate_pids):
        _terminate_pid(int(candidate_pid))

    state["status"] = 0
    state["pid"] = None
    state["updated_at"] = _now_iso()
    if not pause and not state.get("completed"):
        state["error"] = None
    write_json(state_path, state)
    return True


def stop_all_adhoc_clients(experiment, *, pause: bool = False) -> list[str]:
    stopped: list[str] = []
    for client_state in list_adhoc_clients(experiment):
        client_key = str(client_state.get("client_key") or "")
        if not client_key:
            continue
        stop_adhoc_client(experiment, client_key, pause=pause)
        stopped.append(client_key)
    return stopped


def delete_adhoc_client(experiment, client_key: str) -> None:
    config_path = config_path_for_client(experiment, client_key)
    state = ensure_state_for_config(config_path)
    if state.get("status") == 1:
        stop_adhoc_client(experiment, client_key, pause=False)

    paths = {
        config_path,
        state_path_for_config(config_path),
        stdout_log_path_for_config(config_path),
        stderr_log_path_for_config(config_path),
    }
    agents_path = Path(str(state.get("agents_path") or ""))
    if agents_path.exists():
        paths.add(agents_path)

    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def adhoc_progress_payload(experiment, client_key: str) -> dict:
    config_path = config_path_for_client(experiment, client_key)
    state = ensure_state_for_config(config_path)
    if state.get("infinite"):
        elapsed_time = int(state.get("elapsed_time") or 0)
        return {
            "progress": -1,
            "infinite": True,
            "elapsed_time": elapsed_time,
            "elapsed_days": elapsed_time // 24,
            "elapsed_hours": elapsed_time % 24,
            "last_active_day": int(state.get("last_active_day") or -1),
            "last_active_hour": int(state.get("last_active_hour") or -1),
        }

    return {
        "progress": int(state.get("progress") or 0),
        "infinite": False,
    }
