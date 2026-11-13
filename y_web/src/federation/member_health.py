"""Members of a running World Simulation that do not show up, stall or die (what the Execution tab warns about).

Everything is read from data YWeb already has, so the status endpoint stays cheap:

* the coordinator ``GET /v1/status`` (status and ``last_ready_tick`` of each member), already polled by the page;
* the last events of the coordinator database (``hello``, ``ready``, ``global_advance``) read with three small
  queries (``LIMIT``), read only;
* the process state of the member servers and clients (pid of the experiment and of its clients);
* the tail of ``server_stderr.log`` / ``<client>_client_stderr.log`` of a member, read only for a member in trouble.

``classify_members`` and the other pure functions take plain values (no database, no clock, no files) so that they are
tested with fixtures; ``collect`` gathers the values. Definitions:

* missing   no ``hello`` within ``HELLO_TIMEOUT`` seconds of the start of the coordinator;
* stalled   no new ``ready`` for ``max(STALL_FLOOR, STALL_FACTOR * median tick time)`` seconds while the other members
            wait for it (it is one of the slowest and somebody is ahead);
* dead      the server process, or every client process, of the member exited.

A hint, not a problem (``silent_members``): the member advances its ticks but its server has received no content action
(post, comment, reaction written by its own clients; content imported by the federation does not count) for
``SILENT_TICKS`` ticks. It means the clock runs while no agent acts (World Simulation 1: a resumed microblogging client
that sampled nobody).
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

HELLO_TIMEOUT = 60.0
STALL_FLOOR = 120.0
STALL_FACTOR = 5.0
SLOTS_PER_DAY = 24
RECENT_ADVANCES = 40  # global_advance events read to estimate the time of a tick
RECENT_READY = 200
SILENT_TICKS = (
    12  # ticks without a content action on the server of a member that keeps advancing
)
LOG_TAIL_BYTES = 8192

OK, WAITING, STARTING, MISSING, STALLED, DEAD, FAILED, FINISHED, UNKNOWN = (
    "ok",
    "waiting",
    "starting",
    "missing",
    "stalled",
    "dead",
    "failed",
    "finished",
    "unknown",
)
PROBLEMS = (MISSING, STALLED, DEAD, FAILED)


# ----------------------------------------------------------------------------------------------- pure functions
def median_tick_seconds(advances: Iterable[Tuple[int, float]]) -> Optional[float]:
    """Seconds per tick from ``global_advance`` events ``[(tick, at)]`` (any order): median of the intervals between
    consecutive events divided by the ticks they cover. ``None`` with fewer than two usable events.
    """
    points = sorted(
        {
            (int(t), float(a))
            for t, a in advances
            if t is not None and a is not None and 0 <= int(t) < 2**30
        }
    )
    rates = []
    for (t0, a0), (t1, a1) in zip(points, points[1:]):
        if t1 > t0 and a1 >= a0:
            rates.append((a1 - a0) / (t1 - t0))
    return statistics.median(rates) if rates else None


def stall_threshold(
    tick_seconds: Optional[float],
    floor: float = STALL_FLOOR,
    factor: float = STALL_FACTOR,
) -> float:
    return max(floor, factor * (tick_seconds or 0.0))


def progress(
    global_tick, total_ticks: Optional[int], tick_seconds: Optional[float]
) -> dict:
    """``{tick, total, seconds_per_tick, eta_seconds}``; the ticks done are ``global_tick + 1`` (tick 0 is the first)."""
    done = None if global_tick is None or global_tick < 0 else int(global_tick) + 1
    total = int(total_ticks) if total_ticks else None
    eta = None
    if done is not None and total and tick_seconds:
        eta = max(0.0, (total - done) * tick_seconds)
    return {
        "tick": done,
        "total": total,
        "seconds_per_tick": None if tick_seconds is None else round(tick_seconds, 1),
        "eta_seconds": None if eta is None else int(eta),
    }


def format_duration(seconds: Optional[float]) -> str:
    """``65 s``, ``12 min``, ``13 h``, ``2.5 d``: one figure, no localisation (units are symbols)."""
    if seconds is None:
        return "-"
    s = float(seconds)
    if s < 120:
        return f"{int(round(s))} s"
    if s < 7200:
        return f"{int(round(s / 60))} min"
    if s < 172800:
        return f"{int(round(s / 3600))} h"
    return f"{s / 86400:.1f} d"


_CAUSES = (
    (
        re.compile(
            r"(?:ModuleNotFoundError|ImportError): No module named ['\"]?([\w.\-]+)"
        ),
        "module",
        1,
    ),
    (re.compile(r"cannot import name ['\"]?([\w.]+)"), "import", 1),
    (re.compile(r"Address already in use|\[Errno 98\]|\[Errno 48\]"), "port", 0),
    (
        re.compile(r"Connection refused|ConnectionRefusedError|\[Errno 111\]"),
        "refused",
        0,
    ),
    (re.compile(r"database is locked|OperationalError"), "database", 0),
    (re.compile(r"(?:MemoryError|Out of memory|Killed)\b"), "memory", 0),
)


def probable_cause(text: str) -> Optional[dict]:
    """The most recent recognisable cause in a log tail: ``{"kind", "name", "line"}`` (kind: module, import, port,
    refused, database, memory, error) or ``None`` for an empty or unremarkable tail. Later lines win.
    """
    lines = [l.rstrip() for l in (text or "").splitlines() if l.strip()]
    for line in reversed(lines):
        for pattern, kind, group in _CAUSES:
            m = pattern.search(line)
            if m:
                return {
                    "kind": kind,
                    "name": m.group(group) if group else "",
                    "line": line.strip()[:200],
                }
    for line in reversed(lines):  # a Python exception line such as "ValueError: ..."
        if re.match(r"^[A-Za-z_][\w.]*(Error|Exception)\b", line.strip()):
            return {"kind": "error", "name": "", "line": line.strip()[:200]}
    return None


def classify_members(
    *,
    now: float,
    started_at: Optional[float],
    members: Dict[str, dict],
    hello_at: Dict[str, float],
    last_ready_at: Dict[str, float],
    procs: Dict[str, dict],
    tick_seconds: Optional[float],
    hello_timeout: float = HELLO_TIMEOUT,
    stall_floor: float = STALL_FLOOR,
    stall_factor: float = STALL_FACTOR,
) -> Dict[str, dict]:
    """State of every member: ``{member: {"code", "problem", "waiting_for", "dead": [...], "since"}}``.

    ``members``: ``{member: {"status", "last_ready_tick"}}`` of ``/v1/status`` (empty when the coordinator does not
    answer: every member is "unknown"). ``hello_at`` and ``last_ready_at``: epoch seconds of the first hello of this run
    and of the last ready. ``procs``: ``{member: {"server": bool, "clients": {name: bool}}}``.
    """
    out: Dict[str, dict] = {}
    if not members:
        return {
            m: {
                "code": UNKNOWN,
                "problem": False,
                "waiting_for": [],
                "dead": [],
                "since": None,
            }
            for m in procs
        }
    live = {
        m: v for m, v in members.items() if v.get("status") in ("registered", "running")
    }
    ticks = {m: v.get("last_ready_tick", -1) for m, v in live.items()}
    slowest_tick = min(ticks.values()) if ticks else None
    slowest = sorted(m for m, t in ticks.items() if t == slowest_tick)
    ahead = {
        m for m, t in ticks.items() if slowest_tick is not None and t > slowest_tick
    }
    threshold = stall_threshold(tick_seconds, stall_floor, stall_factor)
    for name, info in members.items():
        status = info.get("status")
        state = {
            "code": OK,
            "problem": False,
            "waiting_for": [],
            "dead": [],
            "since": None,
        }
        out[name] = state
        if status == "finished":
            state["code"] = FINISHED
            continue
        if status == "failed":
            state.update(code=FAILED, problem=True)
            continue
        p = procs.get(name) or {}
        dead = []
        if p.get("server") is False:
            dead.append("server")
        clients = p.get("clients") or {}
        dead += [
            f"client {c}" for c, alive in sorted(clients.items()) if alive is False
        ]
        if clients and not any(clients.values()) and not dead:
            dead = [f"client {c}" for c in sorted(clients)]
        if (
            dead
        ):  # also when only one of several clients died: the member may go on, but it is worth a warning
            state.update(code=DEAD, problem=True, dead=dead)
            continue
        if name not in hello_at:
            waited = None if started_at is None else now - started_at
            if waited is not None and waited > hello_timeout:
                state.update(code=MISSING, problem=True, since=int(waited))
            else:
                state["code"] = STARTING
            continue
        if name in ahead:
            state.update(code=WAITING, waiting_for=list(slowest))
            continue
        if name in slowest and ahead:
            last = last_ready_at.get(name) or hello_at.get(name)
            if last is not None and now - last > threshold:
                state.update(code=STALLED, problem=True, since=int(now - last))
    return out


def silent_members(
    *,
    ticks: Dict[str, Optional[int]],
    last_action_tick: Dict[str, Optional[int]],
    skip: Iterable[str] = (),
    threshold: int = SILENT_TICKS,
) -> Dict[str, dict]:
    """Members that advance but whose server has received no content action for ``threshold`` ticks or more.

    ``ticks``: last tick of each member (``last_ready_tick``); ``last_action_tick``: tick (round) of the last content
    action in its server database, ``-1`` when it has none, ``None`` when it cannot be known (such a member is never
    reported). ``skip``: members already in trouble (dead, stalled ...). Returns
    ``{member: {"tick", "last_action_tick", "ticks"}}``."""
    skipped = set(skip)
    out = {}
    for member, tick in ticks.items():
        last = last_action_tick.get(member)
        if member in skipped or tick is None or last is None or tick < 0:
            continue
        silent_for = int(tick) - int(last)
        if silent_for >= threshold:
            out[member] = {
                "tick": int(tick),
                "last_action_tick": int(last),
                "ticks": silent_for,
            }
    return out


# ------------------------------------------------------------------------------------------- data collection
def last_action_tick(db_path) -> Optional[int]:
    """Tick of the last content action received by a member server: the highest ``round`` of ``reactions`` and of the
    ``post`` rows that were not imported by the federation (``federation_ref``). ``-1``: tables there, no action yet;
    ``None``: the database or its tables cannot be read (unknown, never reported)."""
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return None
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "post" not in tables:
            return None
        imported = (
            " WHERE id NOT IN (SELECT local_id FROM federation_ref WHERE local_kind='post')"
            if "federation_ref" in tables
            else ""
        )
        rounds = [conn.execute(f"SELECT MAX(round) FROM post{imported}").fetchone()[0]]
        if "reactions" in tables:
            rounds.append(
                conn.execute("SELECT MAX(round) FROM reactions").fetchone()[0]
            )
        known = [int(r) for r in rounds if r is not None]
        return max(known) if known else -1
    except (sqlite3.Error, ValueError, TypeError):
        return None
    finally:
        conn.close()


def silent_of(
    pairs, members: Dict[str, dict], states: Dict[str, dict]
) -> Dict[str, dict]:
    """``silent_members`` for the members of a running World Simulation (``pairs``: ``service.members_of``)."""
    from y_web.src.federation import service

    ticks, last = {}, {}
    for row, exp in pairs:
        info = members.get(row.member) or {}
        if info.get("status") not in ("registered", "running"):
            continue
        ticks[row.member] = info.get("last_ready_tick")
        last[row.member] = last_action_tick(
            service.experiment_dir(exp) / "database_server.db"
        )
    return silent_members(
        ticks=ticks,
        last_action_tick=last,
        skip=[m for m, s in states.items() if s.get("problem")],
    )


def read_tail(path, max_bytes: int = LOG_TAIL_BYTES, lines: int = 30) -> str:
    """The last lines of a log file ("" when it cannot be read)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return "\n".join(data.splitlines()[-lines:])


