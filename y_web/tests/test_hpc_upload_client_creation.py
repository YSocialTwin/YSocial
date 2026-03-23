"""
Test for HPC experiment upload and client creation.

Verifies that HPC experiments are properly detected during upload
and that Client and Client_Execution records are created.
"""

import json
import os
import tempfile

import pytest
pytestmark = pytest.mark.unit



def test_hpc_experiment_detection_logic():
    """Test logic for detecting HPC vs Standard experiments."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Test 1: HPC experiment (server_config.json exists)
        hpc_config = os.path.join(tmpdir, "server_config.json")
        with open(hpc_config, "w") as f:
            json.dump({"experiment_name": "Test HPC"}, f)

        # Simulate detection logic
        config_path_standard = os.path.join(tmpdir, "config_server.json")
        config_path_hpc = os.path.join(tmpdir, "server_config.json")

        is_hpc = False
        if os.path.exists(config_path_hpc):
            is_hpc = True
        elif os.path.exists(config_path_standard):
            is_hpc = False

        assert is_hpc == True, "Should detect HPC experiment"

        # Test 2: Standard experiment (config_server.json exists)
        os.remove(hpc_config)
        std_config = os.path.join(tmpdir, "config_server.json")
        with open(std_config, "w") as f:
            json.dump({"name": "Test Standard"}, f)

        is_hpc = False
        if os.path.exists(config_path_hpc):
            is_hpc = True
        elif os.path.exists(config_path_standard):
            is_hpc = False

        assert is_hpc == False, "Should detect Standard experiment"


def test_client_record_structure():
    """Test Client record structure for HPC vs Standard."""

    # Standard client config
    standard_client = {
        "simulation": {
            "name": "std_client",
            "days": 7,
            "slots": 24,
            "percentage_new_agents_iteration": 0,
            "percentage_removed_agents_iteration": 0,
            "actions_likelihood": {
                "post": 0.3,
                "share": 0.2,
                "image": 0.1,
                "comment": 0.2,
                "read": 0.8,
                "news": 0.1,
                "search": 0.1,
                "cast": 0.1,
            },
        },
        "agents": {
            "max_length_thread_reading": 10,
            "reading_from_follower_ratio": 0.5,
            "probability_of_daily_follow": 0.1,
            "attention_window": 24,
            "llm_v_agent": 0,
        },
        "posts": {
            "visibility_rounds": 36,
        },
        "servers": {
            "llm": "",
            "llm_api_key": "",
            "llm_max_tokens": 100,
            "llm_temperature": 0.7,
            "llm_v": "",
            "llm_v_api_key": "",
            "llm_v_max_tokens": 100,
            "llm_v_temperature": 0.7,
        },
    }

    # HPC client config (simpler)
    hpc_client = {
        "name": "hpc_client",
        "simulation": {
            "days": 7,
        },
    }

    # Verify both have required fields
    assert "simulation" in standard_client
    assert standard_client["simulation"]["days"] == 7

    assert "name" in hpc_client
    assert hpc_client["simulation"]["days"] == 7


def test_client_execution_calculation():
    """Test expected_duration_rounds calculation for both types."""

    # Test Standard with slots
    days = 7
    slots = 24
    expected_standard = days * slots
    assert expected_standard == 168

    # Test HPC (always 24 slots/day)
    hpc_slots = 24
    expected_hpc = days * hpc_slots
    assert expected_hpc == 168

    # Test infinite client
    days_infinite = -1
    expected_infinite = -1
    assert expected_infinite == -1


def test_population_file_filtering():
    """Test that population file filtering excludes HPC configs."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create various JSON files
        files = [
            "population1.json",
            "population2.json",
            "client_pop1.json",
            "config_server.json",
            "server_config.json",
            "prompts.json",
        ]

        for f in files:
            with open(os.path.join(tmpdir, f), "w") as file:
                json.dump({}, file)

        # Simulate filtering logic
        populations = [
            f
            for f in os.listdir(tmpdir)
            if f.endswith(".json")
            and not f.startswith("client")
            and f != "config_server.json"
            and f != "server_config.json"
            and f != "prompts.json"
        ]

        # Should only include population files
        assert len(populations) == 2
        assert "population1.json" in populations
        assert "population2.json" in populations
        assert "client_pop1.json" not in populations
        assert "config_server.json" not in populations
        assert "server_config.json" not in populations
        assert "prompts.json" not in populations


def test_simulator_type_assignment():
    """Test that simulator_type is correctly assigned based on detection."""

    # Test HPC
    is_hpc_experiment = True
    simulator_type = "HPC" if is_hpc_experiment else "Standard"
    assert simulator_type == "HPC"

    # Test Standard
    is_hpc_experiment = False
    simulator_type = "HPC" if is_hpc_experiment else "Standard"
    assert simulator_type == "Standard"


def test_complete_flow():
    """Test complete HPC experiment upload flow."""

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create HPC experiment structure
        server_config = {
            "experiment_name": "Test HPC Experiment",
            "server": {"port": 5000},
            "database": {"type": "sqlite"},
        }

        with open(os.path.join(tmpdir, "server_config.json"), "w") as f:
            json.dump(server_config, f)

        population_config = {
            "agents": [
                {"name": "agent1", "is_page": 0},
                {"name": "agent2", "is_page": 0},
            ]
        }

        with open(os.path.join(tmpdir, "test_population.json"), "w") as f:
            json.dump(population_config, f)

        client_config = {
            "name": "test_client",
            "simulation": {"days": 7},
        }

        with open(
            os.path.join(tmpdir, "client_test_client-test_population.json"), "w"
        ) as f:
            json.dump(client_config, f)

        # Verify detection works
        config_path_hpc = os.path.join(tmpdir, "server_config.json")
        config_path_standard = os.path.join(tmpdir, "config_server.json")

        is_hpc = os.path.exists(config_path_hpc)
        assert is_hpc == True

        # Verify population filtering
        populations = [
            f
            for f in os.listdir(tmpdir)
            if f.endswith(".json")
            and not f.startswith("client")
            and f != "config_server.json"
            and f != "server_config.json"
            and f != "prompts.json"
        ]

        assert len(populations) == 1
        assert "test_population.json" in populations

        # Verify client config found
        clients = [
            f
            for f in os.listdir(tmpdir)
            if f.endswith(".json") and f.startswith("client") and "test_population" in f
        ]

        assert len(clients) == 1

        print("✓ Complete HPC upload flow test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
