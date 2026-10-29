"""Assigning a user to an instant messaging experiment needs no participant row (IM has no ``user_mgmt``)."""

import sqlite3
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _im_exp(tmp_path):
    db = tmp_path / "im.db"
    sqlite3.connect(db).execute(
        "CREATE TABLE run_info (run_id TEXT)"
    ).connection.commit()
    return (
        SimpleNamespace(
            idexp=3,
            platform_type="instant_messaging",
            db_name="experiments/uid_abc/database_server.db",
            status=0,
            exp_name="im",
        ),
        db,
    )


def test_ensure_experiment_user_returns_the_human_account_without_touching_the_database(
    tmp_path, monkeypatch
):
    from y_web.src.experiment import helpers
    from y_web.src.im.human_identity import human_account_id

    exp, db = _im_exp(tmp_path)

    def boom(*a, **k):
        raise AssertionError("the IM database must not be opened for provisioning")

    monkeypatch.setattr(helpers, "open_experiment_session", boom)
    user, created = helpers.ensure_experiment_user(
        exp, user_id=7, username="user1", email="u@x", password="x", account_id=7
    )
    assert created is False
    assert user.id == human_account_id("uid_abc", 7) and user.username == "user1"
    names = {
        r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master")
    }
    assert names == {"run_info"}


def test_an_unknown_user_gives_no_participant(tmp_path):
    from y_web.src.experiment import helpers

    exp, _ = _im_exp(tmp_path)
    user, created = helpers.ensure_experiment_user(
        exp, user_id=None, username="x", email="", password=""
    )
    assert user is None and created is False


def test_the_training_modules_provisioning_works_for_im(tmp_path, monkeypatch):
    """Same call as ``provision_participant`` of Training Modules: it must not need ``user_mgmt`` either."""
    from y_web.src.experiment import helpers

    exp, _ = _im_exp(tmp_path)
    monkeypatch.setattr(
        helpers,
        "open_experiment_session",
        lambda e: (_ for _ in ()).throw(RuntimeError("no db")),
    )
    user, _created = helpers.ensure_experiment_user(
        exp, user_id=9, username="stu", email="", password="", joined_on=0
    )
    assert user is not None and user.id.startswith("h-")


def test_the_provisioned_hook_is_emitted_for_im_with_the_human_account(
    tmp_path, monkeypatch
):
    """Training Modules marks the scenario as entered from this hook, so IM must emit it too."""
    from y_web.src.experiment import helpers
    from y_web.src.external_runtime import plugin_hooks
    from y_web.src.im.human_identity import human_account_id

    exp, _ = _im_exp(tmp_path)
    seen = []
    monkeypatch.setattr(
        plugin_hooks, "emit_hook", lambda name, *a, **k: seen.append((name, a))
    )
    user, _created = helpers.ensure_experiment_user(
        exp, user_id=7, username="u", email="", password="", account_id=7
    )
    assert seen == [
        ("experiment_user_provisioned", (exp, 7, human_account_id("uid_abc", 7), False))
    ]
    # no platform account given (e.g. an admin assignment): nothing is reported
    seen.clear()
    helpers.ensure_experiment_user(exp, user_id=7, username="u", email="", password="")
    assert seen == []
