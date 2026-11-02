"""Members of a running World Simulation that do not show up, stall or die: classification, collection, endpoint, page."""

import json
import os
import re
import sqlite3
import time

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import coordinator_process as cp  # noqa: E402
from y_web.src.federation import member_health as mh  # noqa: E402
from y_web.src.federation import service  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_ui import login, site  # noqa: E402,F401  (fixtures and helper)

NOW = 10_000.0
START = NOW - 300.0
BASE = "/admin/world_simulation"


def states(**members):
    """``{"a": (status, last_ready_tick)}`` -> the ``members`` of /v1/status."""
    return {m: {"status": s, "last_ready_tick": t} for m, (s, t) in members.items()}


def classify(members, hello=None, ready=None, procs=None, tick_seconds=10.0, now=NOW, started=START, **kw):
    hello = {m: START + 5 for m in members} if hello is None else hello
    procs = procs if procs is not None else {m: {"server": True, "clients": {"c": True}} for m in members}
    return mh.classify_members(now=now, started_at=started, members=members, hello_at=hello, last_ready_at=ready or {},
                               procs=procs, tick_seconds=tick_seconds, **kw)


# -------------------------------------------------------------------------------------------- pure functions
def test_everybody_at_the_same_tick_is_ok():
    out = classify(states(a=("running", 5), b=("running", 5)), ready={"a": NOW - 1, "b": NOW - 1})
    assert {m: s["code"] for m, s in out.items()} == {"a": "ok", "b": "ok"}
    assert not any(s["problem"] for s in out.values())


def test_the_member_ahead_waits_for_the_slowest_and_the_slowest_is_not_a_problem_yet():
    out = classify(states(a=("running", 7), b=("running", 5)), ready={"a": NOW - 5, "b": NOW - 30})
    assert out["a"]["code"] == "waiting" and out["a"]["waiting_for"] == ["b"]
    assert out["b"]["code"] == "ok" and not out["b"]["problem"]


def test_a_member_without_hello_is_starting_then_missing_after_the_timeout():
    members = states(a=("running", 3), b=("registered", -1))
    early = classify(members, hello={"a": START + 1}, now=START + 59, ready={"a": START + 58})
    assert early["b"]["code"] == "starting" and not early["b"]["problem"]
    late = classify(members, hello={"a": START + 1}, now=START + 61, ready={"a": START + 60})
    assert late["b"]["code"] == "missing" and late["b"]["problem"] and late["b"]["since"] == 61
    assert late["a"]["code"] == "waiting" and late["a"]["waiting_for"] == ["b"]  # the others show who they wait for


def test_hello_timeout_is_a_parameter():
    members = states(a=("registered", -1))
    assert classify(members, hello={}, now=START + 31, hello_timeout=30)["a"]["code"] == "missing"
    assert classify(members, hello={}, now=START + 31, hello_timeout=45)["a"]["code"] == "starting"


def test_stalled_needs_somebody_waiting_and_a_long_silence():
    members = states(a=("running", 7), b=("running", 5))
    quiet = classify(members, ready={"a": NOW - 5, "b": NOW - 200})  # floor is 120 s, tick 10 s -> 5x = 50 s
    assert quiet["b"]["code"] == "stalled" and quiet["b"]["problem"] and quiet["b"]["since"] == 200
    short = classify(members, ready={"a": NOW - 5, "b": NOW - 100})
    assert short["b"]["code"] == "ok"
    alone = classify(states(a=("running", 5), b=("running", 5)), ready={"a": NOW - 500, "b": NOW - 500})
    assert not any(s["problem"] for s in alone.values())  # nobody waits: slow runs are not stalls


def test_the_stall_limit_grows_with_the_tick_time():
    members = states(a=("running", 7), b=("running", 5))
    ready = {"a": NOW - 5, "b": NOW - 600}
    assert classify(members, ready=ready, tick_seconds=60.0)["b"]["code"] == "stalled"  # 5 x 60 = 300 s < 600 s
    assert classify(members, ready=ready, tick_seconds=150.0)["b"]["code"] == "ok"  # 5 x 150 = 750 s
    assert mh.stall_threshold(None) == 120.0 and mh.stall_threshold(10.0) == 120.0 and mh.stall_threshold(100.0) == 500.0


