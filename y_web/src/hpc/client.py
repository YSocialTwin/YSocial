"""
HPC client process management.

Provides functions for starting and stopping HPC client processes,
extracted from y_web.utils.external_processes.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

import ray
from sqlalchemy import select

from y_web import db
from y_web.src.hpc.platforms import find_hpc_platform, get_hpc_platform
from y_web.src.models import Client_Execution
from y_web.src.simulation.subprocess_env import build_subprocess_env, ray_safe_cmd
from y_web.src.system.path_utils import get_base_path, get_writable_path


def _tracked_process_is_alive(pid):
    """Return whether a tracked subprocess PID is still alive."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def _is_hpc_client_process(pid: int) -> bool:
    """Return whether PID looks like an HPC client subprocess."""
    if not pid:
        return False
    try:
        import psutil

        proc = psutil.Process(int(pid))
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        cmdline = " ".join(proc.cmdline()).lower()
        return "run_client.py" in cmdline or "--run-hpc-client-subprocess" in cmdline
    except Exception:
        # Fallback to basic liveness signal check.
        return _tracked_process_is_alive(pid)


def _hpc_process_matches_client(
    pid: int, *, cli_name: Optional[str] = None, exp_folder: Optional[str] = None
) -> bool:
    """
    Best-effort check that PID belongs to this specific HPC client instance.

    Returns True when unsure (conservative) to avoid launching duplicates.
    """
    if not pid:
        return False
    try:
        import psutil

        proc = psutil.Process(int(pid))
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        cmdline = " ".join(proc.cmdline())
        cmdline_l = cmdline.lower()

        if exp_folder:
            raw_folder = str(exp_folder).replace("\\", "/").lower()
            try:
                resolved_folder = (
                    str(Path(exp_folder).resolve()).replace("\\", "/").lower()
                )
            except Exception:
                resolved_folder = raw_folder
            folder_name = Path(exp_folder).name.lower()
            if (
                raw_folder not in cmdline_l
                and resolved_folder not in cmdline_l
                and folder_name not in cmdline_l
            ):
                return False

        if cli_name:
            cli_l = str(cli_name).strip().lower()
            if cli_l:
                # Client names are included in HPC config files as client_<name>-<population>.json
                if f"client_{cli_l}-" not in cmdline_l and cli_l not in cmdline_l:
                    return False

        return True
    except Exception:
        return True


def _clear_stale_hpc_pid(cli, *, exp_folder: Optional[str] = None) -> bool:
    """
    Clear stale/recycled PID from DB tracking.

    Returns True when a stale PID was cleared.
    """
    pid = getattr(cli, "pid", None)
    if not pid:
        return False
    if not _tracked_process_is_alive(pid):
        cli.pid = None
        db.session.commit()
        return True
    if not _is_hpc_client_process(int(pid)):
        cli.pid = None
        db.session.commit()
        return True
    if not _hpc_process_matches_client(
        int(pid), cli_name=getattr(cli, "name", None), exp_folder=exp_folder
    ):
        cli.pid = None
        db.session.commit()
        return True
    return False


def _resolve_hpc_experiment_folder(exp) -> str:
    """Resolve experiment folder path for HPC runtime artifacts."""
    writable_base = get_writable_path()
    y_web_dir = os.path.join(writable_base, "y_web")
    if "database_server.db" in exp.db_name:
        # db_name format: "experiments/uid/database_server.db"
        return os.path.join(
            y_web_dir, exp.db_name.split("database_server.db")[0].rstrip("/\\")
        )
    uid = exp.db_name.removeprefix("experiments_")
    return os.path.join(y_web_dir, "experiments", uid)


def _build_hpc_runtime_client_id(exp_folder: str, client_name: str) -> str:
    """Build a stable experiment-scoped client identifier for Ray registration."""
    folder_name = ""
    try:
        folder_name = Path(exp_folder).resolve().name
    except Exception:
        folder_name = Path(str(exp_folder)).name
    return f"{folder_name}:{str(client_name).strip()}"


