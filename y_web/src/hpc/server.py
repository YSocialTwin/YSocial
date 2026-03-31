"""
HPC server process management.

Provides functions for starting and stopping HPC server processes,
extracted from y_web.utils.external_processes.
"""

import json
import os
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
from y_web.src.models import Exps
from y_web.src.simulation.subprocess_env import build_subprocess_env
from y_web.src.system.path_utils import get_base_path, get_writable_path


def start_hpc_server(exp):
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
    # Import helpers from external_processes to avoid duplication.
    # These imports work because external_processes defines them before delegating here.
    from y_web.src.simulation.server import detect_env_handler

    # Get base path - this will be bundle location when frozen, repo root otherwise
    base_path = get_base_path()
    yserver_path = base_path
    sys.path.append(os.path.join(yserver_path, "external", "YSimulator"))

    # Get writable path for experiments directory
    writable_base = get_writable_path()
    # Define y_web directory path (replaces old BASE_DIR)
    y_web_dir = os.path.join(writable_base, "y_web")

    if "database_server.db" in exp.db_name:
        # Extract experiment uid from db_name path
        # db_name format: "experiments/uid/database_server.db"
        config = os.path.join(y_web_dir, exp.db_name.split("database_server.db")[0])
        exp_uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")
        exp_uid = f"{uid}{os.sep}"
        config = os.path.join(y_web_dir, "experiments", uid)

    # Determine the server directory and script path based on platform type
    if exp.platform_type == "microblogging":
        server_dir = os.path.join(yserver_path, "external", "YServer")
        script_path = os.path.join(
            yserver_path, "external", "YSimulator", "run_server.py"
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
            f"Please ensure YServer is cloned under external/YServer.\n"
            f"You can install or update it from the Admin > Plugins panel."
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

    # Set up environment (always needed, gunicorn branch adds extra vars)
    env = build_subprocess_env()

    if use_gunicorn:
        # Use gunicorn for PostgreSQL
        print(f"Starting server for experiment {exp_uid} with gunicorn (PostgreSQL)...")

        # Build the gunicorn command with explicit parameters
        gunicorn_config_path = f"{server_dir}{os.sep}gunicorn_config.py"

        gunicorn_args = [
            "--config",
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
                "--config",
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
        env["YSERVER_CONFIG"] = config

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
            print(f"Server process started with PID: {process.pid}")
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
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                    env=env,
                )
            else:
                process = subprocess.Popen(
                    fallback_cmd,
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
                "--config",
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
            cmd = cmd_parts + [script_path, "--config", config]
        else:
            # Simple python executable path (may contain spaces on Windows)
            cmd = [python_cmd, script_path, "--config", config]

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
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                    env=env,
                )
            else:
                # On Unix, use start_new_session for proper detachment
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
            print(f"Server process started with PID: {process.pid}")
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
    return process


def stop_hpc_server(exp_id):
    """
    Terminate an HPC server process using the PID stored in the database.

    This function terminates an HPC server process that was started using the
    start_hpc_server() function and has its PID stored in the database.
    It handles graceful shutdown using SIGTERM, followed by SIGKILL if needed.
    It clears the PID from the database after termination and removes the
    ray_config.log file if present.

    Args:
        exp_id: the experiment ID whose HPC server process should be terminated

    Returns:
        bool: True if process was found and terminated, False otherwise
    """
    # Import here to avoid circular import issues.
    from y_web.src.simulation.port_manager import (
        __terminate_process as _terminate_process,
    )

    try:
        # Get experiment from database
        exp = db.session.query(Exps).filter_by(idexp=exp_id).first()
        if not exp or not exp.server_pid:
            print(f"No tracked HPC server process found for experiment {exp_id}")
            return False

        pid = exp.server_pid
        print(f"Terminating HPC server process with PID {pid}...")

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
                    print(f"HPC server process {pid} terminated gracefully.")
                    break
            else:
                # If we get here, process is still running after timeout
                print(
                    f"HPC server process {pid} did not terminate gracefully, forcing kill..."
                )
                _terminate_process(pid)
                time.sleep(0.5)
                print(f"HPC server process {pid} killed.")

        except OSError as e:
            # Process doesn't exist
            print(f"HPC server process {pid} no longer exists: {e}")

        # Get experiment folder path to clean up ray_config.log
        writable_base = get_writable_path()
        y_web_dir = os.path.join(writable_base, "y_web")

        if "database_server.db" in exp.db_name:
            # db_name format: "experiments/uid/database_server.db"
            exp_folder = os.path.join(
                y_web_dir, exp.db_name.split("database_server.db")[0]
            )
        else:
            uid = exp.db_name.removeprefix("experiments_")
            exp_folder = os.path.join(y_web_dir, "experiments", uid)

        # Delete ray_config.log if present
        ray_config_log = os.path.join(exp_folder, "ray_config.log")
        if os.path.exists(ray_config_log):
            try:
                os.remove(ray_config_log)
                print(f"Removed ray_config.log from {exp_folder}")
            except Exception as e:
                print(f"Warning: Could not remove ray_config.log: {e}")

        # Clear PID from database
        exp.server_pid = None
        db.session.commit()
        return True

    except Exception as e:
        print(f"Error terminating HPC server process: {e}")
        return False


@deprecated
def start_server_screen(exp):
    """
    Start the y_server in a detached screen (DEPRECATED).

    This function is deprecated in favor of start_server() which uses subprocess.Popen.
    It is kept for backward compatibility but should not be used in new code.

    Args:
        exp: the experiment object
    """
    from y_web.src.simulation.server import build_screen_command

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