def test_dead_server_or_all_clients_dead_beats_everything():
    members = states(a=("running", 7), b=("running", 5))
    procs = {"a": {"server": True, "clients": {"c": True}}, "b": {"server": False, "clients": {"c": True}}}
    out = classify(members, procs=procs, ready={"a": NOW, "b": NOW - 1})
    assert out["b"]["code"] == "dead" and out["b"]["dead"] == ["server"] and out["b"]["problem"]
    procs["b"] = {"server": True, "clients": {"c1": False, "c2": False}}
    out = classify(members, procs=procs)
    assert out["b"]["code"] == "dead" and out["b"]["dead"] == ["client c1", "client c2"]
    procs["b"] = {"server": True, "clients": {"c1": False, "c2": True}}  # one of two clients: warned, not "not running"
    assert classify(members, procs=procs)["b"]["dead"] == ["client c1"]


def test_finished_and_failed_members():
    out = classify(states(a=("finished", 9), b=("failed", 4)), procs={"a": {"server": False, "clients": {}}, "b": {}})
    assert out["a"]["code"] == "finished" and not out["a"]["problem"]  # a finished member has no process: fine
    assert out["b"]["code"] == "failed" and out["b"]["problem"]


def test_coordinator_down_means_unknown_not_problems():
    out = classify({}, procs={"a": {"server": True, "clients": {}}})
    assert out == {"a": {"code": "unknown", "problem": False, "waiting_for": [], "dead": [], "since": None}}


def test_median_tick_time_from_global_advances():
    # ticks 0..4 at 0, 10, 20, 70, 80 s: intervals 10, 10, 50, 10 -> median 10; unordered input and a jump of 2 ticks
    assert mh.median_tick_seconds([(0, 0.0), (1, 10.0), (2, 20.0), (3, 70.0), (4, 80.0)]) == 10.0
    assert mh.median_tick_seconds([(4, 80.0), (2, 20.0), (0, 0.0)]) == 20.0  # 2 ticks in 20 s, 2 ticks in 60 s
    assert mh.median_tick_seconds([(1, 5.0)]) is None and mh.median_tick_seconds([]) is None
    assert mh.median_tick_seconds([(0, 0.0), (2 ** 31, 5.0)]) is None  # the "no global tick yet" marker is ignored


def test_progress_and_eta():
    assert mh.progress(2, 720, 65.0) == {"tick": 3, "total": 720, "seconds_per_tick": 65.0, "eta_seconds": 717 * 65}
    assert mh.progress(-1, 720, 65.0)["tick"] is None
    assert mh.progress(5, None, 10.0)["eta_seconds"] is None and mh.progress(5, 720, None)["eta_seconds"] is None
    assert mh.progress(719, 720, 10.0)["eta_seconds"] == 0
    assert [mh.format_duration(v) for v in (None, 65, 119, 120, 3600, 47000, 300000)] == ["-", "65 s", "119 s", "2 min", "60 min", "13 h", "3.5 d"]


@pytest.mark.parametrize("text,kind,name", [
    ("Traceback (most recent call last):\n  File x\nModuleNotFoundError: No module named 'ysocial_federation'", "module", "ysocial_federation"),
    ("ImportError: No module named foo.bar", "module", "foo.bar"),
    ("requests.exceptions.ConnectionError: HTTPConnectionPool: [Errno 111] Connection refused", "refused", ""),
    ("OSError: [Errno 98] Address already in use", "port", ""),
    ("ImportError: cannot import name 'Gate' from 'x'", "import", "Gate"),
    ("Traceback\nValueError: bad config", "error", ""),
])
def test_probable_cause_is_found_in_the_log_tail(text, kind, name):
    cause = mh.probable_cause(text)
    assert cause["kind"] == kind and cause["name"] == name and cause["line"]


def test_probable_cause_of_a_quiet_log_is_none_and_the_latest_line_wins():
    assert mh.probable_cause("") is None and mh.probable_cause("INFO started\nINFO ok") is None
    assert mh.probable_cause("Connection refused\nModuleNotFoundError: No module named 'x'")["kind"] == "module"


def test_read_tail_is_bounded(tmp_path):
    path = tmp_path / "log"
    path.write_text("\n".join(f"line {i}" for i in range(5000)))
    tail = mh.read_tail(path, max_bytes=200, lines=3)
    assert tail.splitlines() == ["line 4997", "line 4998", "line 4999"]
    assert mh.read_tail(tmp_path / "missing") == ""


