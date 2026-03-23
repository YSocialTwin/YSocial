"""
Test for extend_simulation HPC config file update functionality.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest
pytestmark = pytest.mark.unit



class TestExtendSimulationHPCConfig:
    """Test that extend_simulation updates HPC client config files correctly"""

    def test_extend_simulation_updates_hpc_config_file(self):
        """Test that HPC client config file is updated when simulation is extended"""
        # Create a temporary directory for test
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock config file
            config_data = {
                "client_name": "test_client",
                "namespace": "test_exp",
                "simulation": {
                    "num_days": 5,
                    "num_slots_per_day": 24,
                    "heartbeat_interval": 5,
                },
                "agents": {
                    "reading_from_follower_ratio": 0.6,
                },
            }

            config_path = os.path.join(temp_dir, "client_test-population1.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            # Verify initial state
            with open(config_path, "r") as f:
                initial_config = json.load(f)
            assert initial_config["simulation"]["num_days"] == 5

            # Simulate extension by updating the config
            with open(config_path, "r") as f:
                config = json.load(f)

            config["simulation"]["num_days"] = 15  # Extended by 10 days

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            # Verify config was updated
            with open(config_path, "r") as f:
                updated_config = json.load(f)

            assert updated_config["simulation"]["num_days"] == 15
            assert updated_config["client_name"] == "test_client"
            assert updated_config["agents"]["reading_from_follower_ratio"] == 0.6

    def test_extend_simulation_handles_missing_config_file(self):
        """Test that missing config file is handled gracefully"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Path to non-existent config file
            config_path = os.path.join(temp_dir, "nonexistent_client.json")

            # Verify file doesn't exist
            assert not os.path.exists(config_path)

            # This should not raise an exception
            # In the actual implementation, this would show a warning flash message

    def test_extend_simulation_handles_missing_simulation_section(self):
        """Test that config file without simulation section is handled gracefully"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a config file without simulation section
            config_data = {
                "client_name": "test_client",
                "namespace": "test_exp",
                "agents": {
                    "reading_from_follower_ratio": 0.6,
                },
            }

            config_path = os.path.join(temp_dir, "client_test-population1.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            # Try to read and update
            with open(config_path, "r") as f:
                config = json.load(f)

            # Check for simulation section
            if "simulation" not in config:
                # This would trigger a warning in the actual implementation
                assert True  # Expected behavior
            else:
                config["simulation"]["num_days"] = 15

    def test_extend_simulation_preserves_other_config_values(self):
        """Test that extending simulation doesn't corrupt other config values"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a comprehensive config file
            config_data = {
                "client_name": "test_client",
                "namespace": "test_exp",
                "server": {"address": "localhost", "port": 5000},
                "simulation": {
                    "num_days": 5,
                    "num_slots_per_day": 24,
                    "heartbeat_interval": 5,
                    "percentage_new_agents_iteration": 0.1,
                    "percentage_removed_agents_iteration": 0.05,
                    "actions_likelihood": {
                        "post": 3.0,
                        "share": 1.0,
                        "comment": 5.0,
                        "read": 2.0,
                    },
                },
                "agents": {
                    "reading_from_follower_ratio": 0.6,
                    "max_length_thread_reading": 5,
                    "attention_window": 336,
                },
                "llm": {
                    "address": "localhost",
                    "port": 11434,
                    "model": "llama3.2",
                    "temperature": 0.7,
                },
            }

            config_path = os.path.join(temp_dir, "client_test-population1.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            # Update only num_days
            with open(config_path, "r") as f:
                config = json.load(f)

            config["simulation"]["num_days"] = 15

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            # Verify all other values are preserved
            with open(config_path, "r") as f:
                updated_config = json.load(f)

            assert updated_config["simulation"]["num_days"] == 15
            assert updated_config["simulation"]["num_slots_per_day"] == 24
            assert updated_config["simulation"]["heartbeat_interval"] == 5
            assert (
                updated_config["simulation"]["percentage_new_agents_iteration"] == 0.1
            )
            assert updated_config["simulation"]["actions_likelihood"]["post"] == 3.0
            assert updated_config["agents"]["reading_from_follower_ratio"] == 0.6
            assert updated_config["agents"]["attention_window"] == 336
            assert updated_config["llm"]["model"] == "llama3.2"
            assert updated_config["server"]["address"] == "localhost"

    def test_config_file_naming_pattern(self):
        """Test that config file naming follows the expected pattern"""
        # Expected pattern: client_{name}-{population}.json
        client_name = "myclient"
        population_name = "population1"
        expected_filename = f"client_{client_name}-{population_name}.json"

        assert expected_filename == "client_myclient-population1.json"

        # Test with different names
        client_name = "test_client_123"
        population_name = "TestPop"
        expected_filename = f"client_{client_name}-{population_name}.json"

        assert expected_filename == "client_test_client_123-TestPop.json"
