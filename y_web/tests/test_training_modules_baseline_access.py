"""
Phase 0 characterization tests for the TrainingModules plugin (point [NV] d).

[NV] (d): can a participant session created for one experiment reach the
routes of another experiment, and how is the session identity resolved?

Today the session only stores the bare participant id (Flask-Login
``_user_id``); the user loader reads that id from whatever experiment database
the URL selects (``setup_experiment_context`` rebinds ``db_exp`` from
``exp_id`` in the URL).  Nothing compares the URL experiment with the
experiment the participant logged in to, and routes such as the feed are only
protected by ``@login_required``.
"""

import uuid

import pytest


@pytest.fixture
def two_experiments(monkeypatch, tmp_path):
    from y_web import create_app, db
    from y_web.src.experiment.helpers import open_experiment_session
    from y_web.src.models import Admin_users, Exps, User_mgmt

    def _tmp_writable_path(relative_path=""):
        return str(tmp_path / str(relative_path).replace("/", "_").replace("\\", "_"))

    monkeypatch.setattr(
        "y_web.src.experiment.helpers.get_writable_path", _tmp_writable_path
    )
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", _tmp_writable_path
    )

    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    # Probe route: reports who the loader resolves for the experiment in the URL.
    from flask import jsonify
    from flask_login import current_user, login_required

    @app.get("/<int:exp_id>/_tm_probe")
    @login_required
    def _tm_probe(exp_id):
        return jsonify(username=current_user.username, id=current_user.id)

    exps = {}
    with app.app_context():
        for label in ("a", "b"):
            tag = uuid.uuid4().hex[:6]
            exp = Exps(
                platform_type="microblogging",
                exp_name=f"tm-{label}-{tag}",
                db_name=f"experiments/tm-{label}-{tag}/database_server.db",
                owner="admin",
                exp_descr="phase 0 characterization",
                status=1,
                port=5990,
            )
            db.session.add(exp)
            db.session.commit()
            session, engine = open_experiment_session(exp)
            try:
                session.add(
                    User_mgmt(
                        id=7,
                        username=f"user_{label}",
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
            exps[label] = exp.idexp
            # Real participants also have a platform account with the same
            # username (feed helpers such as is_admin() look it up there).
            db.session.add(
                Admin_users(
                    username=f"user_{label}",
                    email=f"user_{label}_{tag}@example.test",
                    password="x",
                    last_seen="2026-01-01",
                    role="user",
                )
            )
            db.session.commit()
    return app, exps


def _participant_client(app, participant_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(participant_id)
        sess["_fresh"] = True
    return client


def test_session_resolves_the_participant_in_the_experiment_of_the_url(
    two_experiments,
):
    app, exps = two_experiments
    client = _participant_client(app, 7)

    in_a = client.get(f"/{exps['a']}/_tm_probe")
    in_b = client.get(f"/{exps['b']}/_tm_probe")

    assert in_a.status_code == 200 and in_a.get_json()["username"] == "user_a"
    # Same session, other experiment in the URL: a *different* person is loaded
    # because only the bare id is stored in the session.
    assert in_b.status_code == 200 and in_b.get_json()["username"] == "user_b"


def test_session_id_without_a_row_in_the_other_experiment_is_anonymous(
    two_experiments,
):
    app, exps = two_experiments
    client = _participant_client(app, 99)  # exists in neither experiment

    response = client.get(f"/{exps['b']}/_tm_probe")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_feed_route_is_only_protected_by_login_required(two_experiments):
    """The real feed route serves a participant logged in 'for experiment A'
    when the URL names experiment B: no comparison with User_Experiment or with
    the experiment of the session."""
    app, exps = two_experiments
    client = _participant_client(app, 7)

    response = client.get(f"/{exps['b']}/feed/7/feed/rf/1")
    print("FEED_STATUS_OTHER_EXPERIMENT", response.status_code)
    assert response.status_code not in (401, 403)
    assert not (
        response.status_code == 302 and "/login" in response.headers["Location"]
    )
