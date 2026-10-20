"""
Process registry and lifecycle management for YSocial simulation processes.
"""

import os
import signal
import subprocess
import time

from y_web import db
from y_web.src.models import Client, Exps

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


def terminate_process_trees(pids, grace=6.0):
    """Terminate several processes *and all their descendants*, in parallel.

    Simulators spawn helpers (Ray raylet/GCS/workers, gunicorn workers, ...) that
    must not outlive them. The trees are collected first (a child is reparented the
    moment its parent dies), everything gets SIGTERM at once, and whatever is still
    alive after ``grace`` seconds in total is killed. Total time is bounded by
    ``grace`` + ~2 s however many processes there are.

    Returns the set of PIDs that were found alive and are now gone.
    """
    pids = {int(p) for p in pids if p}
    pids.discard(os.getpid())
    if not pids:
        return set()
    try:
        import psutil
    except ImportError:  # no tree support: best effort on the listed PIDs
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        time.sleep(min(grace, 2.0))
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except (OSError, AttributeError):
                pass
        return set(pids)

    me = os.getpid()
    procs = {}
    for pid in pids:
        try:
            root = psutil.Process(pid)
            for proc in [root] + root.children(recursive=True):
                if proc.pid != me:
                    procs[proc.pid] = proc
        except psutil.NoSuchProcess:
            continue
        except Exception as e:
            print(f"Cannot inspect process {pid}: {e}")
    if not procs:
        return set()

    def _signal(proc, kill=False):
        try:
            proc.kill() if kill else proc.terminate()
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            print(f"Cannot signal process {proc.pid}: {e}")

    for proc in procs.values():
        _signal(proc)
    _, alive = psutil.wait_procs(list(procs.values()), timeout=grace)
    for proc in alive:
        print(f"Process {proc.pid} did not stop in {grace:g}s, killing it")
        _signal(proc, kill=True)
    if alive:
        psutil.wait_procs(alive, timeout=2)
    return set(procs)


def _tracked_pids():
    """PIDs of simulator servers and clients recorded in the database."""
    pids = {}
    try:
        for exp in db.session.query(Exps).filter(Exps.server_pid.isnot(None)).all():
            pids[int(exp.server_pid)] = f"server of experiment {exp.idexp}"
        for client in db.session.query(Client).filter(Client.pid.isnot(None)).all():
            pids[int(client.pid)] = f"client {client.id}"
    except Exception as e:
        print(f"Error reading tracked processes: {e}")
    return pids


def _registered_pids():
    """PIDs of processes started by this app instance (in-memory registry)."""
    pids = set()
    for entry in list(_process_registry.values()):
        proc = entry.get("process")
        try:
            if proc is not None and proc.poll() is None:
                pids.add(proc.pid)
        except Exception:
            pass
    return pids


def cleanup_server_processes_from_db():
    """Terminate the server process trees recorded in the database.

    Useful on shutdown and on start-up, when processes of a previous session may
    still be running. The PID of each experiment is cleared afterwards.
    """
    try:
        exps = db.session.query(Exps).filter(Exps.server_pid.isnot(None)).all()
        for exp in exps:
            print(
                f"Terminating server process PID {exp.server_pid} for experiment {exp.idexp}"
            )
        terminate_process_trees([exp.server_pid for exp in exps])
        for exp in exps:
            exp.server_pid = None
        db.session.commit()
    except Exception as e:
        print(f"Error during server process cleanup: {e}")


def cleanup_client_processes_from_db():
    """Terminate the client process trees recorded in the database."""
    try:
        clients = db.session.query(Client).filter(Client.pid.isnot(None)).all()
        for client in clients:
            print(f"Terminating client process PID {client.pid} for client {client.id}")
        terminate_process_trees([client.pid for client in clients])
        for client in clients:
            client.pid = None
        db.session.commit()
    except Exception as e:
        print(f"Error during client process cleanup: {e}")


def stop_all_exps():
    """Stop all experiments and terminate server and client processes"""
    try:
        # Stop watchdog first to prevent auto-restarts during shutdown
        if WATCHDOG_ENABLED:
            try:
                from y_web.src.simulation.watchdog import stop_watchdog

                stop_watchdog()
            except Exception as e:
                print(f"Warning: Could not stop watchdog: {e}")

        # Terminate servers and clients together (whole process trees, in
        # parallel) so shutdown time does not grow with the number of simulators.
        tracked = _tracked_pids()
        for pid, what in tracked.items():
            print(f"Terminating {what} (PID {pid})")
        terminate_process_trees(set(tracked) | _registered_pids())

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

        # Executions interrupted by the shutdown get a terminal state too
        try:
            from y_web.src.models import Client_Execution

            db.session.query(Client_Execution).filter(
                Client_Execution.terminal_state == "running"
            ).update({Client_Execution.terminal_state: "manual_stop"})
        except Exception as e:
            print(f"Could not update client executions: {e}")

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
