"""
Raw HPC log parsing utilities.

Provides functions for incremental log file reading, offset tracking, and
parsing of server/client log entries into aggregated metric dictionaries.
Shared private helpers for database session safety and metric resets are
defined in log_offset.py and re-imported here for backward compatibility.
"""

import json
import logging
import os
import time  # noqa: F401 — kept for any third-party callers
from collections import defaultdict
from datetime import datetime, timedelta  # noqa: F401 — timedelta re-exported for shim

from sqlalchemy import and_  # noqa: F401 — re-exported for shim
from sqlalchemy.exc import OperationalError, PendingRollbackError  # noqa: F401

from y_web import db  # noqa: F401 — kept for any third-party callers
from y_web.src.hpc.log_offset import (
    MAX_RETRIES,
    RETRY_DELAY,
    _commit_with_retry,
    _ensure_session_clean,
    get_log_file_offset,
    reset_hpc_client_metrics,
    reset_hpc_server_metrics,
    update_log_file_offset,
)
from y_web.src.models import (
    Client,
    Client_Execution,
    ClientLogMetrics,
    Exps,
    LogFileOffset,  # noqa: F401 — kept for any third-party callers
    ServerLogMetrics,
)

# Set up logger
logger = logging.getLogger(__name__)

# Base time for HPC simulation time calculations
# Used to create synthetic timestamps where (max_time - min_time) = simulation_time_seconds
HPC_BASE_TIME = datetime(2000, 1, 1, 0, 0, 0)