def _normalize_photo_sharing_client_config(
    exp_folder: str, client_name: str, population_name: str, client_config_path: str
) -> None:
    """Align YPhotoSharing client config with the experiment server runtime."""
    server_config_path = os.path.join(exp_folder, "server_config.json")
    server_config = {}
    if os.path.exists(server_config_path):
        with open(server_config_path, "r", encoding="utf-8") as handle:
            server_config = json.load(handle)

    with open(client_config_path, "r", encoding="utf-8") as handle:
        client_config = json.load(handle)

    runtime_client_id = _build_hpc_runtime_client_id(exp_folder, client_name)
    client_config["client_id"] = runtime_client_id
    client_config["namespace"] = server_config.get("namespace", "yphotosharing")
    client_config["server_name"] = server_config.get(
        "server_name", "orchestrator_server"
    )
    client_config["address"] = "auto"
    population_filename = f"{population_name}.json"
    client_config["agents_file"] = population_filename
    client_config["users_file"] = population_filename
    client_config.setdefault("logging", {})
    client_config["logging"]["log_dir"] = os.path.join(exp_folder, "logs")
    client_config["logging"]["instance_name"] = runtime_client_id

    with open(client_config_path, "w", encoding="utf-8") as handle:
        json.dump(client_config, handle, indent=2)


def _normalize_im_client_config(
    exp_folder: str, client_name: str, population_name: str, client_config_path: str
) -> None:
    """Align a YInstantMessaging client config with the experiment server runtime.

    Only keys that IM excludes from the config hash are written (``client_id``, ``namespace``,
    ``server_name``, ``address``, ``agents_file``, ``logging.log_dir``, ``logging.instance_name``), so
    running it before every start never changes the hash a resumed run is checked against. No secret is
    ever written here, and the result is the same however many times it runs.
    """
    from y_web.routes.admin.sub.experiments._im import IM_NAMESPACE, IM_SERVER_NAME

    server_config_path = os.path.join(exp_folder, "server_config.json")
    server_config = {}
    if os.path.exists(server_config_path):
        with open(server_config_path, "r", encoding="utf-8") as handle:
            server_config = json.load(handle)

    with open(client_config_path, "r", encoding="utf-8") as handle:
        client_config = json.load(handle)

    runtime_client_id = _build_hpc_runtime_client_id(exp_folder, client_name)
    desired = {
        "client_id": runtime_client_id,
        "namespace": server_config.get("namespace", IM_NAMESPACE),
        "server_name": server_config.get("server_name", IM_SERVER_NAME),
        "address": "auto",
        "agents_file": f"{population_name}.json",
    }
    logging_cfg = dict(client_config.get("logging") or {})
    logging_cfg["log_dir"] = os.path.join(exp_folder, "logs")
    logging_cfg["instance_name"] = runtime_client_id
    desired["logging"] = logging_cfg

    if all(client_config.get(key) == value for key, value in desired.items()):
        return
    client_config.update(desired)
    with open(client_config_path, "w", encoding="utf-8") as handle:
        json.dump(client_config, handle, indent=2)


def _normalize_dating_client_config(
    exp_folder: str, client_name: str, population_name: str, client_config_path: str
) -> None:
    """Check that a dating client file still matches its client and its population file.

    Nothing is rewritten (the file is the one the form wrote, and its content is part of what a resumed
    run is compared with); a mismatch stops the start with a clear message.
    """
    with open(client_config_path, "r", encoding="utf-8") as handle:
        client_config = json.load(handle)
    if client_config.get("client_name") != client_name:
        raise ValueError(
            f"{os.path.basename(client_config_path)} is for client "
            f"{client_config.get('client_name')!r}, not {client_name!r}"
        )
    population_file = client_config.get("population_file") or ""
    if not population_file or not os.path.isfile(
        os.path.join(exp_folder, population_file)
    ):
        raise FileNotFoundError(
            f"population file {population_file!r} of client {client_name!r} not found"
        )


_CLIENT_NORMALIZERS = {
    "photo_sharing": _normalize_photo_sharing_client_config,
    "instant_messaging": _normalize_im_client_config,
    "dating": _normalize_dating_client_config,
}


def _migrate_legacy_photo_sharing_client_layout(
    exp_folder: str, client_name: str, population_name: str, client_config_path: str
) -> None:
    """Promote legacy per-client photo-sharing config into the standard HPC layout."""
    if os.path.exists(client_config_path):
        return

    legacy_dir = os.path.join(exp_folder, f"client_{client_name}-{population_name}")
    legacy_config = os.path.join(legacy_dir, "client_config.json")
    if not os.path.exists(legacy_config):
        return

    with open(legacy_config, "r", encoding="utf-8") as handle:
        client_config = json.load(handle)
    with open(client_config_path, "w", encoding="utf-8") as handle:
        json.dump(client_config, handle, indent=2)


