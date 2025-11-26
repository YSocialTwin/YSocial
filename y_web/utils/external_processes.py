"""
External process management utilities.

Manages simulation client processes, Ollama server interactions, and
environment detection. Handles process lifecycle including starting,
monitoring, and terminating simulation clients running in screen sessions.
Provides utilities for network generation, database operations, and
LLM model management.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from multiprocessing import Process
from pathlib import Path

import requests
from flask import current_app
from ollama import Client as oclient
from requests import post
from sklearn.utils import deprecated

from y_web import db
from y_web.models import (
    Client,
    Exps,
    Ollama_Pull,
    Population,
)
from y_web.utils.path_utils import get_base_path, get_resource_path, get_writable_path

# Dictionary to track Ollama model download processes
ollama_processes = {}

# Flag to enable/disable watchdog monitoring
WATCHDOG_ENABLED = True


def cleanup_server_processes_from_db():
    """
    Cleanup server processes based on PIDs stored in the database.

    This function is useful when the application restarts and there are
    still running server processes from previous sessions. It reads PIDs
    from the database and attempts to terminate them.
    """
    try:
        exps = db.session.query(Exps).filter(Exps.server_pid.isnot(None)).all()
        for exp in exps:
            try:
                print(
                    f"Attempting to terminate server process PID {exp.server_pid} for experiment {exp.idexp}"
                )
                os.kill(exp.server_pid, signal.SIGTERM)
                time.sleep(1)
                # Check if process is still running
                try:
                    os.kill(exp.server_pid, 0)  # Check if process exists
                    # If we get here, process is still running, force kill
                    print(f"Process server {exp.server_pid} still running, terminating")
                    __terminate_process(exp.server_pid)
                    # os.kill(exp.server_pid, signal.SIGKILL)
                except OSError:
                    # Process doesn't exist anymore
                    pass
                # Clear the PID from database
                exp.server_pid = None
            except OSError as e:
                # Process doesn't exist
                print(f"Process {exp.server_pid} no longer exists: {e}")
                exp.server_pid = None
            except Exception as e:
                print(f"Error terminating server process {exp.server_pid}: {e}")
        # Commit all changes at once
        db.session.commit()
    except Exception as e:
        print(f"Error during server process cleanup: {e}")


def cleanup_client_processes_from_db():
    """
    Cleanup client processes based on PIDs stored in the database.

    This function is useful when the application restarts and there are
    still running client processes from previous sessions. It reads PIDs
    from the database and attempts to terminate them.
    """
    try:
        clients = db.session.query(Client).filter(Client.pid.isnot(None)).all()
        for client in clients:
            try:
                print(
                    f"Attempting to terminate client process PID {client.pid} for client {client.id}"
                )
                os.kill(client.pid, signal.SIGTERM)
                time.sleep(1)
                # Check if process is still running
                try:
                    os.kill(client.pid, 0)  # Check if process exists
                    # If we get here, process is still running, force kill
                    print(f"Process {client.pid} still running, terminating")
                    __terminate_process(client.pid)
                    # os.kill(client.pid, signal.SIGKILL)
                except OSError:
                    # Process doesn't exist anymore
                    pass
                # Clear the PID from database
                client.pid = None
            except OSError as e:
                # Process doesn't exist
                print(f"Process {client.pid} no longer exists: {e}")
                client.pid = None
            except Exception as e:
                print(f"Error terminating client process {client.pid}: {e}")
        # Commit all changes at once
        db.session.commit()
    except Exception as e:
        print(f"Error during client process cleanup: {e}")


def stop_all_exps():
    """Stop all experiments and terminate server and client processes"""
    try:
        # Stop watchdog first to prevent auto-restarts during shutdown
        if WATCHDOG_ENABLED:
            try:
                from y_web.utils.process_watchdog import stop_watchdog

                stop_watchdog()
            except Exception as e:
                print(f"Warning: Could not stop watchdog: {e}")

        # Terminate all running server processes
        cleanup_server_processes_from_db()

        # Terminate all running client processes
        cleanup_client_processes_from_db()

        # set to 0 all Exps.running
        exps = db.session.query(Exps).all()
        for exp in exps:
            exp.running = 0
            exp.server_pid = None

        # set to 0 all Client.status
        clis = db.session.query(Client).all()
        for cli in clis:
            cli.status = 0
            cli.pid = None

        # Commit all changes at once
        db.session.commit()

        # Explicitly flush to ensure changes are written to database
        db.session.flush()

        print(
            f"Successfully cleared PIDs for {len(exps)} experiments and {len(clis)} clients"
        )

    except Exception as e:
        print(f"Error in stop_all_exps: {e}")
        # Try to rollback and commit again
        try:
            db.session.rollback()

            # Try again with a fresh query
            db.session.query(Exps).update({Exps.running: 0, Exps.server_pid: None})
            db.session.query(Client).update({Client.status: 0, Client.pid: None})
            db.session.commit()

            print("Successfully cleared PIDs on retry after error")
        except Exception as e2:
            print(f"Failed to clear PIDs even on retry: {e2}")


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
    python_exe = Path(sys.executable)

    # Determine platform-specific directory and executable names
    is_windows = sys.platform.startswith("win")

    if is_windows:
        return python_exe

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


##############
# Process termination utilities
###############


def terminate_process_on_port(port):
    """
    Terminate the process using the specified port.

    This function is deprecated in favor of terminate_server_process() for
    processes managed via subprocess.Popen, but is kept for compatibility
    with legacy screen-based processes.

    Args:
        port: the port number
    """
    try:
        result = subprocess.run(
            ["lsof", "-t", "-i", f":{port}"], capture_output=True, text=True, check=True
        )
        pid = result.stdout.strip()

        if pid:
            print(f"Found process {pid} using port {port}. Killing process...")
            __terminate_process(int(pid))
            # os.kill(int(pid), 9)  # Send SIGKILL to the process
            print(f"Process {pid} terminated.")
        else:
            print(f"No process found using port {port}.")
    except Exception as e:
        print(f"Error: {e}")
        pass


def terminate_server_process(exp_id):
    """
    Terminate a server process using the PID stored in the database.

    This function terminates a server process that was started using the
    start_server() function and has its PID stored in the database.
    It handles graceful shutdown of gunicorn-based servers using SIGTERM,
    followed by SIGKILL if needed. It clears the PID from the database
    after termination.

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
                # os.kill(pid, signal.SIGKILL)
                __terminate_process(pid)
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


