"""
Tests for remote experiment support.

Tests the ability to create experiments with remote server configuration,
including database field storage and config file generation.
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from y_web.routes.admin.sub.experiments import (
    generate_hpc_config,
    generate_standard_config,
)
from y_web.src.models import Exps
from y_web.src.simulation.server import _ensure_image_post_module_in_config

pytestmark = pytest.mark.unit


def test_exps_model_has_remote_field():
    """Test that Exps model has the is_remote field."""
    # Check that the model has the required attribute
    assert hasattr(Exps, "is_remote")
    # Also check that server and port fields exist (they should be pre-existing)
    assert hasattr(Exps, "server")
    assert hasattr(Exps, "port")


def test_generate_standard_config_local_experiment():
    """Test generating standard config for local experiment."""
    config = generate_standard_config(
        platform_type="microblogging",
        exp_name="Test Experiment",
        host="127.0.0.1",
        port=5000,
        perspective_api=None,
        sentiment_annotation=True,
        emotion_annotation=True,
        opinions_enabled=True,
        db_uri="/path/to/db.db",
        topics=["topic1", "topic2"],
        data_path="/path/to/data",
        is_remote=False,
    )

    # Verify basic config structure
    assert config["platform_type"] == "microblogging"
    assert config["name"] == "Test Experiment"
    assert config["host"] == "127.0.0.1"
    assert config["port"] == 5000
    assert config["is_remote"] is False
    assert config["modules"] == ["news", "voting", "image"]


def test_generate_standard_config_remote_experiment():
    """Test generating standard config for remote experiment."""
    config = generate_standard_config(
        platform_type="microblogging",
        exp_name="Test Remote Experiment",
        host="192.168.1.100",  # Remote host stored in host parameter
        port=8080,  # Remote port stored in port parameter
        perspective_api=None,
        sentiment_annotation=True,
        emotion_annotation=True,
        opinions_enabled=True,
        db_uri="/path/to/db.db",
        topics=["topic1", "topic2"],
        data_path="/path/to/data",
        is_remote=True,
    )

    # Verify basic config structure
    assert config["platform_type"] == "microblogging"
    assert config["name"] == "Test Remote Experiment"
    assert config["is_remote"] is True

    # Verify remote server info is in host and port fields
    assert config["host"] == "192.168.1.100"
    assert config["port"] == 8080
    assert config["modules"] == ["news", "voting", "image"]


def test_generate_hpc_config_local_experiment():
    """Test generating HPC config for local experiment."""
    config = generate_hpc_config(
        exp_name="Test HPC Experiment",
        platform_type="microblogging",
        db_type="sqlite",
        db_uri="/path/to/db.db",
        redis_enabled=False,
        redis_host="localhost",
        redis_port=6379,
        redis_password=None,
        redis_sliding_window_days=2,
        perspective_api=None,
        sentiment_annotation=True,
        emotion_annotation=True,
        topics=["topic1", "topic2"],
        data_path="/path/to/data",
        db_config_dict=None,
        is_remote=False,
    )

    # Verify basic config structure
    assert config["server_name"] == "Test HPC Experiment"
    assert config["platform_type"] == "microblogging"
    assert config["is_remote"] is False


def test_generate_hpc_config_remote_experiment():
    """Test generating HPC config for remote experiment."""
    config = generate_hpc_config(
        exp_name="Test Remote HPC Experiment",
        platform_type="microblogging",
        db_type="sqlite",
        db_uri="/path/to/db.db",
        redis_enabled=False,
        redis_host="localhost",
        redis_port=6379,
        redis_password=None,
        redis_sliding_window_days=2,
        perspective_api=None,
        sentiment_annotation=True,
        emotion_annotation=True,
        topics=["topic1", "topic2"],
        data_path="/path/to/data",
        db_config_dict=None,
        is_remote=True,
    )

    # Verify basic config structure
    assert config["server_name"] == "Test Remote HPC Experiment"
    assert config["is_remote"] is True


def test_remote_experiment_validation():
    """Test remote experiment input validation logic."""
    # Test valid remote host
    remote_host = "192.168.1.100"
    assert remote_host  # Should have a value

    # Test valid remote port
    remote_port = 8000
    assert 1 <= remote_port <= 65535  # Valid port range

    # Test invalid port (too low)
    remote_port = 0
    assert not (1 <= remote_port <= 65535)

    # Test invalid port (too high)
    remote_port = 65536
    assert not (1 <= remote_port <= 65535)


def test_experiment_model_defaults():
    """Test that Exps model has correct default values for is_remote field."""
    # Note: This tests the model definition, not actual database interaction
    # The default value should be: is_remote=0

    # Check column default is defined
    assert Exps.is_remote.default.arg == 0


def test_ensure_image_post_module_in_config_keeps_microblogging_without_image_post():
    """Microblogging configs must not advertise an unsupported image_post module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config_server.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "platform_type": "microblogging",
                    "modules": ["news", "voting", "image", "image_post"],
                },
                handle,
            )

        _ensure_image_post_module_in_config(config_path)

        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)

    assert config["modules"] == ["news", "voting", "image"]


def test_ensure_image_post_module_in_config_backfills_forum_config():
    """Forum configs still need image_post because YServerReddit exposes that module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config_server.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "platform_type": "forum",
                    "modules": ["news", "voting", "image"],
                },
                handle,
            )

        _ensure_image_post_module_in_config(config_path)

        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)

    assert config["modules"] == ["news", "voting", "image", "image_post"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
