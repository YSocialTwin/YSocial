"""
Client process management for YSocial simulation.

Extracted from y_web/utils/external_processes.py.  The shim keeps all names
available at the legacy path.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from flask import current_app

from y_web import db
from y_web.src.models import (
    Client,
    Client_Execution,
    Exps,
    Population,
)
from y_web.src.simulation.port_manager import _force_terminate_process_tree
from y_web.src.simulation.process_registry import (
    WATCHDOG_ENABLED,
    _register_process,
    _unregister_process,
)
from y_web.src.simulation.subprocess_env import build_subprocess_env
from y_web.src.simulation.server import detect_env_handler
from y_web.src.system.path_utils import get_resource_path, get_writable_path


def _is_client_process(pid):
    """
    Validate that the given PID is actually a client process.

    Args:
        pid: Process ID to validate

    Returns:
        bool: True if the process is a client process, False otherwise
    """
    try:
        import psutil

        proc = psutil.Process(pid)
        cmdline = proc.cmdline()
        cmdline_str = " ".join(cmdline).lower()

        is_client = (
            "y_client_process_runner" in cmdline_str
            or "--run-client-subprocess" in cmdline_str
            or "_client.log" in cmdline_str
        )

        if not is_client:
            print(
                f"Warning: PID {pid} is not a client process. "
                f"Command: {cmdline_str[:100]}..."
            )

        return is_client

    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        print(f"Warning: Cannot access process {pid} info, assuming it's valid")
        return True
    except Exception as e:
        print(f"Warning: Error checking process {pid}: {e}")
        return False


from y_web.src.hpc.client import (  # noqa: E402,F401
    start_hpc_client,
    stop_hpc_client,
)
from y_web.src.hpc.server import (  # noqa: E402,F401
    start_hpc_server,
    start_server_screen,
    stop_hpc_server,
)

##############
# Ollama Functions — delegated to y_web.src.llm.ollama_manager
##############
# fmt: off
from y_web.src.llm.ollama_manager import (  # noqa: E402,F401
    delete_model_pull,
    delete_ollama_model,
    get_ollama_models,
    is_ollama_installed,
    is_ollama_running,
    ollama_processes,
    pull_ollama_model,
    start_ollama_pull,
    start_ollama_server,
)

#############
# vLLM Functions — delegated to y_web.src.llm.vllm_manager
#############
from y_web.src.llm.vllm_manager import (  # noqa: E402,F401
    get_llm_models,
    get_vllm_models,
    is_vllm_installed,
    is_vllm_running,
    start_vllm_server,
)

# Server management — delegated to y_web.src.simulation.server
# fmt: off
from y_web.src.simulation.server import (  # noqa: E402,F401
    _register_server_with_watchdog,
    _update_server_port_in_configs,
    get_server_process_status,
    start_server,
)

# fmt: on


# fmt: on


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
            from y_web.src.simulation.watchdog import get_watchdog

            watchdog = get_watchdog()
            watchdog.unregister_process(f"client_{cli.id}")
        except Exception as e:
            print(f"Warning: Could not unregister client from watchdog: {e}")

    # Unregister from process registry (closes log file handles)
    _unregister_process(f"client_{cli.id}")

    if not cli.pid:
        print(f"No PID found for client {cli.name}")
        return

    try:
        pid = cli.pid
        print(f"Terminating client process with PID {pid}...")

        # Validate that this PID is actually a client process
        # This prevents terminating wrong processes if PIDs have been recycled
        if not _is_client_process(pid):
            print(
                f"Warning: PID {pid} is not a client process (may have been recycled). "
                f"Skipping termination and clearing stale PID from database."
            )
            cli.pid = None
            db.session.commit()
            return

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
            os.path.join("y_web", "src", "simulation", "client_runner.py")
        )

        # Validate that runner script exists
        if not Path(runner_script).exists():
            raise FileNotFoundError(
                f"Client runner script not found: {runner_script}\n"
                f"Please ensure client_runner.py exists in y_web/src/simulation."
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
    from y_web.src.system.path_utils import get_writable_path

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
    env = build_subprocess_env(
        {
            "YCLIENT_LOG_FILE": str(log_dir / f"{cli.name}_client.log"),
            # Mark this as a client subprocess so the atexit handler doesn't run cleanup
            # This prevents the subprocess from killing all other experiments when it exits
            "Y_CLIENT_SUBPROCESS": "1",
        }
    )

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

    # Register process to prevent garbage collection and keep log file handles open
    _register_process(f"client_{cli.id}", process, out_file, err_file)

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
    from y_web.src.simulation.watchdog import get_watchdog

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
                    # Check if client has naturally completed its expected duration
                    client_exec = (
                        db.session.query(Client_Execution)
                        .filter_by(client_id=cli_id)
                        .first()
                    )
                    if client_exec:
                        if (
                            client_exec.expected_duration_rounds > 0
                            and client_exec.elapsed_time
                            >= client_exec.expected_duration_rounds
                        ):
                            # Client has completed - terminate properly instead of restarting
                            print(
                                f"Watchdog: Client {fresh_cli.name} has completed "
                                f"(elapsed: {client_exec.elapsed_time}, "
                                f"expected: {client_exec.expected_duration_rounds}). "
                                f"Terminating instead of restarting."
                            )
                            # Use standard terminate_client to properly update all DB statuses
                            # First, unregister from watchdog
                            try:
                                watchdog = get_watchdog()
                                watchdog.unregister_process(f"client_{cli_id}")
                            except Exception:
                                pass

                            # Update client status to stopped
                            fresh_cli.status = 0
                            fresh_cli.pid = None
                            db.session.commit()

                            # Return None to indicate no restart
                            return None

                    # Terminate any existing process using robust termination
                    # This ensures proper cleanup of hung processes
                    if fresh_cli.pid:
                        pid_to_kill = fresh_cli.pid
                        # Validate that this PID is actually a client process
                        # to prevent terminating wrong processes if PIDs were recycled
                        if _is_client_process(pid_to_kill):
                            print(
                                f"Watchdog: Terminating client process with PID {pid_to_kill}..."
                            )
                            _force_terminate_process_tree(pid_to_kill)
                        else:
                            print(
                                f"Watchdog: PID {pid_to_kill} is not a client process "
                                f"(may have been recycled). Skipping termination."
                            )

                        # Clear PID from database for consistency
                        fresh_cli.pid = None
                        db.session.commit()

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
