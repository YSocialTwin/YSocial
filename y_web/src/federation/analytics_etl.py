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
from typing import Any, Dict, List, Optional, Tuple

ANALYTICS_FILE = "analytics_federation.db"
STATUS_FILE = "analytics_federation.status.json"
SOURCE_FILE = "federation.db"
SCHEMA_VERSION = 4  # 2: share chains, bridge agents and topics carried (X3.2); 3: people (human:) tables (H8); 4: topic diffusion (P1)
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
    "shares": (
        "Cross-posts that share the content of another agent (crosspost.v1 with `quoted`), one row per share and destination.",
        "federation_message (crosspost.v1, quoted)",
        [
            ("day", "INTEGER", "day the share was emitted"),
            ("tick", "INTEGER", "tick the share was emitted"),
            ("sharer", "TEXT", "global_agent_id of the agent that shares"),
            ("origin_member", "TEXT", "platform where the sharer saw the content (quoted.member)"),
            ("destination", "TEXT", "member the share was addressed to"),
            ("original_author", "TEXT", "name of the author of the shared content"),
            ("original_author_id", "TEXT", "global_agent_id of that author, '' when it is not a federation identity"),
            ("quoted_ref", "TEXT", "reference of the shared content ('' for an author outside the federation)"),
            ("depth", "INTEGER", "1 for a share of local content, +1 for each earlier cross-post the content went through"),
        ],
    ),
    "share_depth": (
        "How many shares sit at each depth of a chain.",
        "federation_message (crosspost.v1, quoted)",
        [
            ("depth", "INTEGER", "depth in the chain (see shares.depth)"),
            ("shares", "INTEGER", "shares at that depth"),
        ],
    ),
    "bridge_agents": (
        "Agents whose shares carry content from one platform to another, most active first.",
        "federation_message (crosspost.v1, quoted)",
        [
            ("agent", "TEXT", "global_agent_id of the sharer"),
            ("shares", "INTEGER", "shares sent"),
            ("origins", "INTEGER", "distinct platforms the shared content came from"),
            ("destinations", "INTEGER", "distinct platforms the shares reached"),
        ],
    ),
    "topics_carried": (
        "Topics that travelled with cross-posted content, by platform pair. Coordinator data only: which platform created the "
        "topic on arrival is in `topics_created`, read from the member databases when they can be reached.",
        "federation_message (crosspost.v1, topics)",
        [
            ("topic", "TEXT", "topic name as sent"),
            ("source", "TEXT", "member where the content was posted (from its source_ref)"),
            ("target", "TEXT", "member the content was addressed to"),
            ("n", "INTEGER", "cross-posts carrying the topic"),
            ("first_day", "INTEGER", "day of the first one"),
        ],
    ),
}
FIELD_MAP["human_crossposts"] = (
    "Cross-posts sent by people (identity `human:<id>`), one row per day, platform pair and kind. The identities of the agents never "
    "start with `human:` (INV-14), so this is exactly what the people did.",
    "federation_message (crosspost.v1 whose global_agent_id starts with human:)",
    [
        ("day", "INTEGER", "day the cross-post was emitted"),
        ("human", "TEXT", "global_agent_id of the person (human:<id>)"),
        ("source", "TEXT", "member the person posted on (source_member of the message)"),
        ("target", "TEXT", "member the cross-post was addressed to"),
        ("shares", "INTEGER", "of them, shares of another agent's content (with `quoted`)"),
        ("n", "INTEGER", "cross-posts"),
    ],
)
FIELD_MAP["human_activity"] = (
    "What each person did across the platforms, most active first.",
    "federation_message (crosspost.v1 whose global_agent_id starts with human:)",
    [
        ("human", "TEXT", "global_agent_id of the person (human:<id>)"),
        ("crossposts", "INTEGER", "cross-posts sent"),
        ("shares", "INTEGER", "of them, shares of another agent's content"),
        ("origins", "INTEGER", "distinct platforms the person posted from"),
        ("destinations", "INTEGER", "distinct platforms the cross-posts reached"),
        ("first_day", "INTEGER", "day of the first cross-post"),
        ("last_day", "INTEGER", "day of the last one"),
    ],
)
FIELD_MAP["topics_created"] = (
    "Topics a platform created on arrival of cross-posted content (topic migration), read READ-ONLY from the `federation_topic` "
    "(and `federation_topic_origin`) tables of the member databases. Empty when no member database can be reached.",
    "member databases: federation_topic, federation_topic_origin",
    [
        ("topic", "TEXT", "topic name as the platform stored it (runtimes may cut long names)"),
        ("member", "TEXT", "platform member that created it"),
        ("day", "INTEGER", "day of the creation (NULL when the runtime did not record the tick)"),
        ("source", "TEXT", "member whose content brought it"),
        ("original", "TEXT", "full name as sent when the platform cut it, otherwise the same as topic"),
    ],
)
FIELD_MAP["topic_first_seen"] = (
    "First time a topic shows up on each platform, through the migration only (never counts topics a platform had before).",
    "federation_message (crosspost.v1, topics) and topics_created",
    [
        ("topic", "TEXT", "topic name, lower case"),
        ("member", "TEXT", "platform member"),
        ("first_tick", "INTEGER", "canonical tick: emission for the platform that posted the content, delivery for the one that received it, creation when known"),
        ("via", "TEXT", "source (posted there), received (delivered there) or created (the platform created it)"),
    ],
)
FIELD_MAP["topic_diffusion"] = (
    "How far each topic travelled, most carried first.",
    "federation_message (crosspost.v1, topics) and topics_created",
    [
        ("topic", "TEXT", "topic name, lower case"),
        ("platforms", "INTEGER", "platforms where it appeared through the migration"),
        ("carried", "INTEGER", "cross-posts that carried it"),
        ("created_on", "INTEGER", "platforms that created it on arrival (0 when the member databases were not reachable)"),
        ("first_day", "INTEGER", "day of the first appearance"),
        ("last_day", "INTEGER", "day of the last cross-post carrying it"),
    ],
)
HUMAN_PREFIX = "human:"
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