# ------------------------------------------------------------------------- collection, endpoint and pages
def write_run(fed, *, hello=(), ready=(), advances=(), started=START):
    """The coordinator descriptor (its mtime is the start of the run) and a coordinator database with some events."""
    desc = os.path.join(fed.folder, "federation_coordinator.json")
    open(desc, "w").write("{}")
    os.utime(desc, (started, started))
    conn = sqlite3.connect(os.path.join(fed.folder, "federation.db"), isolation_level=None)
    conn.executescript(SCHEMA)
    for member, at in hello:
        conn.execute("INSERT INTO federation_event (tick, kind, detail_json, at) VALUES (0,'hello',?,?)", (json.dumps({"member": member}), at))
    for member, tick, at in ready:
        conn.execute("INSERT INTO federation_event (tick, kind, detail_json, at) VALUES (?,'ready',?,?)", (tick, json.dumps({"member": member}), at))
    for tick, at in advances:
        conn.execute("INSERT INTO federation_event (tick, kind, detail_json, at) VALUES (?,'global_advance','{}',?)", (tick, at))
    conn.close()


@pytest.fixture
def running(site, monkeypatch):  # noqa: F811
    """A running World Simulation of two members whose servers are alive (this very process) and a client each."""
    from y_web import db
    from y_web.src.models import Client, Exps, Population

    app, exps, tmp = site
    pop = Population.query.first()
    for platform, exp_id in exps.items():
        db.session.add(Client(name=f"c-{platform}", id_exp=exp_id, population_id=pop.id, status=1, days=30, pid=os.getpid()))
        db.session.get(Exps, exp_id).server_pid = os.getpid()
    fed = service.create_federation("w", list(exps.values()), owner="admin", seed=1)
    fed.status = "running"
    db.session.commit()
    coordinator = {"global_tick": 4, "skew": 1, "members": {"microblogging": {"status": "running", "last_ready_tick": 5},
                                                          "forum": {"status": "running", "last_ready_tick": 4}}}
    monkeypatch.setattr(cp, "coordinator_status", lambda fed, timeout=3.0: coordinator)
    return app, fed, exps, tmp, coordinator


def test_a_healthy_run_reports_progress_and_no_problems(running):
    app, fed, exps, tmp, coordinator = running
    now = time.time()
    write_run(fed, started=now - 300, hello=[("microblogging", now - 290), ("forum", now - 290)],
              ready=[("microblogging", 5, now - 2), ("forum", 4, now - 3)],
              advances=[(0, now - 130), (1, now - 100), (2, now - 70), (3, now - 40), (4, now - 10)])
    report = mh.collect(fed, coordinator, now=now)
    assert report["problems"] == []
    assert report["members"]["microblogging"]["code"] == "waiting" and report["members"]["forum"]["code"] == "ok"
    assert report["progress"] == {"tick": 5, "total": 720, "seconds_per_tick": 30.0, "eta_seconds": 715 * 30}


def test_collect_finds_the_member_that_did_not_say_hello_and_reads_the_cause_from_its_log(running):
    from y_web.src.models import Exps

    app, fed, exps, tmp, coordinator = running
    now = time.time()
    coordinator["members"]["forum"] = {"status": "registered", "last_ready_tick": -1}
    write_run(fed, started=now - 300, hello=[("microblogging", now - 290)], ready=[("microblogging", 5, now - 2)])
    (tmp / "experiments" / "forum" / "server_stderr.log").write_text(
        "Traceback (most recent call last):\n  File \"run.py\", line 1\nModuleNotFoundError: No module named 'ysocial_federation'\n")
    report = mh.collect(fed, coordinator, now=now)
    assert report["problems"] == ["forum"]
    forum = report["members"]["forum"]
    assert forum["code"] == "missing" and forum["cause"]["kind"] == "module" and forum["cause"]["name"] == "ysocial_federation"
    assert forum["log"].endswith("forum/server_stderr.log")


def test_collect_reports_a_dead_server_and_ignores_hello_of_a_previous_run(running):
    from y_web import db
    from y_web.src.models import Exps

    app, fed, exps, tmp, coordinator = running
    now = time.time()
    db.session.get(Exps, exps["forum"]).server_pid = None
    db.session.commit()
    # hellos older than the start of this run do not count (a resumed run keeps the old events)
    write_run(fed, started=now - 300, hello=[("microblogging", now - 290), ("forum", now - 5000)],
              ready=[("microblogging", 5, now - 2), ("forum", 4, now - 3)])
    report = mh.collect(fed, coordinator, now=now)
    assert report["members"]["forum"]["code"] == "dead" and report["members"]["forum"]["dead"] == ["server"]
    assert report["problems"] == ["forum"]


