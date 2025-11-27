"""
Background scheduler for automatic log synchronization.

This module provides functionality to periodically read and update
log metrics for active experiments without blocking the main thread.
The scheduler runs in a separate thread and respects the user-configurable
sync interval from the database.
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler = None
_scheduler_lock = threading.Lock()


class LogSyncScheduler:
    """
    Background scheduler for automatic log synchronization.

    Periodically reads logs from active experiments and updates
    the database metrics tables. Runs in a daemon thread that
    stops when the main application exits.
    """

    def __init__(self, app):
        """
        Initialize the log sync scheduler.

        Args:
            app: Flask application instance
        """
        self.app = app
        self._stop_event = threading.Event()
        self._thread = None
        self._started = False

    def start(self):
        """Start the background scheduler thread."""
        if self._started:
            logger.warning("Log sync scheduler already started")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._started = True
        logger.info("Log sync scheduler started")

    def stop(self):
        """Stop the background scheduler thread."""
        if not self._started:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._started = False
        logger.info("Log sync scheduler stopped")

    def _run(self):
        """Main scheduler loop running in background thread."""
        # Wait a bit before first run to let the app fully start
        time.sleep(5)

        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    settings = self._get_settings()

                    if settings and settings.enabled:
                        interval_seconds = settings.sync_interval_minutes * 60

                        # Check if enough time has passed since last sync
                        should_sync = True
                        if settings.last_sync:
                            time_since_sync = (
                                datetime.now(timezone.utc)
                                - settings.last_sync.replace(tzinfo=timezone.utc)
                            ).total_seconds()
                            should_sync = time_since_sync >= interval_seconds

                        if should_sync:
                            logger.info("Starting automatic log sync...")
                            self._sync_all_active_experiments()
                            self._update_last_sync()
                            logger.info("Automatic log sync completed")

                        # Sleep for 1 minute before checking again
                        # This allows for responsive setting changes
                        self._stop_event.wait(60)
                    else:
                        # Sync is disabled, check again in 1 minute
                        self._stop_event.wait(60)

            except Exception as e:
                logger.error(f"Error in log sync scheduler: {e}", exc_info=True)
                # Sleep before retrying on error
                self._stop_event.wait(60)

    def _get_settings(self):
        """Get log sync settings from database."""
        from y_web import db
        from y_web.models import LogSyncSettings

        settings = LogSyncSettings.query.first()
        if not settings:
            # Create default settings if they don't exist
            settings = LogSyncSettings(enabled=True, sync_interval_minutes=10)
            db.session.add(settings)
            db.session.commit()
        return settings

    def _update_last_sync(self):
        """Update the last sync timestamp in database."""
        from y_web import db
        from y_web.models import LogSyncSettings

        settings = LogSyncSettings.query.first()
        if settings:
            settings.last_sync = datetime.now(timezone.utc)
            db.session.commit()

    def _sync_all_active_experiments(self):
        """Sync logs for all running experiments."""
        from y_web.models import Client, Exps
        from y_web.utils.log_metrics import (
            has_server_log_files,
            update_client_log_metrics,
            update_server_log_metrics,
        )
        from y_web.utils.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Get all running experiments
        running_exps = Exps.query.filter_by(running=1).all()

        for exp in running_exps:
            try:
                # Determine experiment folder path
                db_name = exp.db_name
                if db_name.startswith("experiments/") or db_name.startswith(
                    "experiments\\"
                ):
                    parts = db_name.split(os.sep)
                    if len(parts) >= 2:
                        exp_folder = os.path.join(
                            BASE_DIR, f"y_web{os.sep}experiments{os.sep}{parts[1]}"
                        )
                    else:
                        continue
                elif db_name.startswith("experiments_"):
                    uid = db_name.replace("experiments_", "")
                    exp_folder = os.path.join(
                        BASE_DIR, f"y_web{os.sep}experiments{os.sep}{uid}"
                    )
                else:
                    continue

                # Sync server logs
                server_log_file = os.path.join(exp_folder, "_server.log")
                if has_server_log_files(server_log_file):
                    try:
                        update_server_log_metrics(exp.idexp, server_log_file)
                        logger.debug(
                            f"Synced server logs for experiment {exp.exp_name}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Error syncing server logs for experiment {exp.exp_name}: {e}"
                        )

                # Sync client logs for all running clients
                clients = Client.query.filter_by(id_exp=exp.idexp, status=1).all()
                for client in clients:
                    client_log_file = os.path.join(
                        exp_folder, f"{client.name}_client.log"
                    )
                    if os.path.exists(client_log_file):
                        try:
                            update_client_log_metrics(
                                exp.idexp, client.id, client_log_file
                            )
                            logger.debug(
                                f"Synced client logs for {client.name} in experiment {exp.exp_name}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Error syncing client logs for {client.name}: {e}"
                            )

            except Exception as e:
                logger.error(
                    f"Error syncing logs for experiment {exp.exp_name}: {e}",
                    exc_info=True,
                )

    def trigger_sync(self):
        """Manually trigger a log sync (called from API)."""
        if not self._started:
            return False

        try:
            with self.app.app_context():
                self._sync_all_active_experiments()
                self._update_last_sync()
                return True
        except Exception as e:
            logger.error(f"Error in manual log sync: {e}", exc_info=True)
            return False


def get_scheduler():
    """Get the global scheduler instance."""
    return _scheduler


def init_log_sync_scheduler(app):
    """
    Initialize and start the log sync scheduler.

    Should be called once during application startup.

    Args:
        app: Flask application instance
    """
    global _scheduler

    with _scheduler_lock:
        if _scheduler is not None:
            logger.warning("Log sync scheduler already initialized")
            return _scheduler

        _scheduler = LogSyncScheduler(app)
        _scheduler.start()
        return _scheduler


def stop_log_sync_scheduler():
    """Stop the global log sync scheduler."""
    global _scheduler

    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.stop()
            _scheduler = None