def parse_server_log_incremental(log_file_path, exp_id, start_offset=0, is_hpc=False):
    """
    Parse server log file incrementally from a given offset.

    Args:
        log_file_path: Full path to the server log file
        exp_id: Experiment ID
        start_offset: Byte offset to start reading from
        is_hpc: Boolean flag indicating if this is an HPC experiment (uses different log format)

    Returns:
        tuple: (new_offset, metrics_dict)
            - new_offset: New byte offset after reading
            - metrics_dict: Dictionary with aggregated metrics
    """
    if not os.path.exists(log_file_path):
        return start_offset, {}

    # Data structures for aggregation
    daily_data = defaultdict(
        lambda: defaultdict(
            lambda: {"count": 0, "duration": 0.0, "times": [], "simulation_time": 0.0}
        )
    )
    hourly_data = defaultdict(
        lambda: defaultdict(
            lambda: {"count": 0, "duration": 0.0, "times": [], "simulation_time": 0.0}
        )
    )

    try:
        with open(log_file_path, "r") as f:
            # Seek to the start offset
            f.seek(start_offset)

            line_count = 0
            parsed_count = 0
            hpc_summary_count = 0
            hpc_daily_count = 0
            hpc_hourly_count = 0
            errors = []

            for line in f:
                line_count += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    # Parse JSON - log entries should already be properly formatted
                    log_entry = json.loads(line)
                    parsed_count += 1

                    if is_hpc:
                        # HPC server log format: individual request entries
                        # Format: {"request_id": "...", "client_name": "dsf", "path": "get_unreplied_mentions",
                        #          "status_code": 200, "duration": 0.0008, "time": "2026-01-19T12:54:00.784189+00:00",
                        #          "tid": "...", "day": 1, "hour": 3}

                        # Extract required fields
                        day = log_entry.get("day")
                        hour = log_entry.get("hour")
                        duration = float(log_entry.get("duration", 0))
                        path = log_entry.get("path", "unknown")

                        # Skip entries without day field
                        if day is None:
                            if line_count <= 5:
                                errors.append(f"Line {line_count}: Missing day field")
                            continue

                        # Parse timestamp if available for time tracking
                        time_str = log_entry.get("time", "")
                        time_obj = None
                        if time_str:
                            try:
                                # Handle ISO format with timezone
                                if "T" in time_str:
                                    # Remove timezone info for parsing
                                    time_str_clean = time_str.split("+")[0].split("Z")[
                                        0
                                    ]
                                    time_obj = datetime.fromisoformat(time_str_clean)
                                else:
                                    time_obj = datetime.strptime(
                                        time_str, "%Y-%m-%d %H:%M:%S"
                                    )
                            except (ValueError, AttributeError):
                                pass

                        # Aggregate by day
                        if day is not None:
                            hpc_daily_count += 1
                            daily_data[day][path]["count"] += 1
                            daily_data[day][path]["duration"] += duration
                            # For simulation_time, we'll calculate from timestamp differences later
                            if time_obj:
                                daily_data[day][path]["times"].append(time_obj)

                        # Aggregate by day-hour
                        if day is not None and hour is not None:
                            hpc_hourly_count += 1
                            key = f"{day}-{hour}"
                            hourly_data[key][path]["count"] += 1
                            hourly_data[key][path]["duration"] += duration
                            # For simulation_time, we'll calculate from timestamp differences later
                            if time_obj:
                                hourly_data[key][path]["times"].append(time_obj)
                    else:
                        # Standard format: individual log entries per request
                        path = log_entry.get("path", "unknown")
                        duration = float(log_entry.get("duration", 0))
                        day = log_entry.get("day")
                        hour = log_entry.get("hour")
                        time_str = log_entry.get("time", "")

                        # Parse timestamp if available
                        time_obj = None
                        if time_str:
                            try:
                                time_obj = datetime.strptime(
                                    time_str, "%Y-%m-%d %H:%M:%S"
                                )
                            except ValueError:
                                pass

                        # Aggregate by day
                        if day is not None:
                            daily_data[day][path]["count"] += 1
                            daily_data[day][path]["duration"] += duration
                            if time_obj:
                                daily_data[day][path]["times"].append(time_obj)

                        # Aggregate by day-hour
                        if day is not None and hour is not None:
                            key = f"{day}-{hour}"
                            hourly_data[key][path]["count"] += 1
                            hourly_data[key][path]["duration"] += duration
                            if time_obj:
                                hourly_data[key][path]["times"].append(time_obj)

                except json.JSONDecodeError as e:
                    # Skip invalid JSON lines
                    if line_count <= 5:
                        errors.append(
                            f"Line {line_count}: JSON decode error: {str(e)[:100]}"
                        )
                    continue

            # Get the new offset
            new_offset = f.tell()

            # Print debug info for HPC experiments
            if is_hpc:
                print(f"\n=== HPC Log Parsing Debug ({log_file_path}) ===")
                print(f"Total lines read: {line_count}")
                print(f"Successfully parsed JSON: {parsed_count}")
                print(f"HPC summary entries found: {hpc_summary_count}")
                print(f"Daily entries processed: {hpc_daily_count}")
                print(f"Hourly entries processed: {hpc_hourly_count}")
                print(f"Daily data keys: {list(daily_data.keys())}")
                print(f"Hourly data keys: {list(hourly_data.keys())[:10]}")
                if errors:
                    print(f"Errors (first 10): {errors[:10]}")
                print("==========================================\n")

    except Exception as e:
        logger.error(f"Error reading server log file: {e}", exc_info=True)
        print(f"CRITICAL ERROR reading log file: {e}")
        return start_offset, {}

    # Update database with new metrics
    for day, paths in daily_data.items():
        for path, data in paths.items():
            # Calculate simulation time from timestamp differences
            if data["times"]:
                min_time = min(data["times"])
                max_time = max(data["times"])
                # Simulation time is the time span covered by this aggregation period
                simulation_time = (max_time - min_time).total_seconds()
            else:
                min_time = None
                max_time = None
                simulation_time = 0

            # For HPC, store actual simulation time; for synthetic timestamps, use it
            if is_hpc:
                # For HPC: min_time and max_time are from actual timestamps
                # simulation_time is the difference (real elapsed time in simulation)
                pass
            else:
                # For standard experiments: simulation_time not used, keep existing logic
                simulation_time = 0

            # Check if record exists
            metric = ServerLogMetrics.query.filter_by(
                exp_id=exp_id, aggregation_level="daily", day=day, hour=None, path=path
            ).first()

            if metric:
                # Update existing record
                # For HPC, values are absolute (replace); for standard, they're deltas (accumulate)
                if is_hpc:
                    metric.call_count = data["count"]
                    metric.total_duration = data["duration"]
                else:
                    metric.call_count += data["count"]
                    metric.total_duration += data["duration"]
                if min_time and (not metric.min_time or min_time < metric.min_time):
                    metric.min_time = min_time
                if max_time and (not metric.max_time or max_time > metric.max_time):
                    metric.max_time = max_time
            else:
                # Create new record
                metric = ServerLogMetrics(
                    exp_id=exp_id,
                    aggregation_level="daily",
                    day=day,
                    hour=None,
                    path=path,
                    call_count=data["count"],
                    total_duration=data["duration"],
                    min_time=min_time,
                    max_time=max_time,
                )
                db.session.add(metric)

    for key, paths in hourly_data.items():
        day, hour = key.split("-")
        day = int(day)
        hour = int(hour)

        for path, data in paths.items():
            # Calculate simulation time from timestamp differences
            if data["times"]:
                min_time = min(data["times"])
                max_time = max(data["times"])
                # Simulation time is the time span covered by this aggregation period
                simulation_time = (max_time - min_time).total_seconds()
            else:
                min_time = None
                max_time = None
                simulation_time = 0

            # Check if record exists
            metric = ServerLogMetrics.query.filter_by(
                exp_id=exp_id, aggregation_level="hourly", day=day, hour=hour, path=path
            ).first()

            if metric:
                # Update existing record
                # For HPC, values are absolute (replace); for standard, they're deltas (accumulate)
                if is_hpc:
                    metric.call_count = data["count"]
                    metric.total_duration = data["duration"]
                else:
                    metric.call_count += data["count"]
                    metric.total_duration += data["duration"]
                if min_time and (not metric.min_time or min_time < metric.min_time):
                    metric.min_time = min_time
                if max_time and (not metric.max_time or max_time > metric.max_time):
                    metric.max_time = max_time
            else:
                # Create new record
                metric = ServerLogMetrics(
                    exp_id=exp_id,
                    aggregation_level="hourly",
                    day=day,
                    hour=hour,
                    path=path,
                    call_count=data["count"],
                    total_duration=data["duration"],
                    min_time=min_time,
                    max_time=max_time,
                )
                db.session.add(metric)

    _commit_with_retry(db.session)

    # Verify database writes for HPC experiments
    if is_hpc:
        daily_count = ServerLogMetrics.query.filter_by(
            exp_id=exp_id, aggregation_level="daily"
        ).count()
        hourly_count = ServerLogMetrics.query.filter_by(
            exp_id=exp_id, aggregation_level="hourly"
        ).count()
        print(f"\n=== HPC Database Write Verification (exp_id={exp_id}) ===")
        print(f"Daily records in database: {daily_count}")
        print(f"Hourly records in database: {hourly_count}")
        print("======================================================\n")

    return new_offset, {"daily": daily_data, "hourly": hourly_data}


