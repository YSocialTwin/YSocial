"""
Background scheduler for HPC client execution monitoring.

This module provides functionality to monitor HPC client execution logs
for completion detection and progress updates. The monitor runs in a
separate thread without blocking the main application.
"""

import logging
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler = None
_scheduler_lock = threading.Lock()


class LogSyncScheduler:
    """
    Background scheduler for HPC client execution monitoring.

    Monitors HPC client execution logs for completion detection and
    real-time progress updates. Runs in a daemon thread that stops
    when the main application exits.
    """

    def __init__(self, app):
        """
        Initialize the HPC monitor scheduler.

        Args:
            app: Flask application instance
        """
        self.app = app
        self._stop_event = threading.Event()
        self._hpc_monitor_thread = None
        self._started = False

    def start(self):
        """Start the HPC monitor background thread."""
        if self._started:
            logger.warning("HPC monitor already started")
            return

        self._stop_event.clear()
        self._hpc_monitor_thread = threading.Thread(
            target=self._run_hpc_monitor, daemon=True
        )
        self._hpc_monitor_thread.start()
        self._started = True
        logger.info("HPC monitor started")

    def stop(self):
        """Stop the HPC monitor background thread."""
        if not self._started:
            return

        self._stop_event.set()
        if self._hpc_monitor_thread and self._hpc_monitor_thread.is_alive():
            self._hpc_monitor_thread.join(timeout=5)
        self._started = False
        logger.info("HPC monitor stopped")

    def _run_hpc_monitor(self):
        """HPC execution log monitor loop running in background thread."""
        # Wait a bit before first run to let the app fully start
        time.sleep(5)

        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    # Get HPC monitor settings
                    settings = self._get_hpc_monitor_settings()

                    # Check if monitoring is enabled
                    if not settings.enabled:
                        print("[HPC Monitor] Monitoring is disabled, waiting...")
                        self._stop_event.wait(30)  # Check again in 30 seconds
                        continue

                    # Monitor HPC client execution logs
                    from y_web.src.hpc.log_metrics import (
                        monitor_hpc_client_execution_logs,
                    )

                    print("[HPC Monitor] Checking for completed clients...")
                    monitor_hpc_client_execution_logs()

                    # Update last check timestamp
                    self._update_hpc_monitor_last_check()

                    # Sleep for configured interval before next check
                    interval = settings.check_interval_seconds
                    print(f"[HPC Monitor] Next check in {interval} seconds...")
                    self._stop_event.wait(interval)

            except Exception as e:
                logger.error(f"Error in HPC execution log monitor: {e}", exc_info=True)
                print(f"[HPC Monitor] ERROR: {e}")
                # Sleep before retrying on error (use default 5 seconds)
                self._stop_event.wait(5)

    def _get_hpc_monitor_settings(self):
        """Get HPC monitor settings from database with proper error handling."""
        from sqlalchemy.exc import IntegrityError

        from y_web import db
        from y_web.src.models import HpcMonitorSettings

        settings = HpcMonitorSettings.query.first()
        if not settings:
            # Use get_or_create pattern with proper exception handling
            try:
                settings = HpcMonitorSettings(enabled=True, check_interval_seconds=5)
                db.session.add(settings)
                db.session.commit()
            except IntegrityError:
                # Another thread created settings, rollback and fetch
                db.session.rollback()
                settings = HpcMonitorSettings.query.first()
        return settings

    def _update_hpc_monitor_last_check(self):
        """Update the last check timestamp in database."""
        from y_web import db
        from y_web.src.models import HpcMonitorSettings

        try:
            settings = HpcMonitorSettings.query.first()
            if settings:
                settings.last_check = datetime.now(timezone.utc)
                db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to update last_check timestamp: {e}")
            db.session.rollback()


def get_scheduler():
    """Get the global scheduler instance."""
    return _scheduler


def init_log_sync_scheduler(app):
    """
    Initialize and start the HPC monitor scheduler.

    Should be called once during application startup.

    Args:
        app: Flask application instance
    """
    global _scheduler

    with _scheduler_lock:
        if _scheduler is not None:
            logger.warning("HPC monitor scheduler already initialized")
            return _scheduler

        _scheduler = LogSyncScheduler(app)
        _scheduler.start()
        return _scheduler


def stop_log_sync_scheduler():
    """Stop the global HPC monitor scheduler."""
    global _scheduler

    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.stop()
            _scheduler = None