def _member_topics(path: str) -> List[Tuple[str, Any, str, str]]:
    """``(topic, tick, source, original)`` created by the migration in one member database, read-only and tolerant of the
    differences between the runtimes (column names, an optional origin table). ``[]`` when the file or the table is missing."""
    out: List[Tuple[str, Any, str, str]] = []
    if not path or not os.path.isfile(path):
        return out
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return out
    try:
        conn.execute("PRAGMA query_only = ON")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(federation_topic)")}
        if "name" not in cols:
            return out
        tick = "created_tick" if "created_tick" in cols else ("tick" if "tick" in cols else None)
        source = "source_member" if "source_member" in cols else None
        rows = conn.execute(f"SELECT name, {tick or 'NULL'}, {source or 'NULL'} FROM federation_topic ORDER BY name").fetchall()
        origin: Dict[str, str] = {}
        ocols = {r[1] for r in conn.execute("PRAGMA table_info(federation_topic_origin)")}
        if {"full_name", "resolved_name"} <= ocols:  # YServer
            origin = {str(r[1]).lower(): str(r[0]) for r in conn.execute("SELECT full_name, resolved_name FROM federation_topic_origin")}
        elif {"original", "name"} <= ocols:  # forum
            origin = {str(r[1]).lower(): str(r[0]) for r in conn.execute("SELECT original, name FROM federation_topic_origin")}
        for name, t, src in rows:
            out.append((str(name), t, str(src or ""), origin.get(str(name).lower(), str(name))))
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return out


