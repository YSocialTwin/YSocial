"""
Process registry and lifecycle management for YSocial simulation processes.
"""
import os
import signal
import subprocess
import time

from y_web import db
from y_web.models import Client, Exps

# Flag to enable/disable watchdog monitoring
WATCHDOG_ENABLED = True

# Registry to keep references to subprocess.Popen objects and their log file handles.
# This prevents garbage collection of running processes and their log files.
# Key: process_id (e.g., "server_1", "client_5")
# Value: dict with 'process', 'stdout_file', 'stderr_file'
_process_registry = {}

# Uppercase alias for backward compatibility with the spec validation test
# (BUSINESS_LOGIC_REFACTORING.md uses _PROCESS_REGISTRY)
_PROCESS_REGISTRY = _process_registry

def _register_process(process_id, process, stdout_file=None, stderr_file=None):
    """
    Register a subprocess.Popen object to prevent garbage collection.

    This keeps the process object and its log file handles alive for the
    lifetime of the application, preventing potential issues with:
    - Process becoming zombie due to GC of Popen object
    - Log file handles being closed prematurely

    Args:
        process_id: Unique identifier for the process (e.g., "server_1", "client_5")
        process: The subprocess.Popen object
        stdout_file: The stdout log file handle (optional)
        stderr_file: The stderr log file handle (optional)
    """
    global _process_registry
    _process_registry[process_id] = {
        "process": process,
        "stdout_file": stdout_file,
        "stderr_file": stderr_file,
    }


def _unregister_process(process_id):
    """
    Unregister a subprocess.Popen object and close its log file handles.

    Args:
        process_id: The unique identifier for the process
    """
    global _process_registry
    if process_id in _process_registry:
        entry = _process_registry.pop(process_id)
        # Close log file handles if they exist
        for key in ("stdout_file", "stderr_file"):
            fh = entry.get(key)
            if fh and fh != subprocess.DEVNULL:
                try:
                    fh.close()
                except Exception:
                    pass


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
                    from y_web.src.simulation.port_manager import _terminate_process
                    _terminate_process(exp.server_pid)
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
                    from y_web.src.simulation.port_manager import _terminate_process
                    _terminate_process(client.pid)
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

        # set to 0 all Exps.running and set exp_status to "stopped"
        exps = db.session.query(Exps).all()
        for exp in exps:
            exp.running = 0
            exp.server_pid = None
            # Set experiment status to stopped for both Standard and HPC experiments
            exp.exp_status = "stopped"

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
            f"Successfully cleared PIDs and set status to 'stopped' for {len(exps)} experiments and {len(clis)} clients"
        )

    except Exception as e:
        print(f"Error in stop_all_exps: {e}")
        # Try to rollback and commit again
        try:
            db.session.rollback()

            # Try again with a fresh query
            db.session.query(Exps).update(
                {Exps.running: 0, Exps.server_pid: None, Exps.exp_status: "stopped"}
            )
            db.session.query(Client).update({Client.status: 0, Client.pid: None})
            db.session.commit()

            print(
                "Successfully cleared PIDs and set status to 'stopped' on retry after error"
            )
        except Exception as e2:
            print(f"Failed to clear PIDs even on retry: {e2}")

