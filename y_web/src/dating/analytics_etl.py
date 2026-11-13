"""Derived analytics database of a dating experiment (plan S7, IR-D-17).

``analytics_dating.db`` lives in the experiment folder, is owned by YWeb and holds tables shaped for analysis
(per round, day, agent, match and recommender). It is rebuilt from the run database, which is only ever opened
read-only; the runtime never reads it. The build is a full rebuild into a temporary file followed by an atomic
replace, so two builds of the same source give the same rows (``etl_state`` carries no clock; the time of the
build is in a status file beside it). Definitions of the recommender and lifecycle measures are those of the
runtime's own reports (``scripts/metrics_report.py`` and ``scripts/lifecycle_report.py`` of YDating); the tests
compare the two.

``FIELD_MAP`` is the single description of every derived table and column and the source they come from; the
document ``docs/dating-analytics-mapping.md`` is generated from it (``render_field_map``) and a test keeps them
equal.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ANALYTICS_FILE = "analytics_dating.db"
STATUS_FILE = "analytics_dating.status.json"
SOURCE_FILE = "database_server.db"
SCHEMA_VERSION = 1
LIKE = ("LIKE", "SUPERLIKE")

# table -> (description, source, [(column, type, meaning)])
FIELD_MAP: Dict[str, Tuple[str, str, List[Tuple[str, str, str]]]] = {
    "rounds": (
        "One row per round, numbered from 1.",
        "rounds",
        [
            ("ordinal", "INTEGER", "1-based global round: (day - 1) * slots + hour"),
            ("day", "INTEGER", "simulated day, from 1"),
            ("hour", "INTEGER", "slot of the day, from 1"),
        ],
    ),
    "agents": (
        "One row per account with its public attributes, outcome and latent variables (admin only).",
        "user_mgmt, dating_profile, dating_latent",
        [
            ("user_id", "TEXT", "user_mgmt.id"),
            ("username", "TEXT", "user_mgmt.username"),
            ("age", "INTEGER", "user_mgmt.age"),
            ("gender", "TEXT", "user_mgmt.gender"),
            ("city", "TEXT", "dating_profile.city"),
            ("intent", "TEXT", "dating_profile.intent"),
            ("status", "TEXT", "user_mgmt.status (active, paused, left)"),
            (
                "left_reason",
                "TEXT",
                "user_mgmt.left_reason (paired = success, churn = frustration, manual)",
            ),
            ("joined_ordinal", "INTEGER", "round of joining, as an ordinal"),
            (
                "left_ordinal",
                "INTEGER",
                "round of leaving, as an ordinal (NULL while present)",
            ),
            (
                "match_recsys",
                "TEXT",
                "recommender of this agent (empty: experiment default)",
            ),
            ("attractiveness", "REAL", "dating_latent.attractiveness"),
            ("selectivity", "REAL", "dating_latent.selectivity"),
            ("responsiveness", "REAL", "dating_latent.responsiveness"),
            (
                "desirability_rating",
                "REAL",
                "dating_latent.desirability_rating (Elo-style, at the end of the run)",
            ),
        ],
    ),
    "agent_stats": (
        "Activity and outcomes of each account over the whole run.",
        "match_recommendations, swipes, matches, messages, blocks, reports",
        [
            ("user_id", "TEXT", "agents.user_id"),
            ("cards_seen", "INTEGER", "recommendations served to the account"),
            (
                "times_shown",
                "INTEGER",
                "recommendations in which the account was the candidate",
            ),
            (
                "likes_given",
                "INTEGER",
                "swipes LIKE or SUPERLIKE by the account (not undone)",
            ),
            ("passes_given", "INTEGER", "swipes PASS by the account (not undone)"),
            (
                "likes_received",
                "INTEGER",
                "LIKE or SUPERLIKE swipes on the account (not undone)",
            ),
            ("passes_received", "INTEGER", "PASS swipes on the account (not undone)"),
            ("matches", "INTEGER", "matches the account is part of"),
            ("messages_sent", "INTEGER", "messages sent by the account"),
            ("messages_received", "INTEGER", "messages sent to the account"),
            ("blocks_received", "INTEGER", "blocks against the account"),
            ("reports_received", "INTEGER", "reports against the account"),
        ],
    ),
    "daily": (
        "Run totals per simulated day.",
        "match_recommendations, swipes, matches, messages, blocks, reports, date_proposals, user_mgmt",
        [
            ("day", "INTEGER", "simulated day"),
            (
                "stacks",
                "INTEGER",
                "(viewer, round) pairs that were served recommendations",
            ),
            ("cards_shown", "INTEGER", "recommendations served"),
            ("swipes", "INTEGER", "swipes not undone"),
            ("likes", "INTEGER", "LIKE or SUPERLIKE swipes"),
            ("matches", "INTEGER", "matches created"),
            ("messages", "INTEGER", "messages sent"),
            ("active_agents", "INTEGER", "accounts that swiped or wrote"),
            ("blocks", "INTEGER", "blocks"),
            ("reports", "INTEGER", "reports"),
            ("date_proposals", "INTEGER", "date proposals made"),
            ("exits", "INTEGER", "accounts that left"),
        ],
    ),
    "recommender_stats": (
        "Exposure and outcome measures per recommender model (day NULL: whole run).",
        "match_recommendations, swipes, matches, messages",
        [
            ("model", "TEXT", "match_recommendations.model"),
            ("day", "INTEGER", "simulated day; NULL for the whole run"),
            ("stacks", "INTEGER", "(viewer, round) pairs served"),
            ("cards_shown", "INTEGER", "recommendations served"),
            ("swipes", "INTEGER", "swipes not undone on those recommendations"),
            ("like_rate", "REAL", "likes per swipe"),
            (
                "gini_exposure",
                "REAL",
                "Gini coefficient of the exposures over the profiles shown",
            ),
            (
                "gini_likes_received",
                "REAL",
                "Gini coefficient of the likes received over all accounts",
            ),
            ("matches", "INTEGER", "matches whose pair was served by the model"),
            ("match_rate_per_stack", "REAL", "matches per stack served"),
            (
                "matches_with_message_share",
                "REAL",
                "share of those matches with at least one message",
            ),
        ],
    ),
    "match_stats": (
        "One row per match.",
        "matches, messages, date_proposals, match_recommendations",
        [
            ("match_id", "TEXT", "matches.id"),
            ("user_a", "TEXT", "matches.user_a"),
            ("user_b", "TEXT", "matches.user_b"),
            ("created_ordinal", "INTEGER", "round of the match, as an ordinal"),
            ("status", "TEXT", "matches.status"),
            ("ended_ordinal", "INTEGER", "round the match ended (NULL while active)"),
            ("first_message_by", "TEXT", "matches.first_message_by"),
            ("messages", "INTEGER", "messages in the match"),
            ("deleted_messages", "INTEGER", "messages deleted by their sender"),
            ("date_proposals", "INTEGER", "date proposals in the match"),
            ("model", "TEXT", "recommender that served the pair"),
        ],
    ),
    "funnel": (
        "Date proposals by status and by outcome.",
        "date_proposals",
        [
            ("kind", "TEXT", "status or outcome"),
            ("key", "TEXT", "value of date_proposals.status or date_proposals.outcome"),
            ("n", "INTEGER", "number of proposals"),
        ],
    ),
    "exits": (
        "Departures per day and cause (paired and churn are kept apart: success is not abandonment).",
        "user_mgmt",
        [
            ("day", "INTEGER", "simulated day of leaving"),
            ("reason", "TEXT", "user_mgmt.left_reason"),
            ("n", "INTEGER", "accounts"),
        ],
    ),
    "summary": (
        "Single-number measures of the run, the same as the runtime's lifecycle report.",
        "user_mgmt, matches, messages, date_proposals, profile_events",
        [
            ("key", "TEXT", "measure name"),
            ("value", "REAL", "value"),
        ],
    ),
    "etl_state": (
        "What the build was made from; carries no clock, so equal sources give equal databases.",
        "(derived)",
        [
            ("schema_version", "INTEGER", "version of this layout"),
            (
                "source_signature",
                "TEXT",
                "size and time of the source database and its write-ahead log",
            ),
            ("last_round", "INTEGER", "ordinal of the newest round"),
            ("day", "INTEGER", "day of the newest round"),
            ("hour", "INTEGER", "slot of the newest round"),
        ],
    ),
}
TABLE_ORDER = list(FIELD_MAP)
EXPORT_TABLES = [t for t in TABLE_ORDER if t != "etl_state"]

_locks: Dict[str, threading.Lock] = {}
_guard = threading.Lock()


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


def gini(values) -> float:
    """Gini coefficient of non-negative values (0 equal, 1 one holds everything); as in the runtime's report."""
    xs = sorted(v for v in values if v is not None)
    n, total = len(xs), sum(xs)
    if n == 0 or total == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * cum) / (n * total) - (n + 1) / n


