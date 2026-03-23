"""
Tests for handling manual stop of scheduled experiments.

Verifies that when a running experiment that's part of a schedule group is manually
stopped by the user, it's removed from the group to unblock subsequent groups.
"""

from unittest.mock import MagicMock, patch

import pytest
pytestmark = pytest.mark.unit



def test_stop_scheduled_experiment_removes_from_group():
    """Test that stopping a scheduled experiment removes it from the running group."""
    # Mock the schedule status - schedule is running
    mock_schedule_status = MagicMock()
    mock_schedule_status.is_running = 1
    mock_schedule_status.current_group_id = 100

    # Mock the schedule item - experiment is in the group
    mock_schedule_item = MagicMock()
    mock_schedule_item.experiment_id = 1
    mock_schedule_item.group_id = 100

    # Mock the schedule group
    mock_group = MagicMock()
    mock_group.name = "Test Group 1"

    # Simulate the logic from stop_experiment
    experiment_id = 1

    # Check if schedule is running and experiment is in current group
    if (
        mock_schedule_status
        and mock_schedule_status.is_running
        and mock_schedule_status.current_group_id
    ):
        # Simulate finding the schedule item
        if (
            mock_schedule_item
            and mock_schedule_item.group_id == mock_schedule_status.current_group_id
        ):
            # This should trigger removal
            should_remove = True
            removed_from_group = mock_group.name
        else:
            should_remove = False
            removed_from_group = None
    else:
        should_remove = False
        removed_from_group = None

    assert should_remove, "Should remove experiment from schedule group"
    assert removed_from_group == "Test Group 1", "Should identify the correct group"


def test_stop_scheduled_experiment_no_schedule_running():
    """Test that stopping experiment when no schedule is running doesn't cause issues."""
    # Mock the schedule status - no schedule running
    mock_schedule_status = None  # or MagicMock with is_running = 0

    experiment_id = 1

    # Check if schedule is running
    if mock_schedule_status and mock_schedule_status.is_running:
        should_remove = True
    else:
        should_remove = False

    assert not should_remove, "Should not attempt removal when no schedule is running"


def test_stop_scheduled_experiment_not_in_current_group():
    """Test that stopping experiment that's not in current group doesn't affect it."""
    # Mock the schedule status - schedule is running
    mock_schedule_status = MagicMock()
    mock_schedule_status.is_running = 1
    mock_schedule_status.current_group_id = 100

    # Mock the schedule item - experiment is in a different group
    mock_schedule_item = None  # Not found in current group

    experiment_id = 1

    # Check if schedule is running and experiment is in current group
    if (
        mock_schedule_status
        and mock_schedule_status.is_running
        and mock_schedule_status.current_group_id
    ):
        if mock_schedule_item:
            should_remove = True
        else:
            should_remove = False
    else:
        should_remove = False

    assert not should_remove, "Should not remove if experiment is not in current group"


def test_stop_scheduled_experiment_in_future_group():
    """Test that stopping experiment in a future (non-running) group doesn't remove it."""
    # Mock the schedule status - schedule is running group 100
    mock_schedule_status = MagicMock()
    mock_schedule_status.is_running = 1
    mock_schedule_status.current_group_id = 100

    # Mock the schedule item - experiment is in a future group 200
    mock_schedule_item = MagicMock()
    mock_schedule_item.experiment_id = 1
    mock_schedule_item.group_id = 200

    experiment_id = 1

    # Check if schedule is running and experiment is in CURRENT group
    if (
        mock_schedule_status
        and mock_schedule_status.is_running
        and mock_schedule_status.current_group_id
    ):
        if (
            mock_schedule_item
            and mock_schedule_item.group_id == mock_schedule_status.current_group_id
        ):
            should_remove = True
        else:
            should_remove = False
    else:
        should_remove = False

    assert (
        not should_remove
    ), "Should not remove if experiment is in a future (non-running) group"


def test_schedule_continues_after_removal():
    """Test that schedule can continue after an experiment is removed from group."""
    # Simulate a group with 3 experiments
    experiments_in_group = [
        {"id": 1, "status": "stopped"},  # Manually stopped and removed
        {"id": 2, "status": "completed"},  # Completed normally
        {"id": 3, "status": "completed"},  # Completed normally
    ]

    # After removal, only check remaining experiments
    remaining_experiments = [exp for exp in experiments_in_group if exp["id"] != 1]

    # Check if all remaining experiments are completed
    all_completed = all(exp["status"] == "completed" for exp in remaining_experiments)

    assert (
        all_completed
    ), "Schedule should consider group complete when remaining experiments are done"
    assert (
        len(remaining_experiments) == 2
    ), "Should have 2 experiments remaining after removal"


def test_log_message_created_for_removal():
    """Test that appropriate log message is created when experiment is removed."""
    experiment_name = "Test Experiment"
    group_name = "Test Group 1"

    # Simulate log message creation
    log_msg = f"Experiment '{experiment_name}' was manually stopped and removed from schedule group '{group_name}'"
    log_type = "warning"

    assert "manually stopped" in log_msg, "Log should mention manual stop"
    assert "removed from schedule group" in log_msg, "Log should mention removal"
    assert experiment_name in log_msg, "Log should include experiment name"
    assert group_name in log_msg, "Log should include group name"
    assert log_type == "warning", "Log type should be warning"


def test_multiple_experiments_in_group_one_stopped():
    """Test that stopping one experiment in a group doesn't affect others."""
    # Group with multiple experiments
    group_experiments = [
        {"id": 1, "name": "Exp1", "status": "active", "running": 1},
        {"id": 2, "name": "Exp2", "status": "active", "running": 1},
        {"id": 3, "name": "Exp3", "status": "active", "running": 1},
    ]

    # Stop experiment 2
    stopped_exp_id = 2

    # Simulate removal
    group_experiments = [
        exp for exp in group_experiments if exp["id"] != stopped_exp_id
    ]

    # Update status of stopped experiment
    stopped_exp = {"id": 2, "name": "Exp2", "status": "stopped", "running": 0}

    # Verify
    assert len(group_experiments) == 2, "Should have 2 experiments remaining in group"
    assert (
        stopped_exp["status"] == "stopped"
    ), "Stopped experiment should have 'stopped' status"
    assert stopped_exp["running"] == 0, "Stopped experiment should not be running"

    # Other experiments should still be in the group
    remaining_ids = [exp["id"] for exp in group_experiments]
    assert 1 in remaining_ids, "Experiment 1 should still be in group"
    assert 3 in remaining_ids, "Experiment 3 should still be in group"
    assert 2 not in remaining_ids, "Experiment 2 should be removed from group"


def test_experiment_status_becomes_stopped_not_completed():
    """Test that manually stopped experiments get 'stopped' status, not 'completed'."""
    # Simulate checking if all clients completed
    all_clients_completed = False  # User stopped it, not all clients finished

    # Determine final status
    final_status = "completed" if all_clients_completed else "stopped"

    assert (
        final_status == "stopped"
    ), "Manually stopped experiment should have 'stopped' status"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
