"""World Simulation notifications and run health (F5.5 / F5.6)."""

import os
import signal
import time

import pytest

from y_web import db
from y_web.src.federation import coordinator_process as cp
from y_web.src.federation import health, service
from y_web.src.federation.notifications import notify_failure
from y_web.src.simulation import execution_backend as eb
from y_web.tests.test_federation_lifecycle import (  # noqa: F401  (fixtures)
    needs_sdk,
    running_world,
)
from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)


def notifications():
    from y_web.src.models import DownloadNotification

    return DownloadNotification.query.order_by(DownloadNotification.id).all()


@pytest.fixture
def owner(running_world):  # noqa: F811
    from werkzeug.security import generate_password_hash

    from y_web.src.models import Admin_users

    fed, fake, tmp = running_world
    db.session.add(
        Admin_users(
            username="owner",
            email="o@t.com",
            password=generate_password_hash("x"),
            role="researcher",
            last_seen="2026-01-01",
        )
    )
    fed.owner = "owner"
    db.session.commit()
    return fed, fake, tmp


def test_a_notification_names_the_world_simulation_and_reaches_the_owner(owner):
    fed, fake, tmp = owner
    rows = notify_failure(fed, "coordinator", "boom")
    assert len(rows) == 1 and rows[0].status == "failed" and not rows[0].is_read
    assert (
        "World Simulation" in rows[0].title
        and fed.name in rows[0].message
        and "boom" in rows[0].message
    )
    assert "federation" not in (rows[0].title + rows[0].message).lower()
    from y_web.src.models import Admin_users

    assert rows[0].user_id == Admin_users.query.filter_by(username="owner").one().id


def test_without_a_known_owner_the_admins_are_told(running_world):
    fed, fake, tmp = running_world
    fed.owner = "nobody"
    rows = notify_failure(fed, "start", "x")
    assert len(rows) >= 1


@needs_sdk
def test_a_failed_start_is_notified(owner):
    fed, fake, tmp = owner
    fake.fail_on = "forum"
    with pytest.raises(RuntimeError):
        eb.start_federation(fed)
    rows = notifications()
    assert (
        len(rows) == 1
        and rows[0].title == "World Simulation: start failed"
        and "boom" in rows[0].message
    )


@needs_sdk
def test_a_dead_coordinator_ends_the_run_and_is_notified(owner):
    fed, fake, tmp = owner
    eb.start_federation(fed)
    assert health.check_federation(fed) == "ok"
    os.kill(fed.coordinator_pid, signal.SIGKILL)
    time.sleep(0.3)
    assert health.check_federation(fed) == "failed"
    assert fed.status == "failed" and ("stop_server", "forum") in fake.events
    assert [r.title for r in notifications()] == ["World Simulation: coordinator error"]
    assert health.check_federation(fed) == "idle"


@pytest.mark.parametrize(
    "states,expected,notified",
    [
        (("finished", "finished"), "completed", 0),
        (("finished", "failed"), "failed", 1),
    ],
)
def test_end_of_run(owner, monkeypatch, states, expected, notified):
    fed, fake, tmp = owner
    fed.status = "running"
    fed.coordinator_pid = os.getpid()  # alive
    monkeypatch.setattr(
        cp,
        "coordinator_status",
        lambda f, timeout=2.0: {
            "members": {"a": {"status": states[0]}, "b": {"status": states[1]}}
        },
    )
    monkeypatch.setattr(
        cp, "stop_coordinator", lambda f: setattr(f, "coordinator_pid", None) or True
    )
    try:
        assert health.check_federation(fed) == expected
        assert fed.status == expected and len(notifications()) == notified
    finally:
        fed.coordinator_pid = (
            None  # the fixture teardown must not signal this very process
        )


def test_a_running_simulation_in_progress_is_left_alone(owner, monkeypatch):
    fed, fake, tmp = owner
    fed.status = "running"
    fed.coordinator_pid = os.getpid()
    monkeypatch.setattr(
        cp,
        "coordinator_status",
        lambda f, timeout=2.0: {
            "members": {"a": {"status": "running"}, "b": {"status": "finished"}}
        },
    )
    try:
        assert (
            health.check_federation(fed) == "ok"
            and fed.status == "running"
            and notifications() == []
        )
    finally:
        fed.coordinator_pid = None
