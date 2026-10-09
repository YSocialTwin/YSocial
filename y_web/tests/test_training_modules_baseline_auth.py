"""
Phase 0 characterization tests for the TrainingModules plugin (points [NV] a, c).

These tests assert what the core does *today*, not what it should do.  They are
the evidence behind docs/decisions.md of the TrainingModules plugin: if one of
them starts failing after a core change, the plan (piano tecnico, sezione 1)
must be re-checked before going on.

They exercise core code only and do not depend on any plugin being installed.
"""

import uuid

import pytest
from flask import Response
from sqlalchemy import select
from werkzeug.security import generate_password_hash


@pytest.fixture
def core_app(monkeypatch, tmp_path):
    """Real create_app() with experiment databases redirected under tmp_path."""
    from y_web import create_app

    def _tmp_writable_path(relative_path=""):
        return str(tmp_path / str(relative_path).replace("/", "_").replace("\\", "_"))

    monkeypatch.setattr(
        "y_web.src.experiment.helpers.get_writable_path", _tmp_writable_path
    )
    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


def _suffix():
    return uuid.uuid4().hex[:6]


def _make_admin_user(role, suffix=None):
    from y_web import db
    from y_web.src.models import Admin_users

    suffix = suffix or _suffix()
    row = Admin_users(
        username=f"u{suffix}",
        email=f"u{suffix}@example.test",
        password=generate_password_hash("Passw0rd!"),
        last_seen="2026-01-01",
        role=role,
    )
    db.session.add(row)
    db.session.commit()
    return row


# ---------------------------------------------------------------------------
# [NV] (a) check_privileges: its return value and the routes that discard it
# ---------------------------------------------------------------------------
def test_check_privileges_returns_none_for_admin_and_researcher(core_app):
    from y_web.src.system.miscellanea import check_privileges

    with core_app.test_request_context("/"):
        for role in ("admin", "researcher"):
            row = _make_admin_user(role)
            assert check_privileges(row.username) is None


def test_check_privileges_returns_redirect_response_for_role_user(core_app):
    """The denial is a *returned* redirect, not an exception."""
    from y_web.src.system.miscellanea import check_privileges

    with core_app.test_request_context("/"):
        row = _make_admin_user("user")
        result = check_privileges(row.username)
        assert isinstance(result, Response)
        assert result.status_code == 302


def test_check_privileges_raises_for_unknown_username(core_app):
    """An unknown username is an AttributeError (None.role), not a denial."""
    from y_web.src.system.miscellanea import check_privileges

    with core_app.test_request_context("/"):
        with pytest.raises(AttributeError):
            check_privileges("no-such-user-" + _suffix())


def test_admin_route_discards_check_privileges_result_for_role_user(core_app):
    """
    /admin/models_data calls ``check_privileges(current_user.username)`` and
    ignores the returned redirect: a logged-in account whose Admin_users role
    is ``user`` is therefore NOT turned away from this admin JSON endpoint.
    """
    with core_app.app_context():
        row = _make_admin_user("user")
        user_id = row.get_id()

    client = core_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user_id
        sess["_fresh"] = True

    response = client.get("/admin/models_data")
    assert response.status_code != 302, "role=user was redirected (guard works)"
    assert response.status_code == 200
    assert response.is_json


def test_admin_route_with_same_check_is_fine_for_admin(core_app):
    """Control: an admin gets the same answer, so the previous test is not
    simply a route that is open to everybody for other reasons (it needs a
    logged-in session: anonymous users are redirected by @login_required)."""
    client = core_app.test_client()
    response = client.get("/admin/models_data")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Login flow facts that the plugin plan relies on (roles, session)
# ---------------------------------------------------------------------------
def test_login_rejects_unknown_role_student(core_app):
    """Today ``student`` is not an accepted role (plan: E3 makes it an alias of user)."""
    with core_app.app_context():
        row = _make_admin_user("student")
        email = row.email

    client = core_app.test_client()
    response = client.post(
        "/login",
        data={"email": email, "password": "Passw0rd!"},
        follow_redirects=False,
    )
    # login_post flashes "Invalid user role" and redirects back to the login page
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    with client.session_transaction() as sess:
        flashed = [m for _cat, m in sess.get("_flashes", [])]
        assert any("Invalid user role" in m for m in flashed)
        assert "_user_id" not in sess


