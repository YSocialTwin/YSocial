from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from y_web.src.simulation.execution_backend import (
    start_client_for_experiment,
    start_server_for_experiment,
    stop_client_for_experiment,
    stop_server_for_experiment,
    uses_hpc_backend,
)
from y_web.src.simulation.process_runner import _resolve_client_package_dir
from y_web.src.simulation.server import _resolve_server_runtime_paths

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("platform_type", "expected_suffix"),
    [
        ("microblogging", "external/YServer/y_server_run.py"),
        ("forum", "external/YServerReddit/y_server_run.py"),
    ],
)
def test_resolve_server_runtime_paths_separates_standard_and_forum(
    platform_type, expected_suffix
):
    server_dir, script_path = _resolve_server_runtime_paths("/repo", platform_type)

    assert script_path.endswith(expected_suffix)
    assert script_path.startswith(server_dir)


@pytest.mark.parametrize(
    ("platform_type", "expected_suffix"),
    [
        ("microblogging", "external/YClient"),
        ("forum", "external/YClientReddit"),
    ],
)
def test_resolve_client_package_dir_separates_standard_and_forum(
    platform_type, expected_suffix
):
    package_dir = _resolve_client_package_dir("/repo", platform_type)
    assert package_dir.endswith(expected_suffix)


@pytest.mark.parametrize(
    ("simulator_type", "expected"),
    [("Standard", False), ("HPC", True)],
)
def test_uses_hpc_backend(simulator_type, expected):
    exp = SimpleNamespace(simulator_type=simulator_type)
    assert uses_hpc_backend(exp) is expected


def test_start_server_for_forum_uses_standard_server_path(monkeypatch):
    exp = SimpleNamespace(simulator_type="Standard", platform_type="forum")
    mock_standard = MagicMock(return_value="forum-server")
    mock_hpc = MagicMock()

    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.start_server", mock_standard
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.start_hpc_server", mock_hpc
    )

    assert start_server_for_experiment(exp) == "forum-server"
    mock_standard.assert_called_once_with(exp)
    mock_hpc.assert_not_called()


def test_start_client_for_forum_uses_standard_client_path(monkeypatch):
    exp = SimpleNamespace(simulator_type="Standard", platform_type="forum")
    client = SimpleNamespace()
    population = SimpleNamespace()
    mock_standard = MagicMock(return_value="forum-client")
    mock_hpc = MagicMock()
    mock_backup = MagicMock()

    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.start_client", mock_standard
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.start_hpc_client", mock_hpc
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.backup_population_for_hpc_client",
        mock_backup,
    )

    assert (
        start_client_for_experiment(exp, client, population, resume=True)
        == "forum-client"
    )
    mock_standard.assert_called_once_with(exp, client, population, resume=True)
    mock_hpc.assert_not_called()
    mock_backup.assert_not_called()


def test_hpc_client_start_keeps_backup_specificity(monkeypatch):
    exp = SimpleNamespace(simulator_type="HPC", platform_type="microblogging")
    client = SimpleNamespace()
    population = SimpleNamespace()
    mock_standard = MagicMock()
    mock_hpc = MagicMock(return_value="hpc-client")
    mock_backup = MagicMock()

    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.start_client", mock_standard
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.start_hpc_client", mock_hpc
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.backup_population_for_hpc_client",
        mock_backup,
    )

    assert start_client_for_experiment(exp, client, population) == "hpc-client"
    mock_backup.assert_called_once_with(exp, client, population)
    mock_hpc.assert_called_once_with(exp, client, population)
    mock_standard.assert_not_called()


def test_stop_client_for_forum_uses_standard_terminate(monkeypatch):
    exp = SimpleNamespace(simulator_type="Standard", platform_type="forum")
    client = SimpleNamespace()
    mock_standard = MagicMock(return_value="stopped")
    mock_hpc = MagicMock()

    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.terminate_client", mock_standard
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.stop_hpc_client", mock_hpc
    )

    assert stop_client_for_experiment(exp, client, pause=True) == "stopped"
    mock_standard.assert_called_once_with(client, pause=True)
    mock_hpc.assert_not_called()


def test_stop_server_for_forum_uses_standard_termination(monkeypatch):
    exp = SimpleNamespace(
        idexp=24, port=5555, simulator_type="Standard", platform_type="forum"
    )
    mock_standard = MagicMock(return_value=True)
    mock_hpc = MagicMock()
    mock_port_fallback = MagicMock()

    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.terminate_server_process", mock_standard
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.stop_all_adhoc_clients",
        MagicMock(),
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.stop_hpc_server", mock_hpc
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.terminate_process_on_port",
        mock_port_fallback,
    )

    assert stop_server_for_experiment(exp) is True
    mock_standard.assert_called_once_with(exp.idexp)
    mock_hpc.assert_not_called()
    mock_port_fallback.assert_not_called()


def test_stop_server_for_forum_falls_back_to_port_termination(monkeypatch):
    exp = SimpleNamespace(
        idexp=24, port=5555, simulator_type="Standard", platform_type="forum"
    )
    mock_standard = MagicMock(return_value=False)
    mock_port_fallback = MagicMock()

    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.terminate_server_process", mock_standard
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.stop_all_adhoc_clients",
        MagicMock(),
    )
    monkeypatch.setattr(
        "y_web.src.simulation.execution_backend.terminate_process_on_port",
        mock_port_fallback,
    )

    assert stop_server_for_experiment(exp) is False
    mock_standard.assert_called_once_with(exp.idexp)
    mock_port_fallback.assert_called_once_with(exp.port)


def test_server_watchdog_syncs_stress_reward_for_forum_clients():
    source = open(
        "/app/y_web/src/simulation/server.py",
        "r",
    ).read()

    assert '{"microblogging", "forum", "hpc"}' in source
    assert "Watchdog: Synchronized stress_reward into" in source
