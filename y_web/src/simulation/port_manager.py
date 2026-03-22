"""
Port management and process-termination helpers for YSocial simulation.

Extracted from y_web/utils/external_processes.py.  All callers in that
module now import from here; the shim keeps the names available at the
legacy path.
"""

import os
import signal
import subprocess
import time

from flask import current_app

from y_web import db
from y_web.models import Exps
from y_web.src.system.path_utils import get_writable_path

# ---------------------------------------------------------------------------
# Server port range constants
# ---------------------------------------------------------------------------

SERVER_PORT_MIN = 5000
SERVER_PORT_MAX = 6000


# ---------------------------------------------------------------------------
# Low-level process termination helpers
# ---------------------------------------------------------------------------


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


# Public alias so submodules / shims can re-export without mangling
_terminate_process = __terminate_process


def _force_terminate_process_tree(pid):
    """
    Forcefully terminate a process and all its children.

    This is essential for hung gunicorn servers where the parent process
    and its workers may be unresponsive. We use psutil to find and kill
    all child processes, then kill the parent.

    Args:
        pid: the process ID to terminate
    """
    try:
        import psutil

        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            print(f"Process {pid} no longer exists.")
            return

        # Get all children before killing anything
        children = []
        try:
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            pass

        # Try graceful termination first (SIGTERM)
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass

        # Terminate children
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass

        # Wait briefly for graceful shutdown
        gone, alive = psutil.wait_procs([parent] + children, timeout=3)

        # Force kill any remaining processes
        for p in alive:
            try:
                print(f"Force killing process {p.pid}...")
                p.kill()
            except psutil.NoSuchProcess:
                pass

        # Final wait to ensure they're dead
        psutil.wait_procs(alive, timeout=2)

        print(f"Terminated process tree for PID {pid} ({len(children)} children).")

    except ImportError:
        # Fallback if psutil is not available
        print("psutil not available, using basic termination...")
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    except Exception as e:
        print(f"Error terminating process tree for {pid}: {e}")


# ---------------------------------------------------------------------------
# Port-level termination
# ---------------------------------------------------------------------------


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
            print(f"Process {pid} terminated.")
        else:
            print(f"No process found using port {port}.")
    except Exception as e:
        print(f"Error: {e}")
        pass


def _terminate_processes_on_port(port):
    """
    Terminate all processes using a specific port.

    This is a safety net to ensure the port is freed even if the main
    process termination didn't work properly (e.g., zombie workers).

    Args:
        port: the port number
    """
    import platform

    try:
        if platform.system() == "Windows":
            # Windows: use netstat to find PIDs
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pid = int(parts[-1])
                        print(f"Found process {pid} using port {port}, terminating...")
                        _force_terminate_process_tree(pid)
        else:
            # Unix: use lsof to find PIDs
            result = subprocess.run(
                ["lsof", "-t", "-i", f":{port}"],
                capture_output=True,
                text=True,
            )
            pids = result.stdout.strip().split("\n")
            for pid_str in pids:
                if pid_str:
                    pid = int(pid_str)
                    print(f"Found process {pid} using port {port}, terminating...")
                    _force_terminate_process_tree(pid)
    except Exception as e:
        print(f"Error terminating processes on port {port}: {e}")


# ---------------------------------------------------------------------------
# Database-file locking helpers
# ---------------------------------------------------------------------------


def _find_processes_with_open_file(file_path):
    """
    Find all processes that have a specific file open.

    This is OS-independent and uses psutil to check open files.
    Useful for finding processes that are holding database locks.

    Args:
        file_path: the path to the file to check

    Returns:
        list: list of psutil.Process objects that have the file open
    """
    try:
        import psutil
    except ImportError:
        print("Warning: psutil not available, cannot check for file locks")
        return []

    lockers = []
    # Normalize the file path for comparison
    try:
        normalized_path = os.path.realpath(file_path)
    except Exception:
        normalized_path = file_path

    for proc in psutil.process_iter(["pid", "open_files", "name"]):
        try:
            open_files = proc.info.get("open_files") or []
            for f in open_files:
                # Check both original path and normalized path
                if f.path == file_path or f.path == normalized_path:
                    lockers.append(proc)
                    break
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            # Skip processes we can't access
            pass
        except Exception:
            # Skip any other errors for individual processes
            pass

    return lockers


def _terminate_processes_holding_database(db_path):
    """
    Terminate all processes that have the database file open.

    This is essential for SQLite databases where processes may hold
    locks that persist even after the main process is terminated.
    Also works for finding processes with open connections to
    database files.

    Args:
        db_path: the path to the database file (e.g., database_server.db)
    """
    try:
        lockers = _find_processes_with_open_file(db_path)
        if lockers:
            print(f"Found {len(lockers)} process(es) holding database file: {db_path}")
            for proc in lockers:
                try:
                    print(
                        f"Terminating process {proc.pid} ({proc.name()}) "
                        f"holding database..."
                    )
                    # Try graceful termination first
                    proc.terminate()
                except Exception as e:
                    print(f"Error terminating process {proc.pid}: {e}")

            # Wait briefly for processes to terminate gracefully
            try:
                import psutil

                gone, alive = psutil.wait_procs(lockers, timeout=3)
                # Force kill any remaining processes
                for proc in alive:
                    try:
                        print(f"Force killing process {proc.pid}...")
                        proc.kill()
                    except Exception:
                        pass
            except Exception:
                pass

            print("Database file locking processes terminated.")
        else:
            print(f"No processes found holding database file: {db_path}")

    except Exception as e:
        print(f"Error checking/terminating database locking processes: {e}")


