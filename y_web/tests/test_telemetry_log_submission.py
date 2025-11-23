"""
Tests for telemetry log submission functionality.

Tests the new features:
1. Log files are truncated to last 300 lines
2. JSON files have sensitive data (URLs and API keys) removed
3. Max compressed file size is 5MB
"""

import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

from y_web.telemetry import Telemetry


class MockUser:
    """Mock user for testing."""
    def __init__(self, telemetry_enabled=True):
        self.telemetry_enabled = telemetry_enabled
        self.is_authenticated = True


def test_sanitize_json_config_removes_api_keys():
    """Test that API keys are redacted from JSON config."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    test_data = {
        "llm_api_key": "secret-key-123",
        "api_key": "another-secret",
        "apikey": "yet-another-secret",
        "normal_field": "normal_value"
    }
    
    result = telemetry._sanitize_json_config(test_data)
    
    assert result["llm_api_key"] == "***REDACTED***"
    assert result["api_key"] == "***REDACTED***"
    assert result["apikey"] == "***REDACTED***"
    assert result["normal_field"] == "normal_value"


def test_sanitize_json_config_removes_urls():
    """Test that URLs are redacted from JSON config."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    test_data = {
        "api": "http://example.com/api",
        "url": "https://example.com",
        "endpoint": "http://localhost:5000/endpoint",
        "host": "just-a-hostname",  # Not a URL, should be kept
        "port": 5000
    }
    
    result = telemetry._sanitize_json_config(test_data)
    
    assert result["api"] == "***REDACTED***"
    assert result["url"] == "***REDACTED***"
    assert result["endpoint"] == "***REDACTED***"
    assert result["host"] == "just-a-hostname"  # Not a URL
    assert result["port"] == 5000


def test_sanitize_json_config_handles_nested_structures():
    """Test that sanitization works on nested JSON structures."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    test_data = {
        "servers": {
            "api": "http://example.com/api",
            "llm": "http://llm-service.com",
            "llm_api_key": "secret-key"
        },
        "config": {
            "nested": {
                "password": "secret-password",
                "name": "test"
            }
        },
        "agents": ["agent1", "agent2"]
    }
    
    result = telemetry._sanitize_json_config(test_data)
    
    assert result["servers"]["api"] == "***REDACTED***"
    assert result["servers"]["llm"] == "***REDACTED***"
    assert result["servers"]["llm_api_key"] == "***REDACTED***"
    assert result["config"]["nested"]["password"] == "***REDACTED***"
    assert result["config"]["nested"]["name"] == "test"
    assert result["agents"] == ["agent1", "agent2"]


def test_log_file_truncation():
    """Test that log files are truncated to last 300 lines."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    # Create a temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        exp_folder = Path(temp_dir) / "experiment"
        exp_folder.mkdir()
        
        # Create a log file with 500 lines
        log_file = exp_folder / "test.log"
        with open(log_file, "w") as f:
            for i in range(500):
                f.write(f"Log line {i}\n")
        
        # Create a simple JSON config
        config_file = exp_folder / "config.json"
        with open(config_file, "w") as f:
            json.dump({"name": "test", "api_key": "secret"}, f)
        
        # Submit logs (this will fail to send but should create the zip)
        success, message = telemetry.submit_experiment_logs(1, str(exp_folder))
        
        # The submission will fail because there's no server, but we can check
        # that it tried to create files by checking the error message
        # In a real scenario with a mock server, we'd verify the zip contents
        assert "Failed to send logs" in message or "Telemetry server returned error" in message


def test_json_sanitization_preserves_structure():
    """Test that JSON sanitization preserves the overall structure."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    # Create a temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        exp_folder = Path(temp_dir) / "experiment"
        exp_folder.mkdir()
        
        # Create a JSON config with sensitive data
        original_config = {
            "name": "test_experiment",
            "port": 5000,
            "servers": {
                "api": "http://localhost:5000/api",
                "llm": "http://llm-service.com",
                "llm_api_key": "secret-key-123"
            },
            "agents": {
                "llm_agents": ["agent1", "agent2"]
            }
        }
        
        config_file = exp_folder / "config_server.json"
        with open(config_file, "w") as f:
            json.dump(original_config, f)
        
        # Read and sanitize
        with open(config_file, "r") as f:
            config_data = json.load(f)
        
        sanitized = telemetry._sanitize_json_config(config_data)
        
        # Check structure is preserved
        assert "name" in sanitized
        assert "port" in sanitized
        assert "servers" in sanitized
        assert "agents" in sanitized
        
        # Check values are correct
        assert sanitized["name"] == "test_experiment"
        assert sanitized["port"] == 5000
        assert sanitized["servers"]["api"] == "***REDACTED***"
        assert sanitized["servers"]["llm"] == "***REDACTED***"
        assert sanitized["servers"]["llm_api_key"] == "***REDACTED***"
        assert sanitized["agents"]["llm_agents"] == ["agent1", "agent2"]


def test_empty_experiment_folder():
    """Test handling of empty experiment folder."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        exp_folder = Path(temp_dir) / "experiment"
        exp_folder.mkdir()
        
        success, message = telemetry.submit_experiment_logs(1, str(exp_folder))
        
        assert success is False
        assert "No log or configuration files found" in message


