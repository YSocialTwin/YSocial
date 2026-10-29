"""Read-only reader of a dating run database for the observer frontend (plan, 6.1-6.4).

The database is opened with ``mode=ro`` and ``PRAGMA query_only``; nothing here writes. Every method returns plain
dictionaries built from an explicit list of columns, so a column that is not named never reaches a template or a JSON
answer. That is the guarantee behind IR-D-16: only the ``overview`` viewpoint (researchers and admins) can see the
reserved fields (latent traits, recommendation score/model/reason, deleted text, blocks, reports, stress).

Viewpoints
    overview  everything the run recorded
    account   exactly what that account could see in the app: its deck, its swipes, its matches and chats
    public    the showcase of public profiles; no swipes, matches or chats

Time travel: ``round`` is the 1-based ordinal of the round (``(day - 1) * slots + hour``); every query keeps only
rows whose round is not later than it. Profile text is rebuilt from ``profile_events`` (the ``old`` values of the
events that happen after the round are applied back).
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from y_web.src.dating import DATING_MARKER_TABLE

OVERVIEW = "overview"
ACCOUNT = "account"
PUBLIC = "public"
KINDS = (OVERVIEW, ACCOUNT, PUBLIC)

DEFAULT_SLOTS = 24
# fields of profile_events that are part of the public profile
PROFILE_FIELDS = ("bio", "prompt_answers", "city", "intent")


class DatingReadError(Exception):
    """The database is missing, is not a dating database, or cannot be read."""


class ViewpointError(ValueError):
    """The viewpoint asks for something that does not exist or is not allowed (an unknown kind, no account)."""


class Viewpoint:
    def __init__(self, kind: str, account_id: Optional[str], round_ordinal: int):
        if kind not in KINDS:
            raise ViewpointError(f"unknown viewpoint {kind!r}")
        if kind == ACCOUNT and not account_id:
            raise ViewpointError("the account viewpoint needs an account")
        self.kind = kind
        self.account_id = account_id if kind == ACCOUNT else None
        self.round = int(round_ordinal or 0)


def avatar_hue(key: str) -> int:
    """Deterministic hue (0-359) of a placeholder avatar."""
    digest = hashlib.sha1(str(key).encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % 360


def initials(name: str) -> str:
    parts = [
        p for p in str(name or "?").replace("_", " ").replace("-", " ").split() if p
    ]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


@contextmanager
def open_reader(path: str) -> Iterator["DatingReader"]:
    """Open ``path`` read-only; raises :class:`DatingReadError` when it cannot serve the observer."""
    import os

    if not os.path.isfile(path):
        raise DatingReadError("The database of this experiment does not exist yet.")
    try:
        uri = "file:{}?mode=ro".format(path.replace("?", "%3f").replace("#", "%23"))
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        has = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (DATING_MARKER_TABLE,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise DatingReadError(f"The database cannot be read: {exc}") from exc
    if not has:
        conn.close()
        raise DatingReadError("This database is not a dating database.")
    try:
        yield DatingReader(conn)
    except sqlite3.Error as exc:
        raise DatingReadError(f"The database cannot be read: {exc}") from exc
    finally:
        conn.close()


def _loads(text, default):
    try:
        value = json.loads(text) if isinstance(text, str) and text else default
    except ValueError:
        return default
    return value if isinstance(value, type(default)) else default


class DatingReader:
    def __init__(self, conn: sqlite3.Connection, slots_per_day: int = DEFAULT_SLOTS):
        self.c = conn
        self.slots = slots_per_day
        self._rounds: Optional[List[sqlite3.Row]] = None

    # ------------------------------------------------------------------ rounds
    def rounds(self) -> List[sqlite3.Row]:
        if self._rounds is None:
            self._rounds = self.c.execute(
                "SELECT id, day, hour FROM rounds ORDER BY day, hour"
            ).fetchall()
        return self._rounds

    def latest_round(self) -> int:
        return len(self.rounds())

    def _cut(self, ordinal: int) -> int:
        """Sortable key ``day * 10000 + hour`` of the round with that ordinal (0 when there is none)."""
        rounds = self.rounds()
        if not rounds or ordinal < 1:
            return 0
        row = rounds[min(ordinal, len(rounds)) - 1]
        return row["day"] * 10000 + row["hour"]

    def day_hour(self, ordinal: int):
        rounds = self.rounds()
        if not rounds or ordinal < 1:
            return (0, 0)
        row = rounds[min(ordinal, len(rounds)) - 1]
        return (row["day"], row["hour"])

    def status(self) -> Dict[str, Any]:
        latest = self.latest_round()
        day, hour = self.day_hour(latest)
        return {"latest_round": latest, "day": day, "hour": hour}

    # SQL fragment: rows of table alias ``t`` whose round_id is not later than the cut
    _UPTO = (
        "JOIN rounds rr ON rr.id = {a}.round_id AND rr.day * 10000 + rr.hour <= :cut"
    )

    def _upto(self, alias: str) -> str:
        return self._UPTO.format(a=alias)

    # ------------------------------------------------------------------ accounts
    def _active_ids(self, cut: int) -> Dict[str, sqlite3.Row]:
        rows = self.c.execute(
            "SELECT u.id, u.username, u.age, u.gender, u.status, u.joined_on, u.left_on, "
            "dp.city, dp.intent, dp.bio, dp.prompt_answers, dp.photo_count "
            "FROM user_mgmt u JOIN dating_profile dp ON dp.user_id = u.id "
            "LEFT JOIN rounds j ON j.id = u.joined_on "
            "LEFT JOIN rounds l ON l.id = u.left_on "
            "WHERE (j.id IS NULL OR j.day * 10000 + j.hour <= :cut) "
            "AND (l.id IS NULL OR l.day * 10000 + l.hour > :cut) "
            "AND u.is_page = 0 ORDER BY u.username",
            {"cut": cut},
        ).fetchall()
        return {r["id"]: r for r in rows}

    def has_account(self, user_id: str) -> bool:
        """The account exists in the run (a person who has not entered yet has none)."""
        return (
            self.c.execute(
                "SELECT 1 FROM user_mgmt WHERE id = ?", (user_id,)
            ).fetchone()
            is not None
        )

    def vocabulary(self) -> Dict[str, List[str]]:
        """Genders and interests present in the run: suggestions for the entry form of a person."""
        genders = [
            r[0]
            for r in self.c.execute(
                "SELECT DISTINCT gender FROM user_mgmt WHERE gender IS NOT NULL AND gender != '' ORDER BY gender"
            )
        ]
        interests = [
            r[0]
            for r in self.c.execute(
                "SELECT interest FROM interests ORDER BY interest LIMIT 200"
            )
        ]
        return {"genders": genders, "interests": interests}

    def accounts(self, ordinal: int) -> List[Dict[str, Any]]:
        """Accounts present at the round (picker of the account viewpoint)."""
        return [
            {"id": r["id"], "username": r["username"], "hue": avatar_hue(r["id"])}
            for r in self._active_ids(self._cut(ordinal)).values()
        ]

    def _profile_at(self, user_id: str, cut: int, base: sqlite3.Row) -> Dict[str, Any]:
        profile = {f: base[f] for f in PROFILE_FIELDS}
        later = self.c.execute(
            "SELECT pe.field, pe.old FROM profile_events pe JOIN rounds r ON r.id = pe.round_id "
            "WHERE pe.user_id = ? AND r.day * 10000 + r.hour > ? ORDER BY r.day DESC, r.hour DESC",
            (user_id, cut),
        ).fetchall()
        for ev in later:  # newest first: the oldest 'old' wins
            if ev["field"] in PROFILE_FIELDS:
                profile[ev["field"]] = ev["old"]
        return profile

    def _public_profile(
        self, user_id: str, cut: int, base: sqlite3.Row
    ) -> Dict[str, Any]:
        data = self._profile_at(user_id, cut, base)
        interests = [
            r["interest"]
            for r in self.c.execute(
                "SELECT DISTINCT i.interest FROM user_interest ui "
                "JOIN interests i ON i.iid = ui.interest_id "
                "JOIN rounds r ON r.id = ui.round_id AND r.day * 10000 + r.hour <= ? "
                "WHERE ui.user_id = ? ORDER BY i.interest",
                (cut, user_id),
            )
        ]
        photos = [
            {"position": r["position"], "caption": r["caption"], "url": r["media_url"]}
            for r in self.c.execute(
                "SELECT pm.position, pm.caption, pm.media_url FROM profile_media pm "
                "JOIN rounds r ON r.id = pm.round_id AND r.day * 10000 + r.hour <= ? "
                "WHERE pm.user_id = ? AND pm.active = 1 ORDER BY pm.position",
                (cut, user_id),
            )
        ]
        return {
            "id": user_id,
            "username": base["username"],
            "initials": initials(base["username"]),
            "hue": avatar_hue(user_id),
            "age": base["age"],
            "gender": base["gender"],
            "city": data["city"],
            "intent": data["intent"],
            "bio": data["bio"] or "",
            "prompts": _loads(data["prompt_answers"], {}),
            "interests": interests,
            "photos": photos,
        }

    # ------------------------------------------------------------------ public showcase
    def showcase(
        self, ordinal: int, page: int = 1, per_page: int = 24
    ) -> Dict[str, Any]:
        cut = self._cut(ordinal)
        accounts = list(self._active_ids(cut).values())
        total = len(accounts)
        start = max(page - 1, 0) * per_page
        items = [
            self._public_profile(r["id"], cut, r)
            for r in accounts[start : start + per_page]
        ]
        return {"profiles": items, "total": total, "page": page, "per_page": per_page}

    def profile(self, user_id: str, vp: Viewpoint) -> Optional[Dict[str, Any]]:
        cut = self._cut(vp.round)
        base = self._active_ids(cut).get(user_id)
        if base is None:
            return None
        data = self._public_profile(user_id, cut, base)
        if vp.kind == OVERVIEW:
            data["overview"] = self._overview_extra(user_id, cut)
        return data

    def search(self, term: str, ordinal: int, limit: int = 40) -> List[Dict[str, Any]]:
        term = (term or "").strip().lower()
        if not term:
            return []
        cut = self._cut(ordinal)
        out = []
        for r in self._active_ids(cut).values():
            hay = " ".join(
                str(x or "") for x in (r["username"], r["city"], r["intent"], r["bio"])
            ).lower()
            if term in hay:
                out.append(self._public_profile(r["id"], cut, r))
                if len(out) >= limit:
                    break
        return out

    # ------------------------------------------------------------------ overview-only data
    def _overview_extra(self, user_id: str, cut: int) -> Dict[str, Any]:
        latent = self.c.execute(
            "SELECT attractiveness, selectivity, responsiveness, desirability_rating "
            "FROM dating_latent WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        blocks = self.c.execute(
            "SELECT COUNT(*) FROM blocks b "
            + self._upto("b")
            + " WHERE b.from_id = :u",
            {"cut": cut, "u": user_id},
        ).fetchone()[0]
        return {
            "latent": dict(latent) if latent else None,
            "blocks_made": blocks,
        }

    # ------------------------------------------------------------------ deck (account and overview)
    def deck(
        self, viewer_id: str, vp: Viewpoint, ordinal: Optional[int] = None
    ) -> Dict[str, Any]:
        """The recommendations shown to ``viewer_id`` in the newest round (not later than the viewpoint's)
        that has any, with the decision taken on each. Reserved fields only for the overview.
        """
        cut = self._cut(vp.round)
        row = self.c.execute(
            "SELECT mr.round_id, r.day, r.hour FROM match_recommendations mr "
            "JOIN rounds r ON r.id = mr.round_id AND r.day * 10000 + r.hour <= :cut "
            "WHERE mr.viewer_id = :v ORDER BY r.day DESC, r.hour DESC LIMIT 1",
            {"cut": cut, "v": viewer_id},
        ).fetchone()
        if row is None:
            return {"round": None, "cards": []}
        recs = self.c.execute(
            "SELECT mr.id, mr.candidate_id, mr.position, mr.model, mr.score, mr.reason "
            "FROM match_recommendations mr WHERE mr.viewer_id = ? AND mr.round_id = ? "
            "ORDER BY mr.position",
            (viewer_id, row["round_id"]),
        ).fetchall()
        active = self._active_ids(cut)
        decisions = {
            r["rec_id"]: r
            for r in self.c.execute(
                "SELECT sw.rec_id, sw.decision, sw.mode, sw.undone FROM swipes sw "
                "JOIN rounds r ON r.id = sw.round_id AND r.day * 10000 + r.hour <= ? "
                "WHERE sw.swiper_id = ?",
                (cut, viewer_id),
            )
        }
        cards = []
        for rec in recs:
            base = active.get(rec["candidate_id"])
            if base is None:
                continue
            decision = decisions.get(rec["id"])
            card = {
                "profile": self._public_profile(rec["candidate_id"], cut, base),
                "position": rec["position"],
                "decision": (
                    None
                    if decision is None or decision["undone"]
                    else decision["decision"]
                ),
            }
            if vp.kind == OVERVIEW:
                card["overview"] = {
                    "model": rec["model"],
                    "score": rec["score"],
                    "reason": rec["reason"],
                    "mode": decision["mode"] if decision else None,
                }
            cards.append(card)
        return {"round": {"day": row["day"], "hour": row["hour"]}, "cards": cards}

    # ------------------------------------------------------------------ matches and chats
    def matches(self, viewer_id: Optional[str], vp: Viewpoint) -> List[Dict[str, Any]]:
        cut = self._cut(vp.round)
        sql = (
            "SELECT m.id, m.user_a, m.user_b, m.status, m.created_round, m.ended_round, m.ended_by "
            "FROM matches m JOIN rounds r ON r.id = m.created_round AND r.day * 10000 + r.hour <= :cut "
        )
        params: Dict[str, Any] = {"cut": cut}
        if vp.kind == ACCOUNT:
            sql += "WHERE m.user_a = :v OR m.user_b = :v "
            params["v"] = viewer_id
        sql += "ORDER BY r.day DESC, r.hour DESC"
        names = {
            r["id"]: r["username"]
            for r in self.c.execute("SELECT id, username FROM user_mgmt")
        }
        out = []
        for m in self.c.execute(sql, params).fetchall():
            ended = False
            if m["ended_round"]:
                er = self.c.execute(
                    "SELECT day * 10000 + hour AS k FROM rounds WHERE id = ?",
                    (m["ended_round"],),
                ).fetchone()
                ended = bool(er and er["k"] <= cut)
            other_id = (
                m["user_b"]
                if vp.kind != ACCOUNT or m["user_a"] == viewer_id
                else m["user_a"]
            )
            item = {
                "id": m["id"],
                "other_id": other_id,
                "other": names.get(other_id, "?"),
                "hue": avatar_hue(other_id),
                "initials": initials(names.get(other_id)),
                "active": not ended,
            }
            if vp.kind == OVERVIEW:
                item["a"] = names.get(m["user_a"], "?")
                item["b"] = names.get(m["user_b"], "?")
                item["ended_by"] = names.get(m["ended_by"]) if m["ended_by"] else None
            out.append(item)
        return out

    def chat(self, match_id: str, vp: Viewpoint) -> Optional[Dict[str, Any]]:
        cut = self._cut(vp.round)
        m = self.c.execute(
            "SELECT m.id, m.user_a, m.user_b FROM matches m "
            "JOIN rounds r ON r.id = m.created_round AND r.day * 10000 + r.hour <= ? WHERE m.id = ?",
            (cut, match_id),
        ).fetchone()
        if m is None:
            return None
        if vp.kind == ACCOUNT and vp.account_id not in (m["user_a"], m["user_b"]):
            return None  # an account never reads a chat it is not part of
        names = {
            r["id"]: r["username"]
            for r in self.c.execute(
                "SELECT id, username FROM user_mgmt WHERE id IN (?, ?)",
                (m["user_a"], m["user_b"]),
            )
        }
        msgs = []
        for r in self.c.execute(
            "SELECT ms.id, ms.sender_id, ms.text, ms.deleted, ms.minute, rr.day, rr.hour "
            "FROM messages ms JOIN rounds rr ON rr.id = ms.round_id AND rr.day * 10000 + rr.hour <= ? "
            "WHERE ms.match_id = ? ORDER BY rr.day, rr.hour, ms.minute, ms.id",
            (cut, match_id),
        ):
            deleted = bool(r["deleted"])
            item = {
                "id": r["id"],
                "sender": names.get(r["sender_id"], "?"),
                "sender_id": r["sender_id"],
                "mine": vp.kind == ACCOUNT and r["sender_id"] == vp.account_id,
                "day": r["day"],
                "hour": r["hour"],
                "deleted": deleted,
                "text": "" if (deleted and vp.kind != OVERVIEW) else r["text"],
            }
            if vp.kind != OVERVIEW and deleted:
                item["text"] = ""
            msgs.append(item)
        return {
            "id": m["id"],
            "a": {"id": m["user_a"], "name": names.get(m["user_a"], "?")},
            "b": {"id": m["user_b"], "name": names.get(m["user_b"], "?")},
            "messages": msgs,
        }

    # ------------------------------------------------------------------ notifications of an account
    def notifications(
        self, viewer_id: str, vp: Viewpoint, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """New matches and messages addressed to the account, newest first (what its app would notify)."""
        cut = self._cut(vp.round)
        names = {
            r["id"]: r["username"]
            for r in self.c.execute("SELECT id, username FROM user_mgmt")
        }
        items = []
        for m in self.c.execute(
            "SELECT m.id, m.user_a, m.user_b, r.day, r.hour FROM matches m "
            "JOIN rounds r ON r.id = m.created_round AND r.day * 10000 + r.hour <= ? "
            "WHERE m.user_a = ? OR m.user_b = ?",
            (cut, viewer_id, viewer_id),
        ):
            other = m["user_b"] if m["user_a"] == viewer_id else m["user_a"]
            items.append(
                {
                    "kind": "match",
                    "match_id": m["id"],
                    "other": names.get(other, "?"),
                    "day": m["day"],
                    "hour": m["hour"],
                }
            )
        for ms in self.c.execute(
            "SELECT ms.match_id, ms.sender_id, rr.day, rr.hour FROM messages ms "
            "JOIN matches m ON m.id = ms.match_id AND (m.user_a = :v OR m.user_b = :v) "
            "JOIN rounds rr ON rr.id = ms.round_id AND rr.day * 10000 + rr.hour <= :cut "
            "WHERE ms.sender_id != :v AND ms.deleted = 0",
            {"v": viewer_id, "cut": cut},
        ):
            items.append(
                {
                    "kind": "message",
                    "match_id": ms["match_id"],
                    "other": names.get(ms["sender_id"], "?"),
                    "day": ms["day"],
                    "hour": ms["hour"],
                }
            )
        items.sort(key=lambda i: (i["day"], i["hour"]), reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------ overview: history
    def history(self, vp: Viewpoint) -> List[Dict[str, Any]]:
        """Counts per round up to the viewpoint's round (rounds, swipes, matches, messages); overview only."""
        if vp.kind != OVERVIEW:
            raise ViewpointError("history is an overview feature")
        cut = self._cut(vp.round)
        out = []
        counts = {
            "swipes": "SELECT round_id, COUNT(*) n FROM swipes GROUP BY round_id",
            "matches": "SELECT created_round AS round_id, COUNT(*) n FROM matches GROUP BY created_round",
            "messages": "SELECT round_id, COUNT(*) n FROM messages GROUP BY round_id",
        }
        by = {
            k: {r["round_id"]: r["n"] for r in self.c.execute(q)}
            for k, q in counts.items()
        }
        for i, r in enumerate(self.rounds(), 1):
            if r["day"] * 10000 + r["hour"] > cut:
                break
            out.append(
                {
                    "round": i,
                    "day": r["day"],
                    "hour": r["hour"],
                    **{k: by[k].get(r["id"], 0) for k in counts},
                }
            )
        return out
