"""The continue button inside the simulation (real core, real experiment databases, rule written where Scenario Design keeps it)."""

import re

from sqlalchemy import text

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    requires_plugin,
)
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    _exp_session,
    _experiment,
    _experiment_paths_under_tmp,
)
from y_web.tests.test_training_modules_registration_integration import (
    _account,
    _users_in,
)


def _stamps(session, table):
    """Timestamp columns the real Scenario Design table may already have (this test creates a minimal one if absent)."""
    cols = {row[1] for row in session.execute(text(f"PRAGMA table_info({table})"))}
    present = [c for c in ("created_at", "updated_at", "started_at") if c in cols]
    return "".join(f", {c}" for c in present), "".join(
        ", CURRENT_TIMESTAMP" for _ in present
    )


def _release(app, exp_id, master, rule):
    """A release as Scenario Design leaves it: the published scenario of the master, with its button rule."""
    with app.app_context():
        session, engine = _exp_session(app, exp_id)
        try:
            session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS sd_scenario (id INTEGER PRIMARY KEY AUTOINCREMENT, exp_id INTEGER NOT NULL,"
                    " name VARCHAR(255) NOT NULL, status VARCHAR(16) NOT NULL, archived_at DATETIME, advance_rule TEXT)"
                )
            )
            session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS sd_publication (id INTEGER PRIMARY KEY AUTOINCREMENT, scenario_id INTEGER NOT NULL,"
                    " exp_id INTEGER NOT NULL, status VARCHAR(16) NOT NULL)"
                )
            )
            cols, vals = _stamps(session, "sd_scenario")
            sid = session.execute(
                text(
                    f"INSERT INTO sd_scenario (exp_id, name, status, advance_rule{cols}) VALUES (:m, 'Drill', 'published', :r{vals})"
                ),
                {"m": master, "r": rule},
            ).lastrowid
            cols, vals = _stamps(session, "sd_publication")
            session.execute(
                text(
                    f"INSERT INTO sd_publication (scenario_id, exp_id, status{cols}) VALUES (:i, :m, 'succeeded'{vals})"
                ),
                {"i": sid, "m": master},
            )
            session.commit()
        finally:
            session.close()
            engine.dispose()


@requires_plugin
def test_the_button_appears_in_the_simulation_and_moves_the_student_on(
    core_app,
):  # noqa: F811
    core_app.config.pop("TM_EXPERIMENT_SCENARIO")  # read the real experiment databases
    app, admin = core_app, _client_as(core_app, "admin")
    master, with_button, without = (
        _experiment(app, "microblogging", "Standard") for _ in range(3)
    )
    _release(app, with_button, master, '{"mode": "always"}')
    _release(app, without, master, None)
    module = _post(admin, f"{API}/modules", {"title": "Two simulations"}).get_json()[
        "module"
    ]["module_uid"]
    rev = 1
    for i in (1, 2):
        r = _post(
            admin,
            f"{API}/modules/{module}/versions/1/steps",
            {
                "type": "scenario",
                "title": f"Simulation {i}",
                "revision": rev,
                "completion_policy": {"signal_mode": "declared", "criteria": []},
                "config": {
                    "slot_key": f"s{i}",
                    "hint_name": "Sim",
                    "platform_type": "microblogging",
                    "simulator_type": "Standard",
                },
            },
        )
        rev = r.get_json()["revision"]
    assert (
        _post(
            admin, f"{API}/modules/{module}/versions/1/publish", {"revision": rev}
        ).status_code
        == 200
    )
    rid = _post(
        admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Run"}
    ).get_json()["run"]["id"]
    bound = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"]
    keys = [b["step_key"] for b in bound]
    for key, exp in zip(keys, (with_button, without)):
        assert (
            admin.put(
                f"{API}/runs/{rid}/bindings/{key}",
                json={"exp_id": exp},
                headers={"X-CSRF-Token": "tok"},
            ).status_code
            == 200
        )
    page = admin.get(f"/admin/training/runs/{rid}").get_data(as_text=True)
    assert "Continue button: always" in page
    account, username, email = _account(app)
    assert (
        _post(
            admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}
        ).status_code
        == 201
    )
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200

    me = app.test_client()
    assert me.post("/login", data={"email": email, "password": "x"}).status_code == 302
    me.get(f"/training/runs/{rid}")
    with me.session_transaction() as s:
        csrf = s["tm_csrf"]
    launch = me.post(
        f"/training/runs/{rid}/steps/{keys[0]}/start", data={"csrf_token": csrf}
    )
    token = re.search(
        r'name="auth_token" value="([^"]+)"', launch.get_data(as_text=True)
    ).group(1)
    entered = me.post(
        "/select_experiment", data={"experiment_id": with_button, "auth_token": token}
    )
    user = _users_in(app, with_button, username)[0]
    feed = me.get(f"/{with_button}/feed/{user}/feed/rf/1")
    html = feed.get_data(as_text=True)
    assert (
        feed.status_code == 200
        and 'id="tm-advance"' in html
        and f"/training/runs/{rid}/steps/{keys[0]}/advance" in html
    )

    state = me.get(f"/training/runs/{rid}/steps/{keys[0]}/advance").get_json()
    assert state["visible"] is True
    pressed = me.post(
        f"/training/runs/{rid}/steps/{keys[0]}/advance", headers={"X-CSRF-Token": csrf}
    )
    assert pressed.status_code == 200 and pressed.get_json()["status"] == "completed"
    run_page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    assert (
        'data-step="%s" data-status="completed"' % keys[0] in run_page
        and 'data-step="%s" data-status="available"' % keys[1] in run_page
    )
    assert 'id="tm-advance"' not in me.get(
        f"/{with_button}/feed/{user}/feed/rf/1"
    ).get_data(
        as_text=True
    )  # finished: gone

    # the second simulation has no rule: nothing is shown there
    launch = me.post(
        f"/training/runs/{rid}/steps/{keys[1]}/start", data={"csrf_token": csrf}
    )
    token = re.search(
        r'name="auth_token" value="([^"]+)"', launch.get_data(as_text=True)
    ).group(1)
    me.post("/select_experiment", data={"experiment_id": without, "auth_token": token})
    other = _users_in(app, without, username)[0]
    assert 'id="tm-advance"' not in me.get(
        f"/{without}/feed/{other}/feed/rf/1"
    ).get_data(as_text=True)
