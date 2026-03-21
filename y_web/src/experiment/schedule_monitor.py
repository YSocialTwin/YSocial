"""
Background monitor for experiment schedule advancement.

Automatically advances the experiment schedule to the next group
when the current group's experiments complete, without requiring
the browser to remain open and active.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

# Global monitor instance
_monitor = None
_monitor_lock = threading.Lock()

# How often (in seconds) to check whether the current group has finished
POLL_INTERVAL_SECONDS = 10

# Timeout (in seconds) to wait for the monitor thread to stop
_THREAD_STOP_TIMEOUT_SECONDS = 10


class ExperimentScheduleMonitor:
    """
    Background monitor that advances experiment schedule groups automatically.

    Runs in a daemon thread and periodically calls the schedule-progress
    check logic so that the next group starts as soon as the previous one
    completes, regardless of whether the admin browser tab is open.
    """

    def __init__(self, app):
        """
        Initialize the monitor.

        Args:
            app: Flask application instance
        """
        self.app = app
        self._stop_event = threading.Event()
        self._thread = None
        self._started = False

    def start(self):
        """Start the background monitor thread."""
        if self._started:
            logger.warning("Experiment schedule monitor already started")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started = True
        logger.info("Experiment schedule monitor started")

    def stop(self):
        """Stop the background monitor thread."""
        if not self._started:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=_THREAD_STOP_TIMEOUT_SECONDS)
        self._started = False
        logger.info("Experiment schedule monitor stopped")

    def _run(self):
        """Background monitoring loop."""
        # Wait for the application to fully start before first check
        time.sleep(5)

        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self._check_and_advance()
            except Exception as e:
                logger.error(
                    f"Error in experiment schedule monitor: {e}", exc_info=True
                )
            self._stop_event.wait(POLL_INTERVAL_SECONDS)

    def _check_and_advance(self):
        """Check schedule progress and advance to next group if current is done."""
        from y_web.routes.admin.sub.experiments import _do_check_schedule_progress

        _do_check_schedule_progress()


def get_monitor():
    """Get the global monitor instance."""
    return _monitor


def init_experiment_schedule_monitor(app):
    """
    Initialize and start the experiment schedule monitor.

    Should be called once during application startup.

    Args:
        app: Flask application instance
    """
    global _monitor

    with _monitor_lock:
        if _monitor is not None:
            logger.warning("Experiment schedule monitor already initialized")
            return _monitor

        _monitor = ExperimentScheduleMonitor(app)
        _monitor.start()
        return _monitor


def stop_experiment_schedule_monitor():
    """Stop the global experiment schedule monitor."""
    global _monitor

    with _monitor_lock:
        if _monitor is not None:
            _monitor.stop()
            _monitor = None
