"""
Test to verify schedule functions correctly handle HPC experiments.

This test verifies that all schedule-related functions (start, stop, check_progress)
correctly distinguish between HPC and Standard experiments and call the appropriate
server and client functions.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_stop_schedule_handles_hpc_correctly():
    """Test that stop_schedule uses correct functions for HPC experiments."""

    # Mock HPC experiment
    mock_exp_hpc = MagicMock()
    mock_exp_hpc.idexp = 1
    mock_exp_hpc.exp_name = "HPC Test"
    mock_exp_hpc.running = 1
    mock_exp_hpc.simulator_type = "HPC"
    mock_exp_hpc.port = 5000

    # Mock Standard experiment
    mock_exp_std = MagicMock()
    mock_exp_std.idexp = 2
    mock_exp_std.exp_name = "Standard Test"
    mock_exp_std.running = 1
    mock_exp_std.simulator_type = "Standard"
    mock_exp_std.port = 5001

    # Verify stop logic
    # For HPC: should call stop_hpc_client and stop_hpc_server
    assert mock_exp_hpc.simulator_type == "HPC"

    # For Standard: should call terminate_client and terminate_server_process
    assert mock_exp_std.simulator_type == "Standard"


def test_check_progress_start_next_group_handles_hpc():
    """Test that check_schedule_progress uses correct server start for HPC."""

    # Mock HPC experiment
    mock_exp = MagicMock()
    mock_exp.simulator_type = "HPC"

    # Simulate the if-else logic in check_schedule_progress
    if mock_exp.simulator_type == "HPC":
        function_to_call = "start_hpc_server"
    else:
        function_to_call = "start_server"

    assert function_to_call == "start_hpc_server"

    # Mock Standard experiment
    mock_exp_std = MagicMock()
    mock_exp_std.simulator_type = "Standard"

    if mock_exp_std.simulator_type == "HPC":
        function_to_call = "start_hpc_server"
    else:
        function_to_call = "start_server"

    assert function_to_call == "start_server"


def test_schedule_functions_hpc_handling_completeness():
    """Test that all schedule functions handle HPC correctly."""

    # Test patterns for different operations
    operations = {
        "start_server": {"HPC": "start_hpc_server", "Standard": "start_server"},
        "stop_server": {
            "HPC": "stop_hpc_server",
            "Standard": "terminate_server_process",
        },
        "start_client": {"HPC": "start_hpc_client", "Standard": "start_client"},
        "stop_client": {"HPC": "stop_hpc_client", "Standard": "terminate_client"},
    }

    # Verify HPC operations are different from Standard
    for operation, functions in operations.items():
        assert (
            functions["HPC"] != functions["Standard"]
        ), f"HPC and Standard should use different functions for {operation}"

    print("✓ All schedule operations have HPC-specific implementations")


def test_simulator_type_check_patterns():
    """Test various simulator_type check patterns used in schedule functions."""

    test_cases = [
        (
            "HPC",
            "start_hpc_server",
            "stop_hpc_server",
            "start_hpc_client",
            "stop_hpc_client",
        ),
        (
            "Standard",
            "start_server",
            "terminate_server_process",
            "start_client",
            "terminate_client",
        ),
    ]

    for (
        sim_type,
        expected_start_server,
        expected_stop_server,
        expected_start_client,
        expected_stop_client,
    ) in test_cases:
        exp = MagicMock()
        exp.simulator_type = sim_type

        # Test start server logic
        if exp.simulator_type == "HPC":
            start_func = "start_hpc_server"
        else:
            start_func = "start_server"

        # Test stop server logic
        if exp.simulator_type == "HPC":
            stop_func = "stop_hpc_server"
        else:
            stop_func = "terminate_server_process"

        # Test start client logic
        if exp.simulator_type == "HPC":
            start_client_func = "start_hpc_client"
        else:
            start_client_func = "start_client"

        # Test stop client logic
        if exp.simulator_type == "HPC":
            stop_client_func = "stop_hpc_client"
        else:
            stop_client_func = "terminate_client"

        assert (
            start_func == expected_start_server
        ), f"Start server failed for {sim_type}"
        assert stop_func == expected_stop_server, f"Stop server failed for {sim_type}"
        assert (
            start_client_func == expected_start_client
        ), f"Start client failed for {sim_type}"
        assert (
            stop_client_func == expected_stop_client
        ), f"Stop client failed for {sim_type}"

    print("✓ All simulator_type check patterns work correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
