"""Background monitor of the World Simulation queue (F5.5), modelled on the experiment schedule monitor.

It starts the next queued World Simulation when the previous one ends, ends the entry of a simulation that completed or
failed, and checks the health of every running simulation (coordinator alive, members finished). After a restart of YWeb
the queue simply continues from the state kept in the database."""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_monitor = None
_monitor_lock = threading.Lock()

POLL_INTERVAL_SECONDS = 10
_THREAD_STOP_TIMEOUT_SECONDS = 10


class FederationScheduleMonitor:
    def __init__(
        self,
        app,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        first_delay: float = 5.0,
    ):
        self.app = app
        self.poll_interval = poll_interval
        self.first_delay = first_delay
        self._stop_event = threading.Event()
        self._thread = None
        self._started = False

    def start(self):
        if self._started:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="world-simulation-monitor"
        )
        self._thread.start()
        self._started = True
        logger.info("World Simulation schedule monitor started")

    def stop(self):
        if not self._started:
            return
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=_THREAD_STOP_TIMEOUT_SECONDS)
        self._started = False

    def _run(self):
        time.sleep(self.first_delay)  # let the application finish starting
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self.poll()
            except Exception as exc:
                logger.error(
                    "Error in the World Simulation schedule monitor: %s",
                    exc,
                    exc_info=True,
                )
            self._stop_event.wait(self.poll_interval)

    def poll(self):
        """One check: the health of running simulations that are not in the queue, then one step of the queue."""
        from y_web.src.federation import health, schedule_queue
        from y_web.src.models.admin import Federation, FederationScheduleQueue

        queued = {
            i.federation_id
            for i in FederationScheduleQueue.query.filter_by(status="running").all()
        }
        for fed in Federation.query.filter(
            Federation.status.in_(("running", "paused"))
        ).all():
            if fed.id not in queued:
                health.check_federation(fed)
        return schedule_queue.advance()


def get_monitor():
    return _monitor


def init_federation_schedule_monitor(app):
    """Start the monitor once per process (called when the World Simulation blueprint is registered)."""
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = FederationScheduleMonitor(app)
            _monitor.start()
        return _monitor


def stop_federation_schedule_monitor():
    global _monitor
    with _monitor_lock:
        if _monitor is not None:
            _monitor.stop()
            _monitor = None