def test_collect_is_empty_unless_the_run_is_running(running):
    app, fed, exps, tmp, coordinator = running
    fed.status = "paused"
    assert mh.collect(fed, coordinator) == {}


def test_status_endpoint_has_badges_banner_and_progress_text(running):
    app, fed, exps, tmp, coordinator = running
    now = time.time()
    coordinator["members"]["forum"] = {"status": "registered", "last_ready_tick": -1}
    write_run(fed, started=now - 300, hello=[("microblogging", now - 290)], ready=[("microblogging", 5, now - 2)],
              advances=[(0, now - 100), (1, now - 35), (2, now - 5)])
    (tmp / "experiments" / "forum" / "server_stderr.log").write_text("requests.exceptions.ConnectionError: [Errno 111] Connection refused\n")
    data = login(app, "admin").get(f"{BASE}/{fed.id}/status.json").get_json()
    badges = {m["member"]: m["health"] for m in data["members"]}
    assert badges["forum"] == {"code": "missing", "problem": True, "text": "Missing"}
    assert badges["microblogging"]["text"] == "Waiting for Forum" and not badges["microblogging"]["problem"]
    [problem] = data["problems"]
    assert problem["member"] == "forum" and problem["label"] == "Forum" and "has not said hello" in problem["text"]
    assert problem["cause"] == "Probable cause: connection refused" and problem["log"].endswith("server_stderr.log")
    assert "server_stderr.log" in data["log_hint"]
    assert data["progress_text"] == "Tick 5/720, ~48 s per tick, ETA 9 h"  # intervals 65 s and 30 s -> median 47.5 s


def test_status_endpoint_of_a_stopped_run_has_no_warnings(site):
    app, exps, tmp = site
    fed = service.create_federation("w", list(exps.values()), owner="admin", seed=1)
    data = login(app, "admin").get(f"{BASE}/{fed.id}/status.json").get_json()
    assert data["problems"] == [] and data["progress_text"] == "" and all(m["health"] is None for m in data["members"])


def test_status_endpoint_survives_an_error_in_the_collection(running, monkeypatch):
    app, fed, exps, tmp, coordinator = running
    monkeypatch.setattr(mh, "collect", lambda *a, **k: 1 / 0)
    response = login(app, "admin").get(f"{BASE}/{fed.id}/status.json")
    assert response.status_code == 200 and response.get_json()["problems"] == []


def test_execution_tab_has_the_banner_the_badge_column_and_the_progress_line(running):
    app, fed, exps, tmp, coordinator = running
    html = login(app, "admin").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    for marker in ('id="ws-problems"', 'id="ws-problems-list"', 'id="ws-progress-line"', 'id="ws-coordinator-down"', "<th>Health</th>"):
        assert marker in html
    assert re.search(r'id="ws-problems"[^>]*\bhidden\b', html)  # hidden until the status poll finds a problem
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "assets", "js", "admin-world-simulation.js")).read()
    assert "m.health" in js and "s.problems" in js and "s.progress_text" in js


def test_list_warns_about_a_member_in_trouble(running):
    app, fed, exps, tmp, coordinator = running
    now = time.time()
    coordinator["members"]["forum"] = {"status": "registered", "last_ready_tick": -1}
    write_run(fed, started=now - 300, hello=[("microblogging", now - 290)], ready=[("microblogging", 5, now - 2)])
    html = login(app, "admin").get(BASE).get_data(as_text=True)
    assert "ws-warning" in html and "1 member needs attention" in html and "Forum has not said hello" in html


def test_list_of_a_healthy_run_has_no_warning(running):
    app, fed, exps, tmp, coordinator = running
    now = time.time()
    write_run(fed, started=now - 300, hello=[("microblogging", now - 290), ("forum", now - 290)],
              ready=[("microblogging", 4, now - 2), ("forum", 4, now - 3)])
    coordinator["members"]["microblogging"]["last_ready_tick"] = 4
    assert "ws-warning" not in login(app, "admin").get(BASE).get_data(as_text=True)