def parse_client_log_incremental(
    log_file_path, exp_id, client_id, start_offset=0, is_hpc=False
):
    """
    Parse client log file incrementally from a given offset.

    Args:
        log_file_path: Full path to the client log file
        exp_id: Experiment ID
        client_id: Client ID
        start_offset: Byte offset to start reading from
        is_hpc: Boolean flag indicating if this is an HPC experiment (uses different log format)

    Returns:
        tuple: (new_offset, metrics_dict)
            - new_offset: New byte offset after reading
            - metrics_dict: Dictionary with aggregated metrics
    """
    if not os.path.exists(log_file_path):
        return start_offset, {}

    # Data structures for aggregation
    daily_data = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "execution_time": 0.0})
    )
    hourly_data = defaultdict(
        lambda: defaultdict(lambda: {"count": 0, "execution_time": 0.0})
    )

    # Track max day/hour for HPC client_execution updates
    max_day = -1
    max_hour = -1

    # Track stats for logging
    total_lines = 0
    parsed_lines = 0
    hpc_hourly_count = 0
    hpc_daily_count = 0

    try:
        with open(log_file_path, "r") as f:
            # Seek to the start offset
            f.seek(start_offset)

            for line in f:
                total_lines += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    log_entry = json.loads(line)
                    parsed_lines += 1

                    if is_hpc:
                        # HPC format: use summary entries (hourly and daily)
                        # Format: {"time": "...", "summary_type": "hourly", "day": 1, "slot": 8,
                        #          "total_execution_time_seconds": 0.0246,
                        #          "actions_by_method": {"follow": 1, "post": 2}}
                        summary_type = log_entry.get("summary_type")
                        if summary_type not in ("hourly", "daily"):
                            continue

                        if summary_type == "hourly":
                            hpc_hourly_count += 1
                        elif summary_type == "daily":
                            hpc_daily_count += 1

                        day = log_entry.get("day")
                        if day is None:
                            continue  # Skip entries without a valid day

                        total_execution_time = float(
                            log_entry.get("total_execution_time_seconds", 0)
                        )
                        actions_by_method = log_entry.get("actions_by_method", {})

                        # Calculate time per action once for proportional distribution
                        total_actions = (
                            sum(actions_by_method.values()) if actions_by_method else 0
                        )
                        time_per_action = (
                            (total_execution_time / total_actions)
                            if total_actions > 0
                            else 0
                        )

                        # For hourly summaries, get slot (hour) once before loop
                        hour = (
                            log_entry.get("slot") if summary_type == "hourly" else None
                        )

                        # Track max day/hour for client_execution updates
                        if summary_type == "hourly" and hour is not None:
                            if day > max_day or (day == max_day and hour > max_hour):
                                max_day = day
                                max_hour = hour

                        # Process each action method
                        for method_name, count in actions_by_method.items():
                            # Calculate proportional execution time for this method
                            method_time = time_per_action * count

                            # For daily summaries, aggregate by day
                            # HPC summaries contain absolute values, not deltas
                            if summary_type == "daily":
                                daily_data[day][method_name]["count"] = count
                                daily_data[day][method_name][
                                    "execution_time"
                                ] = method_time

                            # For hourly summaries, aggregate by day-hour
                            elif summary_type == "hourly" and hour is not None:
                                key = f"{day}-{hour}"
                                hourly_data[key][method_name]["count"] = count
                                hourly_data[key][method_name][
                                    "execution_time"
                                ] = method_time
                    else:
                        # Standard format: individual log entries per method call
                        method_name = log_entry.get("method_name", "unknown")
                        execution_time = float(
                            log_entry.get("execution_time_seconds", 0)
                        )
                        day = log_entry.get("day")
                        hour = log_entry.get("hour")

                        # Aggregate by day
                        if day is not None:
                            daily_data[day][method_name]["count"] += 1
                            daily_data[day][method_name][
                                "execution_time"
                            ] += execution_time

                        # Aggregate by day-hour
                        if day is not None and hour is not None:
                            key = f"{day}-{hour}"
                            hourly_data[key][method_name]["count"] += 1
                            hourly_data[key][method_name][
                                "execution_time"
                            ] += execution_time

                except json.JSONDecodeError:
                    # Skip invalid JSON lines
                    continue

            # Get the new offset
            new_offset = f.tell()

    except Exception as e:
        logger.error(f"Error reading client log file: {e}", exc_info=True)
        return start_offset, {}

    # Log parsing summary for HPC
    if is_hpc:
        logger.info(
            f"HPC log parsing for client {client_id}: total_lines={total_lines}, "
            f"parsed_lines={parsed_lines}, hourly_summaries={hpc_hourly_count}, "
            f"daily_summaries={hpc_daily_count}, max_day={max_day}, max_hour={max_hour}"
        )

    # Update database with new metrics
    for day, methods in daily_data.items():
        for method_name, data in methods.items():
            # Check if record exists
            metric = ClientLogMetrics.query.filter_by(
                exp_id=exp_id,
                client_id=client_id,
                aggregation_level="daily",
                day=day,
                hour=None,
                method_name=method_name,
            ).first()

            if metric:
                # Update existing record
                # For HPC, values are absolute (replace); for standard, they're deltas (accumulate)
                if is_hpc:
                    metric.call_count = data["count"]
                    metric.total_execution_time = data["execution_time"]
                else:
                    metric.call_count += data["count"]
                    metric.total_execution_time += data["execution_time"]
            else:
                # Create new record
                metric = ClientLogMetrics(
                    exp_id=exp_id,
                    client_id=client_id,
                    aggregation_level="daily",
                    day=day,
                    hour=None,
                    method_name=method_name,
                    call_count=data["count"],
                    total_execution_time=data["execution_time"],
                )
                db.session.add(metric)

    for key, methods in hourly_data.items():
        day, hour = key.split("-")
        day = int(day)
        hour = int(hour)

        for method_name, data in methods.items():
            # Check if record exists
            metric = ClientLogMetrics.query.filter_by(
                exp_id=exp_id,
                client_id=client_id,
                aggregation_level="hourly",
                day=day,
                hour=hour,
                method_name=method_name,
            ).first()

            if metric:
                # Update existing record
                # For HPC, values are absolute (replace); for standard, they're deltas (accumulate)
                if is_hpc:
                    metric.call_count = data["count"]
                    metric.total_execution_time = data["execution_time"]
                else:
                    metric.call_count += data["count"]
                    metric.total_execution_time += data["execution_time"]
            else:
                # Create new record
                metric = ClientLogMetrics(
                    exp_id=exp_id,
                    client_id=client_id,
                    aggregation_level="hourly",
                    day=day,
                    hour=hour,
                    method_name=method_name,
                    call_count=data["count"],
                    total_execution_time=data["execution_time"],
                )
                db.session.add(metric)

    _commit_with_retry(db.session)

    # For HPC, update Client_Execution with progress information
    if is_hpc and max_day >= 0 and max_hour >= 0:
        logger.info(
            f"HPC: Updating Client_Execution for client {client_id} with max_day={max_day}, max_hour={max_hour}"
        )
        try:
            client_exec = Client_Execution.query.filter_by(client_id=client_id).first()
            if client_exec:
                # Update last active day and hour
                client_exec.last_active_day = max_day
                client_exec.last_active_hour = max_hour

                # Update elapsed_time (current round, 1-indexed)
                # day 0, hour 0 = round 1
                client_exec.elapsed_time = max_day * 24 + max_hour + 1

                logger.info(
                    f"HPC: Updated Client_Execution for client {client_id}: "
                    f"elapsed_time={client_exec.elapsed_time}, expected={client_exec.expected_duration_rounds}"
                )

                # Check if simulation is complete
                current_round = client_exec.elapsed_time
                if current_round >= client_exec.expected_duration_rounds:
                    # Get the client and mark as stopped
                    client = Client.query.filter_by(id=client_id).first()
                    if client and client.status == 1:
                        client.status = 0
                        logger.info(
                            f"HPC client {client_id} simulation complete at round {current_round}, marking as stopped"
                        )

                        # Commit the client status change before checking other clients
                        _commit_with_retry(db.session)

                        # Check if all clients for this experiment are now complete
                        exp_id = client.id_exp

                        # Get the experiment first to check status
                        exp = Exps.query.filter_by(idexp=exp_id).first()

                        # Only proceed with auto-stop if experiment is not already completed
                        # This prevents race conditions when multiple clients finish simultaneously
                        if exp and exp.exp_status != "completed":
                            all_clients = Client.query.filter_by(id_exp=exp_id).all()

                            # Check if all clients are stopped (status = 0)
                            all_stopped = all(c.status == 0 for c in all_clients)

                            if all_stopped:
                                logger.info(
                                    f"All clients for HPC experiment {exp_id} are complete. Stopping server and updating status."
                                )

                                try:
                                    # Import here to avoid circular import
                                    from y_web.src.hpc.client import stop_hpc_client
                                    from y_web.src.hpc.server import stop_hpc_server

                                    # Stop all clients that might still have running processes
                                    for c in all_clients:
                                        if c.pid:
                                            try:
                                                logger.info(
                                                    f"Stopping HPC client {c.id} (PID: {c.pid})"
                                                )
                                                stop_hpc_client(c)
                                            except Exception as e:
                                                logger.error(
                                                    f"Error stopping HPC client {c.id}: {e}",
                                                    exc_info=True,
                                                )

                                    # Stop the server
                                    try:
                                        logger.info(
                                            f"Stopping HPC server for experiment {exp_id}"
                                        )
                                        stop_hpc_server(exp_id)
                                    except Exception as e:
                                        logger.error(
                                            f"Error stopping HPC server for experiment {exp_id}: {e}",
                                            exc_info=True,
                                        )

                                    # Update experiment status to completed
                                    # Re-query to get fresh instance
                                    exp = Exps.query.filter_by(idexp=exp_id).first()
                                    if exp:
                                        exp.exp_status = "completed"
                                        _commit_with_retry(db.session)
                                        logger.info(
                                            f"Experiment {exp_id} marked as completed"
                                        )

                                except Exception as e:
                                    logger.error(
                                        f"Error in auto-stop flow for HPC experiment {exp_id}: {e}",
                                        exc_info=True,
                                    )
                    else:
                        # Client was not running, just commit the execution update
                        _commit_with_retry(db.session)
                else:
                    # Client not complete yet, just commit the execution update
                    _commit_with_retry(db.session)
            else:
                logger.warning(
                    f"HPC: No Client_Execution record found for client {client_id}"
                )
        except Exception as e:
            logger.error(
                f"Error updating client_execution for HPC client {client_id}: {e}",
                exc_info=True,
            )
    elif is_hpc:
        logger.warning(
            f"HPC: Not updating Client_Execution for client {client_id} because "
            f"max_day={max_day}, max_hour={max_hour} (both must be >= 0)"
        )

    return new_offset, {
        "daily": daily_data,
        "hourly": hourly_data,
        "max_day": max_day,
        "max_hour": max_hour,
    }


