"""
HPC metric persistence and completion monitoring.

Provides wrapper functions for persisting parsed log metrics, checking
HPC client execution completion, and orchestrating the overall monitoring
loop. Parsing helpers are imported from y_web.src.hpc.log_parser.
"""

import json
import logging
import os

from y_web import db
from y_web.src.hpc.log_offset import (
    _commit_with_retry,
    _ensure_session_clean,
    get_log_file_offset,
    reset_hpc_client_metrics,
    reset_hpc_server_metrics,
    update_log_file_offset,
)
from y_web.src.hpc.log_parser import (
    parse_client_log_incremental,
    parse_server_log_incremental,
)
from y_web.src.models import (
    Client,
    Client_Execution,
    ClientLogMetrics,
    Exps,
    ServerLogMetrics,
)

logger = logging.getLogger(__name__)

# Per-process monitor session state.
# Only auto-stop an HPC server after this monitor has observed at least one
# running client for the experiment in the current session.
_HPC_EXP_HAS_SEEN_RUNNING_CLIENT = {}

_NATURAL_COMPLETION_MARKER = "Client natural completion reached"
_SERVER_COMPLETION_MARKERS = {
    "Notified server of completion",
    "Simulation complete. Server notified.",
}


def _is_hpc_client_tracked_process_alive(client: Client, *, exp_folder: str) -> bool:
    """
    Return True when the tracked PID still belongs to this HPC client process.

    The check validates both process liveness and command-line ownership to avoid
    treating recycled PIDs as active client processes.
    """
    pid = getattr(client, "pid", None)
    if not pid:
        return False

    try:
        from y_web.src.hpc.client import (
            _hpc_process_matches_client,
            _is_hpc_client_process,
            _tracked_process_is_alive,
        )

        pid_int = int(pid)
        if not _tracked_process_is_alive(pid_int):
            return False
        if not _is_hpc_client_process(pid_int):
            return False
        return bool(
            _hpc_process_matches_client(
                pid_int,
                cli_name=getattr(client, "name", None),
                exp_folder=exp_folder,
            )
        )
    except Exception:
        return False


def _recover_stale_running_client_statuses(exp: Exps, *, exp_folder: str) -> int:
    """
    Heal stale client statuses where status=0 but tracked process is still alive.

    Returns:
        int: Number of clients promoted back to running status.
    """
    recovered = 0
    clients = Client.query.filter_by(id_exp=exp.idexp).all()
    for client in clients:
        if int(getattr(client, "status", 0) or 0) == 1:
            continue
        if _is_hpc_client_tracked_process_alive(client, exp_folder=exp_folder):
            client.status = 1
            recovered += 1

    if recovered > 0:
        _commit_with_retry(db.session)
    return recovered


def _mark_hpc_experiment_seen_running_client(exp_id: int) -> None:
    """Record that an experiment has had at least one running client in this session."""
    try:
        _HPC_EXP_HAS_SEEN_RUNNING_CLIENT[int(exp_id)] = True
    except Exception:
        pass


def _has_hpc_experiment_seen_running_client(exp_id: int) -> bool:
    """Return whether this experiment had a running client in this monitor session."""
    try:
        return bool(_HPC_EXP_HAS_SEEN_RUNNING_CLIENT.get(int(exp_id)))
    except Exception:
        return False


def _clear_hpc_experiment_seen_running_client(exp_id: int) -> None:
    """Clear the per-session running-client marker for an experiment."""
    try:
        _HPC_EXP_HAS_SEEN_RUNNING_CLIENT.pop(int(exp_id), None)
    except Exception:
        pass


def _tail_contains_completion_marker(lines) -> bool:
    """Return whether the provided log tail includes a natural-completion marker."""
    for raw_line in lines:
        line = (raw_line or "").strip()
        if not line:
            continue

        if _NATURAL_COMPLETION_MARKER in line:
            return True

        try:
            entry = json.loads(line)
        except Exception:
            continue

        message = entry.get("message", "")
        if message == _NATURAL_COMPLETION_MARKER:
            return True
        if message in _SERVER_COMPLETION_MARKERS:
            return True

    return False


