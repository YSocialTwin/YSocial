"""Students of a run are registered in, and logged into, every simulation of the module (real core, real experiment databases)."""

import re
import uuid

from werkzeug.security import generate_password_hash

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin
from y_web.tests.test_training_modules_phase6_integration import (  # noqa: F401
    _experiment, _experiment_paths_under_tmp, _exp_session)
from y_web.tests.test_training_modules_phase10_integration import _count

SIMS = [("microblogging", "Standard"), ("microblogging", "Standard"), ("forum", "Standard")]


def _account(app):
    """A student account that is assigned to no experiment at all."""
    from y_web import db
    from y_web.src.models import Admin_users

    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        row = Admin_users(username=f"r{tag}", email=f"r{tag}@example.test", password=generate_password_hash("x"),
                          last_seen="2026-01-01", role="user")
        db.session.add(row)
        db.session.commit()
        return row.id, row.username, row.email


def _users_in(app, exp_id, username):
    from y_web.src.models import User_mgmt

    with app.app_context():
        session, engine = _exp_session(app, exp_id)
        try:
            return [u.id for u in session.query(User_mgmt).filter_by(username=username).all()]
        finally:
            session.close()
            engine.dispose()


def _assigned(app, account):
    from y_web import db
    from y_web.src.models import User_Experiment

    with app.app_context():
        return sorted(r.exp_id for r in db.session.query(User_Experiment).filter_by(user_id=account).all())


@requires_plugin
def test_students_are_registered_and_logged_into_every_simulation_of_the_module(core_app):  # noqa: F811
    from y_web import db
    from y_web.src.models import Exps

    app, admin = core_app, _client_as(core_app, "admin")
    exps = [_experiment(app, p, s) for p, s in SIMS]
    with app.app_context():
        db.session.get(Exps, exps[2]).status = 0      # the third simulation still has to be switched on
        db.session.commit()
    module = _post(admin, f"{API}/modules", {"title": "Three simulations"}).get_json()["module"]["module_uid"]
    rev = 1
    for i, (platform, simulator) in enumerate(SIMS, start=1):
        r = _post(admin, f"{API}/modules/{module}/versions/1/steps", {
            "type": "scenario", "title": f"Simulation {i}", "revision": rev, "completion_policy": {"signal_mode": "declared", "criteria": []},
            "config": {"slot_key": f"s{i}", "hint_name": "Sim", "platform_type": platform, "simulator_type": simulator}})
        assert r.status_code == 201, r.get_json()
        rev = r.get_json()["revision"]
    assert _post(admin, f"{API}/modules/{module}/versions/1/publish", {"revision": rev}).status_code == 200
    rid = _post(admin, f"{API}/runs", {"module_uid": module, "version_no": 1, "name": "Run"}).get_json()["run"]["id"]
    keys = [b["step_key"] for b in admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"]]
    for key, exp in zip(keys, exps):
        assert admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": exp}, headers={"X-CSRF-Token": "tok"}).status_code == 200

    people = [_account(app) for _ in range(2)]
    assert all(_assigned(app, a) == [] for a, _, _ in people)
    enrolled = _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [a for a, _, _ in people]})
    assert enrolled.status_code == 201
    before = admin.get(f"{API}/runs/{rid}/registration").get_json()
    assert before["summary"]["ok"] is False and before["summary"]["not_assigned"] == 6

    # switching the third simulation on registers the students in it; the run page then sets up the others
    assert _post(admin, f"{API}/runs/{rid}/experiments/{exps[2]}/activate").status_code == 200
    for account, username, _ in people:
        assert _assigned(app, account) == [exps[2]] and len(_users_in(app, exps[2], username)) == 1
        assert _users_in(app, exps[0], username) == []
    done = _post(admin, f"{API}/runs/{rid}/registration/sync").get_json()
    assert done["summary"]["ok"] is True and done["summary"]["ready"] == 6
    for account, username, _ in people:
        assert _assigned(app, account) == sorted(exps)
        assert all(len(_users_in(app, e, username)) == 1 for e in exps)
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200

    # each student enters every simulation through the plugin and lands in the user that was registered there
    for account, username, email in people:
        known = {e: _users_in(app, e, username)[0] for e in exps}
        me = app.test_client()
        assert me.post("/login", data={"email": email, "password": "x"}).headers["Location"].endswith("/training")
        assert me.get(f"/training/runs/{rid}").status_code == 200
        with me.session_transaction() as s:
            csrf = s["tm_csrf"]
        for key, exp in zip(keys, exps):
            launch = me.post(f"/training/runs/{rid}/steps/{key}/start", data={"csrf_token": csrf})
            assert launch.status_code == 200, (exp, launch.status_code)
            token = re.search(r'name="auth_token" value="([^"]+)"', launch.get_data(as_text=True)).group(1)
            entered = me.post("/select_experiment", data={"experiment_id": exp, "auth_token": token})
            assert entered.status_code == 302 and entered.headers["Location"].endswith(f"/{exp}/onboarding/{known[exp]}")
            assert me.get(entered.headers["Location"]).status_code == 200      # logged in there
            assert me.post(f"/training/runs/{rid}/steps/{key}/declare", data={"csrf_token": csrf}).status_code == 303
        assert all(_users_in(app, e, username) == [known[e]] for e in exps)    # nobody was registered twice
    assert _count(app, f"SELECT COUNT(*) FROM tm_identity_map WHERE status='active'") == 6
