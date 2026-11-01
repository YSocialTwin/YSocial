"""Derived analytics database of a World Simulation (F7.1, pattern of the dating and IM ``analytics_etl.py``).

``analytics_federation.db`` lives in the folder of the World Simulation, is owned by YWeb and holds tables shaped for
analysis. It is rebuilt in full from ``federation.db`` (the database of the coordinator), which is only ever opened
read-only; the coordinator never reads the derived file. The build writes a temporary file and replaces the old one
atomically, so two builds of the same source give the same rows (``etl_state`` carries no clock; the time of the build
is in a status file beside it).

Days are the canonical days of the federation (``tick // 24``, base 0).

``FIELD_MAP`` is the single description of every derived table and column; the reference of the configuration and
the analytics pages read the names from it.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

ANALYTICS_FILE = "analytics_federation.db"
STATUS_FILE = "analytics_federation.status.json"
SOURCE_FILE = "federation.db"
SCHEMA_VERSION = 1
SLOTS_PER_DAY = 24
SOURCE_REF_PREFIX = "ysocial://"
NEW = "(new)"  # origin of a join that follows no leave

# table -> (description, source, [(column, type, meaning)])
FIELD_MAP: Dict[str, Tuple[str, str, List[Tuple[str, str, str]]]] = {
    "daily_attention": (
        "Attention of the agents on each platform, one row per day and member.",
        "federation_attention",
        [
            ("day", "INTEGER", "canonical day, from 0"),
            ("member", "TEXT", "platform member"),
            ("agents", "INTEGER", "agents with a weight on this member that day"),
            ("weight", "REAL", "sum of the weights of those agents"),
            ("share", "REAL", "weight / total weight of the day over all members (0 when nobody has attention)"),
        ],
    ),
    "migration_flows": (
        "Agents that became active on a member, by the member they had most recently left (or '(new)').",
        "federation_event (membership_change)",
        [
            ("day", "INTEGER", "day of the join"),
            ("from_member", "TEXT", "member left most recently by the agent, '(new)' when none"),
            ("to_member", "TEXT", "member joined"),
            ("n", "INTEGER", "agents"),
        ],
    ),
    "crosspost_flows": (
        "Cross-posts delivered between platforms, one row per day, origin and destination.",
        "federation_message (crosspost.v1)",
        [
            ("day", "INTEGER", "day the cross-post was emitted"),
            ("source", "TEXT", "member where the content was posted (from its source_ref)"),
            ("target", "TEXT", "member the cross-post was addressed to"),
            ("n", "INTEGER", "cross-posts"),
        ],
    ),
    "cascades": (
        "How far each cross-posted content went: one row per original content.",
        "federation_message (crosspost.v1)",
        [
            ("source_ref", "TEXT", "ysocial:// reference of the original content"),
            ("origin", "TEXT", "member of the original content"),
            ("day", "INTEGER", "day of the first cross-post"),
            ("size", "INTEGER", "cross-posts of this content"),
            ("targets", "INTEGER", "distinct platforms reached"),
        ],
    ),
    "survival": (
        "Agents still present on each platform at the end of each day, and those who left that day.",
        "federation_affective, federation_event (membership_change)",
        [
            ("day", "INTEGER", "canonical day"),
            ("member", "TEXT", "platform member"),
            ("active", "INTEGER", "agents with an affective report for the day (active at its end)"),
            ("left", "INTEGER", "agents whose membership ended that day"),
            ("survival", "REAL", "active / active on the first day with data for the member"),
        ],
    ),
}
EXPORT_TABLES = tuple(FIELD_MAP)
_guard = threading.Lock()
_locks: Dict[str, threading.Lock] = {}


def analytics_path(folder: str) -> str:
    return os.path.join(folder, ANALYTICS_FILE)


def source_path(folder: str) -> str:
    return os.path.join(folder, SOURCE_FILE)


def _status_path(folder: str) -> str:
    return os.path.join(folder, STATUS_FILE)


def _lock_for(folder: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(os.path.abspath(folder), threading.Lock())


def source_signature(path: str) -> str:
    parts = []
    for suffix in ("", "-wal"):
        try:
            st = os.stat(path + suffix)
        except OSError:
            continue
        if suffix and st.st_size == 0:
            continue
        parts.append(f"{suffix}:{st.st_size}:{st.st_mtime_ns}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _ddl() -> str:
    out = [
        "CREATE TABLE etl_state (schema_version INTEGER, source_signature TEXT, last_day INTEGER, "
        "messages INTEGER, events INTEGER);"
    ]
    for table, (_d, _s, cols) in FIELD_MAP.items():
        out.append(f"CREATE TABLE {table} ({', '.join(f'{c} {t}' for c, t, _m in cols)});")
    return "\n".join(out)


def _origin(source_ref: str) -> str:
    """Member of an ``ysocial://<federation>/<member>/<kind>/<id>`` reference ('' when it does not parse)."""
    parts = str(source_ref or "")[len(SOURCE_REF_PREFIX):].split("/")
    return parts[1] if str(source_ref or "").startswith(SOURCE_REF_PREFIX) and len(parts) >= 4 else ""


