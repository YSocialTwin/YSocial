"""C6 - ``experiment_user_provisioned`` event emitted by ``ensure_experiment_user`` (E5).
Exercised with a fake plugin."""

import sys

from y_web.tests.test_training_modules_baseline_auth import (  # noqa: F401
    _make_admin_user,
    _make_experiment,
    core_app,
)
from y_web.tests.test_training_modules_manifest_keys import _make_plugin

HOOKS = '''
EVENTS = []

def record(exp, account_id, exp_user_id, created):
    EVENTS.append((exp.idexp, account_id, exp_user_id, created))

def raising(exp, account_id, exp_user_id, created):
    raise RuntimeError("hook crashed")
'''


def _install(tmp_path, monkeypatch, name="record"):
    repo = _make_plugin(
        tmp_path, monkeypatch, {"hooks": {"experiment_user_provisioned": f"pkg.hooks:{name}"}}
    )
    (repo / "pkg" / "hooks.py").write_text(HOOKS)


def _events():
    mods = [m for n, m in sys.modules.items() if n.endswith("pkg.hooks") and "fake_suite" in n]
    return mods[-1].EVENTS if mods else []


def _ensure(exp, account, **extra):
    from y_web.src.experiment.helpers import ensure_experiment_user

    return ensure_experiment_user(
        exp,
        user_id=extra.pop("user_id", account.id),
        username=account.username,
        email=account.email,
        password=account.password,
        **extra,
    )


def test_event_carries_explicit_account_id_and_created_flag(core_app, tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch)
    with core_app.test_request_context("/"):
        account = _make_admin_user("student")
        exp = _make_experiment()
        user, created = _ensure(exp, account, account_id=account.id)
        assert created is True
        again, created_again = _ensure(exp, account, account_id=account.id)
        assert created_again is False and again.id == user.id
        assert _events() == [
            (exp.idexp, account.id, user.id, True),
            (exp.idexp, account.id, user.id, False),  # also for reused rows
        ]


def test_no_event_without_account_id(core_app, tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch)
    with core_app.test_request_context("/"):
        account = _make_admin_user("user")
        exp = _make_experiment()
        _ensure(exp, account)
        assert _events() == []


def test_raising_hook_never_changes_the_result(core_app, tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, "raising")
    with core_app.test_request_context("/"):
        account = _make_admin_user("user")
        exp = _make_experiment()
        user, created = _ensure(exp, account, account_id=account.id)
        assert created is True and user.id == account.id


def test_without_any_hook_the_function_behaves_as_before(core_app):
    with core_app.test_request_context("/"):
        account = _make_admin_user("user")
        exp = _make_experiment()
        user, created = _ensure(exp, account, account_id=account.id)
        assert (user.id, created) == (account.id, True)


def test_select_experiment_flow_emits_the_event(core_app, tmp_path, monkeypatch):
    from y_web import db
    from y_web.src.models import User_Experiment

    _install(tmp_path, monkeypatch)
    with core_app.app_context():
        account = _make_admin_user("student")
        exp = _make_experiment()
        db.session.add(User_Experiment(user_id=account.id, exp_id=exp.idexp))
        db.session.commit()
        account_id, email, exp_id = account.id, account.email, exp.idexp
    client = core_app.test_client()
    client.post("/login", data={"email": email, "password": "Passw0rd!"})
    with client.session_transaction() as sess:
        token = sess["exp_select_token"]
    client.post("/select_experiment", data={"experiment_id": exp_id, "auth_token": token})
    assert (exp_id, account_id, account_id, True) in _events()
