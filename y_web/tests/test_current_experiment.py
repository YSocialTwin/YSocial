"""The session remembers the experiment a user is working with (several can be active at once)."""

from types import SimpleNamespace

import pytest

from y_web.src.experiment import current

pytestmark = pytest.mark.unit


@pytest.fixture
def flask_app(tmp_path):
    from flask import Flask

    app = Flask(__name__)
    app.secret_key = "t"
    return app


def _exp(idexp):
    return SimpleNamespace(idexp=idexp)


def test_remember_writes_the_session_only_on_change(flask_app):
    with flask_app.test_request_context():
        from flask import session

        current.remember("4")
        assert session[current.SESSION_KEY] == 4
        session.modified = False
        current.remember(4)
        assert session.modified is False  # same experiment: no new cookie
        current.remember("not a number")
        assert session[current.SESSION_KEY] == 4
        current.forget()
        assert current.SESSION_KEY not in session


def test_outside_a_request_nothing_is_remembered():
    current.remember(3)
    assert current.current_experiment_id() is None


def test_the_experiment_the_user_opened_wins_among_several_active(
    flask_app, monkeypatch
):
    active = [_exp(1), _exp(2), _exp(3)]
    monkeypatch.setattr(current, "current_experiment_id", lambda: 2)
    assert current.choose_active_experiment(active).idexp == 2


def test_without_a_remembered_experiment_the_only_active_one_is_chosen(monkeypatch):
    monkeypatch.setattr(current, "current_experiment_id", lambda: None)
    assert current.choose_active_experiment([_exp(5)]).idexp == 5
    assert current.choose_active_experiment([_exp(1), _exp(2)]) is None
    assert current.choose_active_experiment([]) is None


def test_a_remembered_experiment_of_another_platform_is_not_among_the_candidates(
    monkeypatch,
):
    monkeypatch.setattr(current, "current_experiment_id", lambda: 9)
    # the caller passes only the active experiments of its own platform
    assert current.choose_active_experiment([_exp(1), _exp(2)]) is None
    assert current.choose_active_experiment([_exp(1)]).idexp == 1


def test_a_vanished_experiment_is_forgotten(monkeypatch):
    from y_web import create_app

    app = create_app(db_type="sqlite")
    with app.test_request_context():
        from flask import session

        session[current.SESSION_KEY] = 987654
        assert current.current_experiment_id() is None
        assert current.SESSION_KEY not in session


def test_the_dispatcher_follows_the_session_then_falls_back_to_the_preferred_repository(
    monkeypatch,
):
    from y_web.platforms import dispatch

    seen = []
    monkeypatch.setattr(
        dispatch,
        "REQUEST_RESOLVERS",
        [lambda arguments: seen.append("x") or SimpleNamespace(platform_type="zzz")],
    )
    assert dispatch.resolve_experiment({}).platform_type == "zzz"
    assert seen == ["x"]
