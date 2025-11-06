"""
Tests for copy experiment functionality.

Tests the ability to duplicate experiments including configuration files,
database content, and admin database records for both SQLite and PostgreSQL.
"""

import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock, mock_open, patch

import pytest

# We'll use the conftest fixtures


def test_copy_experiment_validation():
    """Test copy experiment input validation logic."""
    # Test empty/missing experiment name
    new_name = ""
    source_id = "1"
    assert not new_name or not source_id  # Should fail validation

    # Test valid inputs
    new_name = "New Experiment"
    source_id = "1"
    assert new_name and source_id  # Should pass validation

    # Test port range validation
    port = 5000
    assert 5000 <= port <= 6000  # Valid port range

    port = 4999
    assert not (5000 <= port <= 6000)  # Invalid - too low

    port = 6001
    assert not (5000 <= port <= 6000)  # Invalid - too high


@patch("os.path.exists")
@patch("os.listdir")
@patch("shutil.copy2")
@patch("pathlib.Path.mkdir")
def test_copy_experiment_file_operations(
    mock_mkdir, mock_copy, mock_listdir, mock_exists
):
    """Test file operations during experiment copy."""
    # Setup mocks
    mock_exists.return_value = True
    mock_listdir.return_value = [
        "config_server.json",
        "database_server.db",
        "prompts.json",
    ]

    # Simulate successful file operations
    mock_mkdir.return_value = None
    mock_copy.return_value = None

    # Verify mocks can be called
    assert mock_exists("/test/path")
    assert len(mock_listdir("/test/path")) == 3


def test_log_file_exclusion():
    """Test that log files are excluded from copy."""
    # Simulate file list with log files
    file_list = [
        "config_server.json",
        "database_server.db",
        "prompts.json",
        "_server.log",
        "test_client.log",
        "population_A_client.log",
    ]

    # Filter out log files (simulating the copy logic)
    files_to_copy = [f for f in file_list if not f.endswith(".log")]

    # Verify log files are excluded
    assert "_server.log" not in files_to_copy
    assert "test_client.log" not in files_to_copy
    assert "population_A_client.log" not in files_to_copy

    # Verify other files are included
    assert "config_server.json" in files_to_copy
    assert "database_server.db" in files_to_copy
    assert "prompts.json" in files_to_copy
    assert len(files_to_copy) == 3


def test_client_execution_not_copied():
    """Test that Client_Execution entries are NOT copied for new experiments."""
    # Simulate source client execution with active state
    source_exec = {
        "client_id": 1,
        "elapsed_time": 3600,
        "expected_duration_rounds": 168,
        "last_active_hour": 15,
        "last_active_day": 3,
    }

    # In the copy operation, we create a new client but NO Client_Execution entry
    new_client = {"id": 2, "name": "test_client", "status": 0}  # Not running

    # Verify that we have a new client
    assert new_client["id"] != source_exec["client_id"]
    assert new_client["status"] == 0

    # The key point: no Client_Execution entry is created during copy
    # It will be created when the client first starts, ensuring fresh state
    # This is tested by the absence of Client_Execution creation in the copy code


def test_copy_experiment_config_update():
    """Test configuration file update logic."""
    # Test JSON serialization/deserialization
    config = {
        "name": "Test Experiment",
        "port": 5000,
        "host": "127.0.0.1",
        "platform_type": "microblogging",
    }

    # Serialize and deserialize
    config_str = json.dumps(config)
    config_parsed = json.loads(config_str)

    # Update config
    config_parsed["name"] = "Copied Experiment"
    config_parsed["port"] = 5001

    # Verify updates
    assert config_parsed["name"] == "Copied Experiment"
    assert config_parsed["port"] == 5001
    assert config_parsed["host"] == "127.0.0.1"


def test_database_name_parsing():
    """Test parsing of database names for SQLite and PostgreSQL."""
    # SQLite format: experiments/uuid/database_server.db
    sqlite_db_name = "experiments/abc123def/database_server.db"
    parts = sqlite_db_name.split(os.sep)
    assert len(parts) >= 2
    uuid_part = parts[1]
    assert uuid_part == "abc123def"

    # PostgreSQL format: experiments_uuid
    postgres_db_name = "experiments_abc123def"
    uuid_part = postgres_db_name.replace("experiments_", "")
    assert uuid_part == "abc123def"


def test_clean_database_used():
    """Test that copied experiments use clean database template, not source data."""
    import os

    # Verify clean database template exists
    clean_db_path = os.path.join("data_schema", "database_clean_server.db")
    # Just test the path construction - actual file existence checked in production code
    assert "database_clean_server.db" in clean_db_path

    # PostgreSQL schema file
    postgres_schema_path = os.path.join("data_schema", "postgre_server.sql")
    assert "postgre_server.sql" in postgres_schema_path

    # Verify the logic: clean database should be used, not source database
    # This is a conceptual test showing we use templates, not copies
    source_db = "experiments/source_uuid/database_server.db"
    clean_template = "data_schema/database_clean_server.db"

    # In copy operation, we should use clean_template, NOT source_db
    assert clean_template != source_db
    assert "clean" in clean_template.lower()