def render_field_map() -> str:
    """The mapping document, generated so that it cannot drift from the tables."""
    out = [
        "# Dating analytics: derived tables and their sources",
        "",
        "Generated from `y_web/src/dating/analytics_etl.py` (`FIELD_MAP`); do not edit by hand.",
        "`analytics_dating.db` is rebuilt in full from `database_server.db` (opened read-only) and replaced atomically.",
        "",
    ]
    for table in TABLE_ORDER:
        desc, source, columns = FIELD_MAP[table]
        out += [
            f"## `{table}`",
            "",
            desc,
            "",
            f"Source: {source}",
            "",
            "| Column | Type | Meaning |",
            "| --- | --- | --- |",
        ]
        out += [f"| `{c}` | {t} | {m} |" for c, t, m in columns]
        out.append("")
    return "\n".join(out)


def _ddl() -> str:
    return "\n".join(
        "CREATE TABLE {} ({});".format(
            t, ", ".join(f"{c} {ty}" for c, ty, _ in FIELD_MAP[t][2])
        )
        for t in TABLE_ORDER
    )


def _q(conn: sqlite3.Connection, sql: str, args=()):
    return conn.execute(sql, args).fetchall()


def compute(src: sqlite3.Connection) -> Dict[str, List[tuple]]:
    """Every derived table as a list of rows (deterministic order)."""
    rounds = _q(src, "SELECT id, day, hour FROM rounds ORDER BY day, hour")
    ordinal = {rid: i for i, (rid, _d, _h) in enumerate(rounds, 1)}
    day_of = {rid: d for rid, d, _h in rounds}
    out: Dict[str, List[tuple]] = {}
    out["rounds"] = [(i, d, h) for i, (_r, d, h) in enumerate(rounds, 1)]

    users = _q(
        src,
        "SELECT u.id, u.username, u.age, u.gender, dp.city, dp.intent, u.status, u.left_reason, u.joined_on, "
        "u.left_on, u.match_recsys, dl.attractiveness, dl.selectivity, dl.responsiveness, dl.desirability_rating "
        "FROM user_mgmt u LEFT JOIN dating_profile dp ON dp.user_id = u.id "
        "LEFT JOIN dating_latent dl ON dl.user_id = u.id ORDER BY u.username, u.id",
    )
    out["agents"] = [
        (
            u[0],
            u[1],
            u[2],
            u[3],
            u[4],
            u[5],
            u[6],
            u[7],
            ordinal.get(u[8]),
            ordinal.get(u[9]),
            u[10],
            u[11],
            u[12],
            u[13],
            u[14],
        )
        for u in users
    ]
    user_ids = [r[0] for r in _q(src, "SELECT id FROM user_mgmt")]

    recs = _q(
        src,
        "SELECT id, viewer_id, candidate_id, model, round_id FROM match_recommendations",
    )
    swipes = _q(
        src,
        "SELECT rec_id, swiper_id, target_id, decision, round_id FROM swipes WHERE undone = 0",
    )
    matches = _q(
        src,
        "SELECT id, user_a, user_b, created_round, status, ended_round, first_message_by FROM matches ORDER BY id",
    )
    msgs = _q(src, "SELECT match_id, sender_id, deleted, round_id FROM messages")
    blocks = _q(src, "SELECT to_id, round_id FROM blocks")
    reports = _q(src, "SELECT to_id, round_id FROM reports")
    dates = _q(src, "SELECT match_id, status, outcome, round_id FROM date_proposals")
    model_of_rec = {r[0]: r[3] for r in recs}
    pair_model: Dict[Tuple[str, str], str] = {}
    for _id, viewer, cand, model, _r in recs:
        pair_model[(viewer, cand)] = model
    match_users = {m[0]: (m[1], m[2]) for m in matches}

    # per agent
    st = {u: Counter() for u in user_ids}
    for _id, viewer, cand, _m, _r in recs:
        st.setdefault(viewer, Counter())["cards_seen"] += 1
        st.setdefault(cand, Counter())["times_shown"] += 1
    for _rid, swiper, target, decision, _r in swipes:
        if decision in LIKE:
            st.setdefault(swiper, Counter())["likes_given"] += 1
            st.setdefault(target, Counter())["likes_received"] += 1
        else:
            st.setdefault(swiper, Counter())["passes_given"] += 1
            st.setdefault(target, Counter())["passes_received"] += 1
    for _id, a, b, *_ in matches:
        st.setdefault(a, Counter())["matches"] += 1
        st.setdefault(b, Counter())["matches"] += 1
    per_match = defaultdict(Counter)
    for match_id, sender, deleted, _r in msgs:
        st.setdefault(sender, Counter())["messages_sent"] += 1
        per_match[match_id]["messages"] += 1
        per_match[match_id]["deleted"] += 1 if deleted else 0
        a, b = match_users.get(match_id, (None, None))
        other = b if sender == a else a
        if other:
            st.setdefault(other, Counter())["messages_received"] += 1
    for to_id, _r in blocks:
        st.setdefault(to_id, Counter())["blocks_received"] += 1
    for to_id, _r in reports:
        st.setdefault(to_id, Counter())["reports_received"] += 1
    keys = (
        "cards_seen",
        "times_shown",
        "likes_given",
        "passes_given",
        "likes_received",
        "passes_received",
        "matches",
        "messages_sent",
        "messages_received",
        "blocks_received",
        "reports_received",
    )
    out["agent_stats"] = [
        (u[0],) + tuple(st.get(u[0], Counter())[k] for k in keys) for u in users
    ]

    # per match
    dates_by_match = Counter(d[0] for d in dates)
    ms = []
    for mid, a, b, created, status, ended, first in matches:
        model = pair_model.get((a, b)) or pair_model.get((b, a))
        ms.append(
            (
                mid,
                a,
                b,
                ordinal.get(created),
                status,
                ordinal.get(ended),
                first,
                per_match[mid]["messages"],
                per_match[mid]["deleted"],
                dates_by_match[mid],
                model,
            )
        )
    out["match_stats"] = ms

    # per day
    days = sorted({d for _r, d, _h in rounds})
    stacks_day = defaultdict(set)
    shown_day = Counter()
    for _id, viewer, _c, _m, rnd in recs:
        stacks_day[day_of.get(rnd)].add((viewer, rnd))
        shown_day[day_of.get(rnd)] += 1
    sw_day, lk_day = Counter(), Counter()
    active = defaultdict(set)
    for _rid, swiper, _t, decision, rnd in swipes:
        d = day_of.get(rnd)
        sw_day[d] += 1
        lk_day[d] += 1 if decision in LIKE else 0
        active[d].add(swiper)
    match_day = Counter(day_of.get(m[3]) for m in matches)
    msg_day = Counter()
    for _mid, sender, _del, rnd in msgs:
        msg_day[day_of.get(rnd)] += 1
        active[day_of.get(rnd)].add(sender)
    block_day = Counter(day_of.get(r) for _t, r in blocks)
    report_day = Counter(day_of.get(r) for _t, r in reports)
    date_day = Counter(day_of.get(d[3]) for d in dates)
    exits = Counter()
    for reason, left_on in _q(
        src, "SELECT left_reason, left_on FROM user_mgmt WHERE status = 'left'"
    ):
        exits[(day_of.get(left_on, -1), reason)] += 1
    exit_day = Counter()
    for (d, _reason), n in exits.items():
        exit_day[d] += n
    out["daily"] = [
        (
            d,
            len(stacks_day[d]),
            shown_day[d],
            sw_day[d],
            lk_day[d],
            match_day[d],
            msg_day[d],
            len(active[d]),
            block_day[d],
            report_day[d],
            date_day[d],
            exit_day[d],
        )
        for d in days
    ]

    # recommender measures (same definitions as the runtime's metrics_report)
    msg_matches = {m[0] for m in msgs}
    rows = []
    for per_day in (False, True):
        key = (
            (lambda model, rnd: (model, day_of.get(rnd)))
            if per_day
            else (lambda model, rnd: (model, None))
        )
        exposure = defaultdict(Counter)
        stacks = defaultdict(set)
        for _id, viewer, cand, model, rnd in recs:
            k = key(model, rnd)
            exposure[k][cand] += 1
            stacks[k].add((viewer, rnd))
        likes = defaultdict(Counter)
        counts = defaultdict(lambda: {"swipes": 0, "likes": 0})
        for rec_id, _s, target, decision, rnd in swipes:
            model = model_of_rec.get(rec_id)
            if model is None:
                continue
            k = key(model, rnd)
            counts[k]["swipes"] += 1
            if decision in LIKE:
                counts[k]["likes"] += 1
                likes[k][target] += 1
        mc = defaultdict(lambda: {"matches": 0, "with_message": 0})
        for mid, a, b, created, *_ in matches:
            model = pair_model.get((a, b)) or pair_model.get((b, a))
            if model is None:
                continue
            k = key(model, created)
            mc[k]["matches"] += 1
            mc[k]["with_message"] += 1 if mid in msg_matches else 0
        for k in sorted(
            exposure, key=lambda x: (x[0], x[1] if x[1] is not None else -1)
        ):
            shown = sum(exposure[k].values())
            n_stacks = len(stacks[k])
            sw, lk = counts[k]["swipes"], counts[k]["likes"]
            m = mc[k]
            rows.append(
                (
                    k[0],
                    k[1],
                    n_stacks,
                    shown,
                    sw,
                    round(lk / sw, 4) if sw else 0.0,
                    round(gini(list(exposure[k].values())), 4),
                    round(gini([likes[k].get(u, 0) for u in user_ids]), 4),
                    m["matches"],
                    round(m["matches"] / n_stacks, 4) if n_stacks else 0.0,
                    round(m["with_message"] / m["matches"], 4) if m["matches"] else 0.0,
                )
            )
    out["recommender_stats"] = rows

    # lifecycle (same as the runtime's lifecycle_report)
    status = Counter(d[1] for d in dates)
    outcome = Counter(d[2] for d in dates if d[2] is not None)
    out["funnel"] = [("status", k, n) for k, n in sorted(status.items())] + [
        ("outcome", k, n) for k, n in sorted(outcome.items())
    ]
    out["exits"] = [
        (d, reason, n)
        for (d, reason), n in sorted(
            exits.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))
        )
    ]
    n_agents = len(user_ids)
    n_matches = len(matches)
    proposals = sum(status.values())
    one = lambda q: _q(src, q)[0][0]  # noqa: E731
    summary = {
        "agents": n_agents,
        "matches": n_matches,
        "matches_with_messages": len(msg_matches),
        "date_proposals": proposals,
        "accept_rate": status.get("accepted", 0) / proposals if proposals else 0.0,
        "share_of_matches_with_a_date": (
            len({d[0] for d in dates}) / n_matches if n_matches else 0.0
        ),
        "exits_paired": sum(n for (_d, r), n in exits.items() if r == "paired"),
        "exits_churn": sum(n for (_d, r), n in exits.items() if r == "churn"),
        "paused_now": one("SELECT COUNT(*) FROM user_mgmt WHERE status = 'paused'"),
        "profile_changes": one("SELECT COUNT(*) FROM profile_events"),
    }
    out["summary"] = sorted(summary.items())
    return out