def compute(src: sqlite3.Connection, member_dbs: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
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
    shares: List[tuple] = []
    depth_of_ref: Dict[str, int] = {}
    carried: Dict[Tuple[str, str, str], List[int]] = {}
    for _fid, target, tick, payload in messages:
        body = json.loads(payload)
        ref, quoted, day = body.get("source_ref", ""), body.get("quoted"), int(tick) // SLOTS_PER_DAY
        depth = depth_of_ref.get(quoted.get("source_ref") or "", 0) + 1 if quoted else 1
        depth_of_ref[ref] = max(depth, depth_of_ref.get(ref, 0))
        if quoted:
            shares.append((day, int(tick), str(body.get("global_agent_id", "")), quoted["member"], target,
                           quoted["author_name"], quoted.get("global_agent_id") or "", quoted.get("source_ref") or "", depth))
        for topic in body.get("topics") or []:
            cell = carried.setdefault((str(topic), _origin(ref), target), [0, day])
            cell[0] += 1
            cell[1] = min(cell[1], day)
    shares.sort()
    # people (H8): cross-posts whose author is a human:<id> identity, from the member the person posted on
    human_cells: Dict[Tuple[int, str, str, str], List[int]] = {}
    human_total: Dict[str, List[Any]] = {}
    for _fid, source, target, tick, payload in q(
        "SELECT fed_msg_id, source_member, target_member, tick_emitted, payload_json FROM federation_message "
        "WHERE payload_type='crosspost.v1' ORDER BY tick_emitted, fed_msg_id"
    ):
        body = json.loads(payload)
        who = str(body.get("global_agent_id", ""))
        if not who.startswith(HUMAN_PREFIX):
            continue
        day, shared = int(tick) // SLOTS_PER_DAY, 1 if body.get("quoted") else 0
        cell = human_cells.setdefault((day, who, source, target), [0, 0])
        cell[0] += 1
        cell[1] += shared
        tot = human_total.setdefault(who, [0, 0, set(), set(), day, day])
        tot[0] += 1
        tot[1] += shared
        tot[2].add(source)
        tot[3].add(target)
        tot[4], tot[5] = min(tot[4], day), max(tot[5], day)
    human_crossposts = [(d, h, s, t, c[1], c[0]) for (d, h, s, t), c in sorted(human_cells.items())]
    human_activity = sorted(((h, v[0], v[1], len(v[2]), len(v[3]), v[4], v[5]) for h, v in human_total.items()),
                            key=lambda r: (-r[1], r[0]))
    depth_count: Dict[int, int] = defaultdict(int)
    bridge: Dict[str, List[Any]] = {}
    for row in shares:
        depth_count[row[8]] += 1
        entry = bridge.setdefault(row[2], [0, set(), set()])
        entry[0] += 1
        entry[1].add(row[3])
        entry[2].add(row[4])
    share_depth = sorted(depth_count.items())
    bridge_agents = sorted(((a, e[0], len(e[1]), len(e[2])) for a, e in bridge.items()), key=lambda r: (-r[1], r[0]))
    topics_carried = [(t, a, b, c[0], c[1]) for (t, a, b), c in sorted(carried.items())]
    # topic migration (P1): where each topic appeared, from the cross-posts that carried it and, when the member databases
    # can be reached, from the topics a platform created on arrival
    seen: Dict[Tuple[str, str], List[Any]] = {}
    tcount: Dict[str, List[Any]] = {}

    def _see(topic: str, member: str, tick: int, via: str) -> None:
        cell = seen.get((topic, member))
        if cell is None or tick < cell[0]:
            seen[(topic, member)] = [tick, via if cell is None or tick < cell[0] else cell[1]]

    for _fid, source, target, emitted, delivered, payload in q(
        "SELECT fed_msg_id, source_member, target_member, tick_emitted, deliver_at_tick, payload_json FROM federation_message "
        "WHERE payload_type='crosspost.v1' ORDER BY tick_emitted, fed_msg_id"
    ):
        body = json.loads(payload)
        for raw in body.get("topics") or []:
            topic = str(raw).strip().lower()
            if not topic:
                continue
            _see(topic, source, int(emitted), "source")
            _see(topic, target, int(delivered), "received")
            cell = tcount.setdefault(topic, [0, int(emitted) // SLOTS_PER_DAY, int(emitted) // SLOTS_PER_DAY, set()])
            cell[0] += 1
            cell[1], cell[2] = min(cell[1], int(emitted) // SLOTS_PER_DAY), max(cell[2], int(emitted) // SLOTS_PER_DAY)
    created_rows: List[tuple] = []
    created_on: Dict[str, set] = defaultdict(set)
    for member in sorted(member_dbs or {}):
        for name, tick, source_member, original in _member_topics((member_dbs or {})[member]):
            day = int(tick) // SLOTS_PER_DAY if tick is not None else None
            created_rows.append((name, member, day, source_member, original))
            for key in {name.strip().lower(), original.strip().lower()}:
                created_on[key].add(member)
                if tick is not None:
                    _see(key, member, int(tick), "created")
                else:
                    seen.setdefault((key, member), [0, "created"])
    topics_created = sorted(created_rows, key=lambda r: (r[1], r[0]))
    topic_first_seen = sorted(((t, m, c[0], c[1]) for (t, m), c in seen.items()), key=lambda r: (r[0], r[2], r[1]))
    diffusion = []
    for topic in sorted({t for t, _m in seen}):
        members = {m for (t, m) in seen if t == topic}
        days = [c[0] // SLOTS_PER_DAY for (t, _m), c in seen.items() if t == topic]
        carried_n = tcount.get(topic, [0, 0, 0, set()])
        diffusion.append((topic, len(members), carried_n[0], len(created_on.get(topic, ())), min(days),
                          carried_n[2] if topic in tcount else max(days)))
    topic_diffusion = sorted(diffusion, key=lambda r: (-r[2], -r[1], r[0]))
    last_day = max([r[0] for r in daily_attention] + [r[0] for r in survival] + [r[0] for r in crosspost_flows], default=-1)
    return {"tables": {"daily_attention": daily_attention, "migration_flows": migration_flows,
                       "crosspost_flows": crosspost_flows, "cascades": cascades, "survival": survival,
                       "shares": shares, "share_depth": share_depth, "bridge_agents": bridge_agents,
                       "topics_carried": topics_carried, "human_crossposts": human_crossposts,
                       "human_activity": human_activity, "topics_created": topics_created,
                       "topic_first_seen": topic_first_seen, "topic_diffusion": topic_diffusion},
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


def build(folder: str, member_dbs: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
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
            computed = compute(src, member_dbs)
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


def ensure_derived(folder: str, member_dbs: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Build when the database is missing or older than the run; one comparison when it is current."""
    state = read_state(folder)
    if state["state"] in ("never", "stale") and os.path.isfile(source_path(folder)):
        build(folder, member_dbs)
        state = read_state(folder)
    return state


def table_rows(folder: str, table: str) -> Tuple[List[str], List[tuple]]:
    """Columns and rows of a derived table (whitelisted names only)."""
    if table not in EXPORT_TABLES:
        raise KeyError(table)
    columns = [c for c, _t, _m in FIELD_MAP[table][2]]
    with sqlite3.connect(f"file:{analytics_path(folder)}?mode=ro", uri=True) as conn:
        return columns, conn.execute(f"SELECT * FROM {table}").fetchall()


def cards(folder: str, member_dbs: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """What the analytics page shows, read from the derived database (``tables`` empty when there is none yet)."""
    state = ensure_derived(folder, member_dbs)
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
