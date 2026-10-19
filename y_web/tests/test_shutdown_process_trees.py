"""Closing the app must terminate every simulator process, helpers included."""

import os
import subprocess
import sys
import time

import pytest

from y_web.src.simulation import process_registry as pr

pytestmark = pytest.mark.unit

pytest.importorskip("psutil")
import psutil  # noqa: E402

PARENT = (
    "import subprocess, sys, time\n"
    "kid = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],"
    " start_new_session=True)\n"
    "print(kid.pid, flush=True)\n"
    "time.sleep(60)\n"
)


def _spawn_tree():
    parent = subprocess.Popen(
        [sys.executable, "-c", PARENT],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    child_pid = int(parent.stdout.readline())
    return parent, child_pid


def _gone(pid):
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def test_terminates_descendants_in_other_sessions():
    (p1, c1), (p2, c2) = _spawn_tree(), _spawn_tree()
    started = time.time()
    try:
        done = pr.terminate_process_trees([p1.pid, p2.pid], grace=5)
        assert {p1.pid, p2.pid, c1, c2} <= done
        p1.wait(timeout=5)
        p2.wait(timeout=5)
        assert _gone(c1) and _gone(c2)
        # Parallel: two trees do not take twice the time of one.
        assert time.time() - started < 5
    finally:
        for pid in (p1.pid, p2.pid, c1, c2):
            try:
                psutil.Process(pid).kill()
            except psutil.NoSuchProcess:
                pass


def test_kills_what_ignores_sigterm():
    stubborn = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
            " print('ready', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        stubborn.stdout.readline()
        pr.terminate_process_trees([stubborn.pid], grace=1)
        stubborn.wait(timeout=5)
        assert stubborn.returncode is not None
    finally:
        if stubborn.poll() is None:
            stubborn.kill()


def test_ignores_missing_pids_none_and_itself():
    assert pr.terminate_process_trees([None, 0, 2**22 + 12345, os.getpid()]) == set()
    assert pr.terminate_process_trees([]) == set()


def test_stop_all_exps_terminates_everything_then_closes_the_db(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    exp = SimpleNamespace(idexp=1, server_pid=111, running=1, exp_status="running")
    cli = SimpleNamespace(id=7, pid=222, status=1)
    execution_query = MagicMock()

    def query(model):
        q = MagicMock()
        rows = {pr.Exps: [exp], pr.Client: [cli]}.get(model, [])
        q.filter.return_value.all.return_value = rows
        q.all.return_value = rows
        if model.__name__ == "Client_Execution":
            return execution_query
        return q

    fake_db = SimpleNamespace(session=MagicMock())
    fake_db.session.query.side_effect = query
    monkeypatch.setattr(pr, "db", fake_db)
    monkeypatch.setattr(pr, "WATCHDOG_ENABLED", False)
    seen = []
    monkeypatch.setattr(pr, "terminate_process_trees", lambda pids, **k: seen.append(set(pids)))

    pr.stop_all_exps()

    assert seen and {111, 222} <= seen[0]
    assert (exp.server_pid, exp.running, exp.exp_status) == (None, 0, "stopped")
    assert (cli.pid, cli.status) == (None, 0)
    execution_query.filter.return_value.update.assert_called_once()
    fake_db.session.commit.assert_called()
