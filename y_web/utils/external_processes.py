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
import random
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from multiprocessing import Process
from pathlib import Path

import numpy as np
import requests
from flask import current_app
from ollama import Client as oclient
from requests import post
from sklearn.utils import deprecated

from y_web import db
from y_web.models import (
    ActivityProfile,
    Client,
    Client_Execution,
    Exps,
    Ollama_Pull,
    PopulationActivityProfile,
)

# Dictionary to track Ollama model download processes
ollama_processes = {}


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
                    print(f"Process {exp.server_pid} still running, sending SIGKILL")
                    os.kill(exp.server_pid, signal.SIGKILL)
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
                    print(f"Process {client.pid} still running, sending SIGKILL")
                    os.kill(client.pid, signal.SIGKILL)
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

    # --- Case 1: Conda / Miniconda ---
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        conda_prefix = Path(conda_prefix).resolve()
        env_name = os.environ.get("CONDA_DEFAULT_ENV") or conda_prefix.name
        env_bin = conda_prefix / "bin"

        # Detect conda base (handle .../envs/<env_name>)
        if conda_prefix.parent.name == "envs":
            conda_base = conda_prefix.parent.parent
        else:
            conda_base = conda_prefix

        conda_sh = conda_base / "etc" / "profile.d" / "conda.sh"
        python_bin = env_bin / "python"

        if conda_sh.exists():
            # Safe approach: just use the environment's Python binary
            return str(python_bin)

    # --- Case 2: Pipenv ---
    if os.environ.get("PIPENV_ACTIVE"):
        return "pipenv run python"

    # --- Case 3: Virtualenv / venv ---
    venv_prefix = os.environ.get("VIRTUAL_ENV")
    if venv_prefix:
        python_bin = Path(venv_prefix) / "bin" / "python"
        return str(python_bin)

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
    script_path_quoted = f'"{script_path}"'
    config_path_quoted = f'"{config_path}"' if config_path else ""

    run_cmd = f"{python_cmd} {script_path_quoted}"
    if config_path_quoted:
        run_cmd += f" -c {config_path_quoted}"

    # Single bash -c block inside screen
    screen_cmd = f"screen -dmS {screen_name} bash -c '{run_cmd}'"
    return screen_cmd


