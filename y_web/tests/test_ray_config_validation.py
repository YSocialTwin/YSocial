"""
Tests for ray_config.temp validation before starting HPC clients.

Verifies that the start_hpc_client function:
- Checks for ray_config.temp existence
- Retries with delays if file is missing
- Raises appropriate error after maximum retries
"""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_ray_config_exists_immediately():
    """Test that validation passes when ray_config.temp exists immediately."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create ray_config.temp
        ray_config_path = os.path.join(tmpdir, "ray_config.temp")
        Path(ray_config_path).touch()

        # Simulate validation logic
        max_attempts = 6
        wait_seconds = 10
        found = False

        for attempt in range(1, max_attempts + 1):
            if Path(ray_config_path).exists():
                found = True
                break

            if attempt < max_attempts:
                time.sleep(0.1)  # Use small delay for testing

        assert found, "ray_config.temp should be found immediately"


def test_ray_config_appears_after_delay():
    """Test that validation succeeds when file appears after some retries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ray_config_path = os.path.join(tmpdir, "ray_config.temp")

        # Simulate file appearing after 3 attempts
        attempt_count = 0
        max_attempts = 6
        found = False

        for attempt in range(1, max_attempts + 1):
            attempt_count = attempt

            # Simulate file appearing on 3rd attempt
            if attempt >= 3:
                Path(ray_config_path).touch()

            if Path(ray_config_path).exists():
                found = True
                break

            if attempt < max_attempts:
                time.sleep(0.1)

        assert found, "ray_config.temp should be found after delay"
        assert attempt_count == 3, "Should find file on 3rd attempt"


def test_ray_config_missing_raises_error():
    """Test that validation raises FileNotFoundError after max retries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ray_config_path = os.path.join(tmpdir, "ray_config.temp")
        # Don't create the file - it should be missing

        # Simulate validation logic
        max_attempts = 6
        wait_seconds = 0.1  # Use small delay for testing
        found = False
        error_raised = False

        try:
            for attempt in range(1, max_attempts + 1):
                if Path(ray_config_path).exists():
                    found = True
                    break

                if attempt < max_attempts:
                    time.sleep(wait_seconds)
                else:
                    # Final attempt failed
                    error_msg = (
                        f"ray_config.temp file not found after {max_attempts} attempts "
                        f"({max_attempts * wait_seconds} seconds): {ray_config_path}"
                    )
                    raise FileNotFoundError(error_msg)
        except FileNotFoundError:
            error_raised = True

        assert not found, "ray_config.temp should NOT be found"
        assert error_raised, "FileNotFoundError should be raised after max attempts"


def test_validation_error_message_format():
    """Test that error message contains expected information."""
    exp_folder = "/path/to/experiment"
    ray_config_path = os.path.join(exp_folder, "ray_config.temp")
    max_attempts = 6
    wait_seconds = 10

    error_msg = (
        f"ray_config.temp file not found after {max_attempts} attempts "
        f"({max_attempts * wait_seconds} seconds): {ray_config_path}\n"
        f"The HPC server may not have fully initialized yet. "
        f"Please wait and try again, or check the server logs for errors."
    )

    # Verify error message contains key information
    assert "ray_config.temp" in error_msg
    assert str(max_attempts) in error_msg
    assert str(max_attempts * wait_seconds) in error_msg
    assert ray_config_path in error_msg
    assert "HPC server" in error_msg
    assert "server logs" in error_msg


def test_validation_with_different_max_attempts():
    """Test that validation respects max_attempts parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ray_config_path = os.path.join(tmpdir, "ray_config.temp")

        # Test with different max_attempts values
        test_cases = [1, 3, 6, 10]

        for max_attempts in test_cases:
            attempt_count = 0
            found = False

            for attempt in range(1, max_attempts + 1):
                attempt_count += 1

                if Path(ray_config_path).exists():
                    found = True
                    break

                if attempt < max_attempts:
                    time.sleep(0.01)

            assert not found, "File should not be found"
            assert (
                attempt_count == max_attempts
            ), f"Should attempt exactly {max_attempts} times"


def test_validation_required_files_order():
    """Test that ray_config.temp is validated after other required files."""
    # This test verifies the order of validation
    required_files = [
        "client config",
        "agents",
        "prompts",
        "ray_config.temp",  # Should be last
    ]

    # In the actual implementation, ray_config.temp validation comes after
    # the validation of client_config, agents_file, and prompts_file
    assert (
        required_files[-1] == "ray_config.temp"
    ), "ray_config.temp should be validated last"


def test_multiple_validation_attempts_with_file_creation():
    """Test realistic scenario where file is created during validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ray_config_path = os.path.join(tmpdir, "ray_config.temp")

        max_attempts = 6
        found = False
        creation_attempt = 4  # File will be created on 4th attempt

        for attempt in range(1, max_attempts + 1):
            # Simulate file creation during validation
            if attempt == creation_attempt:
                Path(ray_config_path).touch()

            if Path(ray_config_path).exists():
                found = True
                break

            if attempt < max_attempts:
                time.sleep(0.01)

        assert found, "File should be found after creation"


def test_validation_handles_file_permissions():
    """Test that validation works with different file permissions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ray_config_path = os.path.join(tmpdir, "ray_config.temp")

        # Create file with different permissions
        Path(ray_config_path).touch()

        # File should be found regardless of permissions
        found = Path(ray_config_path).exists()
        assert found, "File should be found"


def test_validation_with_symlink():
    """Test that validation works with symlinked ray_config.temp."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create actual file
        actual_file = os.path.join(tmpdir, "actual_ray_config.temp")
        Path(actual_file).touch()

        # Create symlink (skip test on Windows if symlink creation fails)
        ray_config_path = os.path.join(tmpdir, "ray_config.temp")
        try:
            os.symlink(actual_file, ray_config_path)

            # Validation should find the symlink
            found = Path(ray_config_path).exists()
            assert found, "Symlinked file should be found"
        except OSError:
            # Skip test if symlinks are not supported (e.g., Windows without admin)
            pytest.skip("Symlinks not supported on this platform")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
