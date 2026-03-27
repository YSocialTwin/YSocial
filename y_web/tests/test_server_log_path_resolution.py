import os

import pytest

pytestmark = pytest.mark.unit


y_server = pytest.importorskip(
    "y_server", reason="y_server module not available in this environment"
)


def test_server_log_path_prefers_config_then_env(monkeypatch):
    from y_server import _server_log_path, app

    with app.app_context():
        monkeypatch.setenv("YSERVER_LOG_FILE", "/tmp/from_env.log")
        app.config["log_file"] = "/tmp/from_config.log"
        assert _server_log_path() == "/tmp/from_config.log"


def test_server_log_path_falls_back_to_env(monkeypatch):
    from y_server import _server_log_path, app

    with app.app_context():
        app.config["log_file"] = ""
        monkeypatch.setenv("YSERVER_LOG_FILE", "/tmp/from_env_only.log")
        assert _server_log_path() == "/tmp/from_env_only.log"