def test_login_role_user_is_not_logged_in_before_experiment_selection(core_app):
    """A participant with no experiment assignment is bounced; no login_user()."""
    with core_app.app_context():
        row = _make_admin_user("user")
        email = row.email

    client = core_app.test_client()
    response = client.post(
        "/login", data={"email": email, "password": "Passw0rd!"}
    )
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert "_user_id" not in sess


# ---------------------------------------------------------------------------
# [NV] (c) participant ids in experiment databases
# ---------------------------------------------------------------------------
def _make_experiment(platform_type="microblogging", simulator_type="Standard"):
    from y_web import db
    from y_web.src.models import Exps

    tag = _suffix()
    exp = Exps(
        platform_type=platform_type,
        exp_name=f"tm-baseline-{tag}",
        db_name=f"experiments/tm-baseline-{tag}/database_server.db",
        owner="admin",
        exp_descr="phase 0 characterization",
        status=1,
        port=5999,
        simulator_type=simulator_type,
    )
    db.session.add(exp)
    db.session.commit()
    return exp


def _experiment_rows(exp):
    from y_web.src.experiment.helpers import open_experiment_session
    from y_web.src.models import User_mgmt

    session, engine = open_experiment_session(exp)
    try:
        return session.query(User_mgmt).order_by(User_mgmt.id).all()
    finally:
        session.close()
        engine.dispose()


def test_ensure_experiment_user_uses_the_platform_account_id_as_participant_id(
    core_app,
):
    from y_web.src.experiment.helpers import ensure_experiment_user

    with core_app.test_request_context("/"):
        account = _make_admin_user("user")
        exp = _make_experiment()
        user, created = ensure_experiment_user(
            exp,
            user_id=account.id,
            username=account.username,
            email=account.email,
            password=account.password,
        )
        assert created is True
        assert user.id == account.id  # Standard: participant id == Admin_users.id
        assert [u.id for u in _experiment_rows(exp)] == [account.id]


def test_ensure_experiment_user_reuses_row_by_username_even_with_other_id(core_app):
    """Identity is by *username*: a row with the same username but another id is
    returned unchanged, so the id seen in the experiment can differ from the
    platform account id."""
    from y_web.src.experiment.helpers import ensure_experiment_user

    with core_app.test_request_context("/"):
        account = _make_admin_user("user")
        exp = _make_experiment()
        first, _ = ensure_experiment_user(
            exp,
            user_id=account.id + 1000,
            username=account.username,
            email=account.email,
            password=account.password,
        )
        again, created = ensure_experiment_user(
            exp,
            user_id=account.id,
            username=account.username,
            email=account.email,
            password=account.password,
        )
        assert created is False
        assert first.id == account.id + 1000
        assert again.id == first.id != account.id


def test_ensure_experiment_user_collides_with_an_existing_agent_id(core_app):
    """An agent (or any row) already holding the account id makes the insert of a
    different username fail: the id spaces of agents and accounts are shared."""
    from sqlalchemy.exc import IntegrityError

    from y_web.src.experiment.helpers import (
        ensure_experiment_user,
        open_experiment_session,
    )
    from y_web.src.models import User_mgmt

    with core_app.test_request_context("/"):
        account = _make_admin_user("user")
        exp = _make_experiment()
        session, engine = open_experiment_session(exp)
        try:
            session.add(
                User_mgmt(
                    id=account.id,
                    username="agent" + _suffix(),
                    email="",
                    password="x",
                    user_type="user",
                    joined_on=0,
                )
            )
            session.commit()
        finally:
            session.close()
            engine.dispose()

        with pytest.raises(IntegrityError):
            ensure_experiment_user(
                exp,
                user_id=account.id,
                username=account.username,
                email=account.email,
                password=account.password,
            )
