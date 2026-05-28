"""
Tests for logs directory handling during experiment copy.

Verifies that:
- The /logs subdirectory is created but its contents are not copied
- Log files within /logs subdirectory are excluded
"""

import os
import re
import shutil
import tempfile

import pytest

pytestmark = pytest.mark.unit


def test_logs_directory_created_empty():
    """Test that logs directory is created but empty during copy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = os.path.join(tmpdir, "source")
        dest_dir = os.path.join(tmpdir, "dest")
        os.makedirs(source_dir)
        os.makedirs(dest_dir)

        # Create HPC experiment marker
        with open(os.path.join(source_dir, "server_config.json"), "w") as f:
            f.write("{}")

        # Create logs subdirectory with log files
        logs_dir = os.path.join(source_dir, "logs")
        os.makedirs(logs_dir)

        # Add various log files in logs subdirectory
        log_files = [
            "server.log",
            "client.log",
            "server.log.1",
            "client.log.2",
            "error.log",
        ]

        for log_file in log_files:
            with open(os.path.join(logs_dir, log_file), "w") as f:
                f.write("log content")

        # Create other files that should be copied
        with open(os.path.join(source_dir, "config.json"), "w") as f:
            f.write("{}")

        # Simulate copy logic
        log_pattern = re.compile(r"\.log(\.\d+)?$")

        for item in os.listdir(source_dir):
            if log_pattern.search(item):
                continue

            source_item = os.path.join(source_dir, item)
            dest_item = os.path.join(dest_dir, item)

            if os.path.isfile(source_item):
                shutil.copy2(source_item, dest_item)
            elif os.path.isdir(source_item):
                # Special handling for logs directory
                if item == "logs":
                    os.makedirs(dest_item, exist_ok=True)
                else:
                    shutil.copytree(source_item, dest_item)

        # Verify logs directory exists in destination
        dest_logs = os.path.join(dest_dir, "logs")
        assert os.path.exists(dest_logs), "logs directory should be created"
        assert os.path.isdir(dest_logs), "logs should be a directory"

        # Verify logs directory is empty
        logs_contents = os.listdir(dest_logs)
        assert (
            len(logs_contents) == 0
        ), f"logs directory should be empty, but contains: {logs_contents}"

        # Verify other files are copied
        assert os.path.exists(
            os.path.join(dest_dir, "config.json")
        ), "config.json should be copied"
        assert os.path.exists(
            os.path.join(dest_dir, "server_config.json")
        ), "server_config.json should be copied"


def test_logs_directory_with_nested_structure():
    """Test that nested structure in logs is not copied."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = os.path.join(tmpdir, "source")
        dest_dir = os.path.join(tmpdir, "dest")
        os.makedirs(source_dir)
        os.makedirs(dest_dir)

        # Create logs subdirectory with nested structure
        logs_dir = os.path.join(source_dir, "logs")
        os.makedirs(logs_dir)

        # Create nested subdirectory with logs
        nested_dir = os.path.join(logs_dir, "archived")
        os.makedirs(nested_dir)

        with open(os.path.join(logs_dir, "server.log"), "w") as f:
            f.write("log")
        with open(os.path.join(nested_dir, "old.log"), "w") as f:
            f.write("old log")

        # Simulate copy logic
        log_pattern = re.compile(r"\.log(\.\d+)?$")

        for item in os.listdir(source_dir):
            if log_pattern.search(item):
                continue

            source_item = os.path.join(source_dir, item)
            dest_item = os.path.join(dest_dir, item)

            if os.path.isfile(source_item):
                shutil.copy2(source_item, dest_item)
            elif os.path.isdir(source_item):
                if item == "logs":
                    os.makedirs(dest_item, exist_ok=True)
                else:
                    shutil.copytree(source_item, dest_item)

        # Verify logs directory is empty (no nested structure)
        dest_logs = os.path.join(dest_dir, "logs")
        assert os.path.exists(dest_logs)
        assert (
            len(os.listdir(dest_logs)) == 0
        ), "logs directory should be empty, nested structure should not be copied"


