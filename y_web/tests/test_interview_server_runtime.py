from types import SimpleNamespace

from y_web.routes.api import interview


def test_pick_listening_port_prefers_configured_port():
    chosen = interview._pick_listening_port([5016, 5022, 5030], preferred_port=5022)
    assert chosen == 5022


def test_server_base_url_prefers_runtime_port(monkeypatch):
    exp = SimpleNamespace(idexp=39, server="127.0.0.1", port=5014, server_pid=7777)

    monkeypatch.setattr(
        interview, "_get_latest_experiment_runtime", lambda current: current
    )
    monkeypatch.setattr(
        interview,
        "_discover_runtime_port_for_experiment_process",
        lambda current, preferred_port=None: 5091,
    )

    assert interview._server_base_url(exp) == "http://127.0.0.1:5091"


def test_server_base_url_falls_back_to_configured_port(monkeypatch):
    exp = SimpleNamespace(idexp=39, server="127.0.0.1", port=5014, server_pid=None)

    monkeypatch.setattr(
        interview, "_get_latest_experiment_runtime", lambda current: current
    )
    monkeypatch.setattr(
        interview,
        "_discover_runtime_port_for_experiment_process",
        lambda current, preferred_port=None: None,
    )

    assert interview._server_base_url(exp) == "http://127.0.0.1:5014"


def test_discover_runtime_port_uses_server_pid_connections(monkeypatch):
    exp = SimpleNamespace(
        idexp=39, db_name="experiments/demo/database_server.db", server_pid=8888
    )

    monkeypatch.setattr(
        interview,
        "_listening_ports_for_pid",
        lambda pid: [5044, 6010] if pid == 8888 else [],
    )

    chosen = interview._discover_runtime_port_for_experiment_process(
        exp, preferred_port=5014
    )

    assert chosen == 5044
