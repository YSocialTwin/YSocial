"""
Tests for process watchdog functionality.

Tests the ProcessWatchdog class and its integration with process management.
"""

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestProcessWatchdog:
    """Tests for the ProcessWatchdog class."""

    def test_watchdog_initialization(self):
        """Test watchdog initializes with correct default values."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()

        assert watchdog._check_interval == 60
        assert watchdog._heartbeat_timeout == 300
        assert watchdog._max_restart_attempts == 3
        assert watchdog._restart_cooldown == 60
        assert not watchdog.is_running

    def test_watchdog_custom_initialization(self):
        """Test watchdog initializes with custom values."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog(
            check_interval=30,
            heartbeat_timeout=120,
            max_restart_attempts=5,
            restart_cooldown=30,
        )

        assert watchdog._check_interval == 30
        assert watchdog._heartbeat_timeout == 120
        assert watchdog._max_restart_attempts == 5
        assert watchdog._restart_cooldown == 30

    def test_register_process(self):
        """Test registering a process for monitoring."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()
        restart_callback = MagicMock(return_value=12345)

        watchdog.register_process(
            process_id="test_process_1",
            pid=1234,
            log_file="/tmp/test.log",
            restart_callback=restart_callback,
            process_type="server",
        )

        assert "test_process_1" in watchdog._processes
        process_info = watchdog._processes["test_process_1"]
        assert process_info.pid == 1234
        assert process_info.log_file == "/tmp/test.log"
        assert process_info.process_type == "server"
        assert process_info.restart_count == 0

    def test_unregister_process(self):
        """Test unregistering a process from monitoring."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()
        restart_callback = MagicMock()

        watchdog.register_process(
            process_id="test_process_1",
            pid=1234,
            log_file="/tmp/test.log",
            restart_callback=restart_callback,
            process_type="server",
        )

        assert "test_process_1" in watchdog._processes

        watchdog.unregister_process("test_process_1")

        assert "test_process_1" not in watchdog._processes

    def test_update_pid(self):
        """Test updating the PID of a registered process."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()
        restart_callback = MagicMock()

        watchdog.register_process(
            process_id="test_process_1",
            pid=1234,
            log_file="/tmp/test.log",
            restart_callback=restart_callback,
            process_type="server",
        )

        watchdog.update_pid("test_process_1", 5678)

        assert watchdog._processes["test_process_1"].pid == 5678

    def test_start_stop_watchdog(self):
        """Test starting and stopping the watchdog thread."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        # Use short check interval for faster test
        watchdog = ProcessWatchdog(check_interval=1)

        assert not watchdog.is_running

        watchdog.start()
        assert watchdog.is_running
        assert watchdog._thread is not None
        assert watchdog._thread.is_alive()

        watchdog.stop()
        assert not watchdog.is_running

    def test_get_status_empty(self):
        """Test getting status with no registered processes."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()
        status = watchdog.get_status()

        assert status == {}

    def test_get_status_with_processes(self):
        """Test getting status with registered processes."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()
        restart_callback = MagicMock()

        watchdog.register_process(
            process_id="server_1",
            pid=1234,
            log_file="/tmp/server.log",
            restart_callback=restart_callback,
            process_type="server",
        )

        status = watchdog.get_status()

        assert "server_1" in status
        assert status["server_1"]["pid"] == 1234
        assert status["server_1"]["process_type"] == "server"
        assert status["server_1"]["log_file"] == "/tmp/server.log"
        assert status["server_1"]["restart_count"] == 0

    def test_is_process_running_with_valid_pid(self):
        """Test checking if a process is running with the current process."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()

        # Current process should be running
        current_pid = os.getpid()
        assert watchdog._is_process_running(current_pid)

    def test_is_process_running_with_invalid_pid(self):
        """Test checking if a process is running with an invalid PID."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()

        # Very high PID should not exist
        assert not watchdog._is_process_running(999999999)

    def test_is_process_running_with_none(self):
        """Test checking if a process is running with None PID."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()

        assert not watchdog._is_process_running(None)

    def test_get_log_mtime_existing_file(self):
        """Test getting modification time of an existing file."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            mtime = watchdog._get_log_mtime(temp_path)
            assert mtime is not None
            assert isinstance(mtime, datetime)
        finally:
            os.unlink(temp_path)

    def test_get_log_mtime_nonexistent_file(self):
        """Test getting modification time of a nonexistent file."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog()

        mtime = watchdog._get_log_mtime("/nonexistent/path/to/file.log")
        assert mtime is None

    def test_heartbeat_detection_via_log_mtime(self):
        """Test that log file modification is used as heartbeat."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog(heartbeat_timeout=5)
        restart_callback = MagicMock(return_value=9999)

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("initial log entry\n")
            temp_path = f.name

        try:
            watchdog.register_process(
                process_id="test_process",
                pid=os.getpid(),  # Use current process so it's "running"
                log_file=temp_path,
                restart_callback=restart_callback,
                process_type="server",
            )

            # Check process - should be healthy (running and recent log)
            process_info = watchdog._processes["test_process"]
            watchdog._check_process(process_info)

            # Restart should not have been called
            restart_callback.assert_not_called()

        finally:
            os.unlink(temp_path)

    def test_restart_on_dead_process(self):
        """Test that restart is called when process is dead."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog(restart_cooldown=0)
        new_pid = 54321
        restart_callback = MagicMock(return_value=new_pid)

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("log entry\n")
            temp_path = f.name

        try:
            # Register with non-existent PID (simulating dead process)
            watchdog.register_process(
                process_id="dead_process",
                pid=999999999,  # Non-existent PID
                log_file=temp_path,
                restart_callback=restart_callback,
                process_type="server",
            )

            # Check process - should trigger restart
            process_info = watchdog._processes["dead_process"]
            watchdog._check_process(process_info)

            # Restart callback should have been called
            restart_callback.assert_called_once()

            # Process info should be updated with new PID
            assert process_info.pid == new_pid
            assert process_info.restart_count == 1

        finally:
            os.unlink(temp_path)

    def test_max_restart_attempts(self):
        """Test that restart stops after max attempts."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog(max_restart_attempts=2, restart_cooldown=0)
        restart_callback = MagicMock(return_value=None)  # Always fails

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("log entry\n")
            temp_path = f.name

        try:
            watchdog.register_process(
                process_id="failing_process",
                pid=999999999,
                log_file=temp_path,
                restart_callback=restart_callback,
                process_type="server",
            )

            process_info = watchdog._processes["failing_process"]

            # First restart attempt
            watchdog._check_process(process_info)
            assert restart_callback.call_count == 1
            assert process_info.restart_count == 1

            # Second restart attempt
            watchdog._check_process(process_info)
            assert restart_callback.call_count == 2
            assert process_info.restart_count == 2

            # Third attempt should be skipped (max attempts reached)
            watchdog._check_process(process_info)
            assert restart_callback.call_count == 2  # Not called again

        finally:
            os.unlink(temp_path)

    def test_restart_cooldown(self):
        """Test that restart respects cooldown period."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog(restart_cooldown=60)  # 60 second cooldown
        restart_callback = MagicMock(return_value=12345)

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("log entry\n")
            temp_path = f.name

        try:
            watchdog.register_process(
                process_id="cooldown_process",
                pid=999999999,
                log_file=temp_path,
                restart_callback=restart_callback,
                process_type="server",
            )

            process_info = watchdog._processes["cooldown_process"]

            # First restart
            watchdog._check_process(process_info)
            assert restart_callback.call_count == 1

            # Immediate second check - should skip due to cooldown
            process_info.pid = 999999999  # Reset to dead PID
            watchdog._check_process(process_info)
            assert restart_callback.call_count == 1  # Not called again

        finally:
            os.unlink(temp_path)

    def test_servers_checked_before_clients(self):
        """Test that servers are checked and restarted before clients."""
        from y_web.utils.process_watchdog import ProcessWatchdog

        watchdog = ProcessWatchdog(restart_cooldown=0)
        check_order = []

        def make_callback(process_id):
            def callback():
                check_order.append(process_id)
                return 12345

            return callback

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("log entry\n")
            temp_path = f.name

        try:
            # Register in mixed order: client, server, client, server
            watchdog.register_process(
                process_id="client_1",
                pid=999999999,
                log_file=temp_path,
                restart_callback=make_callback("client_1"),
                process_type="client",
            )
            watchdog.register_process(
                process_id="server_1",
                pid=999999999,
                log_file=temp_path,
                restart_callback=make_callback("server_1"),
                process_type="server",
            )
            watchdog.register_process(
                process_id="client_2",
                pid=999999999,
                log_file=temp_path,
                restart_callback=make_callback("client_2"),
                process_type="client",
            )
            watchdog.register_process(
                process_id="server_2",
                pid=999999999,
                log_file=temp_path,
                restart_callback=make_callback("server_2"),
                process_type="server",
            )

            # Check all processes
            watchdog._check_all_processes()

            # Servers should be restarted before clients
            assert len(check_order) == 4
            # First two should be servers
            assert check_order[0] in ["server_1", "server_2"]
            assert check_order[1] in ["server_1", "server_2"]
            # Last two should be clients
            assert check_order[2] in ["client_1", "client_2"]
            assert check_order[3] in ["client_1", "client_2"]

        finally:
            os.unlink(temp_path)


class TestGlobalWatchdog:
    """Tests for global watchdog functions."""

    def test_get_watchdog_singleton(self):
        """Test that get_watchdog returns the same instance."""
        from y_web.utils.process_watchdog import get_watchdog, stop_watchdog

        # Clean up any existing watchdog
        stop_watchdog()

        watchdog1 = get_watchdog()
        watchdog2 = get_watchdog()

        assert watchdog1 is watchdog2

        # Cleanup
        stop_watchdog()

    def test_stop_watchdog(self):
        """Test stopping the global watchdog."""
        from y_web.utils.process_watchdog import (
            _watchdog,
            get_watchdog,
            stop_watchdog,
        )

        # Clean up any existing watchdog first
        stop_watchdog()

        watchdog = get_watchdog()
        watchdog.start()

        assert watchdog.is_running

        stop_watchdog()

        # After stop, getting watchdog should return None initially
        # but get_watchdog creates a new one
        import y_web.utils.process_watchdog as pw

        assert pw._watchdog is None


class TestProcessInfo:
    """Tests for ProcessInfo class."""

    def test_process_info_creation(self):
        """Test creating ProcessInfo objects."""
        from y_web.utils.process_watchdog import ProcessInfo

        now = datetime.now()
        callback = MagicMock()

        info = ProcessInfo(
            process_id="test_1",
            pid=1234,
            log_file="/tmp/test.log",
            restart_callback=callback,
            process_type="server",
            registered_at=now,
            last_heartbeat=now,
            restart_count=0,
            last_restart_at=None,
        )

        assert info.process_id == "test_1"
        assert info.pid == 1234
        assert info.log_file == "/tmp/test.log"
        assert info.process_type == "server"
        assert info.restart_count == 0
        assert info.last_restart_at is None