def started_at_of(fed) -> Optional[float]:
    """When the coordinator of the run started: the modification time of its descriptor (removed at stop)."""
    try:
        return (Path(fed.folder) / "federation_coordinator.json").stat().st_mtime
    except OSError:
        return None


_hello_cache: Dict[tuple, Dict[str, float]] = {}


def read_events(
    fed, started_at: Optional[float], known_hello: Optional[Dict[str, float]] = None
) -> dict:
    """``{"hello": {member: at}, "ready": {member: at}, "advances": [(tick, at)]}`` from the coordinator database.

    Read only, three bounded queries. ``hello`` only counts events of this run (``at >= started_at``).
    """
    out = {"hello": dict(known_hello or {}), "ready": {}, "advances": []}
    path = Path(fed.folder) / "federation.db"
    if not path.is_file():
        return out
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            for member_at in conn.execute(
                "SELECT detail_json, at FROM federation_event WHERE kind='hello' AND at>=? ORDER BY id",
                (started_at or 0.0,),
            ):
                member = _member_of(member_at[0])
                if member and member not in out["hello"]:
                    out["hello"][member] = member_at[1]
            for detail, at in conn.execute(
                "SELECT detail_json, at FROM federation_event WHERE kind='ready' ORDER BY id DESC LIMIT ?",
                (RECENT_READY,),
            ):
                member = _member_of(detail)
                if member and member not in out["ready"]:
                    out["ready"][member] = at
            out["advances"] = [
                (t, a)
                for t, a in conn.execute(
                    "SELECT tick, at FROM federation_event WHERE kind='global_advance' ORDER BY id DESC LIMIT ?",
                    (RECENT_ADVANCES,),
                )
            ]
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return out