def _terminate_processes_holding_experiment_database(exp):
    """
    Terminate all processes that have the experiment's database file(s) open.

    This handles both SQLite (checks for open file handles) and PostgreSQL
    (checks for processes with database connections).

    Args:
        exp: the experiment object
    """
    try:
        # Get the main database URI to determine type
        db_uri_main = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    except RuntimeError:
        # No app context - try to import and get from environment
        db_uri_main = os.environ.get("DATABASE_URL", "sqlite")

    if "postgresql" in db_uri_main:
        # For PostgreSQL, we can't easily check open file handles
        # The database connections are network-based
        print(
            "PostgreSQL database detected - terminating processes "
            "will be handled by port/process termination"
        )
        return

    # For SQLite, find and terminate processes holding the database file
    # Get writable path for experiments directory
    writable_base = get_writable_path()
    y_web_dir = os.path.join(writable_base, "y_web")

    # Construct the full database path
    if "database_server.db" in exp.db_name:
        db_file_path = os.path.join(y_web_dir, exp.db_name)
    else:
        uid = exp.db_name.removeprefix("experiments_")
        db_file_path = os.path.join(y_web_dir, "experiments", uid, "database_server.db")

    if os.path.exists(db_file_path):
        print(f"Checking for processes holding database: {db_file_path}")
        _terminate_processes_holding_database(db_file_path)

        # Also check for SQLite journal/WAL files that might be locked
        for suffix in ["-journal", "-wal", "-shm"]:
            journal_path = db_file_path + suffix
            if os.path.exists(journal_path):
                _terminate_processes_holding_database(journal_path)
    else:
        print(f"Database file not found: {db_file_path}")


# ---------------------------------------------------------------------------
# Port availability checking
# ---------------------------------------------------------------------------


def _is_port_available(port):
    """
    Check if a port is available for binding.

    Args:
        port: the port number to check

    Returns:
        bool: True if the port is available, False otherwise
    """
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            # If connect_ex returns non-zero, the port is not in use
            return result != 0
    except Exception:
        # If we can't check, assume it's available
        return True


def _get_ports_allocated_to_experiments(exclude_exp_id=None):
    """
    Get all ports allocated to experiments in the database.

    This includes both active and inactive experiments to ensure
    no port conflicts when restarting servers.

    Args:
        exclude_exp_id: optional experiment ID to exclude from the list

    Returns:
        set: Set of port numbers allocated to experiments
    """
    try:
        query = db.session.query(Exps.port).filter(Exps.port.isnot(None))
        if exclude_exp_id is not None:
            query = query.filter(Exps.idexp != exclude_exp_id)
        result = query.all()
        return {row[0] for row in result if row[0] is not None}
    except Exception as e:
        print(f"Warning: Could not query allocated ports: {e}")
        return set()


def _find_new_available_port(
    exclude_exp_id=None, exclude_current_port=None, min_port=None, max_port=None
):
    """
    Find a new available port that is:
    1. Not currently in use (socket check)
    2. Not allocated to any other experiment in the database
    3. Not the same as the current experiment's port (to force a fresh port)

    This is the robust version used for server starts to ensure
    complete port isolation between experiments.

    Args:
        exclude_exp_id: experiment ID to exclude when checking allocated ports
        exclude_current_port: the current port of this experiment to exclude
                             (ensures we always get a NEW port)
        min_port: minimum port number (default: SERVER_PORT_MIN)
        max_port: maximum port number (default: SERVER_PORT_MAX)

    Returns:
        int: an available port number, or None if none found
    """
    # Set defaults
    if min_port is None:
        min_port = SERVER_PORT_MIN
    if max_port is None:
        max_port = SERVER_PORT_MAX

    # Get all ports allocated to other experiments
    allocated_ports = _get_ports_allocated_to_experiments(exclude_exp_id)

    # Also exclude the current experiment's port to ensure we get a fresh port
    if exclude_current_port is not None:
        allocated_ports.add(exclude_current_port)

    print(f"Ports to avoid: {sorted(allocated_ports) if allocated_ports else 'none'}")

    # Search entire allowed range for a port that is:
    # 1. Not in use by a running process
    # 2. Not allocated to another experiment
    # 3. Not the current experiment's port
    for port in range(min_port, max_port + 1):
        if port not in allocated_ports and _is_port_available(port):
            return port

    return None


def _find_available_port(original_port, port_range=100, min_port=None, max_port=None):
    """
    Find an available port near the original port.

    NOTE: This is the legacy function. For server starts, use
    _find_new_available_port() which also checks database allocations.

    Searches for a free port starting from original_port, then tries
    ports in the specified range. For servers, use min_port=5000, max_port=6000.

    Args:
        original_port: the preferred port number
        port_range: the range of ports to search (default 100)
        min_port: minimum port number (default: 1024)
        max_port: maximum port number (default: 65535)

    Returns:
        int: an available port number, or None if none found
    """
    # Set defaults
    if min_port is None:
        min_port = 1024
    if max_port is None:
        max_port = 65535

    # First try the original port
    if _is_port_available(original_port):
        return original_port

    # Search in range around original port, respecting min/max bounds
    half_range = port_range // 2
    start_port = max(min_port, original_port - half_range)
    end_port = min(max_port, original_port + half_range)

    for port in range(start_port, end_port + 1):
        if port != original_port and _is_port_available(port):
            return port

    # If not found in preferred range, search entire allowed range
    for port in range(min_port, max_port + 1):
        if port != original_port and _is_port_available(port):
            return port

    return None
