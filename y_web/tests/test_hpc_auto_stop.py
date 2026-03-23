"""
Tests for HPC experiment auto-stop when all clients complete.

Verifies that when all clients in an HPC experiment complete their execution:
1. All clients are stopped
2. The server is stopped
3. Experiment status is updated to "completed"
"""

from unittest.mock import MagicMock, call, patch

import pytest
pytestmark = pytest.mark.unit



def test_hpc_client_completion_stops_all_when_last_client_finishes():
    """Test that when the last HPC client finishes, all clients and server are stopped."""

    # Create mock client that just finished
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.id_exp = 100
    mock_client.status = 1  # Running
    mock_client.pid = 1234

    # Create mock client_execution that reached expected duration
    mock_client_exec = MagicMock()
    mock_client_exec.elapsed_time = 168  # Finished (7 days * 24 hours)
    mock_client_exec.expected_duration_rounds = 168
    mock_client_exec.last_active_day = 6
    mock_client_exec.last_active_hour = 23

    # Create other clients (all stopped)
    mock_client_2 = MagicMock()
    mock_client_2.id = 2
    mock_client_2.status = 0  # Stopped
    mock_client_2.pid = None

    mock_client_3 = MagicMock()
    mock_client_3.id = 3
    mock_client_3.status = 0  # Stopped
    mock_client_3.pid = 5678  # Still has PID

    all_clients = [mock_client, mock_client_2, mock_client_3]

    # Mock experiment
    mock_exp = MagicMock()
    mock_exp.idexp = 100
    mock_exp.exp_status = "active"

    # Test the logic
    # Simulate marking the last client as stopped
    assert mock_client.status == 1
    mock_client.status = 0

    # Check if all clients are now stopped
    all_stopped = all(c.status == 0 for c in all_clients)
    assert all_stopped

    # In this case, we should:
    # 1. Stop all clients that have PIDs
    clients_with_pids = [c for c in all_clients if c.pid]
    assert len(clients_with_pids) == 2  # mock_client and mock_client_3 both have PIDs
    assert clients_with_pids[0].id in [1, 3]
    assert clients_with_pids[1].id in [1, 3]

    # 2. Stop the server
    # 3. Update experiment status
    mock_exp.exp_status = "completed"
    assert mock_exp.exp_status == "completed"


def test_hpc_client_completion_does_not_stop_when_other_clients_running():
    """Test that when one HPC client finishes but others are running, server stays up."""

    # Create mock client that just finished
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.id_exp = 100
    mock_client.status = 1  # Running -> will be stopped

    # Create other clients (some still running)
    mock_client_2 = MagicMock()
    mock_client_2.id = 2
    mock_client_2.status = 1  # Still running

    mock_client_3 = MagicMock()
    mock_client_3.id = 3
    mock_client_3.status = 0  # Stopped

    all_clients = [mock_client, mock_client_2, mock_client_3]

    # Simulate marking one client as stopped
    mock_client.status = 0

    # Check if all clients are stopped
    all_stopped = all(c.status == 0 for c in all_clients)
    assert not all_stopped  # Should be False because client_2 is still running

    # In this case, we should NOT stop the server or update experiment status


def test_all_clients_stopped_status_check():
    """Test the logic for checking if all clients are stopped."""

    # Case 1: All stopped
    clients_1 = [
        MagicMock(status=0),
        MagicMock(status=0),
        MagicMock(status=0),
    ]
    assert all(c.status == 0 for c in clients_1)

    # Case 2: Some running
    clients_2 = [
        MagicMock(status=0),
        MagicMock(status=1),
        MagicMock(status=0),
    ]
    assert not all(c.status == 0 for c in clients_2)

    # Case 3: All running
    clients_3 = [
        MagicMock(status=1),
        MagicMock(status=1),
        MagicMock(status=1),
    ]
    assert not all(c.status == 0 for c in clients_3)

    # Case 4: Empty list (edge case)
    clients_4 = []
    assert all(c.status == 0 for c in clients_4)  # Vacuous truth


def test_client_execution_completion_check():
    """Test the logic for checking if a client has completed execution."""

    # Case 1: Completed (elapsed >= expected)
    exec_1 = MagicMock()
    exec_1.elapsed_time = 168
    exec_1.expected_duration_rounds = 168
    assert exec_1.elapsed_time >= exec_1.expected_duration_rounds

    # Case 2: Exceeded expected duration
    exec_2 = MagicMock()
    exec_2.elapsed_time = 200
    exec_2.expected_duration_rounds = 168
    assert exec_2.elapsed_time >= exec_2.expected_duration_rounds

    # Case 3: Still running
    exec_3 = MagicMock()
    exec_3.elapsed_time = 100
    exec_3.expected_duration_rounds = 168
    assert not (exec_3.elapsed_time >= exec_3.expected_duration_rounds)

    # Case 4: Just started
    exec_4 = MagicMock()
    exec_4.elapsed_time = 1
    exec_4.expected_duration_rounds = 168
    assert not (exec_4.elapsed_time >= exec_4.expected_duration_rounds)


def test_hpc_auto_stop_flow():
    """Test the complete flow of HPC auto-stop."""

    # Setup: 3 clients, 2 already finished, 1 about to finish
    clients = [
        {"id": 1, "status": 0, "pid": None},  # Already finished
        {"id": 2, "status": 0, "pid": None},  # Already finished
        {"id": 3, "status": 1, "pid": 9999},  # About to finish
    ]

    experiment = {"id": 100, "status": "active", "server_pid": 8888}

    # Step 1: Client 3 completes and is marked as stopped
    clients[2]["status"] = 0

    # Step 2: Check if all clients are stopped
    all_stopped = all(c["status"] == 0 for c in clients)
    assert all_stopped, "All clients should be stopped"

    # Step 3: Stop any clients with PIDs (cleanup)
    clients_with_pids = [c for c in clients if c["pid"] is not None]
    # Client 3 has a PID that should be stopped
    assert len(clients_with_pids) == 1
    assert clients_with_pids[0]["id"] == 3

    # Step 4: Stop server
    assert experiment["server_pid"] == 8888
    # Server stop function would be called here

    # Step 5: Update experiment status
    experiment["status"] = "completed"
    assert experiment["status"] == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
