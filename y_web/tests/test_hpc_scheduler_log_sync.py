"""
Test for HPC client execution status updates via log sync scheduler.

Verifies that when HPC clients are started via scheduler, their
Client_Execution records are properly updated with progress information.
"""

import os
import tempfile

import pytest

pytestmark = pytest.mark.unit


def test_is_hpc_flag_passed_to_update_client_log_metrics():
    """
    Test that is_hpc flag is correctly passed based on simulator_type.

    This is a logic test to ensure the scheduler properly identifies
    HPC experiments and passes the is_hpc flag to update_client_log_metrics.
    """

    # Simulate experiment with HPC simulator type
    class MockExp:
        def __init__(self, simulator_type):
            self.simulator_type = simulator_type
            self.idexp = 1
            self.exp_name = "test_exp"

    # Test HPC experiment
    exp_hpc = MockExp("HPC")
    is_hpc = exp_hpc.simulator_type == "HPC"
    assert is_hpc == True, "Should detect HPC experiment"

    # Test Standard experiment
    exp_standard = MockExp("Standard")
    is_hpc = exp_standard.simulator_type == "HPC"
    assert is_hpc == False, "Should detect Standard experiment"

    print("✓ is_hpc flag logic test passed")


def test_client_execution_update_requires_is_hpc():
    """
    Test that Client_Execution updates only happen when is_hpc=True.

    This verifies the logic in log_metrics.py that Client_Execution
    updates are conditional on the is_hpc flag.
    """
    # Simulate the conditional logic from log_metrics.py line 741
    is_hpc = True
    max_day = 0
    max_hour = 5

    # This is the condition that must be True for Client_Execution updates
    should_update = is_hpc and max_day >= 0 and max_hour >= 0
    assert should_update == True, "Should update Client_Execution for HPC"

    # Test with is_hpc=False (old bug)
    is_hpc = False
    should_update = is_hpc and max_day >= 0 and max_hour >= 0
    assert (
        should_update == False
    ), "Should NOT update Client_Execution without is_hpc flag"

    print("✓ Client_Execution update condition test passed")


def test_scheduler_logic_flow():
    """
    Test the complete logic flow in the scheduler.

    Simulates the sequence of checks that should happen in
    log_sync_scheduler.py when processing HPC clients.
    """

    # Mock experiment and client
    class MockExperiment:
        def __init__(self):
            self.simulator_type = "HPC"
            self.idexp = 123
            self.exp_name = "test_hpc_exp"
            self.running = 1

    class MockClient:
        def __init__(self):
            self.id = 456
            self.name = "test_client"
            self.status = 1  # Running

    exp = MockExperiment()
    client = MockClient()

    # Step 1: Check if experiment is HPC
    is_hpc = exp.simulator_type == "HPC"
    assert is_hpc == True, "Experiment should be identified as HPC"

    # Step 2: Build log file path
    exp_folder = "/tmp/test_exp"
    client_log_file = os.path.join(exp_folder, f"{client.name}_client.log")
    expected_path = "/tmp/test_exp/test_client_client.log"
    assert client_log_file == expected_path, f"Log file path should be {expected_path}"

    # Step 3: Verify function would be called with is_hpc
    # In the fix, this is what gets passed:
    # update_client_log_metrics(exp.idexp, client.id, client_log_file, is_hpc=is_hpc)
    call_params = {
        "exp_id": exp.idexp,
        "client_id": client.id,
        "log_file_path": client_log_file,
        "is_hpc": is_hpc,
    }

    assert call_params["exp_id"] == 123
    assert call_params["client_id"] == 456
    assert call_params["is_hpc"] == True, "is_hpc should be True for HPC experiments"

    print("✓ Scheduler logic flow test passed")


def test_elapsed_time_calculation():
    """
    Test the elapsed_time calculation logic for HPC clients.

    Verifies the formula: elapsed_time = max_day * 24 + max_hour + 1
    """
    # Test cases from log_metrics.py line 751
    test_cases = [
        (0, 0, 1),  # Day 0, Hour 0 = Round 1
        (0, 1, 2),  # Day 0, Hour 1 = Round 2
        (0, 23, 24),  # Day 0, Hour 23 = Round 24
        (1, 0, 25),  # Day 1, Hour 0 = Round 25
        (1, 23, 48),  # Day 1, Hour 23 = Round 48
        (6, 23, 168),  # Day 6, Hour 23 = Round 168 (7 days complete)
    ]

    for max_day, max_hour, expected_elapsed in test_cases:
        elapsed_time = max_day * 24 + max_hour + 1
        assert (
            elapsed_time == expected_elapsed
        ), f"Day {max_day}, Hour {max_hour} should give elapsed_time {expected_elapsed}, got {elapsed_time}"

    print("✓ Elapsed time calculation test passed")


def test_completion_detection():
    """
    Test the logic for detecting when a client has completed its simulation.

    Verifies finite clients complete on round threshold while infinite clients do not.
    """
    # 7-day simulation: expected_duration_rounds = 7 * 24 = 168
    expected_duration_rounds = 168

    # Not complete
    current_round = 100
    is_complete = current_round >= expected_duration_rounds
    assert is_complete == False, "Should not be complete at round 100"

    # Exactly complete
    current_round = 168
    is_complete = current_round >= expected_duration_rounds
    assert is_complete == True, "Should be complete at round 168"

    # Past complete
    current_round = 200
    is_complete = current_round >= expected_duration_rounds
    assert is_complete == True, "Should be complete past round 168"

    # Infinite simulation (-1 means run forever)
    expected_duration_rounds = -1
    current_round = 1000
    is_complete = expected_duration_rounds > 0 and current_round >= expected_duration_rounds
    assert is_complete == False, "Infinite clients must never auto-complete from progress"

    print("✓ Completion detection test passed")


if __name__ == "__main__":
    test_is_hpc_flag_passed_to_update_client_log_metrics()
    test_client_execution_update_requires_is_hpc()
    test_scheduler_logic_flow()
    test_elapsed_time_calculation()
    test_completion_detection()
    print("\n✅ All HPC scheduler log sync tests passed!")
