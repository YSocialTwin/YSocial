"""
Phase D — hpc/log_metrics.py log processing tests.

Covers the two functions that gate the "experiment complete" detection:

* get_latest_hourly_summary_from_client_log  — parses the last hourly summary
* update_client_execution_from_log           — writes the summary to the DB

Both functions are tested with real file fixtures (``tmp_path``) and mocked DB
sessions so that no database is required.
"""

import json

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_HOURLY_ENTRY_1 = json.dumps(
    {"summary_type": "hourly", "day": 0, "slot": 5, "agents": 10}
)
_HOURLY_ENTRY_2 = json.dumps(
    {"summary_type": "hourly", "day": 1, "slot": 20, "agents": 8}
)
_NON_HOURLY = json.dumps({"summary_type": "daily", "day": 0, "total": 100})
_GARBAGE_LINE = "not-json-at-all"


# ---------------------------------------------------------------------------
# get_latest_hourly_summary_from_client_log
# ---------------------------------------------------------------------------


def test_get_latest_hourly_summary_returns_none_for_missing_file():
    from y_web.src.hpc.log_metrics import get_latest_hourly_summary_from_client_log

    result = get_latest_hourly_summary_from_client_log("/no/such/file.log")
    assert result is None


def test_get_latest_hourly_summary_empty_file_returns_none(tmp_path):
    from y_web.src.hpc.log_metrics import get_latest_hourly_summary_from_client_log

    log_file = tmp_path / "client.log"
    log_file.write_text("")
    assert get_latest_hourly_summary_from_client_log(str(log_file)) is None


def test_get_latest_hourly_summary_parses_last_entry(tmp_path):
    from y_web.src.hpc.log_metrics import get_latest_hourly_summary_from_client_log

    log_file = tmp_path / "client.log"
    log_file.write_text("\n".join([_HOURLY_ENTRY_1, _HOURLY_ENTRY_2, _NON_HOURLY]))

    result = get_latest_hourly_summary_from_client_log(str(log_file))

    assert result is not None
    # The *last* hourly entry is HOURLY_ENTRY_2 (day=1, slot=20)
    assert result["day"] == 1
    assert result["slot"] == 20


def test_get_latest_hourly_summary_calculates_elapsed_time(tmp_path):
    from y_web.src.hpc.log_metrics import get_latest_hourly_summary_from_client_log

    log_file = tmp_path / "client.log"
    log_file.write_text(_HOURLY_ENTRY_2)  # day=1, slot=20

    result = get_latest_hourly_summary_from_client_log(str(log_file))

    # elapsed_time = day * 24 + slot + 1  →  1*24 + 20 + 1 = 45
    assert result["elapsed_time"] == 45


def test_get_latest_hourly_summary_skips_garbage_lines(tmp_path):
    from y_web.src.hpc.log_metrics import get_latest_hourly_summary_from_client_log

    log_file = tmp_path / "client.log"
    log_file.write_text("\n".join([_GARBAGE_LINE, _HOURLY_ENTRY_1]))

    result = get_latest_hourly_summary_from_client_log(str(log_file))
    assert result is not None
    assert result["day"] == 0
    assert result["slot"] == 5


def test_get_latest_hourly_summary_file_with_only_non_hourly_returns_none(tmp_path):
    from y_web.src.hpc.log_metrics import get_latest_hourly_summary_from_client_log

    log_file = tmp_path / "client.log"
    log_file.write_text(_NON_HOURLY)

    assert get_latest_hourly_summary_from_client_log(str(log_file)) is None


# ---------------------------------------------------------------------------
# update_client_execution_from_log
# ---------------------------------------------------------------------------


def test_update_client_execution_from_log_no_op_on_missing_file(app):
    """Missing log file → function returns False without raising."""
    from y_web.src.hpc.log_metrics import update_client_execution_from_log

    with app.app_context():
        result = update_client_execution_from_log(999, "/no/such/log.log")
    assert result is False


def test_update_client_execution_from_log_marks_progress(app, tmp_path):
    """When a valid log exists, the DB record is updated with day/hour/elapsed."""
    from unittest.mock import MagicMock, patch

    from y_web.src.hpc.log_metrics import update_client_execution_from_log

    log_file = tmp_path / "client.log"
    log_file.write_text(_HOURLY_ENTRY_2)  # day=1, slot=20

    mock_exec = MagicMock()
    mock_exec.last_active_day = None
    mock_exec.last_active_hour = None
    mock_exec.elapsed_time = None

    with app.app_context():
        with (
            patch("y_web.src.hpc.log_metrics.Client_Execution.query") as mock_query,
            patch("y_web.src.hpc.log_metrics._commit_with_retry"),
        ):
            mock_query.filter_by.return_value.first.return_value = mock_exec
            result = update_client_execution_from_log(1, str(log_file))

    assert result is True
    assert mock_exec.last_active_day == 1
    assert mock_exec.last_active_hour == 20
    assert mock_exec.elapsed_time == 45