def _resolve_hpc_client_file(exp, client_name, suffix, log_folder=None):
    exp_folder = _resolve_hpc_experiment_folder(exp)
    logs_dir = Path(log_folder or os.path.join(exp_folder, "logs"))
    client_name = str(client_name or "").strip()
    if not client_name:
        return None

    exact_match = logs_dir / f"{client_name}{suffix}"
    if exact_match.exists():
        return str(exact_match)

    if not logs_dir.exists():
        return None

    matches = []
    for entry in logs_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith(suffix):
            continue
        stem = entry.name[: -len(suffix)]
        if stem == client_name:
            return str(entry)
        if stem.rsplit(":", 1)[-1] == client_name:
            matches.append(entry)

    if not matches:
        return None

    matches.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return str(matches[0])


def resolve_hpc_client_log_path(
    exp,
    client_name: str,
    *,
    log_folder: Optional[str] = None,
) -> Optional[str]:
    """
    Resolve the on-disk client log path for an HPC experiment.

    Newer HPC clients write logs using the runtime client id prefix, e.g.
    ``<experiment-folder>:<client-name>_client.log``. Older runs used the plain
    ``<client-name>_client.log`` name. This helper accepts both forms.
    """
    if not client_name:
        return None
    return _resolve_hpc_client_file(exp, client_name, "_client.log", log_folder)


def resolve_hpc_client_execution_log_path(
    exp,
    client_name: str,
    *,
    log_folder: Optional[str] = None,
) -> Optional[str]:
    """Same lookup as :func:`resolve_hpc_client_log_path` for ``*_execution.log``.

    The YInstantMessaging client names its files after the runtime client id
    (``<experiment-folder>:<client-name>_execution.log``).
    """
    if not client_name:
        return None
    return _resolve_hpc_client_file(exp, client_name, "_execution.log", log_folder)


def _sync_stress_reward_into_hpc_client_config(exp_folder, client_config_path):
    """Keep HPC client stress/reward settings aligned with server_config.json."""
    if not exp_folder or not client_config_path:
        return False

    server_config_path = os.path.join(exp_folder, "server_config.json")
    if not os.path.exists(server_config_path) or not os.path.exists(client_config_path):
        return False

    try:
        with open(server_config_path, "r", encoding="utf-8") as handle:
            server_config = json.load(handle)
        with open(client_config_path, "r", encoding="utf-8") as handle:
            client_config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False

    server_sr = server_config.get("stress_reward")
    if not isinstance(server_sr, dict):
        enabled = bool(
            server_config.get(
                "stress_reward_enabled",
                server_config.get("stress_reward_annotation", False),
            )
        )
        server_sr = {"enabled": enabled, "backward_rounds": 24}

    desired_sr = deepcopy(server_sr)
    desired_sr["enabled"] = bool(server_sr.get("enabled", False))
    desired_sr["backward_rounds"] = int(server_sr.get("backward_rounds", 24) or 24)
    if client_config.get("stress_reward") == desired_sr:
        return False

    client_config["stress_reward"] = desired_sr
    with open(client_config_path, "w", encoding="utf-8") as handle:
        json.dump(client_config, handle, indent=4)
    return True


def _resolve_hpc_client_days_from_config(client_config_path: str) -> Optional[int]:
    """
    Read the simulation duration from an HPC client config file.

    Matrix-generated experiments can carry the correct duration in
    ``simulation.num_days`` even when the DB client row still has an older
    ``days`` value. Prefer ``num_days`` but keep legacy ``days`` support.
    """
    if not client_config_path or not Path(client_config_path).exists():
        return None

    try:
        with open(client_config_path, "r", encoding="utf-8") as handle:
            client_config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(client_config, dict):
        return None

    simulation_cfg = client_config.get("simulation")
    if not isinstance(simulation_cfg, dict):
        simulation_cfg = {}

    for key in ("num_days", "days"):
        value = simulation_cfg.get(key)
        if value is None:
            value = client_config.get(key)
        if value is None:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        return -1 if parsed == 0 else parsed

    return None