def __terminate_process(pid):
    import platform

    try:
        if platform.system() == "Windows":
            # On Windows: use psutil or taskkill
            try:
                import psutil

                p = psutil.Process(pid)
                p.terminate()  # graceful
            except ImportError:
                os.system(f"taskkill /PID {pid} /F")
        else:
            # On Unix: send SIGKILL
            os.kill(pid, signal.SIGKILL)
    except Exception as e:
        print(f"Error terminating process {pid}: {e}")


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
    sys.path.append(os.path.join(yserver_path, "external", "YServer"))

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

    # Determine the server directory and script path based on platform type
    if exp.platform_type == "microblogging":
        server_dir = os.path.join(yserver_path, "external", "YServer")
        script_path = os.path.join(
            yserver_path, "external", "YServer", "y_server_run.py"
        )
    elif exp.platform_type == "forum":
        server_dir = os.path.join(yserver_path, "external", "YServerReddit")
        script_path = os.path.join(
            yserver_path, "external", "YServerReddit", "y_server_run.py"
        )
    else:
        raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

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

    return process


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
                    # Terminate any existing process first
                    if fresh_exp.server_pid:
                        try:
                            os.kill(fresh_exp.server_pid, signal.SIGTERM)
                            time.sleep(1)
                        except OSError:
                            pass

                    # Start new server process
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
    )

    # Start watchdog if not already running
    if not watchdog.is_running:
        watchdog.start()


