"""World Simulation lifecycle (F5.3): start/stop/pause/resume with fake runtimes and the real coordinator."""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from y_web.src.federation import coordinator_process as cp
from y_web.src.federation import service
from y_web.src.simulation import execution_backend as eb
from y_web.src.simulation import watchdog as wd
from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)

SDK = (
    Path(__file__).resolve().parents[2]
    / "external"
    / "YFederation"
    / "ysocial_federation"
)
needs_sdk = pytest.mark.skipif(
    not SDK.is_dir(), reason="external/YFederation is not installed"
)


class FakeRuntimes:
    """Stands in for servers and clients: records the calls in order and checks the coordinator is up first."""

    def __init__(self, monkeypatch, fed_getter, fail_on=None):
        self.events = []
        self.fed_getter = fed_getter
        self.fail_on = fail_on
        monkeypatch.setattr(eb, "start_server_for_experiment", self.start_server)
        monkeypatch.setattr(eb, "stop_server_for_experiment", self.stop_server)
        monkeypatch.setattr(eb, "start_client_for_experiment", self.start_client)
        monkeypatch.setattr(eb, "stop_client_for_experiment", self.stop_client)

    def start_server(self, exp):
        if self.fail_on == exp.platform_type:
            raise RuntimeError("boom")
        cfg = json.loads(service.server_config_path(exp).read_text())
        self.events.append(
            (
                "start_server",
                exp.platform_type,
                cp.coordinator_status(self.fed_getter()) is not None,
                cfg.get("federation", {}).get("enabled"),
            )
        )

    def stop_server(self, exp):
        self.events.append(("stop_server", exp.platform_type))

    def start_client(self, exp, client, population, resume=True):
        self.events.append(("start_client", exp.platform_type, resume))

    def stop_client(self, exp, client, pause=False):
        self.events.append(("stop_client", exp.platform_type, pause))


@pytest.fixture
def running_world(world, monkeypatch):  # noqa: F811
    from y_web import db
    from y_web.src.models import Client, Population

    app, exps, tmp = world
    pop = Population.query.first()
    for platform, exp_id in exps.items():
        db.session.add(
            Client(name=f"c-{platform}", id_exp=exp_id, population_id=pop.id, status=0)
        )
    db.session.commit()
    fed = service.create_federation("w", list(exps.values()), seed=3)
    fake = FakeRuntimes(monkeypatch, lambda: fed)
    yield fed, fake, tmp
    cp.stop_coordinator(fed)


@needs_sdk
def test_start_order_is_coordinator_servers_clients(running_world):
    fed, fake, tmp = running_world
    eb.start_federation(fed)
    kinds = [e[0] for e in fake.events]
    assert kinds == ["start_server"] * 2 + ["start_client"] * 2
    assert all(
        e[2] is True and e[3] is True for e in fake.events[:2]
    )  # coordinator answering, section enabled
    assert (
        fed.status == "running"
        and cp.coordinator_status(fed)["federation_id"] == fed.id
    )
    for _, exp in service.members_of(fed):
        assert exp.running == 1 and exp.exp_status == "active"


@needs_sdk
def test_stop_is_the_reverse_and_leaves_members_free(running_world):
    from y_web.src.models import Client

    fed, fake, tmp = running_world
    eb.start_federation(fed)
    fake.events.clear()
    assert eb.stop_federation(fed) == []
    kinds = [e[0] for e in fake.events]
    assert kinds == ["stop_client"] * 2 + ["stop_server"] * 2
    assert fed.status == "stopped" and fed.coordinator_pid is None
    assert cp.coordinator_status(fed) is None
    assert all(c.status == 0 for c in Client.query.all())
    for _, exp in service.members_of(fed):
        assert exp.running == 0 and exp.exp_status == "stopped"
        assert "federation" not in json.loads(
            service.server_config_path(exp).read_text()
        )  # members run alone again


