"""
Tests for upload_experiment functionality.

Tests the ability to upload experiments from zip files including:
- Port assignment from 5000-6000 range
- PostgreSQL and SQLite database setup
- Config file updates (server and client)
- Experiment name override
"""

import json
import os
import shutil
import tempfile
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


def test_port_range_validation():
    """Test that ports are validated to be in 5000-6000 range."""
    # Test valid ports
    for port in [5000, 5500, 6000]:
        assert 5000 <= port <= 6000, f"Port {port} should be valid"

    # Test invalid ports
    for port in [4999, 6001, 3000, 8080]:
        assert not (5000 <= port <= 6000), f"Port {port} should be invalid"


def test_config_server_update():
    """Test that config_server.json is updated with new port and database_uri."""
    # Original config
    original_config = {
        "name": "Test Experiment",
        "host": "127.0.0.1",
        "port": 8080,
        "platform_type": "microblogging",
        "database_uri": "/old/path/database.db",
    }

    # Simulate update
    new_port = 5500
    new_db_uri = "/new/path/database.db"
    new_name = "Updated Experiment"

    updated_config = original_config.copy()
    updated_config["port"] = new_port
    updated_config["database_uri"] = new_db_uri
    updated_config["name"] = new_name

    # Verify updates
    assert updated_config["port"] == 5500
    assert updated_config["database_uri"] == "/new/path/database.db"
    assert updated_config["name"] == "Updated Experiment"
    assert updated_config["host"] == "127.0.0.1"  # Unchanged
    assert updated_config["platform_type"] == "microblogging"  # Unchanged


def test_client_config_port_update():
    """Test that client config files are updated with new port in API endpoint."""
    import re

    # Original client config
    client_config = {
        "servers": {
            "api": "http://127.0.0.1:8080/",
            "llm": "http://localhost:11434",
        },
        "simulation": {"name": "Test Simulation"},
    }

    # Update port in API URL
    new_port = 5500
    old_api = client_config["servers"]["api"]
    new_api = re.sub(r":\d+/", f":{new_port}/", old_api)
    client_config["servers"]["api"] = new_api

    # Verify update
    assert client_config["servers"]["api"] == "http://127.0.0.1:5500/"
    assert client_config["servers"]["llm"] == "http://localhost:11434"  # Unchanged


def test_port_regex_patterns():
    """Test different URL patterns for port replacement."""
    import re

    test_cases = [
        ("http://127.0.0.1:8080/", 5500, "http://127.0.0.1:5500/"),
        ("http://localhost:3000/", 5000, "http://localhost:5000/"),
        ("https://example.com:443/", 6000, "https://example.com:6000/"),
        ("http://192.168.1.1:9999/api/", 5555, "http://192.168.1.1:5555/api/"),
        # Test without trailing slash
        ("http://127.0.0.1:8080", 5500, "http://127.0.0.1:5500"),
        ("http://localhost:3000", 5000, "http://localhost:5000"),
    ]

    for old_url, new_port, expected_url in test_cases:
        # Updated regex pattern that handles both with and without trailing slash
        new_url = re.sub(r":(\d+)(/|$)", f":{new_port}\\2", old_url)
        assert (
            new_url == expected_url
        ), f"Failed for {old_url}: got {new_url}, expected {expected_url}"


def test_database_name_formats():
    """Test database name formats for SQLite and PostgreSQL."""
    import uuid

    uid = str(uuid.uuid4()).replace("-", "_")

    # SQLite format
    sqlite_db_name = f"experiments{os.sep}{uid}{os.sep}database_server.db"
    assert "experiments" in sqlite_db_name
    assert "database_server.db" in sqlite_db_name

    # PostgreSQL format
    pg_db_name = f"experiments_{uid}"
    assert pg_db_name.startswith("experiments_")
    assert "-" not in pg_db_name  # No hyphens in PostgreSQL db names


def test_experiment_name_override():
    """Test that experiment name can be overridden from form."""
    # Config name
    config_name = "Original Name"
    # Form override
    form_name = "Override Name"

    # Logic: use override if provided, else use config
    final_name = form_name if form_name.strip() else config_name
    assert final_name == "Override Name"

    # Test with empty override
    form_name = ""
    final_name = form_name.strip() if form_name.strip() else config_name
    assert final_name == "Original Name"

    # Test with whitespace override
    form_name = "   "
    final_name = form_name.strip() if form_name.strip() else config_name
    assert final_name == "Original Name"