def _sync_hpc_client_duration_from_config(
    client_config_path: str,
    cli,
) -> Optional[int]:
    """
    Sync the DB client duration to the client config when they differ.

    Returns the resolved duration in days when available.
    """
    resolved_days = _resolve_hpc_client_days_from_config(client_config_path)
    if resolved_days is None:
        return None

    current_days = getattr(cli, "days", None)
    if current_days != resolved_days:
        cli.days = resolved_days
        db.session.commit()
    return resolved_days


def _sync_hpc_network_bootstrap(exp_folder, client_config_path, cli) -> bool:
    """Ensure YSimulator can find the copied network CSV for this HPC client."""
    if not exp_folder or not client_config_path:
        return False

    exp_dir = Path(exp_folder)
    config_path = Path(client_config_path)
    if not exp_dir.exists() or not config_path.exists():
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            client_config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False

    # Older layouts may store the runtime identity under "name" instead of
    # the current "client_name" key; accept either when rebuilding aliases.
    config_client_name = str(
        client_config.get("client_name") or client_config.get("name") or ""
    ).strip()
    record_client_name = str(getattr(cli, "name", "") or "").strip()
    desired_client_name = config_client_name or record_client_name
    if not desired_client_name:
        return False

    runtime_client_name = _build_hpc_runtime_client_id(exp_folder, desired_client_name)
    desired_network_paths = [
        exp_dir / f"{runtime_client_name}_network.csv",
        exp_dir / f"{desired_client_name}_network.csv",
    ]
    if any(path.exists() for path in desired_network_paths):
        return False

    candidate_paths = []
    for candidate_name in {record_client_name, config_client_name}:
        if not candidate_name:
            continue
        exact_match = exp_dir / f"{candidate_name}_network.csv"
        if exact_match.exists():
            candidate_paths.append(exact_match)

    for entry in exp_dir.glob("*_network.csv"):
        if entry.is_file() and (
            (record_client_name and entry.name.startswith(f"{record_client_name}_"))
            or (config_client_name and entry.name.startswith(f"{config_client_name}_"))
        ):
            candidate_paths.append(entry)

    generic_network_path = exp_dir / "network.csv"
    if generic_network_path.exists():
        candidate_paths.append(generic_network_path)

    unique_candidates = []
    seen_candidates = set()
    for candidate_path in candidate_paths:
        normalized = str(candidate_path.resolve())
        if normalized in seen_candidates:
            continue
        seen_candidates.add(normalized)
        unique_candidates.append(candidate_path)

    for candidate_path in unique_candidates:
        copied_any = False
        for desired_network_path in desired_network_paths:
            if desired_network_path.exists():
                copied_any = True
                continue
            try:
                shutil.copy2(candidate_path, desired_network_path)
                copied_any = True
            except OSError:
                # Skip inaccessible or otherwise unusable targets and keep looking
                continue
        if copied_any:
            # Keep both the runtime client-id alias and the legacy client-name
            # alias in sync so the current and historical loaders can resolve
            # the initial topology.
            return True

    return False


def _hpc_network_bootstrap_exists(exp_folder, client_config_path, cli) -> bool:
    """Return True when a usable initial-network CSV already exists on disk."""
    if not exp_folder or not client_config_path:
        return False

    exp_dir = Path(exp_folder)
    config_path = Path(client_config_path)
    if not exp_dir.exists() or not config_path.exists():
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            client_config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False

    config_client_name = str(
        client_config.get("client_name") or client_config.get("name") or ""
    ).strip()
    record_client_name = str(getattr(cli, "name", "") or "").strip()
    desired_client_name = config_client_name or record_client_name
    if not desired_client_name:
        return False

    runtime_client_name = _build_hpc_runtime_client_id(exp_folder, desired_client_name)
    candidate_names = {record_client_name, config_client_name, runtime_client_name}

    for candidate_name in candidate_names:
        if not candidate_name:
            continue
        if (exp_dir / f"{candidate_name}_network.csv").exists():
            return True

    if (exp_dir / "network.csv").exists():
        return True

    for entry in exp_dir.glob("*_network.csv"):
        if entry.is_file():
            return True

    return False


def _wait_for_hpc_server_ready(exp_folder: str, timeout_seconds: int = 180) -> None:
    """
    Wait until the server writes its readiness marker after the orchestrator actor starts.
    """
    ready_path = Path(exp_folder) / "ray_ready.temp"
    deadline = time.monotonic() + max(1, timeout_seconds)
    while time.monotonic() < deadline:
        if ready_path.exists():
            return
        time.sleep(1)

    raise FileNotFoundError(
        f"ray_ready.temp file not found after {timeout_seconds} seconds: {ready_path}\n"
        "The HPC server may not have fully initialized its Ray actor yet."
    )


