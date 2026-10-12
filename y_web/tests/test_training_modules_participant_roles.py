"""C4 - ``student`` as an alias of ``user``, ``session["platform_account_id"]`` and the
generic ``post_login`` hook (E3). Hooks are exercised with a fake plugin."""

import uuid

from y_web.routes.auth.routes import PARTICIPANT_ROLES
from y_web.tests.test_training_modules_baseline_auth import (  # noqa: F401
    _make_admin_user,
    _make_experiment,
    core_app,
)
from y_web.tests.test_training_modules_manifest_keys import _make_plugin

PASSWORD = {"password": "Passw0rd!"}


def _assign(user_id, exp_id):
    from y_web import db
    from y_web.src.models import User_Experiment

    db.session.add(User_Experiment(user_id=user_id, exp_id=exp_id))
    db.session.commit()


def _post_login(client, email):
    return client.post("/login", data={"email": email, **PASSWORD})


def _participant(core_app, role, assigned=True):
    with core_app.app_context():
        row = _make_admin_user(role)
        exp = _make_experiment()
        if assigned:
            _assign(row.id, exp.idexp)
        return row.id, row.email, exp.idexp


def test_participant_roles_constant():
    assert PARTICIPANT_ROLES == ("user", "student")


def test_student_follows_exactly_the_user_flow(core_app):
    results = {}
    for role in ("user", "student"):
        uid, email, _exp = _participant(core_app, role)
        client = core_app.test_client()
        resp = _post_login(client, email)
        with client.session_transaction() as sess:
            results[role] = (
                resp.status_code,
                b"experiment" in resp.data.lower(),
                "_user_id" in sess,  # not logged in before experiment selection
                sess.get("platform_account_id") == uid,
                "exp_select_token" in sess,
            )
    assert results["user"] == results["student"] == (200, True, False, True, True)


def test_unassigned_student_is_bounced_like_a_user(core_app):
    outcomes = []
    for role in ("user", "student"):
        _uid, email, _ = _participant(core_app, role, assigned=False)
        client = core_app.test_client()
        resp = _post_login(client, email)
        with client.session_transaction() as sess:
            flashed = [m for _c, m in sess.get("_flashes", [])]
        outcomes.append((resp.status_code, resp.headers["Location"], flashed))
    assert outcomes[0] == outcomes[1]
    assert "not assigned" in outcomes[0][2][0]


def test_platform_account_id_is_absent_for_staff_and_cleared_on_next_login(core_app):
    uid, email, _ = _participant(core_app, "student")
    with core_app.app_context():
        admin = _make_admin_user("admin")
        admin_email = admin.email
    client = core_app.test_client()
    _post_login(client, email)
    with client.session_transaction() as sess:
        assert sess["platform_account_id"] == uid
    _post_login(client, admin_email)  # same browser, now staff
    with client.session_transaction() as sess:
        assert "platform_account_id" not in sess


def test_select_experiment_keeps_platform_account_id(core_app):
    from y_web.src.experiment.helpers import open_experiment_session  # noqa: F401

    uid, email, exp_id = _participant(core_app, "student")
    client = core_app.test_client()
    resp = _post_login(client, email)
    with client.session_transaction() as sess:
        token = sess["exp_select_token"]
    resp = client.post(
        "/select_experiment", data={"experiment_id": exp_id, "auth_token": token}
    )
    assert resp.status_code == 302 and "/onboarding/" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess["platform_account_id"] == uid


def test_logout_clears_platform_account_id(core_app):
    """/logout needs a user the loader can resolve (staff); it drops the key."""
    with core_app.app_context():
        admin_id = _make_admin_user("admin").get_id()
    client = core_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = admin_id
        sess["_fresh"] = True
        sess["platform_account_id"] = 123
    client.get("/logout")
    with client.session_transaction() as sess:
        assert "platform_account_id" not in sess


# ---------------------------------------------------------------- post_login hook
HOOKS = """
def redirect_hook(admin_user):
    return "/training/landing"

def external_hook(admin_user):
    return "https://evil.example/phish"

def protocol_relative_hook(admin_user):
    return "//evil.example/x"

def raising_hook(admin_user):
    raise RuntimeError("hook crashed")

def none_hook(admin_user):
    return None
"""


def _hook_plugin(tmp_path, monkeypatch, hook_name):
    repo = _make_plugin(
        tmp_path, monkeypatch, {"hooks": {"post_login": f"pkg.hooks:{hook_name}"}}
    )
    (repo / "pkg" / "hooks.py").write_text(HOOKS)
    return repo


def test_post_login_hook_can_redirect_participants(core_app, tmp_path, monkeypatch):
    _hook_plugin(tmp_path, monkeypatch, "redirect_hook")
    for role in ("user", "student"):
        uid, email, _ = _participant(core_app, role, assigned=False)
        client = core_app.test_client()
        resp = _post_login(client, email)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/training/landing")
        with client.session_transaction() as sess:
            assert sess["platform_account_id"] == uid


def test_post_login_hook_is_not_called_for_staff(core_app, tmp_path, monkeypatch):
    _hook_plugin(tmp_path, monkeypatch, "redirect_hook")
    with core_app.app_context():
        email = _make_admin_user("admin").email
    resp = _post_login(core_app.test_client(), email)
    assert "/training/landing" not in resp.headers["Location"]


def test_non_local_hook_redirects_are_ignored(core_app, tmp_path, monkeypatch):
    for hook in ("external_hook", "protocol_relative_hook"):
        (tmp_path / hook).mkdir()
        _hook_plugin(tmp_path / hook, monkeypatch, hook)
        _uid, email, _ = _participant(core_app, "student")
        resp = _post_login(core_app.test_client(), email)
        assert resp.status_code == 200  # default experiment selection page


def test_raising_or_none_hook_does_not_interrupt_login(core_app, tmp_path, monkeypatch):
    for hook in ("raising_hook", "none_hook"):
        (tmp_path / hook).mkdir()
        _hook_plugin(tmp_path / hook, monkeypatch, hook)
        _uid, email, _ = _participant(core_app, "student")
        resp = _post_login(core_app.test_client(), email)
        assert resp.status_code == 200 and b"experiment" in resp.data.lower()


def test_no_hook_registered_leaves_the_flow_unchanged(core_app):
    _uid, email, _ = _participant(core_app, "user")
    resp = _post_login(core_app.test_client(), email)
    assert resp.status_code == 200


# ---------------------------------------------------------------- admin forms
def test_admin_can_bulk_create_student_accounts(core_app):
    from sqlalchemy import select

    from y_web import db
    from y_web.src.models import Admin_users

    with core_app.app_context():
        admin = _make_admin_user("admin")
        admin_id = admin.get_id()
    client = core_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = admin_id
        sess["_fresh"] = True
    name = "stud" + uuid.uuid4().hex[:6]
    resp = client.post(
        "/admin/bulk_create_users",
        data={"users_data": f"{name},{name}@example.test,student", "role": "user"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with core_app.app_context():
        row = db.session.scalars(select(Admin_users).filter_by(username=name)).first()
        assert row is not None and row.role == "student"


def test_users_page_offers_the_student_role(core_app):
    with core_app.app_context():
        admin_id = _make_admin_user("admin").get_id()
    client = core_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = admin_id
        sess["_fresh"] = True
    html = client.get("/admin/users").get_data(as_text=True)
    assert '<option value="student">' in html
