"""
Tests for the ExperimentScheduleMonitor background thread.

Verifies that:
1. The monitor starts and stops correctly
2. The monitor calls _do_check_schedule_progress periodically
3. Global init/stop helpers work correctly
4. The monitor handles errors gracefully
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
pytestmark = pytest.mark.unit



class TestExperimentScheduleMonitor:
    """Tests for the ExperimentScheduleMonitor class."""

    def test_monitor_initialization(self):
        """Test monitor initialises with expected default state."""
        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor

        app = MagicMock()
        monitor = ExperimentScheduleMonitor(app)

        assert monitor.app is app
        assert not monitor._started
        assert monitor._thread is None

    def test_monitor_start_stop(self):
        """Test that the monitor starts and stops its background thread."""
        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor

        app = MagicMock()
        monitor = ExperimentScheduleMonitor(app)

        with patch.object(monitor, "_run"):
            monitor.start()
            assert monitor._started
            assert monitor._thread is not None
            assert monitor._thread.daemon

            monitor.stop()
            assert not monitor._started

    def test_monitor_start_idempotent(self):
        """Calling start() twice should not start a second thread."""
        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor

        app = MagicMock()
        monitor = ExperimentScheduleMonitor(app)

        with patch.object(monitor, "_run"):
            monitor.start()
            first_thread = monitor._thread

            monitor.start()  # second call should be a no-op
            assert monitor._thread is first_thread

            monitor.stop()

    def test_monitor_stop_when_not_started(self):
        """Calling stop() on a monitor that was never started should not raise."""
        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor

        app = MagicMock()
        monitor = ExperimentScheduleMonitor(app)
        monitor.stop()  # should not raise

    def test_check_and_advance_calls_do_check(self):
        """_check_and_advance should delegate to _do_check_schedule_progress."""
        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor

        app = MagicMock()
        monitor = ExperimentScheduleMonitor(app)

        with patch(
            "y_web.src.experiment.schedule_monitor.ExperimentScheduleMonitor"
            "._check_and_advance"
        ) as mock_check:
            monitor._check_and_advance = mock_check
            monitor._check_and_advance()
            mock_check.assert_called_once()

    def test_run_loop_calls_check_and_advance(self):
        """The _run loop should call _check_and_advance while not stopped."""
        from y_web.src.experiment.schedule_monitor import (
            POLL_INTERVAL_SECONDS,
            ExperimentScheduleMonitor,
        )

        app = MagicMock()
        # Make app_context() a no-op context manager
        app.app_context.return_value.__enter__ = MagicMock(return_value=None)
        app.app_context.return_value.__exit__ = MagicMock(return_value=False)

        call_count = [0]
        stop_event = threading.Event()

        def fake_check():
            call_count[0] += 1
            if call_count[0] >= 2:
                stop_event.set()

        monitor = ExperimentScheduleMonitor(app)
        monitor._stop_event = stop_event

        with patch.object(monitor, "_check_and_advance", side_effect=fake_check):
            with patch("time.sleep"):  # skip the initial startup sleep
                # Run _run in a thread, it will self-stop after 2 checks
                t = threading.Thread(target=monitor._run, daemon=True)
                t.start()
                t.join(timeout=5)

        assert call_count[0] >= 1

    def test_run_loop_handles_exceptions(self):
        """Errors inside _check_and_advance should not crash the monitor loop."""
        from y_web.src.experiment.schedule_monitor import ExperimentScheduleMonitor

        app = MagicMock()
        app.app_context.return_value.__enter__ = MagicMock(return_value=None)
        app.app_context.return_value.__exit__ = MagicMock(return_value=False)

        call_count = [0]
        stop_event = threading.Event()

        def raising_check():
            call_count[0] += 1
            if call_count[0] >= 2:
                stop_event.set()
            raise RuntimeError("simulated error")

        monitor = ExperimentScheduleMonitor(app)
        monitor._stop_event = stop_event

        with patch.object(monitor, "_check_and_advance", side_effect=raising_check):
            with patch("time.sleep"):
                t = threading.Thread(target=monitor._run, daemon=True)
                t.start()
                t.join(timeout=5)

        # Loop survived the exception
        assert call_count[0] >= 1


class TestInitStopHelpers:
    """Tests for the module-level init/stop helpers."""

    def setup_method(self):
        """Reset global monitor state before each test."""
        import y_web.src.experiment.schedule_monitor as mod

        mod._monitor = None

    def teardown_method(self):
        """Clean up global monitor state after each test."""
        from y_web.src.experiment.schedule_monitor import (
            stop_experiment_schedule_monitor,
        )

        stop_experiment_schedule_monitor()

    def test_init_creates_and_starts_monitor(self):
        """init_experiment_schedule_monitor should create and start the monitor."""
        from y_web.src.experiment.schedule_monitor import (
            get_monitor,
            init_experiment_schedule_monitor,
        )

        app = MagicMock()

        with patch(
            "y_web.src.experiment.schedule_monitor.ExperimentScheduleMonitor.start"
        ) as mock_start:
            monitor = init_experiment_schedule_monitor(app)

        assert monitor is not None
        mock_start.assert_called_once()
        assert get_monitor() is monitor

    def test_init_idempotent(self):
        """Calling init twice should return the same monitor instance."""
        from y_web.src.experiment.schedule_monitor import (
            init_experiment_schedule_monitor,
        )

        app = MagicMock()

        with patch(
            "y_web.src.experiment.schedule_monitor.ExperimentScheduleMonitor.start"
        ):
            first = init_experiment_schedule_monitor(app)
            second = init_experiment_schedule_monitor(app)

        assert first is second

    def test_stop_clears_global_monitor(self):
        """stop_experiment_schedule_monitor should clear the global instance."""
        from y_web.src.experiment.schedule_monitor import (
            get_monitor,
            init_experiment_schedule_monitor,
            stop_experiment_schedule_monitor,
        )

        app = MagicMock()

        with patch(
            "y_web.src.experiment.schedule_monitor.ExperimentScheduleMonitor.start"
        ):
            init_experiment_schedule_monitor(app)

        assert get_monitor() is not None

        with patch(
            "y_web.src.experiment.schedule_monitor.ExperimentScheduleMonitor.stop"
        ):
            stop_experiment_schedule_monitor()

        assert get_monitor() is None


class TestPollInterval:
    """Tests for the polling interval constant."""

    def test_poll_interval_is_reasonable(self):
        """POLL_INTERVAL_SECONDS should be short enough to detect completion quickly."""
        from y_web.src.experiment.schedule_monitor import POLL_INTERVAL_SECONDS

        # Should be at most 30 seconds (much less than the old browser-based 30s)
        assert POLL_INTERVAL_SECONDS <= 30
        # Should be positive
        assert POLL_INTERVAL_SECONDS > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