def update_server_log_metrics(exp_id, log_file_path, is_hpc=False):
    """
    Update server log metrics by reading new log entries.

    Only processes the main log file (_server.log) for incremental updates.
    Rotated log files (.log.1, .log.2, etc.) are skipped because their content
    was already processed when they were the main log file.

    Args:
        exp_id: Experiment ID
        log_file_path: Full path to the main server log file
        is_hpc: Boolean flag indicating if this is an HPC experiment (uses different log format)

    Returns:
        bool: True if successful, False otherwise
    """
    # Ensure session is in clean state before starting
    _ensure_session_clean(db.session)

    try:
        # Only process the main log file, not rotated ones
        # Rotated logs contain data we already processed when they were the main log
        if not os.path.exists(log_file_path):
            logger.warning(f"Log file not found: {log_file_path}")
            return True

        # For HPC experiments, check if we have old incorrectly parsed data
        # If simulation time is missing/zero, reset and re-parse from beginning
        if is_hpc:
            existing_metric = ServerLogMetrics.query.filter_by(
                exp_id=exp_id, aggregation_level="daily"
            ).first()

            if (
                existing_metric
                and existing_metric.min_time
                and existing_metric.max_time
            ):
                # Check if this looks like old data (simulation time near zero)
                sim_time = (
                    existing_metric.max_time - existing_metric.min_time
                ).total_seconds()
                if sim_time < 1.0:  # Less than 1 second suggests old incorrect data
                    logger.info(
                        f"Found old server metrics with near-zero simulation time for exp_id={exp_id}, resetting"
                    )
                    reset_hpc_server_metrics(exp_id)

        # Get relative file name (for storage in database)
        file_name = os.path.basename(log_file_path)

        # Get last offset for this specific file
        last_offset = get_log_file_offset(exp_id, "server", file_name)

        # Check if file has been rotated (size is smaller than offset)
        file_size = os.path.getsize(log_file_path)
        if file_size < last_offset:
            # File was rotated, reset offset to read from beginning
            logger.info(
                f"Log file {file_name} was rotated (size {file_size} < offset {last_offset}), resetting offset"
            )
            last_offset = 0

        # Parse log file incrementally
        new_offset, metrics = parse_server_log_incremental(
            log_file_path, exp_id, last_offset, is_hpc=is_hpc
        )

        # Update offset
        if new_offset > last_offset:
            update_log_file_offset(exp_id, "server", file_name, new_offset)

        return True

    except Exception as e:
        logger.error(f"Error updating server log metrics: {e}", exc_info=True)
        return False