#############


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
            os.kill(int(pid), 9)  # Send SIGKILL to the process
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
                os.kill(pid, signal.SIGKILL)
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

    # Determine the server directory and script path based on platform type
    if exp.platform_type == "microblogging":
        server_dir = f"{yserver_path}external{os.sep}YServer"
        script_path = f"{yserver_path}external{os.sep}YServer{os.sep}y_server_run.py"
    elif exp.platform_type == "forum":
        server_dir = f"{yserver_path}external{os.sep}YServerReddit"
        script_path = (
            f"{yserver_path}external{os.sep}YServerReddit{os.sep}y_server_run.py"
        )
    else:
        raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

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
        if (
            isinstance(python_cmd, str)
            and " " in python_cmd
            and not python_cmd.startswith("/")
        ):
            # Handle commands like "pipenv run python"
            cmd_parts = python_cmd.split()
            # Replace 'python' with 'gunicorn' in pipenv run scenarios
            if cmd_parts[-1] == "python":
                cmd_parts[-1] = "gunicorn"
            cmd = cmd_parts + gunicorn_args
        else:
            # Try to find gunicorn in the same directory as python
            gunicorn_path = Path(python_cmd).parent / "gunicorn"
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

        try:
            # Start the process with Popen
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process group
                env=env,  # Pass environment with config path
            )
            print(f"Server process started with PID: {process.pid}")
        except Exception as e:
            # Fallback: try to use gunicorn from system path
            print(f"Error starting server process: {e}")
            gunicorn_which = shutil.which("gunicorn")
            fallback_cmd = [gunicorn_which or "gunicorn"] + gunicorn_args
            process = subprocess.Popen(
                fallback_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process group
                env=env,
            )
    else:
        # Use standard Python execution for SQLite
        print(f"Starting server for experiment {exp_uid} with Python (SQLite)...")

        # Build the command as a list for subprocess.Popen
        if (
            isinstance(python_cmd, str)
            and " " in python_cmd
            and not python_cmd.startswith("/")
        ):
            # Handle commands like "pipenv run python"
            cmd_parts = python_cmd.split()
            cmd = cmd_parts + [script_path, "-c", config]
        else:
            # Simple python executable path
            cmd = [python_cmd, script_path, "-c", config]

        try:
            # Start the process with Popen
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process group
            )
            print(f"Server process started with PID: {process.pid}")
        except Exception as e:
            # Fallback: try to use the current Python implicitly
            print(f"Error starting server process: {e}")
            cmd = [sys.executable, script_path, "-c", config]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process group
            )

    print(f"Command: {' '.join(cmd)}")
    print(f"Config file: {config}")

    # Save the PID to the database for persistent tracking
    exp.server_pid = process.pid
    db.session.commit()

    # Identify the database URI to be set
    db_type = "sqlite"
    if db_uri_main.startswith("postgresql"):
        db_type = "postgresql"

    if db_type == "sqlite":
        db_uri = f"{BASE_DIR[1:]}{exp.db_name}"
    elif db_type == "postgresql":
        old_db_name = db_uri_main.split("/")[-1]
        db_uri = db_uri_main.replace(old_db_name, exp.db_name)

    print(f"Database URI: {db_uri}")

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

        # Now call change_db endpoint with retry logic
        # data = {"path": f"{db_uri}"}
        # headers = {"Content-Type": "application/json"}
        # ns = f"http://{exp.server}:{exp.port}/change_db"
        # time.sleep(20)
        # response = post(f"{ns}", headers=headers, data=json.dumps(data), timeout=30)
        # if response.status_code == 200:
        #    print("Database configuration successful")
        # else:
        #    print(f"Database configuration returned status {response.status_code}: {response.text}")

    else:
        # For standard Python (SQLite), use simple wait and single call
        time.sleep(20)
        data = {"path": f"{db_uri}"}
        headers = {"Content-Type": "application/json"}
        ns = f"http://{exp.server}:{exp.port}/change_db"
        try:
            post(f"{ns}", headers=headers, data=json.dumps(data))
            print("Database configuration successful")
        except Exception as e:
            print(f"Warning: Could not configure database: {e}")

    return process


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
        db_uri = f"{BASE_DIR[1:]}{exp.db_name}"  # change this to the postgres URI
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
            print("Ollama is running.")
            return True
        else:
            print(
                f"Ollama responded but not running correctly. Status: {response.status_code}"
            )
            return False
    except requests.ConnectionError:
        print("Ollama is not running or cannot be reached.")
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


def terminate_client(cli, pause=False):
    """Stop the y_client using PID from database

    Args:
        cli: the client object
    """
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
            os.kill(pid, signal.SIGKILL)
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

    # update client execution object
    # if not pause:
    #    ce = Client_Execution.query.filter_by(client_id=cli.id).first()
    #    ce.expected_duration_rounds = 0
    #    ce.elapsed_time = 0
    #    db.session.commit()


def start_client(exp, cli, population, resume=True):
    """Handle start client operation."""
    process = Process(
        target=start_client_process,
        args=(
            exp,
            cli,
            population,
            resume,
        ),
    )
    process.start()

    # Store PID in database
    cli.pid = process.pid
    db.session.commit()
    print(f"Client process started with PID: {process.pid}")