def compute(src: sqlite3.Connection) -> Dict[str, Any]:
    """The rows of every derived table, in a stable order, plus the counters of the source."""
    q = lambda sql, args=(): src.execute(sql, args).fetchall()  # noqa: E731

    attention: Dict[Tuple[int, str], List[float]] = defaultdict(lambda: [0, 0.0])
    for day, member, weight in q("SELECT day, member, weight FROM federation_attention WHERE weight > 0"):
        cell = attention[(int(day), member)]
        cell[0] += 1
        cell[1] += float(weight)
    totals: Dict[int, float] = defaultdict(float)
    for (day, _m), (_n, weight) in attention.items():
        totals[day] += weight
    daily_attention = [
        (day, member, n, round(w, 6), round(w / totals[day], 6) if totals[day] > 0 else 0.0)
        for (day, member), (n, w) in sorted(attention.items())
    ]

    last_left: Dict[str, str] = {}
    flows: Dict[Tuple[int, str, str], int] = defaultdict(int)
    left_per_day: Dict[Tuple[int, str], int] = defaultdict(int)
    events = q("SELECT id, tick, detail_json FROM federation_event WHERE kind='membership_change' ORDER BY id")
    for _id, tick, detail in events:
        d = json.loads(detail)
        day, gid, member = int(tick) // SLOTS_PER_DAY, str(d["global_agent_id"]), d["member"]
        if d.get("to") == "active":
            flows[(day, last_left.pop(gid, NEW), member)] += 1
        elif d.get("to") == "left":
            last_left[gid] = member
            left_per_day[(day, member)] += 1
    migration_flows = [(day, a, b, n) for (day, a, b), n in sorted(flows.items())]

    crossflows: Dict[Tuple[int, str, str], int] = defaultdict(int)
    cascade: Dict[str, List[Any]] = {}
    messages = q("SELECT fed_msg_id, target_member, tick_emitted, payload_json FROM federation_message "
                 "WHERE payload_type='crosspost.v1' ORDER BY tick_emitted, fed_msg_id")
    for _fid, target, tick, payload in messages:
        ref = json.loads(payload).get("source_ref", "")
        origin, day = _origin(ref), int(tick) // SLOTS_PER_DAY
        crossflows[(day, origin, target)] += 1
        entry = cascade.setdefault(ref, [origin, day, 0, set()])
        entry[2] += 1
        entry[3].add(target)
    crosspost_flows = [(day, a, b, n) for (day, a, b), n in sorted(crossflows.items())]
    cascades = [(ref, e[0], e[1], e[2], len(e[3])) for ref, e in sorted(cascade.items())]

    active: Dict[Tuple[int, str], int] = defaultdict(int)
    for day, member, n in q("SELECT day, member, COUNT(*) FROM federation_affective GROUP BY day, member"):
        active[(int(day), member)] = int(n)
    keys = sorted(set(active) | set(left_per_day))
    first: Dict[str, int] = {}
    for (day, member) in keys:
        if active.get((day, member)):
            first.setdefault(member, active[(day, member)])
    survival = [
        (day, member, active.get((day, member), 0), left_per_day.get((day, member), 0),
         round(active.get((day, member), 0) / first[member], 6) if first.get(member) else 0.0)
        for day, member in keys
    ]
    last_day = max([r[0] for r in daily_attention] + [r[0] for r in survival] + [r[0] for r in crosspost_flows], default=-1)
    return {"tables": {"daily_attention": daily_attention, "migration_flows": migration_flows,
                       "crosspost_flows": crosspost_flows, "cascades": cascades, "survival": survival},
            "last_day": last_day, "messages": len(messages), "events": len(events)}


def _write(path: str, computed: Dict[str, Any], signature: str) -> None:
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_ddl())
        for table, rows in computed["tables"].items():
            if rows:
                marks = ",".join("?" * len(FIELD_MAP[table][2]))
                conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
        conn.execute("INSERT INTO etl_state VALUES (?,?,?,?,?)",
                     (SCHEMA_VERSION, signature, computed["last_day"], computed["messages"], computed["events"]))
        conn.commit()
    finally:
        conn.close()