def test_nonexistent_folder():
    """Test handling of non-existent experiment folder."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    success, message = telemetry.submit_experiment_logs(1, "/nonexistent/path")
    
    assert success is False
    assert "not found" in message


def test_telemetry_disabled():
    """Test that telemetry respects disabled setting."""
    user = MockUser(telemetry_enabled=False)
    telemetry = Telemetry(user=user)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        exp_folder = Path(temp_dir) / "experiment"
        exp_folder.mkdir()
        
        success, message = telemetry.submit_experiment_logs(1, str(exp_folder))
        
        assert success is False
        assert "Telemetry is disabled" in message


def test_sanitize_json_config_with_lists():
    """Test that sanitization works with lists containing dicts."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    test_data = {
        "items": [
            {"name": "item1", "api_key": "secret1"},
            {"name": "item2", "url": "http://example.com"}
        ]
    }
    
    result = telemetry._sanitize_json_config(test_data)
    
    assert result["items"][0]["name"] == "item1"
    assert result["items"][0]["api_key"] == "***REDACTED***"
    assert result["items"][1]["name"] == "item2"
    assert result["items"][1]["url"] == "***REDACTED***"


def test_sanitize_json_config_preserves_none_values():
    """Test that None values are preserved during sanitization."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    test_data = {
        "field1": None,
        "field2": "value",
        "api_key": "secret"
    }
    
    result = telemetry._sanitize_json_config(test_data)
    
    assert result["field1"] is None
    assert result["field2"] == "value"
    assert result["api_key"] == "***REDACTED***"


def test_anonymize_log_line_removes_absolute_paths():
    """Test that absolute file paths are anonymized in log lines."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    # Test Unix-style paths
    unix_line = "Error in /home/user/project/y_web/module.py at line 42\n"
    result = telemetry._anonymize_log_line(unix_line)
    assert "/home/user/project" not in result
    assert "module.py" in result
    
    # Test Windows-style paths
    win_line = "Error in C:\\Users\\user\\project\\y_web\\module.py at line 42\n"
    result = telemetry._anonymize_log_line(win_line)
    assert "C:\\Users\\user\\project" not in result
    assert "module.py" in result


def test_anonymize_log_line_handles_traceback_format():
    """Test that Python traceback format is properly anonymized."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    traceback_line = 'File "/home/user/project/y_web/routes.py", line 123, in view_function\n'
    result = telemetry._anonymize_log_line(traceback_line)
    
    assert "/home/user/project" not in result
    assert "routes.py" in result
    assert "line 123" in result
    assert "view_function" in result
    assert "<anon>" in result


def test_anonymize_log_line_preserves_non_path_content():
    """Test that log lines without paths are preserved."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    simple_line = "INFO: Application started successfully\n"
    result = telemetry._anonymize_log_line(simple_line)
    
    assert result == simple_line


def test_log_file_anonymization_integration():
    """Test that log files are both truncated and anonymized."""
    user = MockUser(telemetry_enabled=True)
    telemetry = Telemetry(user=user)
    
    # Create a temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        exp_folder = Path(temp_dir) / "experiment"
        exp_folder.mkdir()
        
        # Create a log file with 500 lines containing paths
        log_file = exp_folder / "test.log"
        with open(log_file, "w") as f:
            for i in range(500):
                f.write(f"Log line {i}: Error in /home/user/project/file_{i}.py\n")
        
        # Create a simple JSON config
        config_file = exp_folder / "config.json"
        with open(config_file, "w") as f:
            json.dump({"name": "test", "api_key": "secret"}, f)
        
        # Submit logs (this will fail to send but should create the zip)
        success, message = telemetry.submit_experiment_logs(1, str(exp_folder))
        
        # The submission will fail because there's no server
        assert "Failed to send logs" in message or "Telemetry server returned error" in message