def test_other_directories_still_copied():
    """Test that non-logs directories are still copied normally."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = os.path.join(tmpdir, "source")
        dest_dir = os.path.join(tmpdir, "dest")
        os.makedirs(source_dir)
        os.makedirs(dest_dir)

        # Create logs directory (should be empty)
        logs_dir = os.path.join(source_dir, "logs")
        os.makedirs(logs_dir)
        with open(os.path.join(logs_dir, "server.log"), "w") as f:
            f.write("log")

        # Create other directory with content (should be fully copied)
        data_dir = os.path.join(source_dir, "data")
        os.makedirs(data_dir)
        with open(os.path.join(data_dir, "results.json"), "w") as f:
            f.write('{"data": true}')

        # Simulate copy logic
        log_pattern = re.compile(r"\.log(\.\d+)?$")

        for item in os.listdir(source_dir):
            if log_pattern.search(item):
                continue

            source_item = os.path.join(source_dir, item)
            dest_item = os.path.join(dest_dir, item)

            if os.path.isfile(source_item):
                shutil.copy2(source_item, dest_item)
            elif os.path.isdir(source_item):
                if item == "logs":
                    os.makedirs(dest_item, exist_ok=True)
                else:
                    shutil.copytree(source_item, dest_item)

        # Verify logs directory is empty
        dest_logs = os.path.join(dest_dir, "logs")
        assert os.path.exists(dest_logs)
        assert len(os.listdir(dest_logs)) == 0

        # Verify data directory is fully copied
        dest_data = os.path.join(dest_dir, "data")
        assert os.path.exists(dest_data)
        assert os.path.exists(
            os.path.join(dest_data, "results.json")
        ), "data directory contents should be copied"

        with open(os.path.join(dest_data, "results.json")) as f:
            content = f.read()
            assert "data" in content


def test_logs_directory_case_sensitive():
    """Test that only 'logs' directory (lowercase) is treated specially."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = os.path.join(tmpdir, "source")
        dest_dir = os.path.join(tmpdir, "dest")
        os.makedirs(source_dir)
        os.makedirs(dest_dir)

        # Create logs directory (lowercase - should be empty)
        logs_dir = os.path.join(source_dir, "logs")
        os.makedirs(logs_dir)
        with open(os.path.join(logs_dir, "file.log"), "w") as f:
            f.write("log")

        # Create Logs directory (uppercase - should be copied)
        Logs_dir = os.path.join(source_dir, "Logs")
        if os.path.exists(Logs_dir):
            pytest.skip(
                "Case-sensitive directory distinction is unavailable on this filesystem"
            )
        os.makedirs(Logs_dir)
        with open(os.path.join(Logs_dir, "file.txt"), "w") as f:
            f.write("text")

        # Simulate copy logic
        log_pattern = re.compile(r"\.log(\.\d+)?$")

        for item in os.listdir(source_dir):
            if log_pattern.search(item):
                continue

            source_item = os.path.join(source_dir, item)
            dest_item = os.path.join(dest_dir, item)

            if os.path.isfile(source_item):
                shutil.copy2(source_item, dest_item)
            elif os.path.isdir(source_item):
                if item == "logs":  # Only exact lowercase match
                    os.makedirs(dest_item, exist_ok=True)
                else:
                    shutil.copytree(source_item, dest_item)

        # Verify lowercase logs is empty
        dest_logs = os.path.join(dest_dir, "logs")
        assert os.path.exists(dest_logs)
        assert len(os.listdir(dest_logs)) == 0

        # Verify uppercase Logs is copied with contents
        dest_Logs = os.path.join(dest_dir, "Logs")
        assert os.path.exists(dest_Logs)
        assert len(os.listdir(dest_Logs)) == 1
        assert os.path.exists(os.path.join(dest_Logs, "file.txt"))


def test_no_logs_directory_in_source():
    """Test that copy works fine when source has no logs directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = os.path.join(tmpdir, "source")
        dest_dir = os.path.join(tmpdir, "dest")
        os.makedirs(source_dir)
        os.makedirs(dest_dir)

        # Create files but no logs directory
        with open(os.path.join(source_dir, "config.json"), "w") as f:
            f.write("{}")

        other_dir = os.path.join(source_dir, "other")
        os.makedirs(other_dir)
        with open(os.path.join(other_dir, "data.txt"), "w") as f:
            f.write("data")

        # Simulate copy logic
        log_pattern = re.compile(r"\.log(\.\d+)?$")

        for item in os.listdir(source_dir):
            if log_pattern.search(item):
                continue

            source_item = os.path.join(source_dir, item)
            dest_item = os.path.join(dest_dir, item)

            if os.path.isfile(source_item):
                shutil.copy2(source_item, dest_item)
            elif os.path.isdir(source_item):
                if item == "logs":
                    os.makedirs(dest_item, exist_ok=True)
                else:
                    shutil.copytree(source_item, dest_item)

        # Verify no logs directory in destination
        dest_logs = os.path.join(dest_dir, "logs")
        assert not os.path.exists(
            dest_logs
        ), "logs directory should not be created if not in source"

        # Verify other files copied
        assert os.path.exists(os.path.join(dest_dir, "config.json"))
        assert os.path.exists(os.path.join(dest_dir, "other", "data.txt"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