def start_client_process(exp, cli, population, resume=True):
    """
    Initialize and start client simulation process.

    Args:
        exp: Experiment object
        cli: Client configuration object
        population: Population object
        resume: Boolean indicating if resuming (default: False)
    """
    import json
    import os
    import sys

    from y_web import create_app, db
    from y_web.models import Client_Execution

    app = create_app()  # create app instance for this subprocess

    with app.app_context():
        yclient_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]

        if exp.platform_type == "microblogging":
            sys.path.append(f"{yclient_path}{os.sep}external{os.sep}YClient/")
            from y_client.clients import YClientWeb
        elif exp.platform_type == "forum":
            sys.path.append(f"{yclient_path}{os.sep}external{os.sep}YClientReddit/")
            from y_client.clients import YClientWeb
        else:
            raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

        # get experiment base path
        BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]

        # postgres
        if "experiments_" in exp.db_name:
            uid = exp.db_name.removeprefix("experiments_")
            filename = f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}{population.name.replace(' ', '')}.json".replace(
                "utils/", ""
            )  #
        else:
            uid = exp.db_name.split(os.sep)[1]
            filename = f"{BASE_DIR}{os.sep}{exp.db_name.split('database_server.db')[0]}{population.name.replace(' ', '')}.json".replace(
                "utils/", ""
            )  # .replace(' ', '')

        data_base_path = f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}"
        config_file = json.load(
            open(f"{data_base_path}client_{cli.name}-{population.name}.json")
        )

        print("Starting client process...")

        # DB query requires app context
        ce = Client_Execution.query.filter_by(client_id=cli.id).first()
        print(f"Client {cli.name} execution record: {ce}")
        if ce:
            first_run = False
        else:
            print(f"Client {cli.name} first execution.")
            first_run = True
            ce = Client_Execution(
                client_id=cli.id,
                elapsed_time=0,
                expected_duration_rounds=cli.days * 24,
                last_active_hour=-1,
                last_active_day=-1,
            )
            db.session.add(ce)
            db.session.commit()

        log_file = f"{data_base_path}{cli.name}_client.log"
        if first_run and cli.network_type:
            path = f"{cli.name}_network.csv"

            cl = YClientWeb(
                config_file,
                data_base_path,
                first_run=first_run,
                network=path,
                log_file=log_file,
                llm=exp.llm_agents_enabled,
            )
        else:
            cl = YClientWeb(
                config_file,
                data_base_path,
                first_run=first_run,
                log_file=log_file,
                llm=exp.llm_agents_enabled,
            )

        if resume:
            cl.days = int((ce.expected_duration_rounds - ce.elapsed_time) / 24)

        cl.read_agents()
        cl.add_feeds()

        if first_run and cli.network_type:
            cl.add_network()

        if not os.path.exists(filename):
            cl.save_agents(filename)

        run_simulation(cl, cli.id, filename, exp, population)


def get_users_per_hour(population, agents):
    # get population activity profiles
    activity_profiles = defaultdict(list)
    population_activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population.id)
        .all()
    )
    for ap in population_activity_profiles:
        profile = (
            db.session.query(ActivityProfile)
            .filter(ActivityProfile.id == ap.activity_profile)
            .first()
        )
        activity_profiles[profile.name] = [int(x) for x in profile.hours.split(",")]

    hours_to_users = defaultdict(list)
    for ag in agents:
        profile = activity_profiles[ag.activity_profile]

        for h in profile:
            hours_to_users[h].append(ag)

    return hours_to_users


def sample_agents(agents, expected_active_users):
    weights = [a.daily_activity_level for a in agents]
    # normalize weights to sum to 1
    weights = [w / sum(weights) for w in weights]

    try:
        sagents = np.random.choice(
            agents,
            size=expected_active_users,
            p=weights,
            replace=False,
        )
    except Exception as e:
        sagents = np.random.choice(agents, size=expected_active_users, replace=False)

    return sagents