def get_rotating_log_files(base_log_path):
    """
    Get all rotating log files for a given base log path.

    Rotating logs are named like: _server.log, _server.log.1, _server.log.2, etc.
    Higher numbers are older files. We return them sorted oldest to newest
    so they are processed in chronological order.

    Args:
        base_log_path: Full path to the main log file (e.g., /path/to/_server.log)

    Returns:
        list: List of log file paths sorted oldest to newest
    """
    log_files = []
    log_dir = os.path.dirname(base_log_path)
    base_name = os.path.basename(base_log_path)

    if not os.path.exists(log_dir):
        return log_files

    # Find all rotating log files
    for filename in os.listdir(log_dir):
        if filename == base_name:
            # Main log file (newest)
            log_files.append((0, os.path.join(log_dir, filename)))
        elif filename.startswith(base_name + "."):
            # Rotating log file (e.g., _server.log.1, _server.log.2)
            try:
                suffix = filename[len(base_name) + 1 :]
                if suffix.isdigit():
                    log_files.append((int(suffix), os.path.join(log_dir, filename)))
            except (ValueError, IndexError):
                pass

    # Sort by suffix number descending (highest = oldest first)
    # This ensures we process logs in chronological order (oldest to newest)
    log_files.sort(key=lambda x: x[0], reverse=True)

    return [path for _, path in log_files]


def has_server_log_files(base_log_path):
    """
    Check if any server log files exist (main or rotated).

    Args:
        base_log_path: Full path to the main log file (e.g., /path/to/_server.log)

    Returns:
        bool: True if any log files exist, False otherwise
    """
    return len(get_rotating_log_files(base_log_path)) > 0
