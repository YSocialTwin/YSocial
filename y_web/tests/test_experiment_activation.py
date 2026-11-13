"""The "Activate" toggle of an experiment (route /admin/select_experiment/<id>) after its steps moved to
y_web.src.experiment.activation: same behaviour and messages, and the two functions on their own (idempotent).
"""

import uuid

import pytest

from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)
from y_web.tests.test_world_simulation_ui import (  # noqa: F401  (fixtures and helper)
    login,
    site,
)


def make_user(name, role, number):
    from werkzeug.security import generate_password_hash

    from y_web import db
    from y_web.src.models import Admin_users, User_mgmt

    password = generate_password_hash("x")
    db.session.add(
        User_mgmt(
            id=number,
            username=name,
            email=f"{name}@t.com",
            password=password,
            joined_on=1,
        )
    )
    db.session.add(
        Admin_users(
            id=number,
            username=name,
            email=f"{name}@t.com",
            password=password,
            role=role,
            last_seen="2026-01-01",
        )
    )
    db.session.commit()


@pytest.fixture
def toggle(site, monkeypatch):  # noqa: F811
    """The experiments blueprint on the test app, with the experiment database and participant steps recorded."""
    from flask import Blueprint

    from y_web.routes.admin.sub.experiments import experiments
    from y_web.src.experiment import context, helpers

    app, exps, tmp = site
    stub = Blueprint("admin", __name__)
    stub.add_url_rule("/admin/dashboard", "dashboard", lambda: "dashboard")
    app.register_blueprint(stub)
    app.register_blueprint(experiments)
    for number, (name, role) in enumerate(
        (("toggler", "admin"), ("toggler-researcher", "researcher")), start=900
    ):
        make_user(
            name, role, number
        )  # the session user and the Admin_users row share the id, as in production
    calls = {"register": [], "ensure": [], "ensure_result": "ok"}
    monkeypatch.setattr(
        context,
        "register_experiment_database",
        lambda app_, exp_id, db_name: calls["register"].append((exp_id, db_name)),
    )

    def ensure(exp, **kwargs):
        calls["ensure"].append((exp.idexp, kwargs))
        if calls["ensure_result"] == "none":
            return None, False
        return type("P", (), {"id": kwargs["user_id"]})(), True

    monkeypatch.setattr(helpers, "ensure_experiment_user", ensure)
    return app, exps, calls


def flashes(client):
    with client.session_transaction() as session:
        return [(c, m) for c, m in session.get("_flashes", [])]


def exp_row(exp_id):
    from y_web import db
    from y_web.src.models import Exps

    db.session.expire_all()
    return db.session.get(Exps, exp_id)


def extra(platform, simulator="Standard"):
    from y_web import db
    from y_web.src.models.admin import Exps

    exp = Exps(
        platform_type=platform,
        exp_name=f"{platform}-x",
        db_name=f"experiments/{platform}-x/db.db",
        owner="admin",
        exp_descr="",
        status=0,
        running=0,
        port=5000,
        simulator_type=simulator,
        exp_status="stopped",
    )
    db.session.add(exp)
    db.session.commit()
    return exp.idexp


def admin_row():
    from y_web import db
    from y_web.src.models import Admin_users

    return db.session.query(Admin_users).filter_by(username="toggler").one()


def admin_id():
    return admin_row().id


def user_experiments(exp_id):
    from y_web import db
    from y_web.src.models import User_Experiment

    return (
        db.session.query(User_Experiment)
        .filter_by(user_id=admin_id(), exp_id=exp_id)
        .count()
    )


def test_the_toggle_activates_then_deactivates_with_the_same_messages(toggle):
    app, exps, calls = toggle
    exp_id = exps["microblogging"]
    client = login(app, "toggler")
    response = client.get(f"/admin/select_experiment/{exp_id}")
    assert response.status_code == 302 and response.headers["Location"].endswith(
        "/admin/dashboard"
    )
    assert exp_row(exp_id).status == 1
    assert flashes(client) == [("message", "Experiment 'microblogging' activated.")]
    assert calls["register"] == [(exp_id, "experiments/microblogging/db.db")]
    ((ensured_id, kwargs),) = calls["ensure"]
    assert (
        ensured_id == exp_id
        and kwargs["user_id"] == admin_id()
        and kwargs["account_id"] == admin_id()
    )
    assert (
        kwargs["username"] == "toggler"
        and kwargs["email"] == admin_row().email
        and kwargs["password"] == admin_row().password
    )
    assert kwargs["recsys_type"] == "default" and kwargs["frecsys_type"] == "default"
    assert user_experiments(exp_id) == 1

    client = login(app, "toggler")  # a new session: the messages above were shown
    assert client.get(f"/admin/select_experiment/{exp_id}").status_code == 302
    assert exp_row(exp_id).status == 0
    assert flashes(client) == [("message", "Experiment 'microblogging' deactivated.")]
    assert len(calls["ensure"]) == 1  # deactivating prepares nothing