def _member_of(detail_json: str) -> Optional[str]:
    try:
        return json.loads(detail_json).get("member")
    except (ValueError, AttributeError):
        return None


def _alive(pid) -> bool:
    from y_web.src.federation import coordinator_process as cp

    return cp._pid_alive(pid)


def process_state(exps_clients) -> Dict[str, dict]:
    """``{member: {"server": bool, "clients": {name: bool}}}`` from ``[(member, exp, [clients])]``."""
    out = {}
    for member, exp, clients in exps_clients:
        out[member] = {
            "server": bool(exp.server_pid) and _alive(exp.server_pid),
            "clients": {
                c.name: bool(c.pid) and _alive(c.pid) for c in clients if c.status == 1
            },
        }
    return out


def total_ticks(clients) -> Optional[int]:
    days = [c.days for c in clients if c.days]
    return max(days) * SLOTS_PER_DAY if days else None


def log_files(exp, clients) -> List[Path]:
    from y_web.src.federation import service

    folder = service.experiment_dir(exp)
    return [folder / "server_stderr.log"] + [
        folder / f"{c.name}_client_stderr.log" for c in clients
    ]


def collect(
    fed,
    coordinator: Optional[dict],
    *,
    now: Optional[float] = None,
    hello_timeout: float = HELLO_TIMEOUT,
) -> dict:
    """The health report of a running World Simulation (``{}`` when it is not running).

    ``{"members": {name: state + "cause", "log"}, "problems": [names], "progress": {...}, "coordinator_up": bool}``;
    each member state is that of ``classify_members`` plus ``cause`` (``probable_cause`` of its log tail) and ``log``
    (the file to open) when it is a problem."""
    from y_web import db
    from y_web.src.federation import service
    from y_web.src.models import Client

    if fed.status != "running":
        return {}
    now = time.time() if now is None else now
    pairs = service.members_of(fed)
    clients_of = {}
    for client in (
        db.session.query(Client)
        .filter(Client.id_exp.in_([e.idexp for _, e in pairs]))
        .order_by(Client.id)
        .all()
    ):
        clients_of.setdefault(client.id_exp, []).append(client)
    started = started_at_of(fed)
    key = (fed.id, started)
    events = read_events(fed, started, _hello_cache.get(key))
    if len(_hello_cache) > 64:
        _hello_cache.clear()
    _hello_cache[key] = dict(events["hello"])
    members = (coordinator or {}).get("members") or {}
    tick_seconds = median_tick_seconds(events["advances"])
    procs = process_state(
        [(m.member, e, clients_of.get(e.idexp, [])) for m, e in pairs]
    )
    states = classify_members(
        now=now,
        started_at=started,
        members=members,
        hello_at=events["hello"],
        last_ready_at=events["ready"],
        procs=procs,
        tick_seconds=tick_seconds,
        hello_timeout=hello_timeout,
    )
    for m, exp in pairs:
        state = states.get(m.member)
        if state is None or not state["problem"]:
            continue
        files = log_files(exp, clients_of.get(exp.idexp, []))
        for path in files:
            cause = probable_cause(read_tail(path))
            if cause:
                state["cause"], state["log"] = cause, str(path)
                break
        state.setdefault("log", str(files[0]))
    try:
        silent = silent_of(pairs, members, states)
    except Exception:  # noqa: BLE001 - a hint is never worth an error
        silent = {}
    for m, info in silent.items():
        states[m]["silent"] = info
    every_client = [c for cs in clients_of.values() for c in cs]
    gtick = (coordinator or {}).get("global_tick")
    return {
        "members": states,
        "problems": sorted(n for n, s in states.items() if s["problem"]),
        "progress": progress(gtick, total_ticks(every_client), tick_seconds),
        "coordinator_up": coordinator is not None,
        "silent": silent,
        "stall_after": int(stall_threshold(tick_seconds)),
        "hello_timeout": int(hello_timeout),
    }
