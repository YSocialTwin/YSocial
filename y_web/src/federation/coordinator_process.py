"""Process management of the coordinator of a World Simulation (F5.3): start, stop, status, who waits for whom.

The coordinator is the ``ysocial_federation.coordinator`` module of the YFederation SDK, started as its own process in the
folder of the World Simulation. It picks a free port and writes ``federation_coordinator.json`` there; the token is the
``federation.token`` file written at creation."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from y_web.src.system.path_utils import get_base_path, get_writable_path

TOKEN_HEADER = "X-YFederation-Token"
COORDINATOR_FILE = "federation_coordinator.json"
START_TIMEOUT = 30.0


class CoordinatorError(RuntimeError):
    pass


def external_repo_dir(name: str) -> str:
    candidate = os.path.join(get_writable_path(), "external", name)
    if os.path.isdir(candidate):
        return candidate
    return os.path.join(get_base_path(), "external", name)


def coordinator_argv(folder, python: Optional[str] = None) -> list:
    return [python or sys.executable, "-m", "ysocial_federation.coordinator", "--folder", str(folder)]


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    try:
        import psutil

        return psutil.Process(int(pid)).status() != psutil.STATUS_ZOMBIE
    except Exception:
        return True


def coordinator_info(fed) -> Optional[dict]:
    path = Path(fed.folder) / COORDINATOR_FILE
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def start_coordinator(fed, timeout: float = START_TIMEOUT) -> int:
    """Start the coordinator of ``fed`` and wait until it answers; returns its pid (also stored on the row)."""
    folder = Path(fed.folder)
    if _pid_alive(fed.coordinator_pid) and coordinator_status(fed) is not None:
        return int(fed.coordinator_pid)
    (folder / COORDINATOR_FILE).unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items()}
    sdk = external_repo_dir("YFederation")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [sdk, env.get("PYTHONPATH", "")]))
    env["NO_PROXY"] = "127.0.0.1,localhost"
    log = open(folder / "coordinator.log", "ab")
    proc = subprocess.Popen(coordinator_argv(folder), cwd=str(folder), env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        info = coordinator_info(fed)
        if info and info.get("pid") == proc.pid:
            fed.coordinator_pid = proc.pid
            fed.port = int(info["port"])
            return proc.pid
        if proc.poll() is not None:
            raise CoordinatorError(f"the coordinator exited with code {proc.returncode}; see {folder / 'coordinator.log'}")
        time.sleep(0.1)
    stop_pid(proc.pid)
    raise CoordinatorError("the coordinator did not start in time")


def stop_pid(pid, grace: float = 8.0) -> bool:
    """SIGTERM, then SIGKILL after ``grace`` seconds. True when the process is gone."""
    if not _pid_alive(pid):
        return True
    try:
        os.kill(int(pid), signal.SIGTERM)
    except OSError:
        return True
    end = time.monotonic() + grace
    while time.monotonic() < end:
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)
    try:
        os.kill(int(pid), signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.2)
    return not _pid_alive(pid)


def stop_coordinator(fed) -> bool:
    gone = stop_pid(fed.coordinator_pid)
    (Path(fed.folder) / COORDINATOR_FILE).unlink(missing_ok=True)
    fed.coordinator_pid = None
    fed.port = None
    return gone


def _get(fed, path: str, timeout: float):
    info = coordinator_info(fed)
    if not info:
        return None
    request = urllib.request.Request(f"http://{info['host']}:{info['port']}{path}", headers={TOKEN_HEADER: fed.token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def coordinator_status(fed, timeout: float = 3.0) -> Optional[dict]:
    """The answer of GET /v1/status, or None when the coordinator does not answer."""
    return _get(fed, "/v1/status", timeout)


def waiting_members(status: Optional[dict]) -> dict:
    """{member: [members it waits for]} from a /v1/status answer.

    A member is waiting at the gate when it is ahead of the global tick: it has said ready for a later tick and
    cannot advance until the slowest members (those at the global tick) catch up."""
    if not status:
        return {}
    members = status.get("members") or {}
    live = {m: v for m, v in members.items() if v.get("status") in ("registered", "running")}
    if not live:
        return {}
    slowest = min(v.get("last_ready_tick", -1) for v in live.values())
    slow = sorted(m for m, v in live.items() if v.get("last_ready_tick", -1) == slowest)
    return {m: slow for m, v in live.items() if v.get("last_ready_tick", -1) > slowest}


def federation_of_experiment(exp_id):
    """The World Simulation row (running or not) an experiment belongs to, or None."""
    from y_web import db
    from y_web.src.models.admin import Federation, FederationMember

    return (
        db.session.query(Federation)
        .join(FederationMember, FederationMember.federation_pk == Federation.id)
        .filter(FederationMember.exp_id == exp_id)
        .first()
    )


def is_waiting_at_gate(exp_id, timeout: float = 2.0) -> bool:
    """True when ``exp_id`` is a member of a running World Simulation that is waiting for slower members (watchdog)."""
    from y_web.src.models.admin import FederationMember

    fed = federation_of_experiment(exp_id)
    if fed is None or fed.status not in ("running", "paused"):
        return False
    row = FederationMember.query.filter_by(federation_pk=fed.id, exp_id=exp_id).first()
    return bool(row) and row.member in waiting_members(coordinator_status(fed, timeout))
