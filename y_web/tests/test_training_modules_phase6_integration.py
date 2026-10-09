"""Phase 6 (G6) integration: the participant area against the real core.

Real login flow (``post_login`` hook), real ``/select_experiment``
(``experiment_user_provisioned`` hook, identity map), the real
``experiment_access_guard`` and real experiment databases; one pass per
platform with participant ids that deliberately differ from the account ids.
Skips without the plugin.
"""

import re
import uuid

import pytest
from werkzeug.security import generate_password_hash

from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import API, _client_as, _post, requires_plugin

PLATFORMS = [
    ("microblogging", "Standard"),
    ("microblogging", "HPC"),
    ("forum", "Standard"),
    ("photo_sharing", "Standard"),
]


@pytest.fixture(autouse=True)
def _experiment_paths_under_tmp(monkeypatch, tmp_path):
    """``register_experiment_database`` resolves paths itself: keep every experiment file under tmp_path."""

    def _tmp(relative_path=""):
        return str(tmp_path / str(relative_path).replace("/", "_").replace("\\", "_"))

    monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", _tmp)


def _experiment(app, platform, simulator):
    from y_web import db
    from y_web.src.models import Exps

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        row = Exps(
            platform_type=platform, exp_name=f"p6{tag}", db_name=f"experiments/p6{tag}/database_server.db",
            owner="admin", exp_descr="d", status=1, running=0, port=5000 + int(tag[:3], 16) % 1000,
            simulator_type=simulator,
        )
        db.session.add(row)
        db.session.commit()
        return row.idexp


def _participant(app, exp_id, role="user"):
    from y_web import db
    from y_web.src.models import Admin_users, User_Experiment

    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        row = Admin_users(username=f"s{tag}", email=f"s{tag}@example.test", password=generate_password_hash("x"),
                          last_seen="2026-01-01", role=role)
        db.session.add(row)
        db.session.commit()
        db.session.add(User_Experiment(user_id=row.id, exp_id=exp_id))
        db.session.commit()
        return row.id, row.username, row.email


def _exp_session(app, exp_id):
    from y_web import db
    from y_web.src.experiment.helpers import open_experiment_session
    from y_web.src.models import Exps

    exp = db.session.get(Exps, exp_id)
    return open_experiment_session(exp)


def _preexisting_platform_user(app, exp_id, username, email, platform_id):
    """The participant already exists in the experiment under an id unrelated to the account."""
    from y_web.src.models import User_mgmt

    with app.app_context():
        session, engine = _exp_session(app, exp_id)
        try:
            session.add(User_mgmt(id=platform_id, username=username, email=email, password="x", joined_on=0))
            session.commit()
        finally:
            session.close()
            engine.dispose()


def _post_as(app, exp_id, user_id, count, platform="microblogging"):
    from sqlalchemy import text

    from y_web.src.models import Post

    with app.app_context():
        session, engine = _exp_session(app, exp_id)
        try:
            for _ in range(count):
                if platform == "photo_sharing":  # its own schema: string ids, ``photos`` instead of ``post``
                    session.execute(text("INSERT INTO photos (id, user_id, round, image_url) VALUES (:i, :u, 'r1', 'x')"),
                                    {"i": str(uuid.uuid4()), "u": str(user_id)})
                else:
                    session.add(Post(tweet="t", round=1, user_id=user_id))
            session.commit()
        finally:
            session.close()
            engine.dispose()


def _module(admin, platform, simulator):
    uid = _post(admin, f"{API}/modules", {"title": "G6 module"}).get_json()["module"]["module_uid"]
    rev = 1
    policies = [
        {"signal_mode": "verified", "criteria": [{"type": "min_activity", "posts": 2, "reactions": 0}]},
        {"signal_mode": "declared", "criteria": []},
    ]
    for i, policy in enumerate(policies, start=1):
        cfg = {"slot_key": f"s{i}", "hint_name": "Intro", "platform_type": platform, "simulator_type": simulator}
        r = _post(admin, f"{API}/modules/{uid}/versions/1/steps",
                  {"revision": rev, "type": "scenario", "title": f"Step {i}", "config": cfg, "completion_policy": policy})
        assert r.status_code == 201, r.get_json()
        rev = r.get_json()["revision"]
    assert _post(admin, f"{API}/modules/{uid}/versions/1/publish", {"revision": rev}).status_code == 200
    return uid


