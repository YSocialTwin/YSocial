"""
HPC log-file offset and metrics-reset helpers.

Extracted from log_parser.py (Phase 12b).

Functions
---------
_ensure_session_clean      — roll back a dirty SQLAlchemy session
_commit_with_retry         — commit with deadlock retry logic
get_log_file_offset        — read last-read byte offset for a log file
update_log_file_offset     — persist a new byte offset for a log file
reset_hpc_client_metrics   — delete client metrics + offsets for one client
reset_hpc_server_metrics   — delete server metrics + offsets for one experiment
"""

import logging
import time
from datetime import datetime

from sqlalchemy.exc import OperationalError, PendingRollbackError

from y_web import db
from y_web.src.models import ClientLogMetrics, LogFileOffset, ServerLogMetrics

logger = logging.getLogger(__name__)

# Retry configuration for database deadlocks
MAX_RETRIES = 3
RETRY_DELAY = 0.5  # seconds


def _ensure_session_clean(session):
    """
    Ensure the database session is in a clean state.

    This is needed to handle PendingRollbackError which can occur
    when a previous database operation failed.
    """
    try:
        # Check if session needs rollback
        if session.is_active:
            session.rollback()
    except Exception as e:
        logger.debug(f"Session cleanup exception (can be safely ignored): {e}")


def _commit_with_retry(session, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    """
    Commit a database session with retry logic for deadlock handling.

    Args:
        session: SQLAlchemy session to commit
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds

    Returns:
        bool: True if commit succeeded, False otherwise
    """
    for attempt in range(max_retries):
        try:
            session.commit()
            return True
        except PendingRollbackError:
            # Session was in bad state, rollback and retry
            session.rollback()
            if attempt < max_retries - 1:
                logger.warning(
                    f"Session rollback needed, retrying ({attempt + 1}/{max_retries})..."
                )
                time.sleep(delay * (attempt + 1))
            else:
                logger.error(f"Session rollback persisted after {max_retries} retries")
                return False
        except OperationalError as e:
            session.rollback()
            error_msg = str(e).lower()
            if "deadlock" in error_msg or "lock" in error_msg:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Database deadlock detected, retrying ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(
                        f"Database deadlock persisted after {max_retries} retries"
                    )
                    return False
            else:
                logger.error(f"Database error during commit: {e}")
                return False
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error during commit: {e}")
            return False
    return False


def get_log_file_offset(exp_id, log_file_type, file_path, client_id=None):
    """
    Get the last read offset for a log file.

    Args:
        exp_id: Experiment ID
        log_file_type: Type of log file ('server' or 'client')
        file_path: Relative path to the log file
        client_id: Client ID (only for client logs)

    Returns:
        int: Last read offset in bytes (0 if not found)
    """
    offset_record = LogFileOffset.query.filter_by(
        exp_id=exp_id,
        log_file_type=log_file_type,
        file_path=file_path,
        client_id=client_id,
    ).first()

    if offset_record:
        return offset_record.last_offset
    return 0


def update_log_file_offset(
    exp_id, log_file_type, file_path, new_offset, client_id=None
):
    """
    Update the last read offset for a log file.

    Args:
        exp_id: Experiment ID
        log_file_type: Type of log file ('server' or 'client')
        file_path: Relative path to the log file
        new_offset: New offset in bytes
        client_id: Client ID (only for client logs)
    """
    offset_record = LogFileOffset.query.filter_by(
        exp_id=exp_id,
        log_file_type=log_file_type,
        file_path=file_path,
        client_id=client_id,
    ).first()

    if offset_record:
        offset_record.last_offset = new_offset
        offset_record.last_updated = datetime.utcnow()
    else:
        offset_record = LogFileOffset(
            exp_id=exp_id,
            log_file_type=log_file_type,
            file_path=file_path,
            last_offset=new_offset,
            client_id=client_id,
            last_updated=datetime.utcnow(),
        )
        db.session.add(offset_record)

    _commit_with_retry(db.session)


def reset_hpc_client_metrics(exp_id, client_id):
    """
    Reset client metrics and file offsets for an HPC experiment.

    This is needed when switching to a new log format or to force re-parsing.
    Only affects the specific client, not the entire experiment.

    Args:
        exp_id: Experiment ID
        client_id: Client ID to reset
    """
    try:
        # Delete existing client metrics
        ClientLogMetrics.query.filter_by(exp_id=exp_id, client_id=client_id).delete()

        # Delete file offsets for this client
        LogFileOffset.query.filter_by(
            exp_id=exp_id, log_file_type="client", client_id=client_id
        ).delete()

        success = _commit_with_retry(db.session)
        if success:
            logger.info(
                f"Reset client metrics and offsets for exp_id={exp_id}, client_id={client_id}"
            )
        return success
    except Exception as e:
        logger.error(f"Error resetting client metrics: {e}", exc_info=True)
        # Don't call rollback here - _commit_with_retry already handles it
        return False


def reset_hpc_server_metrics(exp_id):
    """
    Reset server metrics and file offsets for an HPC experiment.

    This is needed when switching to a new log format or to force re-parsing.

    Args:
        exp_id: Experiment ID
    """
    try:
        # Delete existing server metrics
        ServerLogMetrics.query.filter_by(exp_id=exp_id).delete()

        # Delete file offsets for server logs
        LogFileOffset.query.filter_by(exp_id=exp_id, log_file_type="server").delete()

        success = _commit_with_retry(db.session)
        if success:
            logger.info(f"Reset server metrics and offsets for exp_id={exp_id}")
        return success
    except Exception as e:
        logger.error(f"Error resetting server metrics: {e}", exc_info=True)
        # Don't call rollback here - _commit_with_retry already handles it
        return False