@deprecated
def start_server_screen(exp):
    """
    Start the y_server in a detached screen (DEPRECATED).

    This function is deprecated in favor of start_server() which uses subprocess.Popen.
    It is kept for backward compatibility but should not be used in new code.

    Args:
        exp: the experiment object
    """
    yserver_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    sys.path.append(f"{yserver_path}{os.sep}external{os.sep}YServer{os.sep}")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]

    if "database_server.db" in exp.db_name:
        config = f"{yserver_path}y_web{os.sep}{exp.db_name.split('database_server.db')[0]}config_server.json"
        exp_uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")
        exp_uid = f"{uid}{os.sep}"
        config = (
            f"{yserver_path}y_web{os.sep}experiments{os.sep}{exp_uid}config_server.json"
        )

    if exp.platform_type == "microblogging":
        screen_command = build_screen_command(
            script_path=f"{yserver_path}external{os.sep}YServer{os.sep}y_server_run.py",
            config_path=f"{config}",
            screen_name=f"{exp_uid.replace(f'{os.sep}', '')}",
        )

    elif exp.platform_type == "forum":
        screen_command = build_screen_command(
            script_path=f"{yserver_path}external{os.sep}YServerReddit{os.sep}y_server_run.py",
            config_path=f"{config}",
            screen_name=f"{exp_uid.replace(f'{os.sep}', '')}",
        )
        # subprocess.run(cmd, shell=True, check=True)
    else:
        raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

    # Command to run in the detached screen
    # screen_command = f"screen -dmS {exp_uid.replace(f'{os.sep}', '')} {flask_command}"
    print(screen_command)

    print(f"Starting server for experiment {exp_uid} ...")
    subprocess.run(screen_command, shell=True, check=True)

    # identify the db to be set
    db_uri_main = current_app.config["SQLALCHEMY_DATABASE_URI"]

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

    print(f"Database URI: {db_uri}")

    # Wait for the server to start
    time.sleep(20)
    data = {"path": f"{db_uri}"}
    headers = {"Content-Type": "application/json"}
    ns = f"http://{exp.server}:{exp.port}/change_db"
    post(f"{ns}", headers=headers, data=json.dumps(data))


##############
# Ollama Functions
##############


def is_ollama_installed():
    # Step 1: Check if Ollama is installed
    """Handle is ollama installed operation."""
    try:
        subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, check=True
        )
        print("Ollama is installed.")
        return True
    except FileNotFoundError:
        print("Ollama is not installed.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking Ollama installation: {e}")
        return False


def is_ollama_running():
    # Step 2: Check if Ollama is running
    """Handle is ollama running operation."""
    try:
        response = requests.get("http://127.0.0.1:11434/api/version")
        if response.status_code == 200:
            # print("Ollama is running.")
            return True
        else:
            # print(
            #    f"Ollama responded but not running correctly. Status: {response.status_code}"
            # )
            return False
    except requests.ConnectionError:
        # print("Ollama is not running or cannot be reached.")
        return False


def start_ollama_server():
    """Handle start ollama server operation."""
    if is_ollama_installed():
        if not is_ollama_running():
            screen_command = f"screen -dmS ollama ollama serve"

            print(f"Starting ollama server...")
            subprocess.run(screen_command, shell=True, check=True)

            # Wait for the server to start
            time.sleep(5)
        else:
            print("Ollama is already running.")
    else:
        print("Ollama is not installed.")


def pull_ollama_model(model_name):
    """Handle pull ollama model operation."""
    if is_ollama_running():
        process = Process(target=start_ollama_pull, args=(model_name,))
        process.start()
        ollama_processes[model_name] = process


def start_ollama_pull(model_name):
    """
    Start downloading an Ollama model in background.

    Args:
        model_name: Name of model to download
    """
    ol_client = oclient(
        host="http://127.0.0.1:11434", headers={"x-some-header": "some-value"}
    )

    for progress in ol_client.pull(model_name, stream=True):
        model = Ollama_Pull.query.filter_by(model_name=model_name).first()
        if not model:
            model = Ollama_Pull(model_name=model_name, status=0)
            db.session.add(model)
            db.session.commit()

        total = progress.get("total")
        completed = progress.get("completed")
        if completed is not None:
            current = float(completed) / float(total)
            # update the model status
            model = Ollama_Pull.query.filter_by(model_name=model_name).first()
            model.status = current
            db.session.commit()