def _write(path: str, tables: Dict[str, List[tuple]], state: tuple) -> None:
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_ddl())
        for table, rows in tables.items():
            if rows:
                marks = ",".join("?" * len(FIELD_MAP[table][2]))
                conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
        conn.execute("INSERT INTO etl_state VALUES (?,?,?,?,?)", state)
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
    """Rebuild ``analytics_dating.db``; returns ``{"ok", "rounds", "message"}``. A failure keeps the previous file."""
    src_file = source_path(folder)
    if not os.path.isfile(src_file):
        return {"ok": False, "message": "the run database does not exist yet"}
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
            tables = compute(src)
        finally:
            src.close()
        last = len(tables["rounds"])
        day, hour = (
            (tables["rounds"][-1][1], tables["rounds"][-1][2]) if last else (0, 0)
        )
        _write(tmp, tables, (SCHEMA_VERSION, signature, last, day, hour))
        os.replace(tmp, analytics_path(folder))
        _write_status(
            folder,
            state="fresh",
            built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            seconds=round(time.time() - started, 2),
        )
        return {"ok": True, "rounds": last, "message": ""}
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
    out: Dict[str, Any] = {
        "state": "never",
        "day": None,
        "hour": None,
        "message": "",
        "built_at": None,
    }
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
                row = conn.execute(
                    "SELECT schema_version, source_signature, last_round, day, hour FROM etl_state"
                ).fetchone()
        except sqlite3.Error:
            row = None
        if row:
            out.update(last_round=row[2], day=row[3], hour=row[4])
            if out["state"] != "running":
                current = source_signature(source_path(folder))
                out["state"] = (
                    "fresh"
                    if (row[0] == SCHEMA_VERSION and row[1] == current)
                    else "stale"
                )
    if recorded.get("state") == "failed" and out["state"] not in ("running",):
        out["state"] = "failed"
        out["message"] = recorded.get("message", "")
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
    """What the dashboard shows, read from the derived database."""
    state = ensure_derived(folder)
    out: Dict[str, Any] = {"state": state}
    if not os.path.isfile(analytics_path(folder)):
        return out
    out["summary"] = dict(table_rows(folder, "summary")[1])
    out["daily"] = [
        dict(zip(*(table_rows(folder, "daily")[0], r)))
        for r in table_rows(folder, "daily")[1]
    ]
    cols, rows = table_rows(folder, "recommender_stats")
    out["recommenders"] = [dict(zip(cols, r)) for r in rows if r[1] is None]
    out["recommenders_per_day"] = [dict(zip(cols, r)) for r in rows if r[1] is not None]
    out["funnel"] = [
        dict(zip(("kind", "key", "n"), r)) for r in table_rows(folder, "funnel")[1]
    ]
    out["exits"] = [
        dict(zip(("day", "reason", "n"), r)) for r in table_rows(folder, "exits")[1]
    ]
    return out
