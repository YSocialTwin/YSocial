"""A forum HPC client that died without a requested stop is shown as stopped, with an alert and, when known, the reason."""

import json
from types import SimpleNamespace

import pytest

from y_web.tests.test_forum_hpc_switch_matrix import _env

DETAIL = "sqlite3.OperationalError: no such column: user_mgmt.seq"


def _http(monkeypatch, app, admin_id, name, email):
    user = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        is_anonymous=False,
        id=admin_id,
        username=name,
        role="admin",
        telemetry_enabled=0,
        get_id=lambda: str(admin_id),
        email=email,
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: user)
    monkeypatch.setattr(
        "y_web.src.system.miscellanea.check_privileges", lambda *a, **k: None
    )
    return app.test_client()


@pytest.mark.integration
def test_a_dead_client_is_shown_as_stopped_with_an_alert(monkeypatch, tmp_path):
    from y_web import db
    from y_web.src.models import Client, Client_Execution, Exps

    app, folder, (exp_id, admin_id, name, email, uid) = _env(monkeypatch, tmp_path, 1)
    # the log lookup imported its own reference to the path function: pin it too (other tests may import it first)
    monkeypatch.setattr(
        "y_web.src.hpc.client.get_writable_path", lambda *a: str(tmp_path)
    )
    (folder / "logs").mkdir()
    (folder / "logs" / "a_execution.log").write_text(
        json.dumps(
            {
                "level": "ERROR",
                "message": "Client stopped by an error: OperationalError",
                "error_type": "OperationalError",
                "error_message": DETAIL,
                "exit_code": 1,
            }
        )
        + "\n"
    )
    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        exp.running = 1
        ids = {c.name: c.id for c in db.session.query(Client).filter_by(id_exp=exp_id)}
        for client_name, state in (("a", "failed"), ("b", "running")):
            db.session.add(
                Client_Execution(
                    client_id=ids[client_name],
                    elapsed_time=0,
                    expected_duration_rounds=24,
                    last_active_hour=-1,
                    last_active_day=-1,
                    terminal_state=state,
                )
            )
        db.session.query(Client).filter_by(id=ids["a"]).update(
            {"status": 0, "pid": None}
        )
        db.session.commit()
    http = _http(monkeypatch, app, admin_id, name, email)

    html = http.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert "Unexpected error in the client" in html and DETAIL in html
    assert html.count("mdi-alert-circle-outline") >= 1
    assert f'data-client-status="0"' in html  # what the page polls against

    # the progress endpoint reports the state, so an open page notices a change
    state = json.loads(http.get(f"/admin/progress/{ids['a']}").data)
    assert state["status"] == 0 and state["terminal_state"] == "failed"
    assert (
        json.loads(http.get(f"/admin/progress/{ids['b']}").data)["terminal_state"]
        == "running"
    )

    # without a record in the log the page still says that it died, and a running client has no alert
    (folder / "logs" / "a_execution.log").write_text("")
    html = http.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert "stopped unexpectedly" in html and DETAIL not in html
    with app.app_context():
        db.session.query(Client_Execution).filter_by(client_id=ids["a"]).update(
            {"terminal_state": "manual_stop"}
        )
        db.session.commit()
    html = http.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert "stopped unexpectedly" not in html  # a requested stop is not a failure