def get_ollama_models():
    """
    Get list of installed Ollama models.

    Returns:
        List of available model names
    """
    pattern = r"model='(.*?)'"
    models = []

    ol_client = oclient(
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
    )

    # Extract all model values
    for i in ol_client.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]
    return models


def delete_ollama_model(model_name):
    """
    Delete an Ollama model from the system.

    Args:
        model_name: Name of model to delete
    """
    ol_client = oclient(
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
    )

    ol_client.delete(model_name)


def delete_model_pull(model_name):
    """
    Cancel an ongoing model download.

    Args:
        model_name: Name of model to cancel download for
    """
    if model_name in ollama_processes:
        process = ollama_processes[model_name]
        process.terminate()
        process.join()

    model = Ollama_Pull.query.filter_by(model_name=model_name).first()
    db.session.delete(model)
    db.session.commit()


#############
# vLLM Functions
#############


def is_vllm_installed():
    """Check if vLLM is installed."""
    try:
        subprocess.run(
            ["vllm", "--version"], capture_output=True, text=True, check=True
        )
        print("vLLM is installed.")
        return True
    except FileNotFoundError:
        print("vLLM is not installed.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking vLLM installation: {e}")
        return False


def is_vllm_running():
    """Check if vLLM server is running."""
    try:
        response = requests.get("http://127.0.0.1:8000/health")
        if response.status_code == 200:
            print("vLLM is running.")
            return True
        else:
            print(
                f"vLLM responded but not running correctly. Status: {response.status_code}"
            )
            return False
    except requests.ConnectionError:
        print("vLLM is not running or cannot be reached.")
        return False


def start_vllm_server(model_name=None):
    """
    Start vLLM server.

    Args:
        model_name: Name of model to serve (optional, if None, server must be started manually)
    """
    if is_vllm_installed():
        if not is_vllm_running():
            if model_name:
                screen_command = f"screen -dmS vllm vllm serve {model_name} --host 0.0.0.0 --port 8000"
                print(f"Starting vLLM server with model {model_name}...")
                subprocess.run(screen_command, shell=True, check=True)
                # Wait for the server to start
                time.sleep(10)
            else:
                print(
                    "vLLM is installed but not running. Please start manually with a model."
                )
        else:
            print("vLLM is already running.")
    else:
        print("vLLM is not installed.")


def get_vllm_models():
    """
    Get list of models available on vLLM server.

    Returns:
        List of model names available on vLLM server
    """
    if not is_vllm_running():
        return []

    try:
        response = requests.get("http://127.0.0.1:8000/v1/models")
        if response.status_code == 200:
            data = response.json()
            # vLLM returns models in OpenAI-compatible format
            models = [model["id"] for model in data.get("data", [])]
            return models
        else:
            print(f"Failed to get vLLM models. Status: {response.status_code}")
            return []
    except requests.ConnectionError:
        print("vLLM server is not accessible.")
        return []


