"""
Utility functions for incremental log reading and metric aggregation.

This module provides functionality to:
- Track file offsets for incremental reading
- Parse log files and extract metrics
- Aggregate metrics in database tables
"""

import json
import os
from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_

from y_web import db
from y_web.models import (
    ClientLogMetrics,
    LogFileOffset,
    ServerLogMetrics,
)


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
    offset_record = (
        LogFileOffset.query.filter_by(
            exp_id=exp_id,
            log_file_type=log_file_type,
            file_path=file_path,
            client_id=client_id,
        )
        .first()
    )

    if offset_record:
        return offset_record.last_offset
    return 0


def update_log_file_offset(exp_id, log_file_type, file_path, new_offset, client_id=None):
    """
    Update the last read offset for a log file.

    Args:
        exp_id: Experiment ID
        log_file_type: Type of log file ('server' or 'client')
        file_path: Relative path to the log file
        new_offset: New offset in bytes
        client_id: Client ID (only for client logs)
    """
    offset_record = (
        LogFileOffset.query.filter_by(
            exp_id=exp_id,
            log_file_type=log_file_type,
            file_path=file_path,
            client_id=client_id,
        )
        .first()
    )

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

    db.session.commit()


def parse_server_log_incremental(log_file_path, exp_id, start_offset=0):
    """
    Parse server log file incrementally from a given offset.

    Args:
        log_file_path: Full path to the server log file
        exp_id: Experiment ID
        start_offset: Byte offset to start reading from

    Returns:
        tuple: (new_offset, metrics_dict)
            - new_offset: New byte offset after reading
            - metrics_dict: Dictionary with aggregated metrics
    """
    if not os.path.exists(log_file_path):
        return start_offset, {}

    # Data structures for aggregation
    daily_data = defaultdict(lambda: defaultdict(lambda: {"count": 0, "duration": 0.0, "times": []}))
    hourly_data = defaultdict(lambda: defaultdict(lambda: {"count": 0, "duration": 0.0, "times": []}))

    try:
        with open(log_file_path, "r") as f:
            # Seek to the start offset
            f.seek(start_offset)

            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    # Replace single quotes with double quotes for valid JSON
                    line = line.replace("'", '"')
                    log_entry = json.loads(line)

                    path = log_entry.get("path", "unknown")
                    duration = float(log_entry.get("duration", 0))
                    day = log_entry.get("day")
                    hour = log_entry.get("hour")
                    time_str = log_entry.get("time", "")

                    # Parse timestamp if available
                    time_obj = None
                    if time_str:
                        try:
                            time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
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

                except json.JSONDecodeError:
                    # Skip invalid JSON lines
                    continue

            # Get the new offset
            new_offset = f.tell()

    except Exception as e:
        print(f"Error reading server log file: {e}")
        return start_offset, {}

    # Update database with new metrics
    for day, paths in daily_data.items():
        for path, data in paths.items():
            min_time = min(data["times"]) if data["times"] else None
            max_time = max(data["times"]) if data["times"] else None

            # Check if record exists
            metric = ServerLogMetrics.query.filter_by(
                exp_id=exp_id, aggregation_level="daily", day=day, hour=None, path=path
            ).first()

            if metric:
                # Update existing record
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
            min_time = min(data["times"]) if data["times"] else None
            max_time = max(data["times"]) if data["times"] else None

            # Check if record exists
            metric = ServerLogMetrics.query.filter_by(
                exp_id=exp_id, aggregation_level="hourly", day=day, hour=hour, path=path
            ).first()

            if metric:
                # Update existing record
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

    db.session.commit()

    return new_offset, {"daily": daily_data, "hourly": hourly_data}


def parse_client_log_incremental(log_file_path, exp_id, client_id, start_offset=0):
    """
    Parse client log file incrementally from a given offset.

    Args:
        log_file_path: Full path to the client log file
        exp_id: Experiment ID
        client_id: Client ID
        start_offset: Byte offset to start reading from

    Returns:
        tuple: (new_offset, metrics_dict)
            - new_offset: New byte offset after reading
            - metrics_dict: Dictionary with aggregated metrics
    """
    if not os.path.exists(log_file_path):
        return start_offset, {}

    # Data structures for aggregation
    daily_data = defaultdict(lambda: defaultdict(lambda: {"count": 0, "execution_time": 0.0}))
    hourly_data = defaultdict(lambda: defaultdict(lambda: {"count": 0, "execution_time": 0.0}))

    try:
        with open(log_file_path, "r") as f:
            # Seek to the start offset
            f.seek(start_offset)

            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    log_entry = json.loads(line)

                    method_name = log_entry.get("method_name", "unknown")
                    execution_time = float(log_entry.get("execution_time_seconds", 0))
                    day = log_entry.get("day")
                    hour = log_entry.get("hour")

                    # Aggregate by day
                    if day is not None:
                        daily_data[day][method_name]["count"] += 1
                        daily_data[day][method_name]["execution_time"] += execution_time

                    # Aggregate by day-hour
                    if day is not None and hour is not None:
                        key = f"{day}-{hour}"
                        hourly_data[key][method_name]["count"] += 1
                        hourly_data[key][method_name]["execution_time"] += execution_time

                except json.JSONDecodeError:
                    # Skip invalid JSON lines
                    continue

            # Get the new offset
            new_offset = f.tell()

    except Exception as e:
        print(f"Error reading client log file: {e}")
        return start_offset, {}

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

    db.session.commit()

    return new_offset, {"daily": daily_data, "hourly": hourly_data}


def update_server_log_metrics(exp_id, log_file_path):
    """
    Update server log metrics by reading new log entries.

    Args:
        exp_id: Experiment ID
        log_file_path: Full path to the server log file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get relative file path (for storage in database)
        file_name = os.path.basename(log_file_path)

        # Get last offset
        last_offset = get_log_file_offset(exp_id, "server", file_name)

        # Parse log file incrementally
        new_offset, metrics = parse_server_log_incremental(
            log_file_path, exp_id, last_offset
        )

        # Update offset
        if new_offset > last_offset:
            update_log_file_offset(exp_id, "server", file_name, new_offset)

        return True

    except Exception as e:
        print(f"Error updating server log metrics: {e}")
        return False


def update_client_log_metrics(exp_id, client_id, log_file_path):
    """
    Update client log metrics by reading new log entries.

    Args:
        exp_id: Experiment ID
        client_id: Client ID
        log_file_path: Full path to the client log file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get relative file path (for storage in database)
        file_name = os.path.basename(log_file_path)

        # Get last offset
        last_offset = get_log_file_offset(exp_id, "client", file_name, client_id)

        # Parse log file incrementally
        new_offset, metrics = parse_client_log_incremental(
            log_file_path, exp_id, client_id, last_offset
        )

        # Update offset
        if new_offset > last_offset:
            update_log_file_offset(exp_id, "client", file_name, new_offset, client_id)

        return True

    except Exception as e:
        print(f"Error updating client log metrics: {e}")
        return False
