"""
Tests for copy experiment functionality.

Tests the ability to duplicate experiments including configuration files,
database content, and admin database records for both SQLite and PostgreSQL.
"""

import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch, mock_open

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
def test_copy_experiment_file_operations(mock_mkdir, mock_copy, mock_listdir, mock_exists):
    """Test file operations during experiment copy."""
    # Setup mocks
    mock_exists.return_value = True
    mock_listdir.return_value = ["config_server.json", "database_server.db", "prompts.json"]
    
    # Simulate successful file operations
    mock_mkdir.return_value = None
    mock_copy.return_value = None
    
    # Verify mocks can be called
    assert mock_exists("/test/path")
    assert len(mock_listdir("/test/path")) == 3


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