@needs_sdk
def test_pause_and_resume(running_world):
    fed, fake, tmp = running_world
    eb.start_federation(fed)
    fake.events.clear()
    eb.pause_federation(fed)
    assert fed.status == "paused" and {e[:3] for e in fake.events} == {
        ("stop_client", "microblogging", True),
        ("stop_client", "forum", True),
    }
    assert cp.coordinator_status(fed) is not None  # the coordinator keeps the clock
    fake.events.clear()
    eb.resume_federation(fed)
    assert (
        fed.status == "running"
        and all(e == ("start_client", e[1], True) for e in fake.events)
        and len(fake.events) == 2
    )
    eb.stop_federation(fed)


@needs_sdk
def test_failed_start_rolls_back(running_world):
    fed, fake, tmp = running_world
    fake.fail_on = "forum"
    with pytest.raises(RuntimeError):
        eb.start_federation(fed)
    assert fed.status == "failed" and cp.coordinator_status(fed) is None
    assert ("stop_server", "microblogging") in fake.events
    for _, exp in service.members_of(fed):
        assert exp.running == 0 and "federation" not in json.loads(
            service.server_config_path(exp).read_text()
        )


def test_cannot_start_when_a_member_runs_or_state_is_wrong(running_world):
    fed, fake, tmp = running_world
    _, exp = service.members_of(fed)[0]
    exp.running = 1
    with pytest.raises(service.WorldSimulationError) as caught:
        eb.start_federation(fed)
    assert caught.value.codes == ["experiment_running"]
    for fn in (eb.pause_federation, eb.resume_federation):
        with pytest.raises(service.WorldSimulationError):
            fn(fed)


def test_members_start_alone_when_the_world_simulation_is_stopped(running_world):
    fed, fake, tmp = running_world
    for _, exp in service.members_of(fed):
        assert "federation" not in json.loads(
            service.server_config_path(exp).read_text()
        )
        eb.start_server_for_experiment(exp)
    assert [e[3] for e in fake.events if e[0] == "start_server"] == [None, None]


# ------------------------------------------------------------------------------------------------- the watchdog
def test_waiting_members_are_those_ahead_of_the_slowest():
    status = {
        "members": {
            "a": {"status": "running", "last_ready_tick": 5},
            "b": {"status": "running", "last_ready_tick": 3},
            "c": {"status": "finished", "last_ready_tick": 9},
        }
    }
    assert cp.waiting_members(status) == {"a": ["b"]}
    assert cp.waiting_members(None) == {} and cp.waiting_members({"members": {}}) == {}
    even = {
        "members": {
            "a": {"status": "running", "last_ready_tick": 4},
            "b": {"status": "running", "last_ready_tick": 4},
        }
    }
    assert cp.waiting_members(even) == {}


def _info(log, restarts):
    old = datetime.now() - timedelta(hours=3)
    return wd.ProcessInfo(
        "client_77",
        os.getpid(),
        str(log),
        lambda: restarts.append(1) or os.getpid(),
        "client",
        old,
        old,
        0,
        None,
    )


def _check(tmp_path, probe):
    log = tmp_path / "c.log"
    log.write_text("x")
    old = time.time() - 3 * 3600
    os.utime(log, (old, old))
    restarts = []
    dog = wd.ProcessWatchdog(heartbeat_timeout=60)
    dog._processes["client_77"] = info = _info(log, restarts)
    if probe is not None:
        wd.register_gate_wait_probe("client_77", probe)
    try:
        dog._check_process(
            info,
            {
                "processes_checked": 0,
                "processes_healthy": 0,
                "processes_restarted": 0,
                "details": [],
            },
        )
    finally:
        wd.unregister_gate_wait_probe("client_77")
    return restarts


def test_a_client_waiting_at_the_gate_is_not_restarted(tmp_path):
    assert _check(tmp_path, lambda: True) == []


def test_a_silent_client_not_at_the_gate_is_still_restarted(tmp_path):
    assert _check(tmp_path, None) == [1]
    assert _check(tmp_path, lambda: False) == [1]
    assert _check(tmp_path, lambda: 1 / 0) == [
        1
    ]  # a failing probe never hides a hung client