def _status(app, rid, step_key):
    from sqlalchemy import text

    from y_web import db

    with app.app_context():
        engine = db.engines["db_admin"]
        with engine.connect() as c:
            return c.execute(text(
                "SELECT p.status FROM tm_step_progress p JOIN tm_enrollment e ON e.id = p.enrollment_id "
                "WHERE e.run_id = :r AND p.step_key = :k ORDER BY p.attempt_no DESC"), {"r": rid, "k": step_key}).scalar()


@requires_plugin
@pytest.mark.parametrize("platform,simulator", PLATFORMS, ids=[f"{p}-{s}" for p, s in PLATFORMS])
def test_participant_path_through_the_real_core(core_app, platform, simulator):
    from y_web import db
    from y_web.src.models import Exps

    admin = _client_as(core_app, "admin")
    exp = _experiment(core_app, platform, simulator)
    unbound = _experiment(core_app, platform, simulator)
    uid = _module(admin, platform, simulator)
    rid = _post(admin, f"{API}/runs", {"module_uid": uid, "version_no": 1, "name": "G6 run"}).get_json()["run"]["id"]
    keys = [b["step_key"] for b in admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"]]
    for key in keys:
        r = admin.put(f"{API}/runs/{rid}/bindings/{key}", json={"exp_id": exp}, headers={"X-CSRF-Token": "tok"})
        assert r.status_code == 200, r.get_json()
    assert _post(admin, f"{API}/runs/{rid}/activate").status_code == 200

    account, username, email = _participant(core_app, exp)
    with core_app.app_context():
        from y_web.src.models import User_Experiment

        db.session.add(User_Experiment(user_id=account, exp_id=unbound))  # the core would let them in; the guard must not
        db.session.commit()
    platform_id = 700000 + account  # unrelated to the account id
    _preexisting_platform_user(core_app, exp, username, email, platform_id)
    assert _post(admin, f"{API}/runs/{rid}/enrollments", {"admin_user_ids": [account]}).status_code == 201

    me = core_app.test_client()
    login = me.post("/login", data={"email": email, "password": "x"})
    assert login.status_code == 302 and login.headers["Location"].endswith("/training")   # post_login hook
    home = me.get("/training")
    assert home.status_code == 302 and home.headers["Location"].endswith(f"/training/runs/{rid}")
    page = me.get(f"/training/runs/{rid}").get_data(as_text=True)
    assert username not in page and email not in page
    with me.session_transaction() as s:
        csrf = s["tm_csrf"]
    assert me.post(f"/training/runs/{rid}/steps/{keys[1]}/start", data={"csrf_token": csrf}).status_code == 403  # locked

    launch = me.post(f"/training/runs/{rid}/steps/{keys[0]}/start", data={"csrf_token": csrf})
    assert launch.status_code == 200
    token = re.search(r'name="auth_token" value="([^"]+)"', launch.get_data(as_text=True)).group(1)
    entered = me.post("/select_experiment", data={"experiment_id": exp, "auth_token": token})
    assert entered.status_code == 302 and f"/{exp}/onboarding/{platform_id}" in entered.headers["Location"]

    # the identity map learnt the platform id; the guard lets the bound experiment through and closes the other one
    from sqlalchemy import text

    with core_app.app_context():
        with db.engines["db_admin"].connect() as c:
            mapped = c.execute(text("SELECT external_user_id, id_kind FROM tm_identity_map WHERE status='active'")).all()
    assert mapped == [(str(platform_id), "int")]
    blocked = me.get(f"/{unbound}/onboarding/{platform_id}")
    assert blocked.status_code == 302 and blocked.headers["Location"].endswith("/training")

    _post_as(core_app, exp, account, 5, platform)        # same number as the account id: must not count
    _post_as(core_app, exp, platform_id, 1, platform)
    me.get(f"/training/runs/{rid}")
    assert _status(core_app, rid, keys[0]) == "in_progress"
    _post_as(core_app, exp, platform_id, 1, platform)
    me.get(f"/training/runs/{rid}")
    assert _status(core_app, rid, keys[0]) == "completed" and _status(core_app, rid, keys[1]) == "available"

    assert me.post(f"/training/runs/{rid}/steps/{keys[1]}/start", data={"csrf_token": csrf}).status_code == 200
    assert me.post(f"/training/runs/{rid}/steps/{keys[1]}/declare", data={"csrf_token": csrf}).status_code == 303
    assert "completed all the required steps" in me.get(f"/training/runs/{rid}").get_data(as_text=True)

    # staff view: progress by pseudonym only
    body = admin.get(f"{API}/runs/{rid}/progress").get_data(as_text=True)
    assert username not in body and email not in body and str(platform_id) not in body