def run_simulation(cl, cli_id, agent_file, exp, population):
    """
    Run the simulation
    """
    platform_type = exp.platform_type

    total_days = int(cl.days)
    daily_slots = int(cl.slots)

    page_agents = [p for p in cl.agents.agents if p.is_page]

    hour_to_page = get_users_per_hour(population, page_agents)

    for d1 in range(total_days):
        common_agents = [p for p in cl.agents.agents if not p.is_page]
        hour_to_users = get_users_per_hour(population, common_agents)

        daily_active = {}
        tid, _, _ = cl.sim_clock.get_current_slot()

        for _ in range(daily_slots):
            tid, d, h = cl.sim_clock.get_current_slot()

            # get expected active users for this time slot considering the global population (at least 1)
            expected_active_users = max(
                int(len(cl.agents.agents) * cl.hourly_activity[str(h)]), 1
            )

            # take the minimum between expected active over the whole population and available users at time h
            expected_active_users = min(expected_active_users, len(hour_to_users[h]))

            # get active pages at this hour
            active_pages = hour_to_page[h]

            if platform_type == "microblogging":
                # pages post all the time their activity profile is active
                for page in active_pages:
                    page.select_action(
                        tid=tid,
                        actions=[],
                        max_length_thread_reading=cl.max_length_thread_reading,
                    )

                # check whether there are agents left
            if len(cl.agents.agents) == 0:
                break

            # get the daily activities of each agent
            try:
                sagents = sample_agents(hour_to_users[h], expected_active_users)
            except Exception as e:
                # case of no active agents at this hour
                sagents = []

            # shuffle agents
            random.shuffle(sagents)

            ################# PARALLELIZED SECTION #################
            # def agent_task(g, tid):
            for g in sagents:
                acts = [a for a, v in cl.actions_likelihood.items() if v > 0]

                daily_active[g.name] = None

                # Get a random integer within g.round_actions.
                # If g.is_page == 1, then rounds = 0 (the page does not perform actions)
                if g.is_page == 1:
                    rounds = 0
                else:
                    rounds = random.randint(1, int(g.round_actions))

                for _ in range(rounds):
                    # sample two elements from a list with replacement

                    candidates = random.choices(
                        acts,
                        k=2,
                        weights=[cl.actions_likelihood[a] for a in acts],
                    )
                    candidates.append("NONE")

                    try:
                        # reply to received mentions
                        if g not in cl.pages:
                            g.reply(tid=tid)

                        # select action to be performed
                        g.select_action(
                            tid=tid,
                            actions=candidates,
                            max_length_thread_reading=cl.max_length_thread_reading,
                        )
                    except Exception as e:
                        print(f"Error ({g.name}): {e}")
                        print(traceback.format_exc())
                        pass

            # Run agent tasks in parallel
            # with concurrent.futures.ThreadPoolExecutor() as executor:
            #    executor.map(agent_task, sagents)
            ################# END OF PARALLELIZATION #################

            # increment slot
            cl.sim_clock.increment_slot()

            # update client execution object
            ce = Client_Execution.query.filter_by(client_id=cli_id).first()
            if ce:
                ce.elapsed_time += 1
                ce.last_active_hour = h
                ce.last_active_day = d
                db.session.add(ce)  # Explicitly mark as modified for PostgreSQL
                db.session.commit()

        # evaluate follows (once per day, only for a random sample of daily active agents)
        if float(cl.config["agents"]["probability_of_daily_follow"]) > 0:
            da = [
                agent
                for agent in cl.agents.agents
                if agent.name in daily_active
                and agent not in cl.pages
                and random.random()
                < float(cl.config["agents"]["probability_of_daily_follow"])
            ]

            # Evaluating new friendship ties
            for agent in da:
                if agent not in cl.pages:
                    agent.select_action(tid=tid, actions=["FOLLOW", "NONE"])

        # daily churn and new agents
        if len(daily_active) > 0:
            # daily churn
            cl.churn(tid)

            # daily new agents
            if cl.percentage_new_agents_iteration > 0:
                for _ in range(
                    max(
                        1,
                        int(len(daily_active) * cl.percentage_new_agents_iteration),
                    )
                ):
                    cl.add_agent()

        # saving "living" agents at the end of the day
        cl.save_agents(agent_file)
