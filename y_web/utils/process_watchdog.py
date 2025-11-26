"""
Process watchdog for monitoring and restarting hung/dead processes.

This module provides a lightweight watchdog that monitors server and client
processes using log file modifications as heartbeat indicators. When a process
appears hung (no log activity) or dead, it can be automatically restarted.
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

import psutil

logger = logging.getLogger(__name__)


class ProcessWatchdog:
    """
    A lightweight watchdog that monitors processes using log files as heartbeats.

    The watchdog periodically checks:
    1. If the process is still running (using PID)
    2. If the log file has been modified recently (heartbeat check)

    If a process is detected as hung or dead, it calls a restart callback.
    """

    def __init__(
        self,
        check_interval: int = 60,
        heartbeat_timeout: int = 300,
        max_restart_attempts: int = 3,
        restart_cooldown: int = 60,
    ):
        """
        Initialize the watchdog.

        Args:
            check_interval: How often to check processes (in seconds)
            heartbeat_timeout: Max time without log activity before considering hung (seconds)
            max_restart_attempts: Maximum restart attempts before giving up
            restart_cooldown: Minimum time between restart attempts (seconds)
        """
        self._check_interval = check_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._max_restart_attempts = max_restart_attempts
        self._restart_cooldown = restart_cooldown

        # Tracked processes: {process_id: ProcessInfo}
        self._processes: Dict[str, "ProcessInfo"] = {}
        self._lock = threading.RLock()

        # Watchdog thread
        self._running = False
        self._thread: Optional[threading.Thread] = None

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

    def start(self) -> None:
        """Start the watchdog monitoring thread."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logger.info("Watchdog: Started monitoring")

    def stop(self) -> None:
        """Stop the watchdog monitoring thread."""
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=self._check_interval + 5)
                self._thread = None
            logger.info("Watchdog: Stopped monitoring")

    def _monitor_loop(self) -> None:
        """Main monitoring loop running in background thread."""
        while self._running:
            try:
                self._check_all_processes()
            except Exception as e:
                logger.error(f"Watchdog: Error in monitor loop: {e}")

            # Sleep in small increments to allow faster shutdown
            for _ in range(self._check_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _check_all_processes(self) -> None:
        """Check all registered processes."""
        with self._lock:
            process_ids = list(self._processes.keys())

        for process_id in process_ids:
            with self._lock:
                if process_id not in self._processes:
                    continue
                process_info = self._processes[process_id]

            self._check_process(process_info)

    def _check_process(self, process_info: "ProcessInfo") -> None:
        """
        Check a single process and restart if needed.

        Args:
            process_info: Information about the process to check
        """
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

        if needs_restart:
            self._handle_restart(process_info, reason)

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

    def _handle_restart(self, process_info: "ProcessInfo", reason: str) -> None:
        """
        Handle restarting a process.

        Args:
            process_info: Information about the process to restart
            reason: Reason for restart
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
                return

        # Check max restart attempts
        if process_info.restart_count >= self._max_restart_attempts:
            logger.warning(
                f"Watchdog: Max restart attempts ({self._max_restart_attempts}) "
                f"reached for {process_info.process_id}, giving up"
            )
            return

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
            else:
                logger.error(
                    f"Watchdog: Failed to restart {process_info.process_id} "
                    f"(callback returned None)"
                )
                with self._lock:
                    process_info.restart_count += 1
                    process_info.last_restart_at = now

        except Exception as e:
            logger.error(f"Watchdog: Error restarting {process_info.process_id}: {e}")
            with self._lock:
                process_info.restart_count += 1
                process_info.last_restart_at = now

    def get_status(self) -> Dict:
        """
        Get the current status of all monitored processes.

        Returns:
            Dictionary with status information for each process
        """
        with self._lock:
            status = {}
            for process_id, info in self._processes.items():
                is_running = self._is_process_running(info.pid)
                last_modified = self._get_log_mtime(info.log_file)

                status[process_id] = {
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
            return status

    @property
    def is_running(self) -> bool:
        """Check if the watchdog is running."""
        return self._running


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
    check_interval: int = 60,
    heartbeat_timeout: int = 300,
    max_restart_attempts: int = 3,
    restart_cooldown: int = 60,
) -> ProcessWatchdog:
    """
    Get or create the global watchdog instance.

    Args:
        check_interval: How often to check processes (in seconds)
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
                check_interval=check_interval,
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