def get_llm_models(llm_url=None):
    """
    Get list of models from any OpenAI-compatible LLM server.

    Args:
        llm_url: Base URL of the LLM server (e.g., 'http://localhost:8000/v1').
                 If None, uses LLM_URL from environment or falls back to ollama.

    Returns:
        List of model names available on the LLM server
    """
    import os

    # Determine URL
    if llm_url is None:
        llm_url = os.getenv("LLM_URL")
        if not llm_url:
            backend = os.getenv("LLM_BACKEND", "ollama")
            if backend == "vllm":
                llm_url = "http://127.0.0.1:8000/v1"
            else:
                llm_url = "http://127.0.0.1:11434/v1"

    # Construct models endpoint URL
    models_url = (
        llm_url.replace("/v1", "/v1/models")
        if "/v1" in llm_url
        else f"{llm_url}/models"
    )

    try:
        response = requests.get(models_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # OpenAI-compatible format
            models = [model["id"] for model in data.get("data", [])]
            return models
        else:
            print(
                f"Failed to get LLM models from {models_url}. Status: {response.status_code}"
            )
            return []
    except requests.exceptions.RequestException as e:
        print(f"LLM server at {models_url} is not accessible: {e}")
        return []


##############
# Client Process Management
##############


def terminate_client(cli, pause=False):
    """Stop the y_client using PID from database

    Args:
        cli: the client object
        pause: whether this is a pause (may be resumed) or full stop
    """
    # Unregister from watchdog first
    if WATCHDOG_ENABLED:
        try:
            from y_web.utils.process_watchdog import get_watchdog

            watchdog = get_watchdog()
            watchdog.unregister_process(f"client_{cli.id}")
        except Exception as e:
            print(f"Warning: Could not unregister client from watchdog: {e}")

    if not cli.pid:
        print(f"No PID found for client {cli.name}")
        return

    try:
        pid = cli.pid
        print(f"Terminating client process with PID {pid}...")

        # Try graceful termination first
        os.kill(pid, signal.SIGTERM)

        # Wait up to 5 seconds for graceful shutdown
        for _ in range(50):  # 50 * 0.1s = 5 seconds
            try:
                os.kill(pid, 0)  # Check if process still exists
                time.sleep(0.1)
            except OSError:
                # Process no longer exists
                print(f"Client process {pid} terminated gracefully.")
                break
        else:
            # If we get here, process is still running after timeout
            print(f"Client process {pid} did not terminate gracefully, forcing kill...")
            __terminate_process(pid)

            time.sleep(0.5)
            print(f"Client process {pid} killed.")

    except OSError as e:
        # Process doesn't exist
        print(f"Client process {pid} no longer exists: {e}")
    except Exception as e:
        print(f"Error terminating client process: {e}")

    # Clear PID from database
    cli.pid = None
    db.session.commit()


def start_client(exp, cli, population, resume=True):
    """
    Handle start client operation using subprocess.Popen.

    This function launches a client process for an experiment. The process
    is started using subprocess.Popen to allow for better process management
    and isolation. The process PID is stored in the database for later
    management and graceful termination.

    Args:
        exp: the experiment object
        cli: the client object
        population: the population object
        resume: whether to resume from last state (default: True)

    Returns:
        subprocess.Popen: The started process object
    """
    db_type = "sqlite"
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        db_type = "postgresql"

    # Build the command arguments
    cmd_args = [
        "--exp-id",
        str(exp.idexp),
        "--client-id",
        str(cli.id),
        "--population-id",
        str(population.id),
        "--db-type",
        db_type,
    ]

    if resume:
        cmd_args.append("--resume")
    else:
        cmd_args.append("--no-resume")

    # Determine how to run the client subprocess based on execution environment
    if getattr(sys, "frozen", False):
        # Running from PyInstaller - invoke the bundled executable with special flag
        # The launcher script detects this flag and routes to the client runner
        cmd = [sys.executable, "--run-client-subprocess"] + cmd_args
    else:
        # Running from source - use detected environment with script path
        python_cmd = detect_env_handler()
        runner_script = get_resource_path(
            os.path.join("y_web", "utils", "y_client_process_runner.py")
        )

        # Validate that runner script exists
        if not Path(runner_script).exists():
            raise FileNotFoundError(
                f"Client runner script not found: {runner_script}\n"
                f"Please ensure y_client_process_runner.py exists in the utils directory."
            )

        if (
            isinstance(python_cmd, str)
            and " " in python_cmd
            and not os.path.isabs(python_cmd)
        ):
            # Handle commands like "pipenv run python"
            cmd_parts = python_cmd.split()
            cmd = cmd_parts + [runner_script] + cmd_args
        else:
            # Simple python executable path (may contain spaces on Windows)
            cmd = [python_cmd, runner_script] + cmd_args

    # Create log files for client output
    from y_web.utils.path_utils import get_writable_path

    writable_base = get_writable_path()

    if "experiments_" in exp.db_name:
        uid = exp.db_name.removeprefix("experiments_")
        log_dir = Path(os.path.join(writable_base, "y_web", "experiments", uid))
    else:
        # exp.db_name format: "experiments/uid/database_server.db"
        uid = exp.db_name.split(os.sep)[1]
        log_dir = Path(
            os.path.join(
                writable_base, "y_web", exp.db_name.split("database_server.db")[0]
            )
        )

    stdout_log = log_dir / f"{cli.name}_client_stdout.log"
    stderr_log = log_dir / f"{cli.name}_client_stderr.log"

    # Open log files for the subprocess
    try:
        out_file = open(stdout_log, "a", encoding="utf-8", buffering=1)
        err_file = open(stderr_log, "a", encoding="utf-8", buffering=1)
    except Exception as e:
        print(f"Warning: Could not open log files: {e}")
        out_file = subprocess.DEVNULL
        err_file = subprocess.DEVNULL

    # Set up environment with PYTHONPATH to ensure imports work
    # The subprocess needs to be able to import y_web modules
    env = os.environ.copy()

    if getattr(sys, "frozen", False):
        # Running from PyInstaller - modules are in the bundle
        # The bootstrap script will handle sys.path setup
        # No PYTHONPATH needed as we're using runpy with the bundled interpreter
        pass
    else:
        # Running from source - add project root to PYTHONPATH
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = project_root

    # Determine working directory
    if getattr(sys, "frozen", False):
        # When frozen, use current working directory
        cwd = os.getcwd()
    else:
        # When running from source, use project root
        cwd = project_root

    # Start the process with Popen
    try:
        if sys.platform.startswith("win"):
            # On Windows, use creationflags to avoid console window
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
                cwd=cwd,
            )
        else:
            # On Unix, use start_new_session for proper detachment
            process = subprocess.Popen(
                cmd,
                stdout=out_file,
                stderr=err_file,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
                cwd=cwd,
            )

        print(f"Client process started with PID: {process.pid}")
        if out_file != subprocess.DEVNULL:
            print(f"Logs: {stdout_log} and {stderr_log}")
    except Exception as e:
        print(f"Error starting client process: {e}")
        print(f"Command: {' '.join(cmd)}")
        raise

    # Store PID in database
    cli.pid = process.pid
    db.session.commit()

    # Register with watchdog for automatic restart on hang/death
    if WATCHDOG_ENABLED:
        try:
            _register_client_with_watchdog(exp, cli, population, process.pid, log_dir)
        except Exception as e:
            print(f"Warning: Could not register client with watchdog: {e}")

    return process