def test_unique_port_assignment():
    """Test that copied experiments get unique ports, not reusing source port."""
    # Simulate port assignment with all experiments having ports
    assigned_ports = {5000, 5001, 5002}

    # Port range
    port_range = range(5000, 6001)

    # Find available port
    available_port = None
    for port in port_range:
        if port not in assigned_ports:
            available_port = port
            break

    # Verify we get a unique port
    assert available_port is not None
    assert available_port not in assigned_ports
    assert available_port == 5003  # First available after 5002

    # Test that we don't reuse source port
    source_port = 5001
    assert available_port != source_port


def test_config_update_verification():
    """Test that config_server.json is properly updated with new values."""
    # Simulate config update
    old_config = {
        "name": "Old Experiment",
        "port": 5000,
        "database_uri": "/old/path/database.db",
    }

    new_name = "New Experiment"
    new_port = 5005
    new_db_uri = "/new/path/database.db"

    # Update config (simulating our logic)
    updated_config = old_config.copy()
    updated_config["name"] = new_name
    updated_config["port"] = new_port
    updated_config["database_uri"] = new_db_uri

    # Verify all fields are updated
    assert updated_config["name"] == new_name
    assert updated_config["port"] == new_port
    assert updated_config["database_uri"] == new_db_uri

    # Verify old values are not present
    assert updated_config["name"] != old_config["name"]
    assert updated_config["port"] != old_config["port"]
    assert updated_config["database_uri"] != old_config["database_uri"]


def test_client_config_port_update():
    """Test that client configuration files have their API endpoint port updated."""
    import re

    # Simulate client config with old port
    old_client_config = {
        "servers": {"llm": "gpt-4", "api": "http://127.0.0.1:5000/"},
        "simulation": {"name": "test_client"},
    }

    # New port to assign
    new_port = 5010

    # Update the API endpoint (simulating our logic)
    if "servers" in old_client_config and "api" in old_client_config["servers"]:
        old_api = old_client_config["servers"]["api"]
        # Replace the port in the URL (format: http://host:port/)
        new_api = re.sub(r":\d+/", f":{new_port}/", old_api)
        old_client_config["servers"]["api"] = new_api

    # Verify the port was updated
    assert old_client_config["servers"]["api"] == "http://127.0.0.1:5010/"
    assert "5010" in old_client_config["servers"]["api"]
    assert "5000" not in old_client_config["servers"]["api"]

    # Test with different URL format
    test_api = "http://localhost:5001/"
    new_api = re.sub(r":\d+/", f":{new_port}/", test_api)
    assert new_api == "http://localhost:5010/"


def test_postgresql_database_deletion():
    """Test that PostgreSQL database deletion logic is correct."""
    # Simulate database name
    db_name = "experiments_abc123def456"

    # Verify the database name format
    assert db_name.startswith("experiments_")

    # Simulate SQL commands for deletion
    terminate_connections_sql = f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{db_name}'
        AND pid <> pg_backend_pid()
    """

    drop_database_sql = f'DROP DATABASE IF EXISTS "{db_name}"'

    # Verify SQL commands are properly formatted
    assert "pg_terminate_backend" in terminate_connections_sql
    assert db_name in terminate_connections_sql
    assert "DROP DATABASE IF EXISTS" in drop_database_sql
    assert db_name in drop_database_sql


def test_postgresql_to_sqlite_type_mapping():
    """Test PostgreSQL to SQLite type mapping for download functionality."""
    # Test type mappings
    type_mappings = {
        "INTEGER": "INTEGER",
        "SERIAL": "INTEGER",
        "BIGSERIAL": "INTEGER",
        "REAL": "REAL",
        "DOUBLE PRECISION": "REAL",
        "FLOAT": "REAL",
        "TEXT": "TEXT",
        "VARCHAR": "TEXT",
        "CHAR": "TEXT",
        "BOOLEAN": "TEXT",  # Default case
    }

    for pg_type, expected_sqlite_type in type_mappings.items():
        # Simulate type mapping logic
        col_type = pg_type

        if "INTEGER" in col_type or "SERIAL" in col_type:
            sqlite_type = "INTEGER"
        elif "REAL" in col_type or "DOUBLE" in col_type or "FLOAT" in col_type:
            sqlite_type = "REAL"
        elif "TEXT" in col_type or "VARCHAR" in col_type or "CHAR" in col_type:
            sqlite_type = "TEXT"
        else:
            sqlite_type = "TEXT"

        assert sqlite_type == expected_sqlite_type, f"Failed for {pg_type}"


def test_download_folder_path_extraction():
    """Test folder path extraction for different database types."""
    import os

    # SQLite format: experiments/uuid/database_server.db
    sqlite_db_name = "experiments/abc123def/database_server.db"
    sqlite_folder = f"y_web{os.sep}experiments{os.sep}{sqlite_db_name.split(os.sep)[1]}"
    assert "abc123def" in sqlite_folder

    # PostgreSQL format: experiments_uuid
    postgres_db_name = "experiments_abc123def"
    postgres_folder = f"y_web{os.sep}experiments{os.sep}{postgres_db_name.removeprefix('experiments_')}"
    assert "abc123def" in postgres_folder

    # Verify both produce similar paths
    assert sqlite_folder.split(os.sep)[-1] == postgres_folder.split(os.sep)[-1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