def test_a_hpc_experiment_gets_a_fresh_participant_id_and_photo_sharing_the_account(
    toggle,
):
    app, exps, calls = toggle
    hpc = extra("microblogging", "HPC")
    photo = extra("photo_sharing", "HPC")
    client = login(app, "toggler")
    for exp_id in (hpc, photo):
        client.get(f"/admin/select_experiment/{exp_id}")
    by_exp = {e: k for e, k in calls["ensure"]}
    uuid.UUID(by_exp[hpc]["user_id"])  # a uuid, as before
    assert by_exp[photo]["user_id"] == admin_id()


@pytest.mark.parametrize("platform", ["instant_messaging", "dating"])
def test_instant_messaging_and_dating_only_get_the_access_row(toggle, platform):
    app, exps, calls = toggle
    exp_id = extra(platform, "HPC")
    client = login(app, "toggler")
    assert client.get(f"/admin/select_experiment/{exp_id}").status_code == 302
    assert exp_row(exp_id).status == 1 and user_experiments(exp_id) == 1
    assert flashes(client) == [("message", f"Experiment '{platform}-x' activated.")]
    assert calls["register"] == [] and calls["ensure"] == []


def test_the_toggle_refuses_an_experiment_of_another_researcher(toggle):
    from y_web import db

    app, exps, calls = toggle
    exp = exp_row(exps["microblogging"])
    exp.owner = "someone-else"
    db.session.commit()
    client = login(app, "toggler-researcher")
    assert client.get(f"/admin/select_experiment/{exp.idexp}").status_code == 302
    assert exp_row(exp.idexp).status == 0 and calls["ensure"] == []
    assert flashes(client) == [
        ("error", "You are not allowed to access this experiment.")
    ]


def test_a_participant_that_cannot_be_prepared_is_reported_and_the_status_stays_as_it_always_did(
    toggle,
):
    app, exps, calls = toggle
    calls["ensure_result"] = "none"
    client = login(app, "toggler")
    response = client.get(f"/admin/select_experiment/{exps['forum']}")
    assert response.status_code == 302 and response.headers["Location"].endswith(
        "/admin/dashboard"
    )
    assert flashes(client) == [("message", "Unable to prepare the experiment user.")]
    assert exp_row(exps["forum"]).status == 1 and user_experiments(exps["forum"]) == 0


def test_the_functions_are_idempotent(toggle):
    from y_web import db
    from y_web.src.experiment import activation
    from y_web.src.models import Admin_users

    app, exps, calls = toggle
    exp = exp_row(exps["forum"])
    admin = db.session.query(Admin_users).filter_by(username="toggler").one()
    first = activation.activate_experiment(exp, admin)
    assert (first.kind, first.ok, first.changed) == (
        "activated",
        True,
        True,
    ) and first.message == "Experiment 'forum' activated."
    again = activation.activate_experiment(exp, admin)
    assert (again.kind, again.changed, again.message) == ("already_active", False, "")
    assert (
        len(calls["ensure"]) == 1 and user_experiments(exp.idexp) == 1
    )  # nothing was repeated
    assert (
        activation.deactivate_experiment(exp).kind == "deactivated" and exp.status == 0
    )
    assert (activation.deactivate_experiment(exp).kind, exp.status) == (
        "already_inactive",
        0,
    )


def test_a_failed_activation_can_restore_the_status(toggle):
    from y_web import db
    from y_web.src.experiment import activation
    from y_web.src.models import Admin_users

    app, exps, calls = toggle
    calls["ensure_result"] = "none"
    exp = exp_row(exps["forum"])
    admin = db.session.query(Admin_users).filter_by(username="toggler").one()
    result = activation.activate_experiment(exp, admin, rollback_on_failure=True)
    assert (result.kind, result.ok) == ("failed", False) and exp.status == 0
