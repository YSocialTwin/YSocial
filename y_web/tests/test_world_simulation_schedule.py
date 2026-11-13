"""Queue of World Simulations (F5.5): order, one at a time, refusals, restart, the page."""

import json

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web import db
from y_web.src.federation import health, schedule_monitor, schedule_queue, service
from y_web.src.models.admin import Federation, FederationScheduleQueue
from y_web.src.simulation import execution_backend as eb
from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)
from y_web.tests.test_world_simulation_ui import login, site  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def _no_monitor_left_by_another_module():
    """The monitor is a process-wide singleton: one started by an application of another test module (without
    TESTING) must not leak into these tests."""
    schedule_monitor.stop_federation_schedule_monitor()
    yield
    schedule_monitor.stop_federation_schedule_monitor()


def more_experiments(tmp, tag):
    """Two more stopped experiments (microblogging + forum) on the population of the fixture."""
    from y_web.src.models.admin import Exps, Population, Population_Experiment

    pop = Population.query.first()
    ids = []
    for platform in ("microblogging", "forum"):
        exp = Exps(
            platform_type=platform,
            exp_name=f"{platform}-{tag}",
            db_name=f"experiments/{platform}{tag}/db.db",
            owner="admin",
            exp_descr="",
            status=0,
            running=0,
            port=5000,
            simulator_type="Standard",
            exp_status="stopped",
        )
        db.session.add(exp)
        db.session.flush()
        db.session.add(Population_Experiment(id_population=pop.id, id_exp=exp.idexp))
        folder = tmp / "experiments" / f"{platform}{tag}"
        folder.mkdir(parents=True)
        (folder / "config_server.json").write_text(json.dumps({"name": platform}))
        ids.append(exp.idexp)
    db.session.commit()
    return ids


@pytest.fixture
def two(world, monkeypatch):  # noqa: F811
    app, exps, tmp = world
    first = service.create_federation("first", list(exps.values()), owner="admin")
    second = service.create_federation(
        "second", more_experiments(tmp, "2"), owner="admin"
    )
    log = []

    def fake_start(fed, **kw):
        log.append(("start", fed.name))
        fed.status = "running"
        db.session.commit()

    monkeypatch.setattr(eb, "start_federation", fake_start)
    monkeypatch.setattr(health, "check_federation", lambda fed, **kw: "ok")
    return first, second, log, tmp


def statuses():
    return [
        i.status
        for i in FederationScheduleQueue.query.order_by(
            FederationScheduleQueue.position
        ).all()
    ]


def test_positions_follow_the_order_of_insertion(two):
    first, second, log, tmp = two
    a, b = schedule_queue.enqueue(first), schedule_queue.enqueue(second)
    assert (a.position, b.position) == (1, 2) and statuses() == ["queued", "queued"]


def test_one_at_a_time_in_order_and_the_next_starts_when_the_previous_ends(two):
    first, second, log, tmp = two
    schedule_queue.enqueue(first)
    schedule_queue.enqueue(second)
    schedule_queue.advance()
    assert log == [("start", "first")] and statuses() == ["running", "queued"]
    schedule_queue.advance()  # still running: the second must wait
    assert log == [("start", "first")]
    first.status = "completed"
    schedule_queue.advance()
    assert statuses() == ["completed", "running"] and log[-1] == ("start", "second")
    second.status = "failed"
    schedule_queue.advance()
    assert statuses() == ["completed", "failed"]


def test_a_stopped_by_hand_run_is_cancelled_and_the_queue_goes_on(two):
    first, second, log, tmp = two
    schedule_queue.enqueue(first)
    schedule_queue.enqueue(second)
    schedule_queue.advance()
    first.status = "stopped"
    schedule_queue.advance()
    assert statuses() == ["cancelled", "running"]


def test_the_queue_resumes_after_a_restart_of_the_monitor(two, world):  # noqa: F811
    first, second, log, tmp = two
    app = world[0]
    schedule_queue.enqueue(first)
    schedule_queue.enqueue(second)
    schedule_monitor.FederationScheduleMonitor(app).poll()
    assert statuses() == ["running", "queued"]
    restarted = schedule_monitor.FederationScheduleMonitor(
        app
    )  # a new process: only the database remains
    restarted.poll()
    assert statuses() == ["running", "queued"] and log == [("start", "first")]
    first.status = "completed"
    restarted.poll()
    assert statuses() == ["completed", "running"]


