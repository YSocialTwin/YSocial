"""
HPC client process management.

Provides functions for starting and stopping HPC client processes,
extracted from y_web.utils.external_processes.
"""

import json
import os
import signal
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

import ray

from y_web import db
from y_web.src.models import Client_Execution
from y_web.src.simulation.subprocess_env import build_subprocess_env
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
            try:
                norm_folder = str(Path(exp_folder).resolve()).replace("\\", "/")
            except Exception:
                norm_folder = str(exp_folder).replace("\\", "/")
            if norm_folder and norm_folder.lower() not in cmdline_l:
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

    exp_folder = _resolve_hpc_experiment_folder(exp)
    logs_dir = Path(log_folder or os.path.join(exp_folder, "logs"))
    client_name = str(client_name).strip()
    if not client_name:
        return None

    exact_match = logs_dir / f"{client_name}_client.log"
    if exact_match.exists():
        return str(exact_match)

    if not logs_dir.exists():
        return None

    matches = []
    for entry in logs_dir.iterdir():
        if not entry.is_file() or not entry.name.endswith("_client.log"):
            continue
        stem = entry.name[: -len("_client.log")]
        if stem == client_name:
            return str(entry)
        if stem.rsplit(":", 1)[-1] == client_name:
            matches.append(entry)

    if not matches:
        return None

    matches.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return str(matches[0])


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


def _set_client_execution_terminal_state(cli, terminal_state: str) -> bool:
    """Persist the terminal state for an HPC client execution record."""
    if not terminal_state:
        return False

    client_id = getattr(cli, "id", None)
    if client_id is None:
        return False

    client_exec = Client_Execution.query.filter_by(client_id=client_id).first()
    if not client_exec:
        return False

    client_exec.terminal_state = terminal_state
    db.session.commit()
    return True


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
        prompts_file = os.path.join(exp_folder, "prompts.json")

    # Validate that required files exist
    for file_path, file_name in [
        (client_config, "client config"),
        (agents_file, "agents"),
        (prompts_file, "prompts"),
    ]:
        if not Path(file_path).exists():
            raise FileNotFoundError(
                f"{file_name.capitalize()} file not found: {file_path}\n"
                f"Please ensure the HPC experiment is properly configured."
            )

    try:
        _sync_stress_reward_into_hpc_client_config(exp_folder, client_config)
    except Exception as exc:
        print(f"Warning: failed to synchronize HPC stress_reward config: {exc}")

    # Validate ray_config.temp exists (required for HPC client startup)
    # Wait up to 60 seconds (6 attempts x 10 seconds) for the file to appear
    ray_config_path = os.path.join(exp_folder, "ray_config.temp")
    max_attempts = 6
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

    # Remove completion log entries from actor log if restarting
    # Actor logs are in logs/{client_name}_actor.log
    logs_folder = os.path.join(exp_folder, "logs")
    actor_log_path = os.path.join(logs_folder, f"{cli.name}_actor.log")

    if os.path.exists(actor_log_path):
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

    # Determine the script path based on platform type
    runtime_config_dir = exp_folder
    if exp.platform_type == "photo_sharing":
        script_path = os.path.join(_external_repo_dir("YPhotoSharing"), "run_client.py")
        runtime_config_dir = client_config

        try:
            _normalize_photo_sharing_client_config(
                exp_folder, cli.name, population.name, client_config
            )
        except Exception:
            pass
    elif exp.platform_type == "microblogging":
        script_path = os.path.join(_external_repo_dir("YSimulator"), "run_client.py")
    else:
        raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

    # Validate that script_path exists (skip check for PyInstaller bundles)
    is_frozen = getattr(sys, "frozen", False)
    has_meipass = hasattr(sys, "_MEIPASS")
    is_bundle_exe = "python" not in Path(sys.executable).name.lower()

    if (
        not (is_frozen or has_meipass or is_bundle_exe)
        and not Path(script_path).exists()
    ):
        expected_repo = (
            "YPhotoSharing" if exp.platform_type == "photo_sharing" else "YSimulator"
        )
        raise FileNotFoundError(
            f"Client script not found: {script_path}\n"
            f"Please ensure {expected_repo} is cloned under external/{expected_repo}.\n"
            f"You can install or update it from the Admin > Plugins panel."
        )

    # Get the Python executable to use
    python_cmd = detect_env_handler()

    # Build the command
    if is_frozen or has_meipass or is_bundle_exe:
        # Running from PyInstaller bundle
        if exp.platform_type == "photo_sharing":
            cmd = [
                sys.executable,
                script_path,
                "--config",
                runtime_config_dir,
            ]
        else:
            cmd = [
                sys.executable,
                "--run-hpc-client-subprocess",
                "--config",
                client_config,
                "--agents",
                agents_file,
                "--prompts",
                prompts_file,
            ]
    elif (
        isinstance(python_cmd, str)
        and " " in python_cmd
        and not os.path.isabs(python_cmd)
    ):
        # Handle commands like "pipenv run python"
        cmd_parts = python_cmd.split()
        if exp.platform_type == "photo_sharing":
            cmd = cmd_parts + [
                script_path,
                "--config",
                runtime_config_dir,
            ]
        else:
            cmd = cmd_parts + [
                script_path,
                "--config",
                client_config,
                "--agents",
                agents_file,
                "--prompts",
                prompts_file,
            ]
    else:
        # Simple python executable path (may contain spaces on Windows)
        if exp.platform_type == "photo_sharing":
            cmd = [
                python_cmd,
                script_path,
                "--config",
                runtime_config_dir,
            ]
        else:
            cmd = [
                python_cmd,
                script_path,
                "--config",
                client_config,
                "--agents",
                agents_file,
                "--prompts",
                prompts_file,
            ]

    print(f"Starting HPC client {cli.name} for experiment {exp.idexp}...")
    print(f"Config: {client_config}")
    print(f"Agents: {agents_file}")
    print(f"Prompts: {prompts_file}")

    env = build_subprocess_env()

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

    # Initialize or get Client_Execution record for progress tracking
    # This is essential for HPC clients to track simulation progress
    client_exec = Client_Execution.query.filter_by(client_id=cli.id).first()
    if not client_exec:
        # Create new Client_Execution record
        # For infinite clients (days = -1), set expected_duration_rounds to -1
        expected_rounds = -1 if cli.days == -1 else cli.days * 24
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
                            is_photo_sharing = (
                                getattr(exp, "platform_type", None) == "photo_sharing"
                            )
                            orchestrator_name = (
                                "orchestrator_server"
                                if is_photo_sharing
                                else "Orchestrator"
                            )
                            runtime_actor_name = (
                                f"Client_{runtime_client_id}"
                                if is_photo_sharing
                                else runtime_client_id
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
        if terminal_state and terminated:
            _set_client_execution_terminal_state(cli, terminal_state)
        db.session.commit()
        return terminated

    except Exception as e:
        print(f"Error terminating HPC client process: {e}")
        return False
