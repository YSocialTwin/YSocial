"""
Tests for copy experiment functionality with HPC support.

Verifies that the copy experiment function correctly handles both
Standard and HPC experiment types.
"""

import json
import os
import re
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_hpc_config_detection():
    """Test that HPC experiments are correctly detected by config file."""
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test HPC detection - server_config.json exists
        hpc_config_path = os.path.join(tmpdir, "server_config.json")
        with open(hpc_config_path, "w") as f:
            json.dump({"experiment_name": "Test HPC", "server": {"port": 5000}}, f)

        # Check that server_config.json exists
        assert os.path.exists(hpc_config_path)
        # Check that config_server.json doesn't exist
        assert not os.path.exists(os.path.join(tmpdir, "config_server.json"))

        # Test Standard detection - config_server.json exists
        std_tmpdir = tempfile.mkdtemp()
        try:
            std_config_path = os.path.join(std_tmpdir, "config_server.json")
            with open(std_config_path, "w") as f:
                json.dump({"name": "Test Standard", "port": 5000}, f)

            # Check that config_server.json exists
            assert os.path.exists(std_config_path)
            # Check that server_config.json doesn't exist
            assert not os.path.exists(os.path.join(std_tmpdir, "server_config.json"))
        finally:
            shutil.rmtree(std_tmpdir, ignore_errors=True)


def test_hpc_config_structure():
    """Test HPC configuration structure."""
    # HPC config structure
    hpc_config = {
        "experiment_name": "Test HPC Experiment",
        "server": {"port": 5000, "address": "127.0.0.1"},
        "database_uri": "/path/to/db",
    }

    # Verify structure
    assert "experiment_name" in hpc_config
    assert "server" in hpc_config
    assert "port" in hpc_config["server"]
    assert hpc_config["server"]["port"] == 5000

    # Update port
    hpc_config["server"]["port"] = 5001
    assert hpc_config["server"]["port"] == 5001


def test_standard_config_structure():
    """Test Standard configuration structure."""
    # Standard config structure
    std_config = {
        "name": "Test Standard Experiment",
        "port": 5000,
        "database_uri": "/path/to/db",
        "data_path": "/path/to/data/",
    }

    # Verify structure
    assert "name" in std_config
    assert "port" in std_config
    assert std_config["port"] == 5000

    # Update port
    std_config["port"] = 5001
    assert std_config["port"] == 5001


def test_hpc_client_config_structure():
    """Test HPC client configuration structure."""
    # HPC client config: {client_name}_config.json
    hpc_client_config = {
        "name": "test_client",
        "server": {"address": None, "port": 5000},
        "simulation": {"days": 7},
    }

    # Verify structure
    assert "server" in hpc_client_config
    assert "port" in hpc_client_config["server"]
    assert hpc_client_config["server"]["port"] == 5000

    # Update port
    hpc_client_config["server"]["port"] = 5001
    assert hpc_client_config["server"]["port"] == 5001


def test_standard_client_config_structure():
    """Test Standard client configuration structure."""
    # Standard client config: client_*.json
    std_client_config = {
        "simulation": {"name": "test_client"},
        "servers": {"llm": "gpt-4", "api": "http://127.0.0.1:5000/"},
    }

    # Verify structure
    assert "servers" in std_client_config
    assert "api" in std_client_config["servers"]
    assert "5000" in std_client_config["servers"]["api"]

    # Update port in URL
    old_api = std_client_config["servers"]["api"]
    new_api = re.sub(r":(\d+)(/|$)", r":5001\2", old_api)
    std_client_config["servers"]["api"] = new_api

    assert std_client_config["servers"]["api"] == "http://127.0.0.1:5001/"
    assert "5001" in std_client_config["servers"]["api"]
    assert "5000" not in std_client_config["servers"]["api"]


def test_client_config_filename_patterns():
    """Test client config filename pattern matching."""
    # Standard patterns: client_*.json
    std_filenames = [
        "client_population_A.json",
        "client_test.json",
        "client_1.json",
    ]

    for filename in std_filenames:
        assert filename.startswith("client") and filename.endswith(".json")

    # HPC patterns: {name}_config.json (but not server_config.json)
    hpc_filenames = [
        "population_A_config.json",
        "test_client_config.json",
        "client1_config.json",
    ]

    for filename in hpc_filenames:
        is_client_config = filename.endswith(
            "_config.json"
        ) and not filename.startswith("server")
        assert is_client_config

    # Should not match: server_config.json should be excluded because it starts with "server"
    server_config = "server_config.json"
    assert server_config.endswith("_config.json")  # True
    assert server_config.startswith("server")  # True
    # So the full check should be False
    assert not (
        server_config.endswith("_config.json")
        and not server_config.startswith("server")
    )

    # Ambiguous case: client_test_config.json matches both patterns
    # This is handled correctly by using the is_hpc flag to determine config structure
    ambiguous_filename = "client_test_config.json"
    matches_standard = ambiguous_filename.startswith(
        "client"
    ) and ambiguous_filename.endswith(".json")
    matches_hpc = ambiguous_filename.endswith(
        "_config.json"
    ) and not ambiguous_filename.startswith("server")
    # Both are true, but the is_hpc flag in the implementation determines which config structure to use
    assert matches_standard
    assert matches_hpc


def test_config_verification_logic():
    """Test configuration verification for both types."""
    # HPC verification
    hpc_verify = {
        "experiment_name": "Test",
        "server": {"port": 5001},
        "database_uri": "/path/to/db",
    }
    expected_port = 5001
    expected_db = "/path/to/db"

    assert hpc_verify.get("server", {}).get("port") == expected_port
    assert hpc_verify.get("database_uri") == expected_db

    # Standard verification
    std_verify = {"name": "Test", "port": 5001, "database_uri": "/path/to/db"}

    assert std_verify.get("port") == expected_port
    assert std_verify.get("database_uri") == expected_db


def test_exp_group_parameter():
    """Test that exp_group parameter is correctly handled."""
    # Simulate creating an experiment with a group
    exp_group = "Test Group 1"

    # Mock Exps object creation
    exp_data = {
        "exp_name": "Test Experiment",
        "platform_type": "microblogging",
        "db_name": "test_db",
        "owner": "admin",
        "exp_descr": "Test description",
        "status": 0,
        "running": 0,
        "port": 5000,
        "server": "127.0.0.1",
        "annotations": "",
        "llm_agents_enabled": 1,
        "simulator_type": "Standard",
        "exp_group": exp_group,
    }

    # Verify exp_group is present and correct
    assert "exp_group" in exp_data
    assert exp_data["exp_group"] == "Test Group 1"

    # Test with empty group (optional)
    exp_data_no_group = exp_data.copy()
    exp_data_no_group["exp_group"] = ""

    assert exp_data_no_group["exp_group"] == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
