"""
Process watchdog for monitoring and restarting hung/dead processes.

This module provides a lightweight watchdog that monitors server and client
processes using log file modifications as heartbeat indicators. When a process
appears hung (no log activity) or dead, it can be automatically restarted.

The watchdog runs periodically (default every 15 minutes), performs its check,
restarts any hung/dead processes, and terminates until the next scheduled run.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

import psutil

logger = logging.getLogger(__name__)

# Default watchdog settings
DEFAULT_RUN_INTERVAL_MINUTES = 15
DEFAULT_HEARTBEAT_TIMEOUT = 300  # seconds
DEFAULT_MAX_RESTART_ATTEMPTS = 3
DEFAULT_RESTART_COOLDOWN = 60  # seconds


class ProcessWatchdog:
    """
    A lightweight watchdog that monitors processes using log files as heartbeats.

    The watchdog periodically checks:
    1. If the process is still running (using PID)
    2. If the log file has been modified recently (heartbeat check)

    If a process is detected as hung or dead, it calls a restart callback.

    The watchdog runs on a schedule (default every 15 minutes), performs its
    check/restart cycle, and terminates until the next scheduled run.
    """

    def __init__(
        self,
        run_interval_minutes: int = DEFAULT_RUN_INTERVAL_MINUTES,
        heartbeat_timeout: int = DEFAULT_HEARTBEAT_TIMEOUT,
        max_restart_attempts: int = DEFAULT_MAX_RESTART_ATTEMPTS,
        restart_cooldown: int = DEFAULT_RESTART_COOLDOWN,
    ):
        """
        Initialize the watchdog.

        Args:
            run_interval_minutes: How often to run the watchdog check (in minutes)
            heartbeat_timeout: Max time without log activity before considering hung (seconds)
            max_restart_attempts: Maximum restart attempts before giving up
            restart_cooldown: Minimum time between restart attempts (seconds)
        """
        self._run_interval_minutes = run_interval_minutes
        self._heartbeat_timeout = heartbeat_timeout
        self._max_restart_attempts = max_restart_attempts
        self._restart_cooldown = restart_cooldown

        # Tracked processes: {process_id: ProcessInfo}
        self._processes: Dict[str, "ProcessInfo"] = {}
        self._lock = threading.RLock()

        # Scheduler thread
        self._scheduler_running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._last_run: Optional[datetime] = None
        self._next_run: Optional[datetime] = None

    @property
    def run_interval_minutes(self) -> int:
        """Get the current run interval in minutes."""
        return self._run_interval_minutes

    @run_interval_minutes.setter
    def run_interval_minutes(self, value: int) -> None:
        """Set the run interval in minutes."""
        if value < 1:
            value = 1
        self._run_interval_minutes = value
        # Update next run time
        if self._last_run:
            self._next_run = self._last_run + timedelta(minutes=value)

    def register_process(
        self,
        process_id: str,
        pid: int,
        log_file: str,
        restart_callback: Callable[[], Optional[int]],
        process_type: str = "unknown",
    ) -> None:
        """
        Register a process for monitoring.

        Args:
            process_id: Unique identifier for the process (e.g., "server_1" or "client_5")
            pid: Process ID
            log_file: Path to the log file used as heartbeat indicator
            restart_callback: Callback function to restart the process, returns new PID
            process_type: Type of process ("server" or "client")
        """
        with self._lock:
            self._processes[process_id] = ProcessInfo(
                process_id=process_id,
                pid=pid,
                log_file=log_file,
                restart_callback=restart_callback,
                process_type=process_type,
                registered_at=datetime.now(),
                last_heartbeat=datetime.now(),
                restart_count=0,
                last_restart_at=None,
            )
            logger.info(
                f"Watchdog: Registered {process_type} process {process_id} (PID: {pid})"
            )

    def unregister_process(self, process_id: str) -> None:
        """
        Unregister a process from monitoring.

        Args:
            process_id: Unique identifier for the process
        """
        with self._lock:
            if process_id in self._processes:
                del self._processes[process_id]
                logger.info(f"Watchdog: Unregistered process {process_id}")

    def update_pid(self, process_id: str, new_pid: int) -> None:
        """
        Update the PID for a tracked process.

        Args:
            process_id: Unique identifier for the process
            new_pid: New process ID
        """
        with self._lock:
            if process_id in self._processes:
                self._processes[process_id].pid = new_pid
                self._processes[process_id].last_heartbeat = datetime.now()

    def start_scheduler(self) -> None:
        """Start the watchdog scheduler that runs periodically."""
        with self._lock:
            if self._scheduler_running:
                return

            self._scheduler_running = True
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop, daemon=True
            )
            self._scheduler_thread.start()
            logger.info(
                f"Watchdog: Started scheduler (runs every {self._run_interval_minutes} minutes)"
            )

    def stop_scheduler(self) -> None:
        """Stop the watchdog scheduler."""
        with self._lock:
            self._scheduler_running = False
            if self._scheduler_thread:
                self._scheduler_thread.join(timeout=10)
                self._scheduler_thread = None
            logger.info("Watchdog: Stopped scheduler")

    # Backward compatibility aliases
    def start(self) -> None:
        """Start the watchdog scheduler (alias for start_scheduler)."""
        self.start_scheduler()

    def stop(self) -> None:
        """Stop the watchdog scheduler (alias for stop_scheduler)."""
        self.stop_scheduler()

    def _scheduler_loop(self) -> None:
        """Scheduler loop that triggers watchdog runs at the configured interval."""
        while self._scheduler_running:
            now = datetime.now()

            # Determine if it's time to run
            should_run = False
            if self._next_run is None:
                # First run - schedule for interval from now
                self._next_run = now + timedelta(minutes=self._run_interval_minutes)
            elif now >= self._next_run:
                should_run = True

            if should_run:
                try:
                    self.run_once()
                except Exception as e:
                    logger.error(f"Watchdog: Error in scheduled run: {e}")

                self._last_run = datetime.now()
                self._next_run = self._last_run + timedelta(
                    minutes=self._run_interval_minutes
                )

            # Sleep for a short time to allow checking for shutdown
            for _ in range(10):  # Check every second for 10 seconds
                if not self._scheduler_running:
                    break
                time.sleep(1)

    def run_once(self) -> Dict:
        """
        Run the watchdog check once and return results.

        This method checks all registered processes, restarts any that are
        hung or dead, and returns a summary of the results.

        Returns:
            Dictionary with results of the watchdog run
        """
        logger.info("Watchdog: Running process check...")
        results = {
            "run_time": datetime.now().isoformat(),
            "processes_checked": 0,
            "processes_restarted": 0,
            "processes_healthy": 0,
            "details": [],
        }

        try:
            self._check_all_processes(results)
        except Exception as e:
            logger.error(f"Watchdog: Error during check: {e}")
            results["error"] = str(e)

        logger.info(
            f"Watchdog: Check complete - {results['processes_checked']} checked, "
            f"{results['processes_restarted']} restarted, "
            f"{results['processes_healthy']} healthy"
        )

        return results

    def _check_all_processes(self, results: Dict) -> None:
        """Check all registered processes.

        Servers are checked and restarted before clients to ensure proper
        dependency order - if all clients attached to a server hung, the
        issue is likely in the server, so restart the server first.
        """
        with self._lock:
            # Separate processes by type and sort: servers first, then clients
            server_ids = [
                pid
                for pid, info in self._processes.items()
                if info.process_type == "server"
            ]
            client_ids = [
                pid
                for pid, info in self._processes.items()
                if info.process_type == "client"
            ]
            # Process servers first, then clients
            process_ids = server_ids + client_ids

        for process_id in process_ids:
            with self._lock:
                if process_id not in self._processes:
                    continue
                process_info = self._processes[process_id]

            self._check_process(process_info, results)

    def _check_process(self, process_info: "ProcessInfo", results: Dict) -> None:
        """
        Check a single process and restart if needed.

        Args:
            process_info: Information about the process to check
            results: Results dictionary to update
        """
        results["processes_checked"] += 1
        pid = process_info.pid
        log_file = process_info.log_file

        # Check if process is running
        is_running = self._is_process_running(pid)

        # Check log file heartbeat
        last_modified = self._get_log_mtime(log_file)

        if last_modified:
            process_info.last_heartbeat = last_modified

        now = datetime.now()
        time_since_heartbeat = now - process_info.last_heartbeat

        # Determine if process needs restart
        needs_restart = False
        reason = ""

        if not is_running:
            needs_restart = True
            reason = "process not running"
        elif (
            time_since_heartbeat.total_seconds() > self._heartbeat_timeout
            and last_modified is not None
        ):
            # Only consider hung if we've seen the log file before
            needs_restart = True
            reason = f"no heartbeat for {time_since_heartbeat.total_seconds():.0f}s"

        process_detail = {
            "process_id": process_info.process_id,
            "process_type": process_info.process_type,
            "pid": pid,
            "is_running": is_running,
            "needs_restart": needs_restart,
            "reason": reason,
            "restarted": False,
        }

        if needs_restart:
            restarted = self._handle_restart(process_info, reason)
            process_detail["restarted"] = restarted
            if restarted:
                results["processes_restarted"] += 1
                process_detail["new_pid"] = process_info.pid
        else:
            results["processes_healthy"] += 1

        results["details"].append(process_detail)

    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        if pid is None:
            return False

        try:
            proc = psutil.Process(pid)
            status = proc.status()
            # Consider zombie processes as not running
            return status != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _get_log_mtime(self, log_file: str) -> Optional[datetime]:
        """
        Get the last modification time of a log file.

        Args:
            log_file: Path to the log file

        Returns:
            Last modification time, or None if file doesn't exist
        """
        try:
            if os.path.exists(log_file):
                mtime = os.path.getmtime(log_file)
                return datetime.fromtimestamp(mtime)
        except OSError:
            pass
        return None

    def _handle_restart(self, process_info: "ProcessInfo", reason: str) -> bool:
        """
        Handle restarting a process.

        Args:
            process_info: Information about the process to restart
            reason: Reason for restart

        Returns:
            True if restart was successful, False otherwise
        """
        now = datetime.now()

        # Check cooldown
        if process_info.last_restart_at:
            time_since_restart = (now - process_info.last_restart_at).total_seconds()
            if time_since_restart < self._restart_cooldown:
                logger.debug(
                    f"Watchdog: Skipping restart for {process_info.process_id}, "
                    f"cooldown not elapsed ({time_since_restart:.0f}s < {self._restart_cooldown}s)"
                )
                return False

        # Check max restart attempts
        if process_info.restart_count >= self._max_restart_attempts:
            logger.warning(
                f"Watchdog: Max restart attempts ({self._max_restart_attempts}) "
                f"reached for {process_info.process_id}, giving up"
            )
            return False

        logger.warning(
            f"Watchdog: Restarting {process_info.process_type} "
            f"{process_info.process_id} (reason: {reason})"
        )

        try:
            # Call the restart callback
            new_pid = process_info.restart_callback()

            if new_pid:
                with self._lock:
                    process_info.pid = new_pid
                    process_info.restart_count += 1
                    process_info.last_restart_at = now
                    process_info.last_heartbeat = now

                logger.info(
                    f"Watchdog: Successfully restarted {process_info.process_id} "
                    f"(new PID: {new_pid}, attempt {process_info.restart_count})"
                )
                return True
            else:
                logger.error(
                    f"Watchdog: Failed to restart {process_info.process_id} "
                    f"(callback returned None)"
                )
                with self._lock:
                    process_info.restart_count += 1
                    process_info.last_restart_at = now
                return False

        except Exception as e:
            logger.error(f"Watchdog: Error restarting {process_info.process_id}: {e}")
            with self._lock:
                process_info.restart_count += 1
                process_info.last_restart_at = now
            return False

    def get_status(self) -> Dict:
        """
        Get the current status of all monitored processes and watchdog.

        Returns:
            Dictionary with status information
        """
        with self._lock:
            processes = {}
            for process_id, info in self._processes.items():
                is_running = self._is_process_running(info.pid)
                last_modified = self._get_log_mtime(info.log_file)

                processes[process_id] = {
                    "pid": info.pid,
                    "process_type": info.process_type,
                    "is_running": is_running,
                    "log_file": info.log_file,
                    "last_heartbeat": (
                        info.last_heartbeat.isoformat() if info.last_heartbeat else None
                    ),
                    "log_last_modified": (
                        last_modified.isoformat() if last_modified else None
                    ),
                    "restart_count": info.restart_count,
                    "last_restart_at": (
                        info.last_restart_at.isoformat()
                        if info.last_restart_at
                        else None
                    ),
                }

            return {
                "scheduler_running": self._scheduler_running,
                "run_interval_minutes": self._run_interval_minutes,
                "last_run": self._last_run.isoformat() if self._last_run else None,
                "next_run": self._next_run.isoformat() if self._next_run else None,
                "heartbeat_timeout": self._heartbeat_timeout,
                "max_restart_attempts": self._max_restart_attempts,
                "restart_cooldown": self._restart_cooldown,
                "processes": processes,
            }

    @property
    def is_running(self) -> bool:
        """Check if the watchdog scheduler is running."""
        return self._scheduler_running


class ProcessInfo:
    """Information about a monitored process."""

    def __init__(
        self,
        process_id: str,
        pid: int,
        log_file: str,
        restart_callback: Callable[[], Optional[int]],
        process_type: str,
        registered_at: datetime,
        last_heartbeat: datetime,
        restart_count: int,
        last_restart_at: Optional[datetime],
    ):
        self.process_id = process_id
        self.pid = pid
        self.log_file = log_file
        self.restart_callback = restart_callback
        self.process_type = process_type
        self.registered_at = registered_at
        self.last_heartbeat = last_heartbeat
        self.restart_count = restart_count
        self.last_restart_at = last_restart_at


# Global watchdog instance
_watchdog: Optional[ProcessWatchdog] = None
_watchdog_lock = threading.Lock()


def get_watchdog(
    run_interval_minutes: int = DEFAULT_RUN_INTERVAL_MINUTES,
    heartbeat_timeout: int = DEFAULT_HEARTBEAT_TIMEOUT,
    max_restart_attempts: int = DEFAULT_MAX_RESTART_ATTEMPTS,
    restart_cooldown: int = DEFAULT_RESTART_COOLDOWN,
) -> ProcessWatchdog:
    """
    Get or create the global watchdog instance.

    Args:
        run_interval_minutes: How often to run the watchdog check (in minutes)
        heartbeat_timeout: Max time without log activity before considering hung (seconds)
        max_restart_attempts: Maximum restart attempts before giving up
        restart_cooldown: Minimum time between restart attempts (seconds)

    Returns:
        The global ProcessWatchdog instance
    """
    global _watchdog

    with _watchdog_lock:
        if _watchdog is None:
            _watchdog = ProcessWatchdog(
                run_interval_minutes=run_interval_minutes,
                heartbeat_timeout=heartbeat_timeout,
                max_restart_attempts=max_restart_attempts,
                restart_cooldown=restart_cooldown,
            )
        return _watchdog


def stop_watchdog() -> None:
    """Stop and clear the global watchdog instance."""
    global _watchdog

    with _watchdog_lock:
        if _watchdog is not None:
            _watchdog.stop()
            _watchdog = None


def run_watchdog_once() -> Dict:
    """
    Run the watchdog check once immediately.

    Returns:
        Dictionary with results of the watchdog run
    """
    watchdog = get_watchdog()
    return watchdog.run_once()


def set_watchdog_interval(minutes: int) -> None:
    """
    Set the watchdog run interval.

    Args:
        minutes: Interval in minutes between watchdog runs
    """
    watchdog = get_watchdog()
    watchdog.run_interval_minutes = minutes


def get_watchdog_status() -> Dict:
    """
    Get the current watchdog status.

    Returns:
        Dictionary with watchdog status information
    """
    watchdog = get_watchdog()
    return watchdog.get_status()
