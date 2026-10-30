"""A person registered to a Dating experiment keeps their account session after choosing it (IR-D-05)."""

from y_web.tests.test_training_modules_baseline_auth import (  # noqa: F401
    _make_admin_user,
    _make_experiment,
    core_app,
)


def test_choosing_a_dating_experiment_lands_on_the_play_view_and_stays_logged_in(
    core_app,
):
    from y_web import db
    from y_web.src.dating import DATING_PLATFORM
    from y_web.src.models import User_Experiment

    with core_app.app_context():
        account = _make_admin_user("user")
        exp = _make_experiment(platform_type=DATING_PLATFORM, simulator_type="YDating")
        db.session.add(User_Experiment(user_id=account.id, exp_id=exp.idexp))
        db.session.commit()
        email, exp_id, account_id = account.email, exp.idexp, account.id
    client = core_app.test_client()
    client.post("/login", data={"email": email, "password": "Passw0rd!"})
    with client.session_transaction() as sess:
        token = sess["exp_select_token"]
    response = client.post(
        "/select_experiment", data={"experiment_id": exp_id, "auth_token": token}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/{exp_id}/dating")
    with client.session_transaction() as sess:
        assert sess["_user_id"] == f"admin_{account_id}"
        assert sess["platform_account_id"] == account_id
