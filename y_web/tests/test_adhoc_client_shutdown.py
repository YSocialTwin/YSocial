from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


from pathlib import Path
from types import SimpleNamespace

from flask import Flask


def test_stop_adhoc_client_terminates_orphan_processes_without_state_pid(monkeypatch):
    from y_web.src.simulation import adhoc_client as mod

    config_path = Path("/tmp/adhoc_client_test.json")
    state_path = Path("/tmp/adhoc_client_test.state.json")
    writes = []
    terminated = []

    monkeypatch.setattr(
        mod, "config_path_for_client", lambda experiment, client_key: config_path
    )
    monkeypatch.setattr(mod, "state_path_for_config", lambda path: state_path)
    monkeypatch.setattr(
        mod,
        "ensure_state_for_config",
        lambda path: {"status": 0, "pid": None, "completed": False},
    )
    monkeypatch.setattr(mod, "_unregister_process", lambda key: None)
    monkeypatch.setattr(mod, "_find_matching_adhoc_pids", lambda path: [12345, 12346])
    monkeypatch.setattr(
        mod,
        "_terminate_pid",
        lambda pid, timeout_seconds=3.0: terminated.append(pid) or True,
    )
    monkeypatch.setattr(
        mod, "write_json", lambda path, payload: writes.append((path, payload.copy()))
    )

    experiment = SimpleNamespace(idexp=8)

    assert mod.stop_adhoc_client(experiment, "propaganda_prop1", pause=False) is True
    assert terminated == [12345, 12346]
    assert writes[-1][0] == state_path
    assert writes[-1][1]["status"] == 0
    assert writes[-1][1]["pid"] is None


def test_stop_server_for_experiment_stops_all_adhoc_clients(monkeypatch):
    from y_web.src.simulation import execution_backend as mod

    calls = []
    experiment = SimpleNamespace(idexp=8, simulator_type="Standard", port=5002)

    monkeypatch.setattr(
        mod,
        "stop_all_adhoc_clients",
        lambda experiment, pause=False: calls.append(("adhoc", pause)),
    )
    monkeypatch.setattr(
        mod,
        "terminate_server_process",
        lambda exp_id: calls.append(("server", exp_id)) or True,
    )
    monkeypatch.setattr(
        mod, "terminate_process_on_port", lambda port: calls.append(("port", port))
    )

    assert mod.stop_server_for_experiment(experiment) is True
    assert calls == [("adhoc", False), ("server", 8)]


def test_stop_experiment_also_stops_adhoc_clients_when_exp_already_marked_stopped(
    monkeypatch,
):
    from y_web.routes.admin.sub.experiments import _crud as mod

    app = Flask(__name__)
    experiment = SimpleNamespace(idexp=8, running=0)

    class _FakeExpsQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return experiment

    stopped = []

    monkeypatch.setattr(mod, "check_privileges", lambda username: None)
    monkeypatch.setattr(mod, "current_user", SimpleNamespace(username="admin"))
    monkeypatch.setattr(
        mod, "_current_admin_user_or_none", lambda: SimpleNamespace(username="admin")
    )
    monkeypatch.setattr(mod, "user_can_manage_experiment", lambda admin_user, exp: True)
    monkeypatch.setattr(
        mod, "_experiment_configuration_update_required", lambda exp: False
    )
    monkeypatch.setattr(
        mod,
        "stop_all_adhoc_clients",
        lambda exp, pause=False: stopped.append((exp.idexp, pause)),
    )
    monkeypatch.setattr(mod, "Exps", SimpleNamespace(query=_FakeExpsQuery()))
    monkeypatch.setattr(mod, "experiment_details", lambda uid: f"details:{uid}")

    with app.test_request_context("/admin/stop_experiment/8"):
        result = mod.stop_experiment.__wrapped__(8)

    assert result == "details:8"
    assert stopped == [(8, False)]