def _register_client_with_watchdog(exp, cli, population, pid, log_dir):
    """
    Register a client process with the watchdog for monitoring.

    Args:
        exp: the experiment object
        cli: the client object
        population: the population object
        pid: the process ID
        log_dir: directory containing log files
    """
    from y_web.utils.process_watchdog import get_watchdog

    # Use {client_name}_client.log as the heartbeat file
    log_file = os.path.join(log_dir, f"{cli.name}_client.log")

    # Store only the IDs to avoid detached SQLAlchemy instance issues
    exp_id = exp.idexp
    cli_id = cli.id
    pop_id = population.id

    # Create restart callback
    def restart_callback():
        """Callback to restart the client process."""
        try:
            # Import here to avoid circular imports
            from y_web import create_app

            # Create app context for database operations
            app = create_app()
            with app.app_context():
                # Re-fetch objects from database to get fresh state
                fresh_exp = db.session.query(Exps).filter_by(idexp=exp_id).first()
                fresh_cli = db.session.query(Client).filter_by(id=cli_id).first()
                fresh_pop = db.session.query(Population).filter_by(id=pop_id).first()

                if fresh_exp and fresh_cli and fresh_pop:
                    # Terminate any existing process first
                    if fresh_cli.pid:
                        try:
                            os.kill(fresh_cli.pid, signal.SIGTERM)
                            time.sleep(1)
                        except OSError:
                            pass

                    # Start new client process (resume=True to continue from last state)
                    new_process = start_client(
                        fresh_exp, fresh_cli, fresh_pop, resume=True
                    )
                    return new_process.pid if new_process else None
        except Exception as e:
            print(f"Error in client restart callback: {e}")
        return None

    # Get or create watchdog and register process
    watchdog = get_watchdog()
    process_id = f"client_{cli_id}"

    watchdog.register_process(
        process_id=process_id,
        pid=pid,
        log_file=log_file,
        restart_callback=restart_callback,
        process_type="client",
    )

    # Start watchdog if not already running
    if not watchdog.is_running:
        watchdog.start()
