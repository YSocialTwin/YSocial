"""
Server process management for YSocial simulation.

Extracted from y_web/utils/external_processes.py.  The shim keeps all names
available at the legacy path.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
from flask import current_app
from requests import post
from sklearn.utils import deprecated

from y_web import db
from y_web.models import (
    Client_Execution,
    Exps,
)
from y_web.utils.path_utils import get_base_path, get_resource_path, get_writable_path
from y_web.src.simulation.port_manager import (
    SERVER_PORT_MIN,
    SERVER_PORT_MAX,
    _find_new_available_port,
    _force_terminate_process_tree,
    _terminate_processes_holding_experiment_database,
    _terminate_processes_on_port,
    _terminate_process,
    terminate_process_on_port,
)
from y_web.src.simulation.process_registry import (
    WATCHDOG_ENABLED,
    _register_process,
    _unregister_process,
)

# Internal alias for the double-underscore name used in terminate_server_process
_local_terminate_process = _terminate_process


def _resolve_server_runtime_paths(base_path, platform_type):
    """Resolve the server package directory and entry script for a platform."""
    if platform_type == "microblogging":
        server_dir = os.path.join(base_path, "external", "YServer")
    elif platform_type == "forum":
        server_dir = os.path.join(base_path, "external", "YServerReddit")
    else:
        raise NotImplementedError(f"Unsupported platform {platform_type}")
    return server_dir, os.path.join(server_dir, "y_server_run.py")


@deprecated
def detect_env_handler_old():
    """Handle detect env handler old operation."""
    python_exe = sys.executable
    env_type = None
    env_name = None
    env_bin = None
    conda_sh = None

    # Check for conda
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        env_type = "conda"

        env_name = os.environ.get("CONDA_DEFAULT_ENV") or Path(conda_prefix).name
        env_bin = Path(conda_prefix) / "bin"

        # Use CONDA_PREFIX to locate the conda base
        conda_base = Path(conda_prefix).resolve().parent  # this goes one up to base

        # Handle cases like /Users/foo/miniforge3/envs/Y2
        if (conda_base / "etc" / "profile.d" / "conda.sh").exists():
            conda_sh = conda_base / "etc" / "profile.d" / "conda.sh"
        else:
            # fallback: check via `which conda`
            conda_exe = shutil.which("conda")
            if conda_exe:
                conda_base = Path(conda_exe).resolve().parent.parent
                maybe_sh = conda_base / "etc" / "profile.d" / "conda.sh"
                if maybe_sh.exists():
                    conda_sh = maybe_sh

        print(f"Detected conda environment: {env_name} at {env_bin}")

        return env_type, env_name, str(env_bin), str(conda_sh) if conda_sh else None

    # Check for pipenv
    if os.environ.get("PIPENV_ACTIVE"):
        env_type = "pipenv"
        env_name = os.path.basename(os.path.dirname(python_exe))
        env_bin = Path(python_exe).parent
        return env_type, env_name, str(env_bin), None

    # Check for venv
    venv_path = os.environ.get("VIRTUAL_ENV")
    if venv_path:
        env_type = "venv"
        env_name = os.path.basename(venv_path)
        env_bin = Path(venv_path) / "bin"
        return env_type, env_name, str(env_bin), None

    # System Python
    return "system", None, str(Path(python_exe).parent), None


@deprecated
def build_screen_command_old(script_path, config_path, screen_name=None):
    """Handle build screen command old operation."""
    env_type, env_name, env_bin, conda_sh = detect_env_handler()
    screen_name = screen_name or env_name or "experiment"

    if env_type == "conda" and conda_sh:
        command = (
            f"screen -dmS {screen_name} bash -c "
            f"'source {conda_sh} && conda activate {env_name} && "
            f"python {script_path} -c {config_path}'"
        )
    elif env_type in ("venv", "pipenv"):
        command = (
            f"screen -dmS {screen_name} bash -c "
            f"'source {env_bin}/activate && python {script_path} -c {config_path}'"
        )
    else:  # system
        command = f"screen -dmS {screen_name} python {script_path} -c {config_path}"

    return command


##############


def detect_env_handler():
    """
    Detect the active Python environment and return executable path.

    Detects conda, pipenv, virtualenv/venv environments and returns
    appropriate Python command/path for running scripts in the same
    environment context.

    Returns:
        String: Python executable path or command prefix (e.g., 'pipenv run python')
    """
    python_exe = Path(sys.executable).resolve()

    # Determine platform-specific directory and executable names
    is_windows = sys.platform.startswith("win")

    # Prefer the interpreter that is already running this process.
    # Environment variables such as CONDA_PREFIX can point to a different
    # installation than sys.executable in desktop/IDE shells, which breaks
    # child process launches by switching them onto the wrong dependency set.
    if python_exe.exists():
        return str(python_exe)

    if is_windows:
        return str(python_exe)

    bin_dir = "bin"
    python_name = "python"

    # --- Case 1: Conda / Miniconda ---
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        conda_prefix = Path(conda_prefix).resolve()
        env_name = os.environ.get("CONDA_DEFAULT_ENV") or conda_prefix.name
        env_bin = conda_prefix / bin_dir

        # Detect conda base (handle .../envs/<env_name>)
        if conda_prefix.parent.name == "envs":
            conda_base = conda_prefix.parent.parent
        else:
            conda_base = conda_prefix

        conda_sh = conda_base / "etc" / "profile.d" / "conda.sh"
        python_bin = env_bin / python_name

        # Verify the Python executable exists before returning it
        if python_bin.exists():
            return str(python_bin)
        elif conda_sh.exists():
            # On Unix, if conda.sh exists but python binary doesn't, still try to return it
            # (might be a symlink or other edge case)
            return str(python_bin)

    # --- Case 2: Pipenv ---
    if os.environ.get("PIPENV_ACTIVE"):
        return "pipenv run python"

    # --- Case 3: Virtualenv / venv ---
    venv_prefix = os.environ.get("VIRTUAL_ENV")
    if venv_prefix:
        python_bin = Path(venv_prefix) / bin_dir / python_name
        # Verify the Python executable exists before returning it
        if python_bin.exists():
            return str(python_bin)
        # If it doesn't exist, fall through to system Python

    # --- Case 4: System Python fallback ---
    return str(python_exe)


@deprecated
def build_screen_command(script_path, config_path, screen_name=None):
    """
    Build a screen command to run Python script in detected environment.

    Creates a detached screen session running the script with the correct
    Python interpreter for the current environment.

    Args:
        script_path: Path to Python script to execute
        config_path: Path to configuration file (optional)
        screen_name: Name for screen session (default: "experiment")

    Returns:
        String: Complete screen command ready for execution
    """
    python_cmd = detect_env_handler()
    screen_name = screen_name or "experiment"

    # Quote script and config paths to handle spaces
    # Use single quotes inside the bash -c command to prevent shell expansion
    script_path_escaped = script_path.replace("'", "'\\''")
    config_path_escaped = config_path.replace("'", "'\\''") if config_path else ""

    run_cmd = f"{python_cmd} '{script_path_escaped}'"
    if config_path_escaped:
        run_cmd += f" -c '{config_path_escaped}'"

    # Single bash -c block inside screen
    screen_cmd = f"screen -dmS {screen_name} bash -c '{run_cmd}'"
    return screen_cmd



def terminate_server_process(exp_id):
    """
    Terminate a server process using the PID stored in the database.

    Args:
        exp_id: the experiment ID whose server process should be terminated

    Returns:
        bool: True if process was found and terminated, False otherwise
    """
    try:
        # Unregister from watchdog first
        if WATCHDOG_ENABLED:
            try:
                from y_web.utils.process_watchdog import get_watchdog

                watchdog = get_watchdog()
                watchdog.unregister_process(f"server_{exp_id}")
            except Exception as e:
                print(f"Warning: Could not unregister server from watchdog: {e}")

        # Unregister from process registry (closes log file handles)
        _unregister_process(f"server_{exp_id}")

        # Get experiment from database
        exp = db.session.query(Exps).filter_by(idexp=exp_id).first()
        if not exp or not exp.server_pid:
            print(f"No tracked server process found for experiment {exp_id}")
            return False

        pid = exp.server_pid
        print(f"Terminating server process with PID {pid}...")

        try:
            # Try graceful termination first
            os.kill(pid, signal.SIGTERM)

            # Wait up to 5 seconds for graceful shutdown
            for _ in range(50):  # 50 * 0.1s = 5 seconds
                try:
                    os.kill(pid, 0)  # Check if process still exists
                    time.sleep(0.1)
                except OSError:
                    # Process no longer exists
                    print(f"Server process {pid} terminated gracefully.")
                    break
            else:
                # If we get here, process is still running after timeout
                print(
                    f"Server process {pid} did not terminate gracefully, forcing kill..."
                )
                _local_terminate_process(pid)
                time.sleep(0.5)
                print(f"Server process {pid} killed.")

        except OSError as e:
            # Process doesn't exist
            print(f"Server process {pid} no longer exists: {e}")

        # Clear PID from database
        exp.server_pid = None
        db.session.commit()
        return True

    except Exception as e:
        print(f"Error terminating server process: {e}")
        return False



def _update_server_port_in_configs(exp, new_port):
    """
    Update the server port in all configuration files and database.

    This updates:
    1. The experiment's config_server.json
    2. All client config files (client_*.json) in the experiment folder
    3. The database entry for the experiment

    Args:
        exp: the experiment object
        new_port: the new port number

    Returns:
        bool: True if all updates succeeded, False otherwise
    """
    old_port = exp.port

    if old_port == new_port:
        return True  # No change needed

    print(f"Watchdog: Updating port from {old_port} to {new_port} in configs...")

    # Get experiment directory - use get_writable_path for PyInstaller compatibility
    from y_web.utils.path_utils import get_writable_path

    writable_base = get_writable_path()
    y_web_dir = os.path.join(writable_base, "y_web")

    if "database_server.db" in exp.db_name:
        # Handle path separator differences - split on both / and \
        path_part = exp.db_name.split("database_server.db")[0].rstrip("/\\")
        # Normalize path separators (replace both / and \ with os.sep)
        path_part = path_part.replace("/", os.sep).replace("\\", os.sep)
        exp_dir = os.path.join(writable_base, "y_web", path_part)
    else:
        uid = exp.db_name.removeprefix("experiments_")
        exp_dir = os.path.join(y_web_dir, "experiments", uid)

    success = True

    # 1. Update config_server.json
    server_config_path = os.path.join(exp_dir, "config_server.json")
    try:
        if os.path.exists(server_config_path):
            with open(server_config_path, "r") as f:
                server_config = json.load(f)

            server_config["port"] = new_port
            # Add data_path so YServer knows where to write logs
            server_config["data_path"] = exp_dir + os.sep

            with open(server_config_path, "w") as f:
                json.dump(server_config, f, indent=4)

            print(f"Watchdog: Updated config_server.json with port {new_port}")
        else:
            print(
                f"Watchdog: Warning - config_server.json not found at {server_config_path}"
            )
    except Exception as e:
        print(f"Watchdog: Error updating config_server.json: {e}")
        success = False

    # 2. Update all client config files
    try:
        if os.path.isdir(exp_dir):
            for item in os.listdir(exp_dir):
                if item.startswith("client") and item.endswith(".json"):
                    client_config_path = os.path.join(exp_dir, item)
                    try:
                        with open(client_config_path, "r") as f:
                            client_config = json.load(f)

                        # Update the API endpoint in servers section
                        if (
                            "servers" in client_config
                            and "api" in client_config["servers"]
                        ):
                            old_api = client_config["servers"]["api"]
                            # Replace port in URL - handles both with and without trailing slash
                            new_api = re.sub(r":(\d+)(/|$)", f":{new_port}\\2", old_api)
                            client_config["servers"]["api"] = new_api

                            with open(client_config_path, "w") as f:
                                json.dump(client_config, f, indent=4)

                            print(f"Watchdog: Updated {item} with new port")
                    except Exception as e:
                        print(f"Watchdog: Error updating {item}: {e}")
                        success = False
    except Exception as e:
        print(f"Watchdog: Error listing experiment directory: {e}")
        success = False

    # 3. Update database entry
    try:
        exp.port = new_port
        db.session.commit()
        print(f"Watchdog: Updated database with new port {new_port}")
    except Exception as e:
        print(f"Watchdog: Error updating database: {e}")
        success = False

    return success


def get_server_process_status(exp_id):
    """
    Get the status of a server process using the PID from the database.

    Args:
        exp_id: the experiment ID

    Returns:
        dict: Dictionary with status information including 'running', 'pid', and 'returncode'
    """
    try:
        exp = db.session.query(Exps).filter_by(idexp=exp_id).first()
        if not exp or not exp.server_pid:
            return {"running": False, "pid": None, "returncode": None}

        pid = exp.server_pid

        # Check if process is running
        try:
            os.kill(pid, 0)  # Signal 0 doesn't kill, just checks if process exists
            return {"running": True, "pid": pid, "returncode": None}
        except OSError:
            # Process doesn't exist
            return {"running": False, "pid": pid, "returncode": None}

    except Exception as e:
        print(f"Error getting server process status: {e}")
        return {"running": False, "pid": None, "returncode": None}


def start_server(exp):
    """
    Start the y_server using subprocess.Popen.

    This function launches a server process for an experiment. For PostgreSQL databases,
    it uses gunicorn WSGI server. For SQLite databases, it uses the standard Python
    execution. The process PID is stored in the database for later management and
    graceful termination.

    Args:
        exp: the experiment object

    Returns:
        subprocess.Popen: The started process object
    """
    # Get base path - this will be bundle location when frozen, repo root otherwise
    base_path = get_base_path()
    yserver_path = base_path

    # Get writable path for experiments directory
    writable_base = get_writable_path()
    # Define y_web directory path (replaces old BASE_DIR)
    y_web_dir = os.path.join(writable_base, "y_web")

    if "database_server.db" in exp.db_name:
        # Extract experiment uid from db_name path
        # db_name format: "experiments/uid/database_server.db"
        config = os.path.join(
            y_web_dir, exp.db_name.split("database_server.db")[0] + "config_server.json"
        )
        exp_uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")
        exp_uid = f"{uid}{os.sep}"
        config = os.path.join(y_web_dir, "experiments", uid, "config_server.json")

    server_dir, script_path = _resolve_server_runtime_paths(
        yserver_path, exp.platform_type
    )

    # Validate that script_path exists (skip check for PyInstaller bundles)
    # Check multiple PyInstaller indicators
    is_frozen = getattr(sys, "frozen", False)
    has_meipass = hasattr(sys, "_MEIPASS")
    is_bundle_exe = "python" not in Path(sys.executable).name.lower()

    if (
        not (is_frozen or has_meipass or is_bundle_exe)
        and not Path(script_path).exists()
    ):
        raise FileNotFoundError(
            f"Server script not found: {script_path}\n"
            f"Please ensure the YServer submodule is initialized.\n"
            f"Run: git submodule update --init --recursive"
        )

    # Validate that config file exists
    if not Path(config).exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config}\n"
            f"Please ensure the experiment is properly configured."
        )

    # === ROBUST PORT ALLOCATION ===
    # Every time a YServer starts:
    # 1. Terminate processes holding the database file (for SQLite)
    # 2. Kill all processes attached to the current assigned port (for safety)
    # 3. Find a NEW port in 5000-6000 that is free AND not allocated to other experiments
    # 4. Update configs and database with the new port
    # 5. Start server on the new port

    old_port = exp.port
    print(
        f"Starting robust port allocation for experiment {exp.idexp} "
        f"(current port: {old_port})..."
    )

    # Step 1: Terminate any processes holding the database file (SQLite safety)
    print("Step 1: Terminating any processes holding the database file...")
    _terminate_processes_holding_experiment_database(exp)
    time.sleep(0.5)  # Brief pause to allow database release

    # Step 2: Kill all processes on the currently assigned port (port safety)
    if old_port:
        print(f"Step 2: Terminating any processes on port {old_port}...")
        _terminate_processes_on_port(old_port)
        time.sleep(1)  # Brief pause to allow port release

    # Step 3: Find a new available port that is:
    # - Not currently in use by any process (socket check)
    # - Not allocated to any other experiment in the database
    # - Not the same as the current experiment's port (always get a fresh port)
    print(
        f"Step 3: Finding new available port in range "
        f"{SERVER_PORT_MIN}-{SERVER_PORT_MAX} (excluding current port {old_port})..."
    )
    new_port = _find_new_available_port(
        exclude_exp_id=exp.idexp,
        exclude_current_port=old_port,
        min_port=SERVER_PORT_MIN,
        max_port=SERVER_PORT_MAX,
    )

    if new_port:
        print(f"Found available port: {new_port}")

        # Step 4: Update config files and database with the new port
        # (always update since we're guaranteed a different port)
        print(f"Step 4: Updating configurations from port {old_port} to {new_port}...")
        if _update_server_port_in_configs(exp, new_port):
            print(f"Successfully updated port to {new_port}")
            # Refresh the experiment object to get updated port
            db.session.refresh(exp)
        else:
            print(
                f"Warning: Some config updates failed. "
                f"Server may fail to start on port {new_port}"
            )
    else:
        # No port found - this is a serious error
        raise RuntimeError(
            f"Could not find available port in range "
            f"{SERVER_PORT_MIN}-{SERVER_PORT_MAX}. "
            f"All ports are either in use or allocated to other experiments."
        )

    # Step 5: Start server on the new port
    # Check database type to decide whether to use gunicorn or direct Python
    db_uri_main = current_app.config["SQLALCHEMY_DATABASE_URI"]
    use_gunicorn = db_uri_main.startswith("postgresql")

    # Get the Python executable to use
    python_cmd = detect_env_handler()

    if use_gunicorn:
        # Use gunicorn for PostgreSQL
        print(f"Starting server for experiment {exp_uid} with gunicorn (PostgreSQL)...")

        # Build the gunicorn command with explicit parameters
        gunicorn_config_path = f"{server_dir}{os.sep}gunicorn_config.py"

        gunicorn_args = [
            "-c",
            gunicorn_config_path,
            "--bind",
            f"{exp.server}:{exp.port}",
            "--chdir",
            server_dir,  # Set working directory for the app
            "wsgi:app",
        ]

        # Build the gunicorn command
        # Note: gunicorn doesn't work well with PyInstaller bundles for server mode
        # If running from PyInstaller, we need to use the standard Python server instead
        # Check multiple PyInstaller indicators
        is_frozen = getattr(sys, "frozen", False)
        has_meipass = hasattr(sys, "_MEIPASS")
        is_bundle_exe = "python" not in Path(sys.executable).name.lower()

        if is_frozen or has_meipass or is_bundle_exe:
            # PyInstaller mode - cannot use gunicorn with frozen executable
            # Fall back to using the server runner with Flask's built-in server
            print(
                "Warning: Running from PyInstaller bundle. Using Flask server instead of gunicorn."
            )
            print(
                "For production use with PostgreSQL, run from source or use Docker deployment."
            )
            cmd = [
                sys.executable,
                "--run-server-subprocess",
                "-c",
                config,
                "--platform",
                exp.platform_type,
            ]
        elif (
            isinstance(python_cmd, str)
            and " " in python_cmd
            and not os.path.isabs(python_cmd)
        ):
            # Handle commands like "pipenv run python"
            cmd_parts = python_cmd.split()
            # Replace 'python' with 'gunicorn' in pipenv run scenarios
            if cmd_parts[-1] == "python":
                cmd_parts[-1] = "gunicorn"
            cmd = cmd_parts + gunicorn_args
        else:
            # Try to find gunicorn in the same directory as python (may contain spaces on Windows)
            # On Windows, executables have .exe extension
            gunicorn_name = (
                "gunicorn.exe" if sys.platform.startswith("win") else "gunicorn"
            )
            gunicorn_path = Path(python_cmd).parent / gunicorn_name
            if gunicorn_path.exists():
                cmd = [str(gunicorn_path)] + gunicorn_args
            else:
                # Fallback to system gunicorn
                gunicorn_which = shutil.which("gunicorn")
                if gunicorn_which:
                    cmd = [gunicorn_which] + gunicorn_args
                else:
                    # Last resort: try 'gunicorn' and let subprocess fail if not found
                    cmd = ["gunicorn"] + gunicorn_args

        # Set environment variable for config file path
        env = os.environ.copy()
        env["YSERVER_CONFIG"] = config
        env["YSERVER_LOG_FILE"] = str(Path(config).parent / "_server.log")

        # Create log files for server output
        log_dir = Path(config).parent
        stdout_log = log_dir / "server_stdout.log"
        stderr_log = log_dir / "server_stderr.log"

        # Open log files for the subprocess - they need to stay open for the lifetime of the process
        try:
            out_file = open(stdout_log, "a", encoding="utf-8", buffering=1)
            err_file = open(stderr_log, "a", encoding="utf-8", buffering=1)
        except Exception as e:
            print(f"Warning: Could not open log files: {e}")
            out_file = subprocess.DEVNULL
            err_file = subprocess.DEVNULL

        try:
            # Start the process with Popen
            # On Windows, use creationflags instead of start_new_session to avoid console window
            # Redirect output to files instead of PIPE to avoid blocking
            if sys.platform.startswith("win"):
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW
                except AttributeError:
                    creationflags = 0x08000000
                process = subprocess.Popen(
                    cmd,
                    stdout=out_file,
                    stderr=err_file,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                    env=env,
                )
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=out_file,
                    stderr=err_file,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
            print(f"Server process started with PID: {process.pid}")
            if out_file != subprocess.DEVNULL:
                print(f"Logs: {stdout_log} and {stderr_log}")
        except Exception as e:
            # Fallback: try to use gunicorn from system path
            print(f"Error starting server process: {e}")
            gunicorn_which = shutil.which("gunicorn")
            fallback_cmd = [gunicorn_which or "gunicorn"] + gunicorn_args
            if sys.platform.startswith("win"):
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW
                except AttributeError:
                    creationflags = 0x08000000
                process = subprocess.Popen(
                    fallback_cmd,
                    stdout=out_file,
                    stderr=err_file,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                    env=env,
                )
            else:
                process = subprocess.Popen(
                    fallback_cmd,
                    stdout=out_file,
                    stderr=err_file,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
    else:
        # Use standard Python execution for SQLite
        print(f"Starting server for experiment {exp_uid} with Python (SQLite)...")

        # Build the command as a list for subprocess.Popen
        # Check if running from PyInstaller bundle
        # We need to check multiple indicators:
        # 1. sys.frozen - set when running in frozen mode
        # 2. sys._MEIPASS - PyInstaller's temp extraction directory
        # 3. Executable name doesn't contain "python"
        is_frozen = getattr(sys, "frozen", False)
        has_meipass = hasattr(sys, "_MEIPASS")
        is_bundle_exe = "python" not in Path(sys.executable).name.lower()

        if is_frozen or has_meipass or is_bundle_exe:
            # Running from PyInstaller - invoke the bundled executable with special flag
            # The launcher script detects this flag and routes to the server runner
            cmd = [
                sys.executable,
                "--run-server-subprocess",
                "-c",
                config,
                "--platform",
                exp.platform_type,
            ]
        elif (
            isinstance(python_cmd, str)
            and " " in python_cmd
            and not os.path.isabs(python_cmd)
        ):
            # Handle commands like "pipenv run python"
            cmd_parts = python_cmd.split()
            cmd = cmd_parts + [script_path, "-c", config]
        else:
            # Simple python executable path (may contain spaces on Windows)
            cmd = [python_cmd, script_path, "-c", config]

        # Create log files for server output to avoid pipe buffering issues
        # The server process should run independently without blocking on PIPE
        log_dir = Path(config).parent
        env = os.environ.copy()
        env["YSERVER_LOG_FILE"] = str(log_dir / "_server.log")
        stdout_log = log_dir / "server_stdout.log"
        stderr_log = log_dir / "server_stderr.log"

        # Open log files for the subprocess - they need to stay open for the lifetime of the process
        # We don't use 'with' because the process needs to outlive this function
        try:
            out_file = open(stdout_log, "a", encoding="utf-8", buffering=1)
            err_file = open(stderr_log, "a", encoding="utf-8", buffering=1)
        except Exception as e:
            print(f"Warning: Could not open log files: {e}")
            # Fallback to DEVNULL if log files can't be opened
            out_file = subprocess.DEVNULL
            err_file = subprocess.DEVNULL

        try:
            # Start the process with Popen
            # On Windows, use creationflags instead of start_new_session to avoid console window
            # Redirect output to files instead of PIPE to avoid blocking
            if sys.platform.startswith("win"):
                # DETACHED_PROCESS = 0x00000008 - creates process without console
                # CREATE_NO_WINDOW = 0x08000000 - creates process with no window (Python 3.7+)
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW
                except AttributeError:
                    # Fallback for older Python versions
                    creationflags = 0x08000000

                # Don't use shell=True when passing special flags like --run-server-subprocess
                # as the shell can interfere with argument parsing
                # For PyInstaller bundles, we need direct subprocess invocation
                process = subprocess.Popen(
                    cmd,
                    stdout=out_file,
                    stderr=err_file,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            else:
                # On Unix, use start_new_session for proper detachment
                process = subprocess.Popen(
                    cmd,
                    stdout=out_file,
                    stderr=err_file,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            print(f"Server process started with PID: {process.pid}")
            if out_file != subprocess.DEVNULL:
                print(f"Logs: {stdout_log} and {stderr_log}")
        except Exception as e:
            # Fallback: try to use the current Python implicitly
            print(f"Error starting server process: {e}")
            print(f"Command: {' '.join(cmd)}")
            print(f"Config file: {config}")

            # Add detailed debugging information
            full_path = os.path.join(y_web_dir, exp.db_name)
            if len(full_path) > 2 and full_path[1] == ":":
                # Windows - strip "C:\" (drive + separator)
                if len(full_path) > 3 and full_path[2] in ("/", "\\"):
                    db_uri = full_path[3:].replace("\\", "/")
                else:
                    db_uri = full_path[2:].replace("\\", "/")
            else:
                # Unix - strip "/"
                db_uri = full_path[1:].replace("\\", "/")

            print(f"Database URI: {db_uri}")
            print(f"Database URI type: {type(db_uri)}")
            print(f"Database URI repr: {repr(db_uri)}")
            raise

    # print(f"Command: {' '.join(cmd)}")
    print(f"Config file: {config}")

    # Save the PID to the database for persistent tracking
    exp.server_pid = process.pid
    db.session.commit()

    # Identify the database URI to be set
    db_type = "sqlite"
    if db_uri_main.startswith("postgresql"):
        db_type = "postgresql"

    if db_type == "sqlite":
        # Construct the database URI properly for both Windows and Unix
        # YServer prepends the system drive, so we need to strip it from our path
        full_path = os.path.join(y_web_dir, exp.db_name)

        # On Windows, strip the drive letter AND the following separator (e.g., "C:\")
        # On Unix, strip the leading "/"
        # YServer will add them back when constructing file paths
        if len(full_path) > 2 and full_path[1] == ":":
            # Windows path - strip drive letter and separator "C:\" or "C:/"
            # Check if there's a separator after the drive letter
            if len(full_path) > 3 and full_path[2] in ("/", "\\"):
                db_uri = full_path[3:].replace("\\", "/")
            else:
                db_uri = full_path[2:].replace("\\", "/")
        else:
            # Unix path - strip leading "/"
            db_uri = full_path[1:].replace("\\", "/")
    elif db_type == "postgresql":
        old_db_name = db_uri_main.split("/")[-1]
        db_uri = db_uri_main.replace(old_db_name, exp.db_name)

    # Wait for the server to start and configure database
    if use_gunicorn:
        # For gunicorn (PostgreSQL), use health check and retry logic
        max_retries = 5
        retry_delay = 5

        for attempt in range(max_retries):
            time.sleep(retry_delay)

            try:
                # Check if server is responding
                health_check_url = f"http://{exp.server}:{exp.port}/"
                response = requests.get(health_check_url, timeout=5)
                print(f"Server is ready (attempt {attempt + 1}/{max_retries})")
                break
            except Exception as e:
                print(
                    f"Server not ready yet (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt == max_retries - 1:
                    print("Warning: Server may not be fully started, proceeding anyway")

    else:
        # For standard Python (SQLite), use simple wait and single call
        time.sleep(20)
        data = {"path": f"{db_uri}"}
        headers = {"Content-Type": "application/json"}
        ns = f"http://{exp.server}:{exp.port}/change_db"
        print(f"Sending to /change_db endpoint: {json.dumps(data)}")
        print(f"POST URL: {ns}")
        try:
            response = post(f"{ns}", headers=headers, data=json.dumps(data))
            print(
                f"Database configuration successful. Response: {response.status_code}"
            )
        except Exception as e:
            print(f"Warning: Could not configure database: {e}")

    # Register with watchdog for automatic restart on hang/death
    if WATCHDOG_ENABLED:
        try:
            _register_server_with_watchdog(exp, process.pid, log_dir)
        except Exception as e:
            print(f"Warning: Could not register server with watchdog: {e}")

    # Register process to prevent garbage collection and keep log file handles open
    _register_process(f"server_{exp.idexp}", process, out_file, err_file)

    return process


##############
# HPC Server/Client Functions — delegated to y_web.src.hpc.server / y_web.src.hpc.client
##############
# fmt: off
from y_web.src.hpc.server import (  # noqa: E402,F401
    start_hpc_server,
    start_server_screen,
    stop_hpc_server,
)
from y_web.src.hpc.client import (  # noqa: E402,F401
    start_hpc_client,
    stop_hpc_client,
)
# fmt: on

def _register_server_with_watchdog(exp, pid, log_dir):
    """
    Register a server process with the watchdog for monitoring.

    Args:
        exp: the experiment object
        pid: the process ID
        log_dir: directory containing log files
    """
    from y_web.utils.process_watchdog import get_watchdog

    # Use _server.log as the heartbeat file (this is the main server log)
    log_file = os.path.join(log_dir, "_server.log")

    # Store only the ID to avoid detached SQLAlchemy instance issues
    exp_id = exp.idexp

    # Build server URL for status checks
    server_url = f"http://{exp.server}:{exp.port}"

    # Create restart callback
    def restart_callback():
        """Callback to restart the server process."""
        try:
            # Import here to avoid circular imports
            from y_web import create_app

            # Create app context for database operations
            app = create_app()
            with app.app_context():
                # Re-fetch experiment from database to get fresh state
                fresh_exp = db.session.query(Exps).filter_by(idexp=exp_id).first()
                if fresh_exp:
                    # Terminate any existing process using robust termination
                    # This ensures proper cleanup of hung processes
                    if fresh_exp.server_pid:
                        pid_to_kill = fresh_exp.server_pid
                        print(
                            f"Watchdog: Terminating server process tree (PID {pid_to_kill})..."
                        )
                        _force_terminate_process_tree(pid_to_kill)

                        # Clear PID from database for consistency
                        fresh_exp.server_pid = None
                        db.session.commit()

                    # start_server() will handle:
                    # 1. Killing any processes on the old port
                    # 2. Finding a new port not allocated to any experiment
                    # 3. Updating configs and database
                    # 4. Starting the server
                    print(f"Watchdog: Starting new server process...")
                    new_process = start_server(fresh_exp)
                    return new_process.pid if new_process else None
        except Exception as e:
            print(f"Error in server restart callback: {e}")
        return None

    # Get or create watchdog and register process
    watchdog = get_watchdog()
    process_id = f"server_{exp_id}"

    watchdog.register_process(
        process_id=process_id,
        pid=pid,
        log_file=log_file,
        restart_callback=restart_callback,
        process_type="server",
        server_url=server_url,
    )

    # Start watchdog if not already running
    if not watchdog.is_running:
        watchdog.start()


