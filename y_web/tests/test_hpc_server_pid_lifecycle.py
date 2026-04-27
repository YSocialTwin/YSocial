from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _build_hpc_experiment(server_pid):
    return SimpleNamespace(
        idexp=6,
        db_name="experiments_exp123",
        platform_type="microblogging",
        server="127.0.0.1",
        port=5004,
        server_pid=server_pid,
    )


def test_stop_hpc_server_clears_stale_recycled_pid(monkeypatch):
    from y_web.src.hpc import server as hpc_server

    exp = _build_hpc_experiment(server_pid=79228)
    query = MagicMock()
    query.filter_by.return_value.first.return_value = exp

    monkeypatch.setattr(hpc_server.db.session, "query", lambda *a, **k: query)
    monkeypatch.setattr(hpc_server, "_tracked_process_is_alive", lambda pid: True)
    monkeypatch.setattr(hpc_server, "_is_hpc_server_process", lambda pid: False)
    monkeypatch.setattr(hpc_server.db.session, "commit", lambda: None)

    assert hpc_server.stop_hpc_server(6) is True
    assert exp.server_pid is None


def test_start_hpc_server_clears_stale_pid_and_restarts(monkeypatch):
    from y_web.src.hpc import server as hpc_server

    exp = _build_hpc_experiment(server_pid=74950)
    process = MagicMock()
    process.pid = 90001

    monkeypatch.setattr(
        hpc_server,
        "current_app",
        SimpleNamespace(config={"SQLALCHEMY_DATABASE_URI": "sqlite:///tmp/main.db"}),
    )
    monkeypatch.setattr(hpc_server, "_tracked_process_is_alive", lambda pid: True)
    monkeypatch.setattr(hpc_server, "_is_hpc_server_process", lambda pid: False)
    monkeypatch.setattr(
        hpc_server,
        "_hpc_server_process_matches_experiment",
        lambda pid, exp_folder=None, port=None: False,
    )
    monkeypatch.setattr(hpc_server, "get_base_path", lambda: "/tmp/base")
    monkeypatch.setattr(hpc_server, "get_writable_path", lambda: "/tmp")
    monkeypatch.setattr(hpc_server.Path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(hpc_server, "build_subprocess_env", lambda: {})
    monkeypatch.setattr(
        "y_web.src.simulation.server.detect_env_handler", lambda: "python"
    )
    monkeypatch.setattr(hpc_server.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(hpc_server.db.session, "commit", lambda: None)

    started = hpc_server.start_hpc_server(exp)

    assert started.pid == 90001
    assert exp.server_pid == 90001


def test_stop_hpc_server_force_terminates_process_tree(monkeypatch):
    from y_web.src.hpc import server as hpc_server

    exp = _build_hpc_experiment(server_pid=5555)
    query = MagicMock()
    query.filter_by.return_value.first.return_value = exp

    monkeypatch.setattr(hpc_server.db.session, "query", lambda *a, **k: query)
    monkeypatch.setattr(
        hpc_server, "_resolve_hpc_experiment_folder", lambda current: "/tmp/exp123"
    )
    monkeypatch.setattr(
        hpc_server,
        "_clear_stale_hpc_server_pid",
        lambda current, exp_folder=None: False,
    )
    monkeypatch.setattr(hpc_server, "_tracked_process_is_alive", lambda pid: True)
    monkeypatch.setattr(hpc_server, "_is_hpc_server_process", lambda pid: True)
    monkeypatch.setattr(hpc_server.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(hpc_server.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(hpc_server.os.path, "exists", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(hpc_server.db.session, "commit", lambda: None)

    with (
        patch(
            "y_web.src.simulation.port_manager._force_terminate_process_tree"
        ) as force_kill,
        patch("y_web.src.simulation.port_manager.__terminate_process") as hard_kill,
    ):
        assert hpc_server.stop_hpc_server(6) is True

    force_kill.assert_called_once_with(5555)
    hard_kill.assert_called_once_with(5555)