def _set_client_execution_terminal_state(cli, terminal_state: str) -> bool:
    """Persist the terminal state for an HPC client execution record."""
    if not terminal_state:
        return False

    client_id = getattr(cli, "id", None)
    if client_id is None:
        return False

    client_exec = db.session.scalars(
        select(Client_Execution).filter_by(client_id=client_id)
    ).first()
    if not client_exec:
        return False

    client_exec.terminal_state = terminal_state
    db.session.commit()
    return True


def _start_im_human_gateway(exp_folder: str) -> None:
    """Start the human gateway before the first IM client (a failure is a warning, never an error)."""
    try:
        from y_web.src.im.gateway_process import start_gateway
        from y_web.src.simulation.server import detect_env_handler
        from y_web.src.system.path_utils import get_external_repo_dir

        repo_dir = get_external_repo_dir(
            get_hpc_platform("instant_messaging").runtime_repo
        )
        start_gateway(exp_folder, repo_dir, detect_env_handler())
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: human gateway not started: {exc}")


def start_hpc_client(exp, cli, population):
    """
    Start an HPC client using subprocess.Popen.

    This function launches an HPC client process for an experiment using the
    run_client.py script from the external/YSimulator folder. The process PID
    is stored in the database for later management and graceful termination.

    Args:
        exp: the experiment object
        cli: the client object
        population: the population object

    Returns:
        subprocess.Popen: The started process object
    """
    # Import helpers from external_processes to avoid duplication.
    # These imports work because external_processes defines them before delegating here.
    from y_web.src.simulation.server import detect_env_handler

    # Get base path - this will be bundle location when frozen, repo root otherwise
    base_path = get_base_path()

    exp_folder = _resolve_hpc_experiment_folder(exp)
    # Clear stale/recycled PID entries first.
    _clear_stale_hpc_pid(cli, exp_folder=exp_folder)
    tracked_pid = getattr(cli, "pid", None)
    if (
        tracked_pid
        and _tracked_process_is_alive(tracked_pid)
        and _hpc_process_matches_client(
            int(tracked_pid), cli_name=getattr(cli, "name", None), exp_folder=exp_folder
        )
    ):
        raise RuntimeError(
            f"HPC client '{cli.name}' is already running with PID {cli.pid}. "
            "Stop or pause it before starting another instance."
        )

    # Construct paths for config, agents, and prompts files
    if exp.platform_type == "photo_sharing":
        client_config = os.path.join(
            exp_folder, f"client_{cli.name}-{population.name}.json"
        )
        _migrate_legacy_photo_sharing_client_layout(
            exp_folder, cli.name, population.name, client_config
        )
        agents_file = os.path.join(exp_folder, f"{population.name}.json")
        prompts_file = os.path.join(exp_folder, "prompts_ygram.json")
    else:
        client_config = os.path.join(
            exp_folder, f"client_{cli.name}-{population.name}.json"
        )
        agents_file = os.path.join(exp_folder, f"{population.name}.json")
        prompts_file = os.path.join(
            exp_folder,
            (
                "prompts_im.json"
                if exp.platform_type == "instant_messaging"
                else "prompts.json"
            ),
        )

    _launch_spec = find_hpc_platform(exp.platform_type)
    _required_files = [
        (client_config, "client config"),
        (agents_file, "agents"),
    ]
    if _launch_spec is None or _launch_spec.requires_prompts_file:
        _required_files.append((prompts_file, "prompts"))

    # Validate that required files exist
    for file_path, file_name in _required_files:
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"{file_name.capitalize()} file not found: {file_path}\n"
                f"Please ensure the HPC experiment is properly configured."
            )

    _syncs_config = _launch_spec is None or _launch_spec.syncs_client_config
    try:
        if _syncs_config:
            _sync_stress_reward_into_hpc_client_config(exp_folder, client_config)
    except Exception as exc:
        print(f"Warning: failed to synchronize HPC stress_reward config: {exc}")

    try:
        synced_days = _sync_hpc_client_duration_from_config(client_config, cli)
    except Exception as exc:
        print(f"Warning: failed to synchronize HPC client duration: {exc}")

    try:
        if _syncs_config:
            _sync_hpc_network_bootstrap(exp_folder, client_config, cli)
    except Exception as exc:
        print(f"Warning: failed to synchronize HPC network bootstrap: {exc}")

    # Validate ray_config.temp exists (required for HPC client startup).
    # Local Ray bootstrap can exceed a minute on some machines, so keep the
    # startup window comfortably above the slow-path initialization time.
    ray_config_path = os.path.join(exp_folder, "ray_config.temp")
    max_attempts = 18
    wait_seconds = 10

    for attempt in range(1, max_attempts + 1):
        if Path(ray_config_path).exists():
            break

        if attempt < max_attempts:
            print(
                f"ray_config.temp not found (attempt {attempt}/{max_attempts}). "
                f"Waiting {wait_seconds} seconds..."
            )
            time.sleep(wait_seconds)
        else:
            # Final attempt failed
            error_msg = (
                f"ray_config.temp file not found after {max_attempts} attempts "
                f"({max_attempts * wait_seconds} seconds): {ray_config_path}\n"
                f"The HPC server may not have fully initialized yet. "
                f"Please wait and try again, or check the server logs for errors."
            )
            raise FileNotFoundError(error_msg)

    # Give the server a few seconds to finish registering its Ray actor and
    # listening endpoints before the client performs the first lookup.
    _wait_for_hpc_server_ready(exp_folder, timeout_seconds=180)
    time.sleep(3)

    if exp.platform_type == "instant_messaging":
        _start_im_human_gateway(exp_folder)  # server -> gateway -> clients (plan 4.8)

    # Remove completion log entries from actor log if restarting
    # Actor logs are in logs/{client_name}_actor.log
    logs_folder = os.path.join(exp_folder, "logs")
    actor_log_path = os.path.join(logs_folder, f"{cli.name}_actor.log")

    if _syncs_config and os.path.exists(actor_log_path):
        try:
            # Read all lines from the actor log
            with open(actor_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Remove the last two lines if they exist
            # These are the completion messages that should be cleared on restart
            if len(lines) >= 2:
                lines = lines[:-2]

                # Write back the modified content
                with open(actor_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

                print(f"Removed completion log entries from {actor_log_path}")
        except Exception as e:
            # Log the error but don't fail the client start
            print(f"Warning: Could not clean actor log {actor_log_path}: {e}")

    writable_external = os.path.join(get_writable_path(), "external")
    resource_external = os.path.join(base_path, "external")

    def _external_repo_dir(repo_name):
        candidate = os.path.join(writable_external, repo_name)
        if os.path.isdir(candidate):
            return candidate
        return os.path.join(resource_external, repo_name)

    # Determine the script path and arguments from the platform spec
    spec = get_hpc_platform(exp.platform_type)
    runtime_config_dir = exp_folder
    script_path = os.path.join(_external_repo_dir(spec.runtime_repo), "run_client.py")
    if spec.normalizes_client_config:
        if not spec.client_config_file_arg:
            runtime_config_dir = client_config

        try:
            _CLIENT_NORMALIZERS[spec.key](
                exp_folder, cli.name, population.name, client_config
            )
        except Exception:
            if spec.key in ("instant_messaging", "dating"):
                raise  # these must not start with a client config that could not be aligned

    if spec.validates_config:
        if spec.key == "dating":
            from y_web.src.dating.validation import validate_dating_folder as _validate
        else:
            from y_web.src.im.validation import validate_im_folder as _validate

        _validate(
            exp_folder,
            _external_repo_dir(spec.runtime_repo),
            client_config=os.path.basename(client_config),
        )

    # Validate that script_path exists (skip check for PyInstaller bundles)
    is_frozen = getattr(sys, "frozen", False)
    has_meipass = hasattr(sys, "_MEIPASS")
    is_bundle_exe = "python" not in Path(sys.executable).name.lower()

    if (
        not (is_frozen or has_meipass or is_bundle_exe)
        and not Path(script_path).exists()
    ):
        expected_repo = spec.runtime_repo
        raise FileNotFoundError(
            f"Client script not found: {script_path}\n"
            f"Please ensure {expected_repo} is cloned under external/{expected_repo}.\n"
            f"You can install or update it from the Admin > Plugins panel."
        )

    # Get the Python executable to use
    python_cmd = detect_env_handler()

    def _client_args():
        if spec.client_config_only:
            if spec.client_config_file_arg:
                return [
                    "--config",
                    runtime_config_dir,
                    "--client-config",
                    os.path.basename(client_config),
                ]
            return ["--config", runtime_config_dir]
        return [
            "--config",
            client_config,
            "--agents",
            agents_file,
            "--prompts",
            prompts_file,
        ]

    # Build the command
    if is_frozen or has_meipass or is_bundle_exe:
        # Running from PyInstaller bundle
        if spec.client_config_only:
            cmd = [sys.executable, script_path] + _client_args()
        else:
            cmd = [sys.executable, "--run-hpc-client-subprocess"] + _client_args()
    elif (
        isinstance(python_cmd, str)
        and " " in python_cmd
        and not os.path.isabs(python_cmd)
    ):
        # Handle commands like "pipenv run python"
        cmd = python_cmd.split() + [script_path] + _client_args()
    else:
        # Simple python executable path (may contain spaces on Windows)
        cmd = [python_cmd, script_path] + _client_args()

    cmd = ray_safe_cmd(cmd)

    print(f"Starting HPC client {cli.name} for experiment {exp.idexp}...")
    print(f"Config: {client_config}")
    print(f"Agents: {agents_file}")
    print(f"Prompts: {prompts_file}")

    from y_web.src.system import prompt_packs

    env = build_subprocess_env()
    env.update(prompt_packs.launch_env(exp, cli))

    try:
        # Start the process with Popen
        if sys.platform.startswith("win"):
            try:
                creationflags = subprocess.CREATE_NO_WINDOW
            except AttributeError:
                creationflags = 0x08000000
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                env=env,
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
        print(f"HPC client process started with PID: {process.pid}")
    except Exception as e:
        print(f"Error starting HPC client process: {e}")
        raise

    # Save the PID to the database for persistent tracking
    cli.pid = process.pid
    db.session.commit()

    expected_rounds = -1 if cli.days == -1 else cli.days * 24

    # Initialize or get Client_Execution record for progress tracking
    # This is essential for HPC clients to track simulation progress
    client_exec = db.session.scalars(
        select(Client_Execution).filter_by(client_id=cli.id)
    ).first()
    if not client_exec:
        # Create new Client_Execution record
        client_exec = Client_Execution(
            client_id=cli.id,
            elapsed_time=0,
            expected_duration_rounds=expected_rounds,
            last_active_hour=-1,
            last_active_day=-1,
            terminal_state="running",
        )
        db.session.add(client_exec)
        db.session.commit()
        print(
            f"Created Client_Execution record for HPC client {cli.name} (expected rounds: {expected_rounds})"
        )
    else:
        client_exec.expected_duration_rounds = expected_rounds
        client_exec.terminal_state = "running"
        db.session.commit()
        print(f"Client_Execution record already exists for HPC client {cli.name}")

    return process


def stop_hpc_client(cli, *, terminal_state: Optional[str] = None):
    """
    Terminate an HPC client process using the PID stored in the database.

    This function terminates an HPC client process that was started using the
    start_hpc_client() function and has its PID stored in the database.
    It handles graceful shutdown using SIGTERM, followed by SIGKILL if needed.
    It clears the PID from the database after termination.

    Args:
        cli: the client object whose HPC client process should be terminated

    Returns:
        bool: True if process was found and terminated, False otherwise
    """
    # Import here to avoid circular import issues.
    from y_web.src.simulation.port_manager import (
        __terminate_process as _terminate_process,
    )

    try:
        manual_stop_requested = terminal_state in {"manual_stop", "paused"}

        # For user-initiated stops/pauses, mark the execution record before
        # touching the process tree. This prevents the HPC monitor from
        # interpreting the shutdown window as a crash and respawning the client.
        if manual_stop_requested:
            _set_client_execution_terminal_state(cli, terminal_state)
            cli.status = 0
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

        if not cli.pid:
            print(f"No tracked HPC client process found for client {cli.name}")
            if terminal_state:
                _set_client_execution_terminal_state(cli, terminal_state)
                return True
            return False

        # Clear stale PID state early (PID recycled or non-HPC process).
        if _clear_stale_hpc_pid(cli):
            print(
                f"Cleared stale PID state for HPC client {cli.name}; nothing to terminate."
            )
            if terminal_state:
                _set_client_execution_terminal_state(cli, terminal_state)
            return True

        try:
            exp = getattr(cli, "experiment", None)
            exp_db_name = getattr(exp, "db_name", None)
            if exp_db_name:
                writable_base = get_writable_path()
                y_web_dir = os.path.join(writable_base, "y_web")
                if "database_server.db" in exp_db_name:
                    exp_folder = os.path.join(
                        y_web_dir,
                        exp_db_name.split("database_server.db")[0].rstrip("/\\"),
                    )
                else:
                    uid = exp_db_name.removeprefix("experiments_")
                    exp_folder = os.path.join(y_web_dir, "experiments", uid)

                ray_addr_path = os.path.join(exp_folder, "ray_config.temp")
                ray_ns_path = os.path.join(exp_folder, "ray_namespace.temp")
                if os.path.exists(ray_addr_path):
                    address = Path(ray_addr_path).read_text(encoding="utf-8").strip()
                    namespace = "social_sim"
                    if os.path.exists(ray_ns_path):
                        namespace = (
                            Path(ray_ns_path).read_text(encoding="utf-8").strip()
                            or namespace
                        )
                    if address:
                        connected_here = False
                        if not ray.is_initialized():
                            ray.init(
                                address=address,
                                namespace=namespace,
                                ignore_reinit_error=True,
                            )
                            connected_here = True
                        try:
                            runtime_client_id = _build_hpc_runtime_client_id(
                                exp_folder, cli.name
                            )
                            actor_spec = find_hpc_platform(
                                getattr(exp, "platform_type", None)
                            ) or get_hpc_platform("microblogging")
                            orchestrator_name = actor_spec.orchestrator_actor
                            runtime_actor_name = actor_spec.client_actor_name(
                                runtime_client_id
                            )
                            orchestrator = ray.get_actor(
                                orchestrator_name, namespace=namespace
                            )
                            try:
                                runtime_client = ray.get_actor(
                                    runtime_actor_name, namespace=namespace
                                )
                                ray.kill(runtime_client, no_restart=True)
                                print(
                                    f"Killed HPC client actor {runtime_actor_name} before stopping process."
                                )
                            except ValueError:
                                print(
                                    f"HPC client actor {runtime_actor_name} not found before stop; "
                                    "continuing with process shutdown."
                                )
                            ray.get(
                                orchestrator.deregister_client.remote(
                                    runtime_client_id
                                ),
                                timeout=5,
                            )
                            print(
                                f"Deregistered HPC client {runtime_client_id} from orchestrator before stop."
                            )
                        finally:
                            if connected_here:
                                ray.shutdown()
        except Exception as exc:
            print(
                f"Warning: failed to deregister HPC client {cli.name} before stop: {exc}"
            )

        pid = cli.pid
        print(f"Terminating HPC client process with PID {pid}...")
        terminated = False

        try:
            # Try graceful termination first
            os.kill(pid, signal.SIGTERM)

            # Wait up to 5 seconds for graceful shutdown
            for _ in range(50):  # 50 * 0.1s = 5 seconds
                if not _tracked_process_is_alive(pid) or not _is_hpc_client_process(
                    pid
                ):
                    print(f"HPC client process {pid} terminated gracefully.")
                    terminated = True
                    break
                time.sleep(0.1)
            else:
                # If we get here, process is still running after timeout
                print(
                    f"HPC client process {pid} did not terminate gracefully, forcing kill..."
                )
                if _tracked_process_is_alive(pid):
                    _terminate_process(pid)
                time.sleep(0.5)
                terminated = not _tracked_process_is_alive(pid)
                if terminated:
                    print(f"HPC client process {pid} killed.")
                else:
                    print(
                        f"Warning: HPC client process {pid} is still running after forced termination."
                    )

        except OSError as e:
            # Process doesn't exist
            print(f"HPC client process {pid} no longer exists: {e}")
            terminated = True

        if not terminated:
            print(
                f"Warning: HPC client process {pid} could not be confirmed stopped; preserving PID tracking."
            )
            return False

        # Clear PID from database
        cli.pid = None
        if terminal_state and terminated and not manual_stop_requested:
            _set_client_execution_terminal_state(cli, terminal_state)
        db.session.commit()
        return terminated

    except Exception as e:
        print(f"Error terminating HPC client process: {e}")
        return False
