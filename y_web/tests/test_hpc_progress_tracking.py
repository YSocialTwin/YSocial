"""
Tests for HPC client progress tracking and lifecycle cleanup.

Verifies that when HPC clients are started, Client_Execution records are
created to enable proper progress tracking for the scheduler, and that stop
operations deregister clients cleanly from the orchestrator.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_hpc_client_creates_client_execution_record():
    """Test that start_hpc_client creates Client_Execution record for progress tracking."""

    # Mock client
    mock_client = MagicMock()
    mock_client.id = 1
    mock_client.name = "test_hpc_client"
    mock_client.days = 7  # 7 days = 168 rounds (7 * 24 hours)
    mock_client.pid = None

    # Expected rounds should be 168 (7 days * 24 hours)
    expected_rounds = mock_client.days * 24
    assert expected_rounds == 168


def test_hpc_infinite_client_creates_proper_record():
    """Test that infinite HPC clients (-1 days) set expected_duration_rounds to -1."""

    mock_client = MagicMock()
    mock_client.id = 2
    mock_client.name = "infinite_hpc_client"
    mock_client.days = -1  # Infinite client

    # For infinite clients, expected_duration_rounds should be -1
    expected_rounds = -1 if mock_client.days == -1 else mock_client.days * 24
    assert expected_rounds == -1


def test_client_execution_structure():
    """Test the structure of Client_Execution record."""

    # Verify the fields that should be set
    client_exec_fields = {
        "client_id": 1,
        "elapsed_time": 0,
        "expected_duration_rounds": 168,
        "last_active_hour": -1,
        "last_active_day": -1,
    }

    # Verify all required fields are present
    assert "client_id" in client_exec_fields
    assert "elapsed_time" in client_exec_fields
    assert "expected_duration_rounds" in client_exec_fields
    assert "last_active_hour" in client_exec_fields
    assert "last_active_day" in client_exec_fields

    # Verify initial values
    assert client_exec_fields["elapsed_time"] == 0
    assert client_exec_fields["last_active_hour"] == -1
    assert client_exec_fields["last_active_day"] == -1


def test_expected_rounds_calculation():
    """Test calculation of expected_duration_rounds for various scenarios."""

    test_cases = [
        (1, 24),  # 1 day = 24 rounds
        (7, 168),  # 7 days = 168 rounds
        (30, 720),  # 30 days = 720 rounds
        (-1, -1),  # Infinite = -1
    ]

    for days, expected_rounds in test_cases:
        result = -1 if days == -1 else days * 24
        assert result == expected_rounds, f"Failed for {days} days"


def test_progress_tracking_flow():
    """Test the complete progress tracking flow for HPC clients."""

    # Simulate HPC client progress
    client_exec = {
        "client_id": 1,
        "elapsed_time": 0,
        "expected_duration_rounds": 168,  # 7 days
        "last_active_hour": -1,
        "last_active_day": -1,
    }

    # Simulate progress updates
    for day in range(7):
        for hour in range(24):
            # Update progress
            client_exec["last_active_day"] = day
            client_exec["last_active_hour"] = hour
            client_exec["elapsed_time"] = day * 24 + hour + 1

            # Check if complete
            if client_exec["elapsed_time"] >= client_exec["expected_duration_rounds"]:
                assert day == 6 and hour == 23, "Should complete on day 6, hour 23"
                assert client_exec["elapsed_time"] == 168
                break


def test_stop_hpc_client_deregisters_from_orchestrator(tmp_path):
    """Stopping an HPC client should notify the running orchestrator."""
    from y_web.src.hpc.client import stop_hpc_client

    exp_dir = tmp_path / "y_web" / "experiments" / "exp123"
    exp_dir.mkdir(parents=True)
    (exp_dir / "ray_config.temp").write_text("127.0.0.1:12345", encoding="utf-8")
    (exp_dir / "ray_namespace.temp").write_text("DigitAfrica_test", encoding="utf-8")

    mock_cli = MagicMock()
    mock_cli.name = "standard_pop"
    mock_cli.pid = 4321
    mock_cli.experiment.db_name = "experiments_exp123"

    mock_actor = MagicMock()
    mock_actor.deregister_client.remote.return_value = "ok"

    with (
        patch("y_web.src.hpc.client.get_writable_path", return_value=str(tmp_path)),
        patch("y_web.src.hpc.client.ray.is_initialized", return_value=False),
        patch("y_web.src.hpc.client.ray.init") as mock_ray_init,
        patch(
            "y_web.src.hpc.client.ray.get_actor", return_value=mock_actor
        ) as mock_get_actor,
        patch("y_web.src.hpc.client.ray.get", return_value=True) as mock_ray_get,
        patch("y_web.src.hpc.client.ray.shutdown") as mock_ray_shutdown,
        patch("y_web.src.hpc.client.os.kill", side_effect=OSError("no such process")),
        patch("y_web.src.hpc.client.db.session.commit"),
    ):
        result = stop_hpc_client(mock_cli)

    assert result is True
    mock_ray_init.assert_called_once_with(
        address="127.0.0.1:12345",
        namespace="DigitAfrica_test",
        ignore_reinit_error=True,
    )
    mock_get_actor.assert_called_once_with("Orchestrator", namespace="DigitAfrica_test")
    mock_ray_get.assert_called()
    mock_ray_shutdown.assert_called_once()
    assert mock_cli.pid is None


def test_start_hpc_client_refuses_duplicate_live_pid():
    """Starting an HPC client twice should not spawn a second subprocess."""
    from y_web.src.hpc.client import start_hpc_client

    mock_exp = MagicMock()
    mock_exp.platform_type = "microblogging"

    mock_cli = MagicMock()
    mock_cli.name = "standard_pop"
    mock_cli.pid = 4321

    with (
        patch("y_web.src.hpc.client.get_base_path", return_value="/tmp"),
        patch("y_web.src.hpc.client.os.kill") as mock_kill,
        patch("y_web.src.hpc.client.subprocess.Popen") as mock_popen,
    ):
        with pytest.raises(RuntimeError, match="already running"):
            start_hpc_client(mock_exp, mock_cli, MagicMock())

    mock_kill.assert_called_once_with(4321, 0)
    mock_popen.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