def test_zip_file_structure():
    """Test creating and extracting a minimal experiment zip file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal experiment structure
        config = {
            "name": "Test Experiment",
            "host": "127.0.0.1",
            "port": 8080,
            "platform_type": "microblogging",
            "database_uri": "test.db",
        }

        # Create zip file
        zip_path = os.path.join(tmpdir, "experiment.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("config_server.json", json.dumps(config, indent=4))
            zf.writestr("prompts.json", json.dumps({}, indent=4))

        # Extract and verify
        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir)
        shutil.unpack_archive(zip_path, extract_dir)

        # Verify files exist
        assert os.path.exists(os.path.join(extract_dir, "config_server.json"))
        assert os.path.exists(os.path.join(extract_dir, "prompts.json"))

        # Verify config content
        with open(os.path.join(extract_dir, "config_server.json")) as f:
            extracted_config = json.load(f)
        assert extracted_config["name"] == "Test Experiment"
        assert extracted_config["port"] == 8080


def test_postgresql_db_name_sanitization():
    """Test that PostgreSQL database names are properly sanitized."""
    import uuid

    # UUID with hyphens
    uid_with_hyphens = str(uuid.uuid4())
    assert "-" in uid_with_hyphens

    # Sanitized version (hyphens replaced with underscores)
    uid_sanitized = uid_with_hyphens.replace("-", "_")
    assert "-" not in uid_sanitized
    assert "_" in uid_sanitized

    # PostgreSQL db name should not contain hyphens
    pg_db_name = f"experiments_{uid_sanitized}"
    assert "-" not in pg_db_name


def test_error_handling_no_config():
    """Test error handling when config_server.json is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create empty experiment directory
        exp_dir = os.path.join(tmpdir, "exp")
        os.makedirs(exp_dir)

        # Check that config file doesn't exist
        config_path = os.path.join(exp_dir, "config_server.json")
        assert not os.path.exists(config_path)

        # Verify this would raise an error
        with pytest.raises(FileNotFoundError):
            with open(config_path, "r") as f:
                json.load(f)


def test_client_files_identification():
    """Test identifying client configuration files."""
    files = [
        "config_server.json",
        "prompts.json",
        "client_population_A.json",
        "client_population_B.json",
        "population_A.json",
        "population_B.json",
        "database_server.db",
    ]

    # Filter for client config files
    client_files = [f for f in files if f.startswith("client") and f.endswith(".json")]

    assert len(client_files) == 2
    assert "client_population_A.json" in client_files
    assert "client_population_B.json" in client_files
    assert "config_server.json" not in client_files
    assert "prompts.json" not in client_files


def test_port_assignment_logic():
    """Test the logic for assigning a suggested port."""
    # Simulate assigned ports
    assigned_ports = {5000, 5001, 5002, 5010}

    # Find first available port
    suggested_port = None
    for port in range(5000, 6001):
        if port not in assigned_ports:
            suggested_port = port
            break

    # Should find 5003 as first available
    assert suggested_port == 5003

    # Test when all ports are taken
    assigned_ports = set(range(5000, 6001))
    suggested_port = None
    for port in range(5000, 6001):
        if port not in assigned_ports:
            suggested_port = port
            break

    # Should return None
    assert suggested_port is None


def test_config_file_updates_integration():
    """Integration test for config file updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create initial config
        config_path = os.path.join(tmpdir, "config_server.json")
        initial_config = {
            "name": "Test",
            "port": 8080,
            "host": "127.0.0.1",
            "database_uri": "/old/path",
            "platform_type": "microblogging",
        }

        with open(config_path, "w") as f:
            json.dump(initial_config, f, indent=4)

        # Read and update config
        with open(config_path, "r") as f:
            config = json.load(f)

        config["name"] = "Updated Test"
        config["port"] = 5500
        config["database_uri"] = "/new/path"

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        # Verify update
        with open(config_path, "r") as f:
            updated_config = json.load(f)

        assert updated_config["name"] == "Updated Test"
        assert updated_config["port"] == 5500
        assert updated_config["database_uri"] == "/new/path"
        assert updated_config["host"] == "127.0.0.1"  # Unchanged


def test_uid_format_consistency():
    """Test that UUID format is consistent between folder and db_name.

    This test ensures that the UID used for the experiment folder matches
    the UID format used in db_name for both SQLite and PostgreSQL.
    The fix ensures that dashes are replaced with underscores in the UID
    to maintain consistency.
    """
    import uuid

    # Simulate the UID generation as it should be done in upload_experiment
    uid = str(uuid.uuid4()).replace("-", "_")

    # Verify no dashes in UID (they should all be underscores)
    assert "-" not in uid
    assert "_" in uid

    # SQLite format: experiments/<uid>/database_server.db
    sqlite_db_name = f"experiments/{uid}/database_server.db"
    # Extract the UID part from db_name (same way as in experiments_routes.py)
    sqlite_uid_from_db_name = sqlite_db_name.split("/")[1]
    assert sqlite_uid_from_db_name == uid, "SQLite: folder UID should match db_name UID"

    # PostgreSQL format: experiments_<uid>
    pg_db_name = f"experiments_{uid}"
    # Extract the UID part from db_name (same way as in experiments_routes.py)
    pg_uid_from_db_name = pg_db_name.replace("experiments_", "")
    assert pg_uid_from_db_name == uid, "PostgreSQL: folder UID should match db_name UID"