def _write_status(folder: str, **values: Any) -> None:
    try:
        tmp = _status_path(folder) + ".part"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(values, handle)
        os.replace(tmp, _status_path(folder))
    except OSError:
        pass


def build(folder: str) -> Dict[str, Any]:
    """Rebuild ``analytics_federation.db``; returns ``{"ok", "last_day", "message"}``. A failure keeps the previous file."""
    src_file = source_path(folder)
    if not os.path.isfile(src_file):
        return {"ok": False, "message": "the federation database does not exist yet"}
    lock = _lock_for(folder)
    if not lock.acquire(blocking=False):
        return {"ok": False, "message": "a build is already running"}
    tmp = analytics_path(folder) + ".part"
    try:
        started = time.time()
        signature = source_signature(src_file)
        src = sqlite3.connect(f"file:{src_file}?mode=ro", uri=True, timeout=10)
        try:
            src.execute("PRAGMA query_only = ON")
            computed = compute(src)
        finally:
            src.close()
        _write(tmp, computed, signature)
        os.replace(tmp, analytics_path(folder))
        _write_status(folder, state="fresh", built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      seconds=round(time.time() - started, 2))
        return {"ok": True, "last_day": computed["last_day"], "message": ""}
    except (sqlite3.Error, OSError) as exc:
        _write_status(folder, state="failed", message=str(exc))
        try:
            os.remove(tmp)
        except OSError:
            pass
        return {"ok": False, "message": str(exc)}
    finally:
        lock.release()


def read_state(folder: str) -> Dict[str, Any]:
    """``state`` (never | running | fresh | stale | failed), the data horizon and the message for the admin."""
    out: Dict[str, Any] = {"state": "never", "last_day": None, "message": "", "built_at": None}
    if _lock_for(folder).locked():
        out["state"] = "running"
    try:
        with open(_status_path(folder), encoding="utf-8") as handle:
            recorded = json.load(handle)
    except (OSError, ValueError):
        recorded = {}
    out["built_at"] = recorded.get("built_at")
    path = analytics_path(folder)
    if os.path.isfile(path):
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
                row = conn.execute("SELECT schema_version, source_signature, last_day FROM etl_state").fetchone()
        except sqlite3.Error:
            row = None
        if row:
            out["last_day"] = row[2]
            if out["state"] != "running":
                current = source_signature(source_path(folder))
                out["state"] = "fresh" if (row[0] == SCHEMA_VERSION and row[1] == current) else "stale"
    if recorded.get("state") == "failed" and out["state"] != "running":
        out["state"], out["message"] = "failed", recorded.get("message", "")
    return out


def ensure_derived(folder: str) -> Dict[str, Any]:
    """Build when the database is missing or older than the run; one comparison when it is current."""
    state = read_state(folder)
    if state["state"] in ("never", "stale") and os.path.isfile(source_path(folder)):
        build(folder)
        state = read_state(folder)
    return state


def table_rows(folder: str, table: str) -> Tuple[List[str], List[tuple]]:
    """Columns and rows of a derived table (whitelisted names only)."""
    if table not in EXPORT_TABLES:
        raise KeyError(table)
    columns = [c for c, _t, _m in FIELD_MAP[table][2]]
    with sqlite3.connect(f"file:{analytics_path(folder)}?mode=ro", uri=True) as conn:
        return columns, conn.execute(f"SELECT * FROM {table}").fetchall()


def cards(folder: str) -> Dict[str, Any]:
    """What the analytics page shows, read from the derived database (``tables`` empty when there is none yet)."""
    state = ensure_derived(folder)
    out: Dict[str, Any] = {"state": state, "tables": {}}
    if not os.path.isfile(analytics_path(folder)):
        return out
    for table in EXPORT_TABLES:
        cols, rows = table_rows(folder, table)
        out["tables"][table] = [dict(zip(cols, r)) for r in rows]
    return out


def render_field_map() -> str:
    """Markdown reference of the derived tables (used by the documentation)."""
    lines = []
    for table, (desc, source, cols) in FIELD_MAP.items():
        lines += [f"### `{table}`", "", f"{desc} Source: {source}.", "", "| Column | Type | Meaning |", "|---|---|---|"]
        lines += [f"| `{c}` | {t} | {m} |" for c, t, m in cols]
        lines.append("")
    return "\n".join(lines)
