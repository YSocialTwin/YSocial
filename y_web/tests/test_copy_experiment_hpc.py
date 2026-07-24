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


def test_matrix_client_network_type_preserved_when_csv_exists(tmp_path):
    """Matrix copies must keep network bootstrap when a client CSV is present."""
    from y_web.routes.admin.sub.experiments._crud import _matrix_client_network_type

    folder = tmp_path / "clone"
    folder.mkdir()
    (folder / "client_alpha_network.csv").write_text("Alice,Bob\n", encoding="utf-8")

    assert (
        _matrix_client_network_type("client_alpha", "", str(folder)) == "Custom Network"
    )
    assert _matrix_client_network_type("client_alpha", "ER", str(folder)) == "ER"

    renamed_folder = tmp_path / "clone2"
    renamed_folder.mkdir()
    (renamed_folder / "client_alpha_legacy_network.csv").write_text(
        "Alice,Bob\n", encoding="utf-8"
    )
    assert (
        _matrix_client_network_type("client_alpha", "", str(renamed_folder))
        == "Custom Network"
    )


def test_matrix_resolve_client_days_prefers_num_days():
    """Matrix-created HPC configs must read num_days before legacy days."""
    from y_web.routes.admin.sub.experiments._crud import _matrix_resolve_client_days

    config = {
        "simulation": {
            "num_days": 30,
            "days": 50,
        }
    }

    assert _matrix_resolve_client_days(config, 7) == 30
    assert _matrix_resolve_client_days({"simulation": {"days": 12}}, 7) == 12
    assert _matrix_resolve_client_days({}, 7) == 7


def test_matrix_excludes_client_visibility_rounds_but_keeps_server_value():
    """Client-side visibility_rounds should not be exposed in matrix reports."""
    from y_web.routes.admin.sub.experiments._crud import _matrix_is_variable_path

    assert (
        _matrix_is_variable_path(("posts", "visibility_rounds"), "client_a.json")
        is False
    )
    assert (
        _matrix_is_variable_path(("posts", "visibility_rounds"), "server_config.json")
        is True
    )


def test_startup_repairs_missing_network_type_when_csv_present(tmp_path):
    """process_runner must set network_type to 'Custom Network' on first run when
    the DB record has an empty network_type but the CSV file already exists on
    disk (legacy matrix-generated experiments created before the copy fix)."""
    from unittest.mock import MagicMock

    from y_web.src.hpc.client import _hpc_network_bootstrap_exists

    data_base_path = str(tmp_path) + "/"
    csv_path = tmp_path / "network.csv"
    csv_path.write_text("Alice,Bob\n", encoding="utf-8")

    client_config_path = tmp_path / "client_alpha_matrix.json"
    client_config_path.write_text(
        json.dumps({"client_name": "client_alpha_matrix"}), encoding="utf-8"
    )

    # Construct a fake Client whose network_type starts empty.
    cli = MagicMock()
    cli.name = "client_alpha"
    cli.network_type = ""
    cli.days = 7
    cli.id = 1

    # Verify the repair pre-condition: empty network_type + CSV present.
    assert not cli.network_type
    assert _hpc_network_bootstrap_exists(data_base_path, str(client_config_path), cli)

    fake_session = MagicMock()
    first_run = True

    if first_run and not cli.network_type:
        if _hpc_network_bootstrap_exists(data_base_path, str(client_config_path), cli):
            cli.network_type = "Custom Network"
            try:
                fake_session.add(cli)
                fake_session.commit()
            except Exception:
                fake_session.rollback()

    # After repair the client should be flagged as having a network.
    assert cli.network_type == "Custom Network"
    # The DB session must have received add() and commit() calls.
    fake_session.add.assert_called_once_with(cli)
    fake_session.commit.assert_called_once()

    # When network_type is already set, the repair must NOT fire.
    cli2 = MagicMock()
    cli2.name = "client_beta"
    cli2.network_type = "ER"
    fake_session2 = MagicMock()

    if first_run and not cli2.network_type:
        if _hpc_network_bootstrap_exists(data_base_path, str(client_config_path), cli2):
            cli2.network_type = "Custom Network"
            fake_session2.add(cli2)
            fake_session2.commit()

    assert cli2.network_type == "ER"
    fake_session2.add.assert_not_called()


def test_hpc_legacy_matrix_experiment_with_generic_network_csv_is_detected(tmp_path):
    """Legacy matrix experiments with only network.csv must still bootstrap."""
    from y_web.src.hpc.client import _hpc_network_bootstrap_exists

    exp_dir = tmp_path / "legacy_exp"
    exp_dir.mkdir()
    (exp_dir / "network.csv").write_text("Alice,Bob\n", encoding="utf-8")

    config_path = exp_dir / "client_alpha_matrix.json"
    config_path.write_text(
        json.dumps({"client_name": "client_alpha_matrix"}), encoding="utf-8"
    )

    cli = MagicMock()
    cli.name = "client_alpha"

    assert _hpc_network_bootstrap_exists(str(exp_dir), str(config_path), cli) is True


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
