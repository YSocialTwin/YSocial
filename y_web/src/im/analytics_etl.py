"""Derived analytics database of an instant messaging experiment (plan 4.7).

``analytics_im.db`` lives in the experiment folder, is owned by YWeb and has the shape of a YSocial experiment
database (tables are created from YSocial's own models, so every column an analytics page selects exists). It is
rebuilt from IM's database, which is only ever opened read-only (``engine.open_reader``); IM never reads it.

Table-level mapping (frozen in Phase 9, see ``docs/im-analytics-mapping.md``):

========================  =====================================================  ==============================
derived table             built from (IM)                                        present when
========================  =====================================================  ==============================
rounds                    rounds (``hour`` = slot, copied as is)                 always
user_mgmt                 accounts (+ persona fields)                            always
post                      messages (reply -> comment, forward -> share)          always
reactions                 reactions (positive emoji -> like, negative -> dislike)  rows exist
mentions                  mentions                                               rows exist
interests/post_topics     topics, message_topics                                 rows exist
hashtags/post_hashtags    hashtags, message_hashtags                             rows exist
post_toxicity             annotations of ``toxicity_*`` methods, status ok       rows exist
post_sentiment            annotations of ``sentiment_*`` methods, status ok      rows exist
post_emotions/emotions    annotations of ``emotion*`` methods, status ok         rows exist
agent_opinion             agent_opinions                                         rows exist
stress_reward             stress_reward (same columns)                           rows exist
follow                     chat_members (member follows the chat's owner)         rows exist
(no table)                recommendations                                        IM has no such data: the page
                                                                                 keeps its normal unavailable state
========================  =====================================================  ==============================

The build is a full rebuild into a temporary file followed by an atomic replace; ``etl_state`` holds the watermark
(source signature, last round, schema versions) so that opening a page with an unchanged source costs one comparison.
Running twice gives identical rows; there is no incremental path whose result could differ from a full rebuild.
"""

import hashlib
import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

ANALYTICS_FILE = "analytics_im.db"
STATUS_FILE = "analytics_im.status.json"
ANALYTICS_SCHEMA_VERSION = 2

NEGATIVE_EMOJI = {"👎", "💩", "🤮", "🤬", "😢", "😡", "😠"}

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def analytics_path(exp_folder: str) -> str:
    return os.path.join(exp_folder, ANALYTICS_FILE)


def _status_path(exp_folder: str) -> str:
    return os.path.join(exp_folder, STATUS_FILE)


def _lock_for(exp_folder: str) -> threading.Lock:
    key = os.path.abspath(exp_folder)
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def source_signature(source_path: str) -> str:
    """Changes whenever the source database does (file and non-empty write-ahead log)."""
    parts = []
    for suffix in ("", "-wal"):
        path = source_path + suffix
        try:
            st = os.stat(path)
        except OSError:
            continue
        if suffix and st.st_size == 0:
            continue
        parts.append(f"{suffix}:{st.st_size}:{st.st_mtime_ns}")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def _write_status(exp_folder: str, **values: Any) -> None:
    try:
        tmp = _status_path(exp_folder) + ".part"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(values, handle)
        os.replace(tmp, _status_path(exp_folder))
    except OSError:
        pass


def read_state(exp_folder: str) -> Dict[str, Any]:
    """What the admin shows: ``state`` (never | running | fresh | stale | failed), the data horizon and a message."""
    path = analytics_path(exp_folder)
    out: Dict[str, Any] = {"state": "never", "day": None, "slot": None, "message": ""}
    lock = _lock_for(exp_folder)
    if lock.locked():
        out["state"] = "running"
    try:
        with open(_status_path(exp_folder), encoding="utf-8") as handle:
            recorded = json.load(handle)
    except (OSError, ValueError):
        recorded = {}
    if os.path.isfile(path):
        import sqlite3

        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "SELECT last_round, day, slot, built_at FROM etl_state ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
            if row:
                out.update(day=row[1], slot=row[2], built_at=row[3], last_round=row[0])
                if out["state"] != "running":
                    out["state"] = "fresh"
        except sqlite3.Error:
            pass
    if recorded.get("state") == "failed" and out["state"] != "running":
        out["state"] = "failed"
        out["message"] = recorded.get("message", "")
    return out