def test_insertion_is_refused_when_a_member_runs(two):
    first, second, log, tmp = two
    _, exp = service.members_of(first)[0]
    exp.running = 1
    with pytest.raises(service.WorldSimulationError) as caught:
        schedule_queue.enqueue(first)
    assert (
        caught.value.codes == ["member_busy"]
        and FederationScheduleQueue.query.count() == 0
    )


def test_insertion_is_refused_when_a_member_is_in_the_experiment_scheduler(two):
    from y_web.src.models import ExperimentScheduleGroup, ExperimentScheduleItem

    first, second, log, tmp = two
    _, exp = service.members_of(first)[0]
    group = ExperimentScheduleGroup(name="g", order_index=0, is_completed=0)
    db.session.add(group)
    db.session.flush()
    db.session.add(
        ExperimentScheduleItem(
            group_id=group.id, experiment_id=exp.idexp, order_index=0
        )
    )
    db.session.commit()
    with pytest.raises(service.WorldSimulationError) as caught:
        schedule_queue.enqueue(first)
    assert caught.value.codes == ["member_busy"]
    group.is_completed = 1  # a finished group no longer blocks
    db.session.commit()
    schedule_queue.enqueue(first)


def test_start_fails_with_a_notification_when_a_member_became_busy(two):
    from y_web.src.models import DownloadNotification

    first, second, log, tmp = two
    schedule_queue.enqueue(first)
    _, exp = service.members_of(first)[0]
    exp.running = 1  # started by hand while the entry was waiting
    schedule_queue.advance()
    assert statuses() == ["failed"] and log == []
    rows = DownloadNotification.query.all()
    assert (
        rows and "World Simulation" in rows[0].title and exp.exp_name in rows[0].message
    )


def test_a_start_that_raises_marks_the_entry_failed_and_goes_on(two, monkeypatch):
    first, second, log, tmp = two

    def boom(fed, **kw):
        if fed.name == "first":
            raise RuntimeError("boom")
        fed.status = "running"

    monkeypatch.setattr(eb, "start_federation", boom)
    schedule_queue.enqueue(first)
    schedule_queue.enqueue(second)
    schedule_queue.advance()
    assert statuses() == ["failed", "running"]


def test_double_insertion_and_cancel_rules(two):
    first, second, log, tmp = two
    item = schedule_queue.enqueue(first)
    with pytest.raises(service.WorldSimulationError) as caught:
        schedule_queue.enqueue(first)
    assert caught.value.codes == ["already_queued"]
    assert schedule_queue.cancel(item) and statuses() == ["cancelled"]
    schedule_queue.enqueue(first)  # a cancelled entry does not block a new one
    schedule_queue.advance()
    running = FederationScheduleQueue.query.filter_by(status="running").one()
    assert not schedule_queue.cancel(running)


def test_the_monitor_is_not_started_in_tests(two):
    assert schedule_monitor.get_monitor() is None


def test_schedule_page_enqueue_and_cancel(site):  # noqa: F811
    app, exps, tmp = site
    fed = service.create_federation("page", list(exps.values()), owner="admin")
    client = login(app, "admin")
    page = client.get("/admin/world_simulation/schedule").get_data(as_text=True)
    assert "page" in page and "The queue is empty." in page
    assert (
        client.post(
            "/admin/world_simulation/schedule/enqueue", data={"simulation_id": fed.id}
        ).status_code
        == 302
    )
    item = FederationScheduleQueue.query.one()
    assert f'data-queue-item="{item.id}"' in client.get(
        "/admin/world_simulation/schedule"
    ).get_data(as_text=True)
    assert (
        client.post(f"/admin/world_simulation/schedule/{item.id}/cancel").status_code
        == 302
    )
    assert item.status == "cancelled"
    assert (
        client.post(
            "/admin/world_simulation/schedule/enqueue", data={"simulation_id": 999}
        ).status_code
        == 404
    )
    assert (
        login(app, "teacher")
        .post(
            "/admin/world_simulation/schedule/enqueue", data={"simulation_id": fed.id}
        )
        .status_code
        == 302
    )
    assert FederationScheduleQueue.query.count() == 1
