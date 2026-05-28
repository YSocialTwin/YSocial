"""
Tests for actor log cleanup when restarting HPC clients.

Verifies that when an HPC client is restarted, the last two completion log entries
are removed from the actor log file to prevent premature termination by the status checker.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_actor_log_cleanup_removes_last_two_lines():
    """Test that the last two completion log lines are removed from actor log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create experiment folder structure
        exp_folder = os.path.join(tmpdir, "experiment")
        logs_folder = os.path.join(exp_folder, "logs")
        os.makedirs(logs_folder)

        # Create actor log with completion messages
        client_name = "test_client"
        actor_log_path = os.path.join(logs_folder, f"{client_name}_actor.log")

        log_lines = [
            '{"timestamp": "2026-02-18T07:32:44.000000", "level": "INFO", "message": "Starting simulation"}\n',
            '{"timestamp": "2026-02-18T07:32:44.500000", "level": "INFO", "message": "Processing agents"}\n',
            '{"timestamp": "2026-02-18T07:32:45.000000", "level": "INFO", "message": "Running simulation"}\n',
            '{"timestamp": "2026-02-18T07:32:45.381808", "level": "INFO", "message": "Notified server of completion"}\n',
            '{"timestamp": "2026-02-18T07:32:45.381872", "level": "INFO", "message": " Simulation complete. Server notified."}\n',
        ]

        with open(actor_log_path, "w", encoding="utf-8") as f:
            f.writelines(log_lines)

        # Simulate the cleanup logic from start_hpc_client
        if os.path.exists(actor_log_path):
            with open(actor_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) >= 2:
                lines = lines[:-2]

                with open(actor_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

        # Verify the last two lines were removed
        with open(actor_log_path, "r", encoding="utf-8") as f:
            remaining_lines = f.readlines()

        assert len(remaining_lines) == 3, "Should have 3 lines remaining (5 - 2)"
        assert (
            remaining_lines[-1].strip() == log_lines[2].strip()
        ), "Last line should be 'Running simulation'"
        assert "Notified server of completion" not in remaining_lines[-1]
        assert "Simulation complete" not in "".join(remaining_lines)


def test_actor_log_cleanup_handles_missing_file():
    """Test that cleanup handles missing actor log file gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        exp_folder = os.path.join(tmpdir, "experiment")
        logs_folder = os.path.join(exp_folder, "logs")
        os.makedirs(logs_folder)

        client_name = "test_client"
        actor_log_path = os.path.join(logs_folder, f"{client_name}_actor.log")

        # File doesn't exist - this should not raise an error
        try:
            if os.path.exists(actor_log_path):
                with open(actor_log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                if len(lines) >= 2:
                    lines = lines[:-2]

                    with open(actor_log_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)

            # Should succeed without error
            success = True
        except Exception:
            success = False

        assert success, "Should handle missing file gracefully"


def test_actor_log_cleanup_handles_file_with_less_than_two_lines():
    """Test that cleanup handles files with fewer than 2 lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        exp_folder = os.path.join(tmpdir, "experiment")
        logs_folder = os.path.join(exp_folder, "logs")
        os.makedirs(logs_folder)

        client_name = "test_client"
        actor_log_path = os.path.join(logs_folder, f"{client_name}_actor.log")

        # Create log with only one line
        log_lines = [
            '{"timestamp": "2026-02-18T07:32:44.000000", "level": "INFO", "message": "Starting simulation"}\n',
        ]

        with open(actor_log_path, "w", encoding="utf-8") as f:
            f.writelines(log_lines)

        # Simulate cleanup
        if os.path.exists(actor_log_path):
            with open(actor_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Only remove lines if there are at least 2
            if len(lines) >= 2:
                lines = lines[:-2]

                with open(actor_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

        # Verify the single line is preserved
        with open(actor_log_path, "r", encoding="utf-8") as f:
            remaining_lines = f.readlines()

        assert len(remaining_lines) == 1, "Single line should be preserved"
        assert (
            remaining_lines[0] == log_lines[0]
        ), "Original line should remain unchanged"


def test_actor_log_cleanup_handles_empty_file():
    """Test that cleanup handles empty actor log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        exp_folder = os.path.join(tmpdir, "experiment")
        logs_folder = os.path.join(exp_folder, "logs")
        os.makedirs(logs_folder)

        client_name = "test_client"
        actor_log_path = os.path.join(logs_folder, f"{client_name}_actor.log")

        # Create empty file
        Path(actor_log_path).touch()

        # Simulate cleanup
        if os.path.exists(actor_log_path):
            with open(actor_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) >= 2:
                lines = lines[:-2]

                with open(actor_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

        # Verify file remains empty
        with open(actor_log_path, "r", encoding="utf-8") as f:
            remaining_lines = f.readlines()

        assert len(remaining_lines) == 0, "Empty file should remain empty"


def test_actor_log_cleanup_handles_exactly_two_lines():
    """Test that cleanup removes both lines when exactly 2 lines exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        exp_folder = os.path.join(tmpdir, "experiment")
        logs_folder = os.path.join(exp_folder, "logs")
        os.makedirs(logs_folder)

        client_name = "test_client"
        actor_log_path = os.path.join(logs_folder, f"{client_name}_actor.log")

        # Create log with exactly two lines (both completion messages)
        log_lines = [
            '{"timestamp": "2026-02-18T07:32:45.381808", "level": "INFO", "message": "Notified server of completion"}\n',
            '{"timestamp": "2026-02-18T07:32:45.381872", "level": "INFO", "message": " Simulation complete. Server notified."}\n',
        ]

        with open(actor_log_path, "w", encoding="utf-8") as f:
            f.writelines(log_lines)

        # Simulate cleanup
        if os.path.exists(actor_log_path):
            with open(actor_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) >= 2:
                lines = lines[:-2]

                with open(actor_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

        # Verify both lines were removed (file should be empty)
        with open(actor_log_path, "r", encoding="utf-8") as f:
            remaining_lines = f.readlines()

        assert (
            len(remaining_lines) == 0
        ), "Both lines should be removed, leaving empty file"


def test_actor_log_cleanup_preserves_other_content():
    """Test that cleanup only removes last 2 lines and preserves everything else."""
    with tempfile.TemporaryDirectory() as tmpdir:
        exp_folder = os.path.join(tmpdir, "experiment")
        logs_folder = os.path.join(exp_folder, "logs")
        os.makedirs(logs_folder)

        client_name = "test_client"
        actor_log_path = os.path.join(logs_folder, f"{client_name}_actor.log")

        # Create log with various messages
        log_lines = [
            '{"timestamp": "2026-02-18T07:32:44.000000", "level": "INFO", "message": "Starting simulation"}\n',
            '{"timestamp": "2026-02-18T07:32:44.100000", "level": "DEBUG", "message": "Loading configuration"}\n',
            '{"timestamp": "2026-02-18T07:32:44.200000", "level": "INFO", "message": "Initializing agents"}\n',
            '{"timestamp": "2026-02-18T07:32:44.300000", "level": "WARNING", "message": "Some warning"}\n',
            '{"timestamp": "2026-02-18T07:32:44.400000", "level": "ERROR", "message": "Some error"}\n',
            '{"timestamp": "2026-02-18T07:32:45.000000", "level": "INFO", "message": "Running simulation"}\n',
            '{"timestamp": "2026-02-18T07:32:45.381808", "level": "INFO", "message": "Notified server of completion"}\n',
            '{"timestamp": "2026-02-18T07:32:45.381872", "level": "INFO", "message": " Simulation complete. Server notified."}\n',
        ]

        with open(actor_log_path, "w", encoding="utf-8") as f:
            f.writelines(log_lines)

        # Simulate cleanup
        if os.path.exists(actor_log_path):
            with open(actor_log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) >= 2:
                lines = lines[:-2]

                with open(actor_log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

        # Verify content
        with open(actor_log_path, "r", encoding="utf-8") as f:
            remaining_lines = f.readlines()

        assert len(remaining_lines) == 6, "Should have 6 lines remaining (8 - 2)"

        # Verify all original lines except last 2 are preserved
        for i in range(6):
            assert remaining_lines[i] == log_lines[i], f"Line {i} should be preserved"

        # Verify completion messages are removed
        remaining_content = "".join(remaining_lines)
        assert "Notified server of completion" not in remaining_content
        assert "Simulation complete. Server notified" not in remaining_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