def _persona(raw) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(value, fallback="") -> str:
    return fallback if value is None else str(value)


def _int(value, fallback=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _build(source_path: str, target_path: str) -> Dict[str, int]:
    """Fill a new derived database; returns the row counts per table."""
    from sqlalchemy import create_engine, insert

    from y_web.src import models as M
    from y_web.src.im.engine import open_reader, check_schema  # noqa: F401  (check_schema used by open_reader)

    engine = create_engine(f"sqlite:///{target_path}")
    counts: Dict[str, int] = {}

    def put(model, rows):
        rows = list(rows)
        if not rows:
            return
        model.__table__.create(bind=engine, checkfirst=True)
        with engine.begin() as conn:
            for start in range(0, len(rows), 2000):
                conn.execute(insert(model.__table__), rows[start : start + 2000])
        counts[model.__table__.name] = counts.get(model.__table__.name, 0) + len(rows)

    with open_reader(source_path) as session:
        raw = session.connection().exec_driver_sql

        def q(sql, *args):
            return raw(sql, args).fetchall()

        # --- rounds -------------------------------------------------------------------------
        rounds = q("SELECT id, day, slot FROM rounds ORDER BY id")
        put(M.Rounds, ({"id": r[0], "day": r[1], "hour": r[2]} for r in rounds))
        round_ids = {r[0] for r in rounds}
        last = max(rounds, key=lambda r: r[0]) if rounds else (0, 0, 0)

        # --- accounts -> user_mgmt ----------------------------------------------------------
        accounts = q(
            "SELECT id, kind, username, language, persona, archetype, activity_profile FROM accounts ORDER BY id"
        )
        uid = {}
        first_round = {
            a: r
            for a, r in q("SELECT sender_account_id, MIN(round_id) FROM messages GROUP BY sender_account_id")
        }
        users = []
        for index, (acc_id, kind, username, language, persona, archetype, activity) in enumerate(accounts, 1):
            uid[acc_id] = index
            p = _persona(persona)
            big5 = p.get("big_five") if isinstance(p.get("big_five"), dict) else {}
            users.append(
                {
                    "id": index,
                    "username": _text(username, acc_id),
                    "email": "",
                    "password": "",
                    "leaning": _text(p.get("leaning"), "neutral")[:10] or "neutral",
                    "user_type": "human" if kind == "human" else "user",
                    "age": _int(p.get("age")),
                    "oe": _text(big5.get("oe") or big5.get("openness")),
                    "co": _text(big5.get("co") or big5.get("conscientiousness")),
                    "ex": _text(big5.get("ex") or big5.get("extraversion")),
                    "ag": _text(big5.get("ag") or big5.get("agreeableness")),
                    "ne": _text(big5.get("ne") or big5.get("neuroticism")),
                    "language": _text(language, "en"),
                    "education_level": p.get("education_level"),
                    "joined_on": _int(first_round.get(acc_id), 0),
                    "gender": p.get("gender"),
                    "nationality": p.get("nationality"),
                    "toxicity": _text(p.get("toxicity"), "no"),
                    "is_page": 1 if kind == "page" else 0,
                    "profession": _text(p.get("profession")),
                    "activity_profile": _text(activity, "Always On"),
                    "archetype": archetype,
                    "cover_image": "",
                }
            )
        put(M.User_mgmt, users)

        # --- messages -> post ---------------------------------------------------------------
        messages = q(
            "SELECT id, text, round_id, sender_account_id, reply_to_message_id, thread_root_id, "
            "fwd_origin_message_id, fwd_from_message_id, client_action_id "
            "FROM messages ORDER BY round_id, sim_ts, id"
        )
        pid = {}
        kept = []
        for row in messages:
            if row[3] in uid:
                pid[row[0]] = len(kept) + 1
                kept.append(row)
        reaction_counts = dict(q("SELECT message_id, COUNT(*) FROM reactions GROUP BY message_id"))
        posts = []
        for row in kept:
            mid, text, rnd, sender, reply_to, root, fwd_origin, fwd_from, action_id = row
            me = pid[mid]
            posts.append(
                {
                    "id": me,
                    "tweet": _text(text),
                    "round": rnd,
                    "user_id": uid[sender],
                    "comment_to": pid.get(reply_to, -1) if reply_to else -1,
                    "thread_id": pid.get(root, me) if root else me,
                    "client_action_id": action_id,
                    "shared_from": pid.get(fwd_origin or fwd_from, -1) if (fwd_origin or fwd_from) else -1,
                    "reaction_count": reaction_counts.get(mid, 0),
                    "created_at": datetime(2000, 1, 1),
                }
            )
        put(M.Post, posts)

        # --- reactions ----------------------------------------------------------------------
        put(
            M.Reactions,
            (
                {
                    "round": rnd,
                    "user_id": uid[acc],
                    "post_id": pid[mid],
                    "type": "dislike" if emoji in NEGATIVE_EMOJI else "like",
                }
                for acc, mid, emoji, rnd in q(
                    "SELECT account_id, message_id, emoji, round_id FROM reactions ORDER BY round_id, message_id, account_id, emoji"
                )
                if acc in uid and mid in pid
            ),
        )

        # --- follow: chat membership as "member follows the chat's owner" -------------------
        round_ids = [r[0] for r in rounds]
        first_round = round_ids[0] if round_ids else 0
        round_set = set(round_ids)
        pairs: Dict[Any, Dict[str, Any]] = {}
        for owner, member, joined, left in q(
            "SELECT c.owner_account_id, m.account_id, m.joined_round, m.left_round FROM chat_members m "
            "JOIN chats c ON c.id = m.chat_id WHERE c.owner_account_id IS NOT NULL "
            "AND m.account_id != c.owner_account_id ORDER BY m.id"
        ):
            if owner not in uid or member not in uid:
                continue
            rec = pairs.setdefault((owner, member), {"joined": None, "left": [], "open": False})
            joined = joined if joined in round_set else first_round
            rec["joined"] = joined if rec["joined"] is None else min(rec["joined"], joined)
            if left is None:
                rec["open"] = True
            else:
                rec["left"].append(left if left in round_set else joined)
        follow_rows = []
        for (owner, member), rec in sorted(pairs.items(), key=lambda kv: (kv[1]["joined"], kv[0])):
            base = {"user_id": uid[owner], "follower_id": uid[member]}
            follow_rows.append({**base, "round": rec["joined"], "action": "follow"})
            if not rec["open"] and rec["left"]:
                follow_rows.append({**base, "round": max(rec["left"]), "action": "unfollow"})
        if round_ids:
            put(M.Follow, follow_rows)

        # --- mentions -----------------------------------------------------------------------
        mention_rounds = dict(q("SELECT id, round_id FROM messages"))
        put(
            M.Mentions,
            (
                {"user_id": uid[acc], "post_id": pid[mid], "round": mention_rounds.get(mid, 0), "answered": 0}
                for mid, acc in q("SELECT message_id, mentioned_account_id FROM mentions ORDER BY id")
                if acc in uid and mid in pid
            ),
        )

        # --- topics, hashtags ---------------------------------------------------------------
        topics = q("SELECT id, label FROM topics ORDER BY id")
        tid = {t[0]: i for i, t in enumerate(topics, 1)}
        links = [
            (mid, topic)
            for mid, topic in q("SELECT message_id, topic_id FROM message_topics ORDER BY id")
            if mid in pid and topic in tid
        ]
        used_topics = {t for _m, t in links}
        opinion_rows = q("SELECT account_id, topic_id, value, round_id, cause_message_id FROM agent_opinions ORDER BY id")
        used_topics |= {r[1] for r in opinion_rows if r[1] in tid}
        if used_topics:
            put(
                M.Interests,
                ({"iid": tid[t[0]], "interest": _text(t[1])[:20]} for t in topics if t[0] in used_topics),
            )
        put(M.Post_topics, ({"post_id": pid[mid], "topic_id": tid[t]} for mid, t in links))
        hashtags = q("SELECT id, hashtag FROM hashtags ORDER BY id")
        hid = {h[0]: i for i, h in enumerate(hashtags, 1)}
        hlinks = [
            (mid, h)
            for mid, h in q("SELECT message_id, hashtag_id FROM message_hashtags ORDER BY message_id, hashtag_id")
            if mid in pid and h in hid
        ]
        if hlinks:
            put(
                M.Hashtags,
                ({"id": hid[h[0]], "hashtag": _text(h[1])[:20]} for h in hashtags if h[0] in {x for _m, x in hlinks}),
            )
        put(M.Post_hashtags, ({"post_id": pid[mid], "hashtag_id": hid[h]} for mid, h in hlinks))

        # --- annotations ----------------------------------------------------------------------
        def annotation_rows(prefix):
            return q(
                "SELECT a.message_id, a.value FROM annotations a "
                "WHERE a.status = 'ok' AND a.method_ref LIKE ? ORDER BY a.method_ref, a.message_id",
                prefix + "%",
            )

        post_info = {p["id"]: p for p in posts}
        seen = set()
        tox = []
        for mid, value in annotation_rows("toxicity"):
            if mid in pid and pid[mid] not in seen:  # the first method (by name) wins when several ran
                seen.add(pid[mid])
                v = _persona(value)
                tox.append({"post_id": pid[mid], **{k: float(v.get(k, 0) or 0) for k in (
                    "toxicity", "severe_toxicity", "identity_attack", "insult", "profanity", "threat",
                    "sexually_explicit", "flirtation")}})
        put(M.Post_Toxicity, tox)
        seen = set()
        sent = []
        post_topic = {}
        for mid, topic in links:
            post_topic.setdefault(pid[mid], tid[topic])
        for mid, value in annotation_rows("sentiment"):
            if mid in pid and pid[mid] not in seen:
                seen.add(pid[mid])
                v = _persona(value)
                post = post_info[pid[mid]]
                sent.append(
                    {
                        "post_id": pid[mid],
                        "user_id": post["user_id"],
                        "round": post["round"],
                        "topic_id": post_topic.get(pid[mid], 0),
                        "is_post": 0 if post["comment_to"] != -1 else 1,
                        "is_comment": 1 if post["comment_to"] != -1 else 0,
                        "is_reaction": 0,
                        "neg": float(v.get("neg", 0) or 0),
                        "neu": float(v.get("neu", 0) or 0),
                        "pos": float(v.get("pos", 0) or 0),
                        "compound": float(v.get("compound", 0) or 0),
                    }
                )
        put(M.Post_Sentiment, sent)

        # emotions: one label per row (``{"emotions": ["approval", ...]}``), the first method by name wins per post
        seen = set()
        emotion_ids: Dict[str, int] = {}
        emotion_links = []
        for mid, value in annotation_rows("emotion"):
            if mid not in pid or pid[mid] in seen:
                continue
            seen.add(pid[mid])
            labels = _persona(value).get("emotions")
            for label in dict.fromkeys(_text(x)[:20] for x in (labels if isinstance(labels, list) else []) if _text(x)):
                emotion_ids.setdefault(label, len(emotion_ids) + 1)
                emotion_links.append({"post_id": pid[mid], "emotion_id": emotion_ids[label]})
        put(M.Emotions, ({"id": i, "emotion": label, "icon": ""} for label, i in emotion_ids.items()))
        put(M.Post_emotions, emotion_links)

        # --- opinions, stress/reward ----------------------------------------------------------
        first_round = min(round_ids) if round_ids else 0

        def opinion_round(rnd):
            """The initial opinions (set at creation, before round 1) are placed in the first round."""
            return rnd if rnd in round_ids else (first_round if rnd is not None and rnd < first_round else None)

        put(
            M.Agent_Opinion,
            (
                {
                    "agent_id": uid[acc],
                    "tid": opinion_round(rnd),
                    "topic_id": tid[topic],
                    "id_interacted_with": -1,
                    "id_post": pid.get(cause, -1) if cause else -1,
                    "opinion": float(value),
                }
                for acc, topic, value, rnd, cause in opinion_rows
                if acc in uid and topic in tid and opinion_round(rnd) is not None
            ),
        )
        put(
            M.StressReward,
            (
                {
                    "id": sid,
                    "uid": uid[u],
                    "variable": var,
                    "value": float(value),
                    "type": typ,
                    "action": action,
                    "tid": t,
                }
                for sid, u, var, value, typ, action, t in q(
                    "SELECT id, uid, variable, value, type, action, tid FROM stress_reward ORDER BY tid, uid, variable, type, id"
                )
                if u in uid and t in round_ids
            ),
        )
        version = q("SELECT MAX(version) FROM schema_version")
        source_version = version[0][0] if version and version[0][0] is not None else 0

    # --- watermark -----------------------------------------------------------------------------
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE etl_state (last_message_id TEXT, last_round INTEGER, day INTEGER, slot INTEGER, "
            "source_signature TEXT, source_schema_version INTEGER, analytics_schema_version INTEGER, built_at TEXT)"
        )
        conn.exec_driver_sql(
            "INSERT INTO etl_state VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                kept[-1][0] if kept else None,
                last[0],
                last[1],
                last[2],
                source_signature(source_path),
                source_version,
                ANALYTICS_SCHEMA_VERSION,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
    engine.dispose()
    return counts


def is_fresh(exp_folder: str, source_path: str) -> bool:
    import sqlite3

    path = analytics_path(exp_folder)
    if not os.path.isfile(path):
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT source_signature, analytics_schema_version FROM etl_state ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row) and row[0] == source_signature(source_path) and row[1] == ANALYTICS_SCHEMA_VERSION


def refresh(exp_folder: str, source_path: str, force: bool = False) -> Dict[str, Any]:
    """Bring ``analytics_im.db`` up to date with the source; single-flight per experiment folder.

    Never raises: a failure is recorded (``read_state`` reports it) and the previous derived file, if any, stays.
    """
    lock = _lock_for(exp_folder)
    if not lock.acquire(blocking=False):
        return {"state": "running"}
    try:
        if not force and is_fresh(exp_folder, source_path):
            return {"state": "fresh", "rebuilt": False}
        if not os.path.isfile(source_path):
            return {"state": "never", "rebuilt": False}
        started = time.time()
        target = analytics_path(exp_folder)
        temp = target + ".part"
        for leftover in (temp, temp + "-journal"):
            if os.path.exists(leftover):
                os.remove(leftover)
        try:
            counts = _build(source_path, temp)
            os.replace(temp, target)
        except Exception as exc:  # a message for the admin, not a stack trace; the old file stays
            if os.path.exists(temp):
                os.remove(temp)
            _write_status(exp_folder, state="failed", message=str(exc) or exc.__class__.__name__)
            return {"state": "failed", "message": str(exc) or exc.__class__.__name__, "rebuilt": False}
        _write_status(exp_folder, state="ok")
        return {"state": "fresh", "rebuilt": True, "counts": counts, "seconds": round(time.time() - started, 3)}
    finally:
        lock.release()
