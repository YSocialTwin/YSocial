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

    # Determine the script path based on platform type
    if exp.platform_type == "microblogging":
        script_path = os.path.join(base_path, "external", "YSimulator", "run_client.py")
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
        raise FileNotFoundError(
            f"Client script not found: {script_path}\n"
            f"Please ensure YSimulator is cloned under external/YSimulator.\n"
            f"You can install or update it from the Admin > Plugins panel."
        )

    # Get the Python executable to use
    python_cmd = detect_env_handler()

    # Build the command
    if is_frozen or has_meipass or is_bundle_exe:
        # Running from PyInstaller bundle
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
        )
        db.session.add(client_exec)
        db.session.commit()
        print(
            f"Created Client_Execution record for HPC client {cli.name} (expected rounds: {expected_rounds})"
        )
    else:
        print(f"Client_Execution record already exists for HPC client {cli.name}")

    return process


def stop_hpc_client(cli):
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
    from y_web.src.simulation.port_manager import (
        _force_terminate_process_tree,
    )

    try:
        if not cli.pid:
            print(f"No tracked HPC client process found for client {cli.name}")
            return False

        # Clear stale PID state early (PID recycled or non-HPC process).
        if _clear_stale_hpc_pid(cli):
            print(
                f"Cleared stale PID state for HPC client {cli.name}; nothing to terminate."
            )
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
                            orchestrator = ray.get_actor(
                                "Orchestrator", namespace=namespace
                            )
                            ray.get(
                                orchestrator.deregister_client.remote(cli.name),
                                timeout=5,
                            )
                            print(
                                f"Deregistered HPC client {cli.name} from orchestrator before stop."
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

        try:
            # Try graceful termination first
            os.kill(pid, signal.SIGTERM)

            # Wait up to 5 seconds for graceful shutdown
            for _ in range(50):  # 50 * 0.1s = 5 seconds
                if not _tracked_process_is_alive(pid) or not _is_hpc_client_process(
                    pid
                ):
                    print(f"HPC client process {pid} terminated gracefully.")
                    break
                time.sleep(0.1)
            else:
                # If we get here, process is still running after timeout
                print(
                    f"HPC client process {pid} did not terminate gracefully, forcing kill..."
                )
                _force_terminate_process_tree(pid)
                if _tracked_process_is_alive(pid):
                    _terminate_process(pid)
                time.sleep(0.5)
                print(f"HPC client process {pid} killed.")

        except OSError as e:
            # Process doesn't exist
            print(f"HPC client process {pid} no longer exists: {e}")

        # Clear PID from database
        cli.pid = None
        db.session.commit()
        return True

    except Exception as e:
        print(f"Error terminating HPC client process: {e}")
        return False
