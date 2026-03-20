import os


def test_server_log_path_prefers_config_then_env(monkeypatch):
    from y_server import app
    from y_server import _server_log_path

    with app.app_context():
        monkeypatch.setenv("YSERVER_LOG_FILE", "/tmp/from_env.log")
        app.config["log_file"] = "/tmp/from_config.log"
        assert _server_log_path() == "/tmp/from_config.log"


def test_server_log_path_falls_back_to_env(monkeypatch):
    from y_server import app
    from y_server import _server_log_path

    with app.app_context():
        app.config["log_file"] = ""
        monkeypatch.setenv("YSERVER_LOG_FILE", "/tmp/from_env_only.log")
        assert _server_log_path() == "/tmp/from_env_only.log"