def update_client_log_metrics(exp_id, client_id, log_file_path, is_hpc=False):
    """
    Update client log metrics by reading new log entries.

    Only processes the main log file ({client_name}_client.log) for incremental updates.
    Rotated log files (.log.1, .log.2, etc.) are skipped because their content
    was already processed when they were the main log file.

    Args:
        exp_id: Experiment ID
        client_id: Client ID
        log_file_path: Full path to the client log file
        is_hpc: Boolean flag indicating if this is an HPC experiment (uses different log format)

    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(
        f"update_client_log_metrics called: exp_id={exp_id}, client_id={client_id}, "
        f"is_hpc={is_hpc}, log_file={log_file_path}"
    )

    # Ensure session is in clean state before starting
    _ensure_session_clean(db.session)

    try:
        # Only process the main log file, not rotated ones
        # Rotated logs contain data we already processed when they were the main log
        if not os.path.exists(log_file_path):
            logger.warning(f"Client log file not found: {log_file_path}")
            return True

        # For HPC experiments, check if we have old incorrectly parsed data
        # If we find "unknown" method name, reset and re-parse from beginning
        if is_hpc:
            has_unknown = ClientLogMetrics.query.filter_by(
                exp_id=exp_id, client_id=client_id, method_name="unknown"
            ).first()

            if has_unknown:
                logger.info(
                    f"Found 'unknown' method in HPC client metrics, resetting for exp_id={exp_id}, client_id={client_id}"
                )
                reset_hpc_client_metrics(exp_id, client_id)

        # Get relative file path (for storage in database)
        file_name = os.path.basename(log_file_path)

        # Get last offset for this specific file
        last_offset = get_log_file_offset(exp_id, "client", file_name, client_id)

        # Check if file has been rotated (size is smaller than offset)
        file_size = os.path.getsize(log_file_path)
        if file_size < last_offset:
            # File was rotated, reset offset to read from beginning
            logger.info(
                f"Client log file {file_name} was rotated (size {file_size} < offset {last_offset}), resetting offset"
            )
            last_offset = 0

        # Parse log file incrementally
        new_offset, metrics = parse_client_log_incremental(
            log_file_path, exp_id, client_id, last_offset, is_hpc=is_hpc
        )

        # Update offset
        if new_offset > last_offset:
            update_log_file_offset(exp_id, "client", file_name, new_offset, client_id)

        return True

    except Exception as e:
        logger.error(f"Error updating client log metrics: {e}", exc_info=True)
        return False


def check_hpc_client_execution_completion(exp_id, client_id, execution_log_path):
    """
    Check if an HPC client has completed execution by reading the execution log.

    Looks for the "Client shutdown complete" message in the last line of the
    execution log file. If found, updates the client_execution table to mark
    the client as completed.

    Args:
        exp_id: Experiment ID
        client_id: Client ID
        execution_log_path: Full path to the {client_name}_execution.log file

    Returns:
        bool: True if client is completed (shutdown message found), False otherwise
    """
    if not os.path.exists(execution_log_path):
        print(f"[HPC Monitor] Execution log does not exist: {execution_log_path}")
        return False

    try:
        # Read the last line of the log file
        with open(execution_log_path, "r") as f:
            # Efficiently read last line by seeking to end
            # Handle both small and large files
            try:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()

                if file_size == 0:
                    print(f"[HPC Monitor] Execution log is empty: {execution_log_path}")
                    return False

                # Read up to 10KB from the end to find the last line
                # This handles cases where the last line might be very long
                chunk_size = min(10240, file_size)
                f.seek(max(0, file_size - chunk_size))
                lines = f.read().splitlines()

                if not lines:
                    print(
                        f"[HPC Monitor] No lines found in execution log: {execution_log_path}"
                    )
                    return False

                last_line = lines[-1].strip()
                print(
                    f"[HPC Monitor] Last line from {execution_log_path}: {last_line[:200]}..."
                )
            except Exception as e:
                print(f"[HPC Monitor] Error seeking in file, using fallback: {e}")
                # Fallback: read entire file if seeking fails
                f.seek(0)
                lines = f.readlines()
                if not lines:
                    return False
                last_line = lines[-1].strip()

        # Parse the last line as JSON
        if not last_line:
            print(f"[HPC Monitor] Last line is empty")
            return False

        try:
            log_entry = json.loads(last_line)
            print(f"[HPC Monitor] Parsed JSON: {log_entry}")
        except json.JSONDecodeError as e:
            print(f"[HPC Monitor] Failed to parse JSON: {e}")
            return False

        # Shutdown alone is not sufficient to declare completion: manual stops
        # also emit a shutdown line. Require either the explicit completion
        # marker emitted by the runtime, or a fully reached expected duration.
        message = log_entry.get("message", "")
        print(f"[HPC Monitor] Message field: '{message}'")

        try:
            client_exec = Client_Execution.query.filter_by(client_id=client_id).first()
        except Exception:
            client_exec = None
        terminal_state = (
            getattr(client_exec, "terminal_state", None) if client_exec else None
        )
        if terminal_state in {"manual_stop", "paused"}:
            print(
                f"[HPC Monitor] Client {client_id} is in terminal state '{terminal_state}', not counting as completed"
            )
            return False
        if terminal_state == "completed":
            print(
                f"[HPC Monitor] Client {client_id} already marked completed in database"
            )
            return True

        if message == "Client shutdown complete":
            if _tail_contains_completion_marker(lines):
                print("[HPC Monitor] *** MATCH: natural completion marker found! ***")
                logger.info(
                    f"HPC client {client_id} natural completion detected for experiment {exp_id}"
                )
                return True

            if (
                client_exec
                and client_exec.expected_duration_rounds > 0
                and client_exec.elapsed_time >= client_exec.expected_duration_rounds
            ):
                print(
                    "[HPC Monitor] Shutdown observed with elapsed time already at or beyond expected duration"
                )
                logger.info(
                    f"HPC client {client_id} completed for experiment {exp_id} based on execution progress"
                )
                return True

        print(f"[HPC Monitor] Message does not match 'Client shutdown complete'")
        return False

    except Exception as e:
        logger.error(
            f"Error checking execution log for client {client_id}: {e}", exc_info=True
        )
        print(f"[HPC Monitor] Exception checking execution log: {e}")
        return False


def get_latest_hourly_summary_from_client_log(client_log_path):
    """
    Extract the latest hourly summary from a client log file.

    Reads the client log file and finds the most recent entry with
    "summary_type": "hourly" to get the current execution progress.

    Args:
        client_log_path: Full path to the {client_name}_client.log file

    Returns:
        dict or None: Dictionary with keys 'day', 'slot', 'elapsed_time' if found, None otherwise
    """
    if not os.path.exists(client_log_path):
        return None

    try:
        latest_hourly = None

        with open(client_log_path, "r") as f:
            # Read all lines to find the latest hourly summary
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    log_entry = json.loads(line)

                    # Check if this is an hourly summary
                    if log_entry.get("summary_type") == "hourly":
                        # Extract the relevant fields
                        day = log_entry.get("day")
                        slot = log_entry.get("slot")

                        if day is not None and slot is not None:
                            # Calculate elapsed_time: each day has 24 hours
                            # If day=1, slot=20, that means we're in day 1, hour 20
                            # elapsed_time = day * 24 + slot + 1 (adding 1 because we count from 1)
                            elapsed_time = day * 24 + slot + 1

                            latest_hourly = {
                                "day": day,
                                "slot": slot,
                                "elapsed_time": elapsed_time,
                            }
                            # Keep reading to find the LATEST one

                except json.JSONDecodeError:
                    # Skip lines that aren't valid JSON
                    continue

        return latest_hourly

    except Exception as e:
        logger.error(
            f"Error reading client log file {client_log_path}: {e}", exc_info=True
        )
        return None


def update_client_execution_from_log(client_id, client_log_path):
    """
    Update client_execution table with latest progress from client log.

    Reads the latest hourly summary from the client log and updates
    the client_execution record with the current day, hour, and elapsed time.

    Args:
        client_id: Client ID
        client_log_path: Full path to the {client_name}_client.log file

    Returns:
        bool: True if updated successfully, False otherwise
    """
    try:
        # Get the latest hourly summary
        summary = get_latest_hourly_summary_from_client_log(client_log_path)

        if not summary:
            print(f"[HPC Monitor] No hourly summary found in client log")
            return False

        print(
            f"[HPC Monitor] Latest hourly summary: day={summary['day']}, slot={summary['slot']}, elapsed={summary['elapsed_time']}"
        )

        # Get the client_execution record
        client_exec = Client_Execution.query.filter_by(client_id=client_id).first()

        if not client_exec:
            print(
                f"[HPC Monitor] No client_execution record found for client {client_id}"
            )
            return False

        # Update the fields
        client_exec.last_active_day = summary["day"]
        client_exec.last_active_hour = summary["slot"]
        client_exec.elapsed_time = summary["elapsed_time"]

        # Commit the changes
        _commit_with_retry(db.session)

        print(
            f"[HPC Monitor] Updated client_execution: day={summary['day']}, hour={summary['slot']}, elapsed={summary['elapsed_time']}"
        )

        return True

    except Exception as e:
        logger.error(
            f"Error updating client_execution from log for client {client_id}: {e}",
            exc_info=True,
        )
        print(f"[HPC Monitor] Error updating client_execution: {e}")
        db.session.rollback()
        return False


def mark_hpc_client_as_completed(exp_id, client_id):
    """
    Mark an HPC client as completed in the client_execution table.

    Updates the client_execution record with:
    - elapsed_time = expected_duration_rounds
    - last_active_day and last_active_hour calculated from expected_duration_rounds
    - client status set to stopped (0)

    Args:
        exp_id: Experiment ID
        client_id: Client ID

    Returns:
        bool: True if successfully marked as completed, False otherwise
    """
    try:
        print(f"[HPC Monitor] Marking client {client_id} as completed...")

        # Get client execution record
        client_exec = Client_Execution.query.filter_by(client_id=client_id).first()
        if not client_exec:
            logger.warning(f"No client_execution record found for client {client_id}")
            print(
                f"[HPC Monitor] No client_execution record found for client {client_id}"
            )
            return False

        # Get the client to verify it exists
        client = Client.query.filter_by(id=client_id).first()
        if not client:
            logger.warning(f"Client {client_id} not found")
            print(f"[HPC Monitor] Client {client_id} not found")
            return False

        print(
            f"[HPC Monitor] Client name: {client.name}, current status: {client.status}"
        )
        print(
            f"[HPC Monitor] Expected duration: {client_exec.expected_duration_rounds} rounds"
        )

        # Calculate max day and hour from expected_duration_rounds
        # Since each experiment has its own database and the Rounds table is in db_exp,
        # it's more reliable to calculate from expected_duration_rounds
        # Assuming day 0, hour 0 = round 1 (as per HPC format in parse_client_log_incremental)
        if client_exec.expected_duration_rounds > 0:
            total_hours = client_exec.expected_duration_rounds - 1
            max_day = total_hours // 24
            max_hour = total_hours % 24
        else:
            # Default to 0,0 if no rounds configured
            max_day = 0
            max_hour = 0

        # Update client_execution record
        client_exec.elapsed_time = client_exec.expected_duration_rounds
        client_exec.last_active_day = max_day
        client_exec.last_active_hour = max_hour
        client_exec.terminal_state = "completed"

        print(
            f"[HPC Monitor] Setting: elapsed_time={client_exec.elapsed_time}, last_active_day={max_day}, last_active_hour={max_hour}"
        )

        # Mark client as stopped (client is guaranteed to exist from earlier check)
        client.status = 0
        print(f"[HPC Monitor] Setting client status to 0 (stopped)")

        logger.info(
            f"Marked HPC client {client_id} as completed: "
            f"elapsed_time={client_exec.elapsed_time}, "
            f"last_active_day={max_day}, last_active_hour={max_hour}"
        )

        # Commit changes
        print(f"[HPC Monitor] Committing changes to database...")
        _commit_with_retry(db.session)
        print(
            f"[HPC Monitor] *** Client {client.name} successfully marked as completed ***"
        )
        return True

    except Exception as e:
        logger.error(
            f"Error marking client {client_id} as completed: {e}", exc_info=True
        )
        db.session.rollback()
        return False


def check_and_terminate_hpc_experiment(exp_id):
    """
    Check if all clients of an HPC experiment are completed and terminate the server if so.

    Args:
        exp_id: Experiment ID

    Returns:
        bool: True if experiment was terminated, False otherwise
    """
    try:
        from y_web.src.hpc.server import _resolve_hpc_experiment_folder, stop_hpc_server
        from y_web.src.models import Exps

        # Get the experiment
        exp = Exps.query.filter_by(idexp=exp_id).first()
        if not exp:
            print(f"[HPC Monitor] Experiment {exp_id} not found")
            return False

        # Only process HPC experiments that are running
        if exp.simulator_type != "HPC" or exp.running != 1:
            print(
                f"[HPC Monitor] Experiment {exp.exp_name} is not HPC or not running (type={exp.simulator_type}, running={exp.running})"
            )
            return False

        # Get all clients for this experiment
        clients = Client.query.filter_by(id_exp=exp_id).all()
        if not clients:
            print(f"[HPC Monitor] No clients found for experiment {exp.exp_name}")
            return False

        # Reconcile stale DB flags (status=0) against live tracked PIDs.
        try:
            exp_folder = _resolve_hpc_experiment_folder(exp)
            recovered = _recover_stale_running_client_statuses(
                exp, exp_folder=exp_folder
            )
            if recovered > 0:
                print(
                    f"[HPC Monitor] Recovered {recovered} client(s) with stale stopped status for experiment {exp.exp_name}"
                )
                clients = Client.query.filter_by(id_exp=exp_id).all()
        except Exception:
            pass

        # Check if all clients are properly completed
        # A client is considered completed ONLY if:
        # 1. It has status = 0 (stopped)
        # 2. It has a client_execution record where elapsed_time == expected_duration_rounds
        #    (which indicates it was marked as completed by the monitoring system)
        truly_completed_count = 0
        running_count = 0
        not_started_count = 0
        manually_stopped_count = 0

        for client in clients:
            if client.status == 1:
                running_count += 1
            else:
                # Check if this stopped client was properly completed
                try:
                    client_exec = Client_Execution.query.filter_by(
                        client_id=client.id
                    ).first()
                except Exception:
                    client_exec = None
                if client_exec and client_exec.expected_duration_rounds > 0:
                    terminal_state = getattr(client_exec, "terminal_state", None)
                    if terminal_state in {"manual_stop", "paused"}:
                        manually_stopped_count += 1
                        print(
                            f"[HPC Monitor] Client {client.name} stopped manually (state={terminal_state})"
                        )
                        continue
                    if terminal_state == "completed":
                        truly_completed_count += 1
                        print(
                            f"[HPC Monitor] Client {client.name} is completed via terminal state"
                        )
                        continue

                    # Use >= instead of == to handle cases where client ran slightly longer
                    # This can happen when:
                    # 1. Client was extended and log parsing shows extra time
                    # 2. Last log entry is from after the expected completion time
                    # 3. Client ran one extra iteration before shutdown
                    if client_exec.elapsed_time >= client_exec.expected_duration_rounds:
                        truly_completed_count += 1
                        print(
                            f"[HPC Monitor] Client {client.name} is truly completed (elapsed={client_exec.elapsed_time}, expected={client_exec.expected_duration_rounds})"
                        )
                    else:
                        # Client is stopped but not completed - might not have started yet
                        not_started_count += 1
                        print(
                            f"[HPC Monitor] Client {client.name} is stopped but not completed (elapsed={client_exec.elapsed_time}, expected={client_exec.expected_duration_rounds})"
                        )
                else:
                    # No execution record or no expected duration - not started
                    not_started_count += 1
                    print(
                        f"[HPC Monitor] Client {client.name} has no execution record or expected duration"
                    )

        total_count = len(clients)
        print(
            f"[HPC Monitor] Experiment {exp.exp_name}: {truly_completed_count} completed, {running_count} running, {not_started_count} not started, {manually_stopped_count} manually stopped (total: {total_count})"
        )
        if running_count > 0:
            _mark_hpc_experiment_seen_running_client(exp_id)
        seen_running_this_session = _has_hpc_experiment_seen_running_client(exp_id)

        # Only terminate if:
        # 1. There are no running clients
        # 2. This session has observed at least one running client
        # 3. At least one client was truly completed (to avoid terminating when nothing has started)
        # 4. All non-running clients are truly completed (not just stopped)
        should_terminate = (
            running_count == 0
            and seen_running_this_session
            and truly_completed_count > 0
            and truly_completed_count == (total_count - running_count)
        )

        if should_terminate:
            print(f"[HPC Monitor] *** ALL CLIENTS COMPLETED for {exp.exp_name} ***")
            logger.info(
                f"All clients completed for HPC experiment {exp_id} ({exp.exp_name}). "
                f"Terminating server..."
            )

            # Terminate the server process
            print(f"[HPC Monitor] Calling stop_hpc_server for experiment {exp_id}...")
            stop_hpc_server(exp_id)
            print(f"[HPC Monitor] stop_hpc_server completed")

            # Update experiment status
            print(
                f"[HPC Monitor] Updating experiment status: setting running=0, exp_status='completed'"
            )
            exp.running = 0
            exp.exp_status = "completed"
            _commit_with_retry(db.session)
            print(
                f"[HPC Monitor] *** EXPERIMENT {exp.exp_name} STATUS UPDATED: running={exp.running}, status={exp.exp_status} ***"
            )

            logger.info(f"HPC experiment {exp_id} terminated successfully")
            _clear_hpc_experiment_seen_running_client(exp_id)
            return True
        else:
            if running_count > 0:
                print(
                    f"[HPC Monitor] Not terminating: {running_count} client(s) still running"
                )
            elif not seen_running_this_session:
                print(
                    "[HPC Monitor] Not terminating: no running client observed in this server session"
                )
            elif truly_completed_count == 0:
                print(
                    f"[HPC Monitor] Not terminating: no clients have been properly completed yet"
                )
            else:
                print(
                    f"[HPC Monitor] Not terminating: some stopped clients are not properly completed"
                )

        return False

    except Exception as e:
        logger.error(
            f"Error checking/terminating HPC experiment {exp_id}: {e}", exc_info=True
        )
        print(f"[HPC Monitor] Error checking/terminating experiment {exp_id}: {e}")
        db.session.rollback()
        return False


def monitor_hpc_client_execution_logs():
    """
    Monitor execution logs for all active HPC experiments.

    For each running HPC client:
    1. Check if {client_name}_execution.log exists
    2. Check if last line contains "Client shutdown complete"
    3. If yes, mark client as completed and update client_execution table
    4. Check if all clients are completed and terminate server if so

    This function should be called periodically (e.g., every 5 seconds).
    """
    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    try:
        # Get all running HPC experiments
        hpc_experiments = Exps.query.filter_by(simulator_type="HPC", running=1).all()
        active_exp_ids = {int(exp.idexp) for exp in hpc_experiments}
        # Drop session markers for experiments that are no longer running.
        for tracked_exp_id in list(_HPC_EXP_HAS_SEEN_RUNNING_CLIENT.keys()):
            if tracked_exp_id not in active_exp_ids:
                _clear_hpc_experiment_seen_running_client(tracked_exp_id)

        if not hpc_experiments:
            # print("[HPC Monitor] No active HPC experiments found")
            return

        print(
            f"[HPC Monitor] Monitoring {len(hpc_experiments)} active HPC experiment(s)"
        )
        logger.debug(f"Monitoring {len(hpc_experiments)} active HPC experiment(s)")

        for exp in hpc_experiments:
            try:
                print(
                    f"[HPC Monitor] Checking experiment: {exp.exp_name} (ID: {exp.idexp})"
                )

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
                        print(f"[HPC Monitor] Invalid db_name format: {db_name}")
                        continue
                elif db_name.startswith("experiments_"):
                    uid = db_name.replace("experiments_", "")
                    exp_folder = os.path.join(
                        BASE_DIR, f"y_web{os.sep}experiments{os.sep}{uid}"
                    )
                else:
                    print(f"[HPC Monitor] Unknown db_name format: {db_name}")
                    continue

                print(f"[HPC Monitor] Experiment folder: {exp_folder}")

                try:
                    recovered = _recover_stale_running_client_statuses(
                        exp, exp_folder=exp_folder
                    )
                    if recovered > 0:
                        print(
                            f"[HPC Monitor] Recovered {recovered} stale stopped client(s) for experiment {exp.exp_name}"
                        )
                except Exception as recovery_exc:
                    print(
                        f"[HPC Monitor] Failed stale status recovery for {exp.exp_name}: {recovery_exc}"
                    )

                # Get all running clients for this experiment
                clients = Client.query.filter_by(id_exp=exp.idexp, status=1).all()
                print(f"[HPC Monitor] Found {len(clients)} running client(s)")
                if clients:
                    _mark_hpc_experiment_seen_running_client(exp.idexp)

                for client in clients:
                    print(
                        f"[HPC Monitor] Checking client: {client.name} (ID: {client.id})"
                    )

                    # Update client execution progress from client log
                    client_log_path = os.path.join(
                        exp_folder, "logs", f"{client.name}_client.log"
                    )

                    print(f"[HPC Monitor] Looking for client log: {client_log_path}")

                    if os.path.exists(client_log_path):
                        print(
                            f"[HPC Monitor] Client log found, updating execution progress..."
                        )
                        update_client_execution_from_log(client.id, client_log_path)
                    else:
                        print(f"[HPC Monitor] Client log not found for {client.name}")

                    # Check if execution log exists (in logs/ subdirectory)
                    execution_log_path = os.path.join(
                        exp_folder, "logs", f"{client.name}_execution.log"
                    )

                    print(
                        f"[HPC Monitor] Looking for execution log: {execution_log_path}"
                    )

                    if not os.path.exists(execution_log_path):
                        print(
                            f"[HPC Monitor] Execution log not found for {client.name}"
                        )
                        continue

                    print(
                        f"[HPC Monitor] Execution log found, checking for shutdown message..."
                    )

                    # Check if client has completed
                    if check_hpc_client_execution_completion(
                        exp.idexp, client.id, execution_log_path
                    ):
                        print(
                            f"[HPC Monitor] *** SHUTDOWN DETECTED for {client.name} ***"
                        )
                        # Mark client as completed
                        if mark_hpc_client_as_completed(exp.idexp, client.id):
                            print(
                                f"[HPC Monitor] Successfully marked {client.name} as completed"
                            )
                            logger.info(
                                f"Successfully marked client {client.name} as completed "
                                f"for experiment {exp.exp_name}"
                            )
                        else:
                            print(
                                f"[HPC Monitor] Failed to mark {client.name} as completed"
                            )
                    else:
                        print(
                            f"[HPC Monitor] No shutdown message found for {client.name}"
                        )

                # After processing all clients, check if experiment should be terminated
                print(
                    f"[HPC Monitor] Checking if all clients completed for experiment {exp.exp_name}"
                )
                if check_and_terminate_hpc_experiment(exp.idexp):
                    print(f"[HPC Monitor] *** EXPERIMENT {exp.exp_name} TERMINATED ***")

            except Exception as e:
                logger.error(
                    f"Error monitoring HPC experiment {exp.exp_name}: {e}",
                    exc_info=True,
                )
                print(f"[HPC Monitor] Error monitoring experiment {exp.exp_name}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error in HPC execution log monitoring: {e}", exc_info=True)
        print(f"[HPC Monitor] Error in monitoring: {e}")
