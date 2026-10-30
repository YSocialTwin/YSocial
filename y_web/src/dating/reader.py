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
_END_CODES = ("paired", "unmatched", "blocked", "ended", "left_platform", "ghosted", "no_opener")
GHOST_SLOTS = 48  # the server's ghosting_threshold_slots: a message nobody answers for this long
# fields of profile_events that are part of the public profile
PROFILE_FIELDS = ("bio", "prompt_answers", "city", "intent")


def _avatar(user_id: str, name: Optional[str], photo: str) -> Dict[str, Any]:
    """What the avatar of a user needs: initials and hue, and the picture when there is one."""
    return {"hue": avatar_hue(user_id), "initials": initials(name), "photo": photo}


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

    def account_brief(self, user_id: Optional[str], ordinal: int) -> Optional[Dict[str, Any]]:
        """One account for the viewpoint bar: name, initials, colour and first picture."""
        if not user_id:
            return None
        row = self.c.execute(
            "SELECT id, username FROM user_mgmt WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return self._brief(row, self._cut(ordinal))

    def _brief(self, row, cut: int) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            **_avatar(row["id"], row["username"], self._photo_url(row["id"], cut)),
        }

    def find_accounts(self, term: str, ordinal: int, limit: int = 8) -> List[Dict[str, Any]]:
        """Accounts whose username contains ``term`` (case-insensitive; prefix matches first)."""
        cut = self._cut(ordinal)
        needle = (term or "").strip().lower()
        rows = list(self._active_ids(cut).values())
        if needle:
            rows = [r for r in rows if needle in (r["username"] or "").lower()]
            rows.sort(key=lambda r: (not (r["username"] or "").lower().startswith(needle), r["username"] or ""))
        return [self._brief(r, cut) for r in rows[: max(1, min(limit, 20))]]

    def resolve_account(self, value: Optional[str]) -> Optional[str]:
        """The id of an account given as an id or as a username (None when there is no such account)."""
        value = (value or "").strip()
        if not value:
            return None
        row = self.c.execute(
            "SELECT id FROM user_mgmt WHERE id = ? OR username = ? COLLATE NOCASE "
            "ORDER BY (id = ?) DESC LIMIT 1",
            (value, value, value),
        ).fetchone()
        return row["id"] if row else None

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

    def _photos_at(self, user_id: str, cut: int) -> List[Dict[str, Any]]:
        """Photos of the profile at a round: added by then and not removed by then (history is kept)."""
        removed_later = set()
        for ev in self.c.execute(
            "SELECT pe.old FROM profile_events pe JOIN rounds r ON r.id = pe.round_id "
            "WHERE pe.user_id = ? AND pe.field = 'photo_removed' AND r.day * 10000 + r.hour > ?",
            (user_id, cut),
        ):
            removed_later.add(_loads(ev["old"], {}).get("id"))
        return [
            {"position": r["position"], "caption": r["caption"], "url": r["media_url"]}
            for r in self.c.execute(
                "SELECT pm.id, pm.position, pm.caption, pm.media_url, pm.active FROM profile_media pm "
                "JOIN rounds r ON r.id = pm.round_id AND r.day * 10000 + r.hour <= ? "
                "WHERE pm.user_id = ? ORDER BY pm.position, pm.rowid",
                (cut, user_id),
            )
            if r["active"] == 1 or r["id"] in removed_later
        ]

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
        photos = self._photos_at(user_id, cut)
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

    def _photo_url(self, user_id: str, cut: int) -> str:
        """The first picture of the profile at the round that has a file (empty when none has one yet)."""
        for ph in self._photos_at(user_id, cut):
            if ph.get("url"):
                return ph["url"]
        return ""

    def facets(self, ordinal: int) -> Dict[str, Any]:
        """Values to offer in the search form: what the profiles shown at the round actually have."""
        rows = list(self._active_ids(self._cut(ordinal)).values())
        ages = [r["age"] for r in rows if r["age"] is not None]
        return {
            "genders": sorted({r["gender"] for r in rows if r["gender"]}),
            "intents": sorted({r["intent"] for r in rows if r["intent"]}),
            "cities": sorted({r["city"] for r in rows if r["city"]}),
            "age_min": min(ages) if ages else 18,
            "age_max": max(ages) if ages else 99,
            "total": len(rows),
        }

    SORTS = ("relevance", "name", "age", "age_desc", "newest")

    def search(
        self,
        term: str,
        ordinal: int,
        limit: int = 60,
        filters: Optional[Dict[str, Any]] = None,
        sort: str = "relevance",
    ) -> Dict[str, Any]:
        """Profiles that match a text (name, city, intent, bio, interests) and the filters, with a total.

        ``filters``: ``genders`` (list), ``intents`` (list), ``city`` (text), ``age_min``/``age_max`` (int),
        ``interest`` (text) and ``photo`` (only profiles with a picture). Each word of the text must be found;
        a hit in the name or in the interests ranks first.
        """
        filters = filters or {}
        words = [w for w in (term or "").lower().split() if w]
        cut = self._cut(ordinal)
        genders = {g.lower() for g in filters.get("genders") or []}
        intents = {i.lower() for i in filters.get("intents") or []}
        city = (filters.get("city") or "").strip().lower()
        interest = (filters.get("interest") or "").strip().lower()
        lo, hi = filters.get("age_min"), filters.get("age_max")
        found = []
        for order, r in enumerate(self._active_ids(cut).values()):
            if genders and (r["gender"] or "").lower() not in genders:
                continue
            if intents and (r["intent"] or "").lower() not in intents:
                continue
            if city and city not in (r["city"] or "").lower():
                continue
            if lo is not None and (r["age"] is None or r["age"] < lo):
                continue
            if hi is not None and (r["age"] is None or r["age"] > hi):
                continue
            profile = self._public_profile(r["id"], cut, r)
            tags = [i.lower() for i in profile["interests"]]
            if interest and not any(interest in t for t in tags):
                continue
            if filters.get("photo") and not any(
                p.get("url") for p in profile["photos"]
            ):
                continue
            score = 0
            if words:
                name = (r["username"] or "").lower()
                hay = " ".join(
                    [
                        name,
                        (r["city"] or "").lower(),
                        (r["intent"] or "").lower(),
                        (r["bio"] or "").lower(),
                    ]
                    + tags
                )
                if not all(w in hay for w in words):
                    continue
                score = sum(
                    3 if w in name else 2 if any(w in t for t in tags) else 1
                    for w in words
                )
            found.append((score, order, profile))
        if sort == "name":
            found.sort(key=lambda x: (x[2]["username"] or "").lower())
        elif sort == "age":
            found.sort(key=lambda x: (x[2]["age"] is None, x[2]["age"] or 0))
        elif sort == "age_desc":
            found.sort(key=lambda x: -(x[2]["age"] or 0))
        elif sort == "newest":
            found.sort(key=lambda x: -x[1])
        else:
            found.sort(key=lambda x: (-x[0], x[1]))
        return {"results": [x[2] for x in found[:limit]], "total": len(found)}

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
            "lifecycle": self.lifecycle_stats(user_id, cut),
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
        # what each candidate answered about the viewer (their latest standing decision, at the cut)
        theirs = {}
        for r in self.c.execute(
            "SELECT sw.swiper_id, sw.decision FROM swipes sw "
            "JOIN rounds r ON r.id = sw.round_id AND r.day * 10000 + r.hour <= ? "
            "WHERE sw.target_id = ? AND COALESCE(sw.undone, 0) = 0 ORDER BY r.day, r.hour",
            (cut, viewer_id),
        ):
            theirs[r["swiper_id"]] = r["decision"]
        # a match needs a like from both sides: when no swipe of theirs is on record the pair is still shown
        # as matched (a data gap worth knowing about) instead of as "not rated"
        matched = set()
        for r in self.c.execute(
            "SELECT m.user_a, m.user_b FROM matches m "
            "JOIN rounds r ON r.id = m.created_round AND r.day * 10000 + r.hour <= ? "
            "WHERE m.user_a = ? OR m.user_b = ?",
            (cut, viewer_id, viewer_id),
        ):
            matched.add(r["user_b"] if r["user_a"] == viewer_id else r["user_a"])
        cards = []
        for rec in recs:
            base = active.get(rec["candidate_id"])
            if base is None:
                continue
            decision = decisions.get(rec["id"])
            card = {
                "theirs": theirs.get(rec["candidate_id"])
                or ("MATCH" if rec["candidate_id"] in matched else "NONE"),
                "matched": rec["candidate_id"] in matched,
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
    # ------------------------------------------------------------------ how a match went
    def _key_slot(self, key: int) -> int:
        day, hour = divmod(key, 10000)
        return day * self.slots + max(hour - 1, 0)

    def _has_dates(self) -> bool:
        return bool(
            self.c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='date_proposals'"
            ).fetchone()
        )

    def journeys(
        self,
        cut: int,
        account_id: Optional[str] = None,
        detail: bool = True,
        match_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """What became of every match (of ``account_id``, else of all) at the cut: the dates and their
        outcomes, whether the conversation was left unanswered (ghosting) and how the match ended.

        ``chips`` is the ordered list of outcomes shown in the matches table (code, tone good, neutral, bad
        or info). With ``detail`` false (an account's own view) a block or an unmatch shows only as an end:
        a person does not learn who ended it nor why.
        """
        sql = (
            "SELECT m.id, m.user_a, m.user_b, m.status, m.created_round, m.ended_round, m.ended_by, "
            "cr.day * 10000 + cr.hour AS created_key FROM matches m "
            "JOIN rounds cr ON cr.id = m.created_round AND cr.day * 10000 + cr.hour <= :cut "
        )
        params: Dict[str, Any] = {"cut": cut}
        if match_id:
            sql += "WHERE m.id = :mid"
            params["mid"] = match_id
        elif account_id:
            sql += "WHERE m.user_a = :v OR m.user_b = :v"
            params["v"] = account_id
        matches = self.c.execute(sql, params).fetchall()
        if not matches:
            return {}
        ids = {m["id"] for m in matches}
        scoped = bool(match_id or account_id)  # read only the messages of the matches asked for
        marks = ",".join("?" * len(ids)) if scoped and len(ids) <= 500 else None
        keys = {
            r["id"]: r["k"]
            for r in self.c.execute("SELECT id, day * 10000 + hour AS k FROM rounds")
        }
        left_reason = {
            r["id"]: r["left_reason"]
            for r in self.c.execute("SELECT id, left_reason FROM user_mgmt WHERE status = 'left'")
        }
        last: Dict[str, sqlite3.Row] = {}
        count: Dict[str, int] = {}
        for r in self.c.execute(
            "SELECT ms.match_id, ms.sender_id, rr.day * 10000 + rr.hour AS k FROM messages ms "
            "JOIN rounds rr ON rr.id = ms.round_id AND rr.day * 10000 + rr.hour <= ? "
            "WHERE ms.deleted = 0 "
            + ("AND ms.match_id IN (%s) " % marks if marks else "")
            + "ORDER BY rr.day, rr.hour, ms.minute, ms.id",
            (cut, *(sorted(ids) if marks else ())),
        ):
            if r["match_id"] in ids:
                last[r["match_id"]] = r
                count[r["match_id"]] = count.get(r["match_id"], 0) + 1
        dates: Dict[str, List[Dict[str, Any]]] = {}
        if self._has_dates():
            for d in self.c.execute(
                "SELECT dp.id, dp.match_id, dp.proposer_id, dp.text, dp.status, dp.outcome, dp.round_id, "
                "dp.outcome_round FROM date_proposals dp "
                "JOIN rounds pr ON pr.id = dp.round_id AND pr.day * 10000 + pr.hour <= ? "
                "ORDER BY pr.day, pr.hour, dp.id",
                (cut,),
            ):
                if d["match_id"] not in ids:
                    continue
                out_key = keys.get(d["outcome_round"]) if d["outcome_round"] else None
                known = out_key is not None and out_key <= cut
                status = d["status"]
                if status == "accepted" and d["outcome"] and not known:
                    outcome = None  # the outcome had not happened yet at this round
                else:
                    outcome = d["outcome"] if known else None
                dates.setdefault(d["match_id"], []).append(
                    {
                        "id": d["id"],
                        "proposer_id": d["proposer_id"],
                        "text": d["text"],
                        "status": status,
                        "outcome": outcome,
                        "key": keys.get(d["round_id"], 0),
                        "outcome_key": out_key if known else None,
                    }
                )
        now = self._key_slot(cut)
        out: Dict[str, Dict[str, Any]] = {}
        for m in matches:
            mid = m["id"]
            ended = False
            if m["ended_round"]:
                ended = keys.get(m["ended_round"], 10**9) <= cut
            ds = dates.get(mid, [])
            ghost = None
            lm = last.get(mid)
            if not ended:
                if lm is not None:
                    waited = now - self._key_slot(lm["k"])
                    if waited >= GHOST_SLOTS:
                        other = m["user_b"] if lm["sender_id"] == m["user_a"] else m["user_a"]
                        ghost = {"silent": other, "sender": lm["sender_id"], "slots": waited}
                else:
                    waited = now - self._key_slot(m["created_key"])
                    if waited >= GHOST_SLOTS:
                        ghost = {"silent": None, "sender": None, "slots": waited}
            chips: List[Dict[str, str]] = []
            status = m["status"] if ended else "active"
            if status == "closed_paired":
                chips.append({"code": "paired", "tone": "good"})
            shown = [d for d in ds if d["outcome"] or d["status"] != "pending"] or ds
            if shown and status != "closed_paired":
                d = shown[-1]
                if d["outcome"] == "POSITIVE":
                    chips.append({"code": "date_good", "tone": "good"})
                elif d["outcome"] == "NEUTRAL":
                    chips.append({"code": "date_neutral", "tone": "neutral"})
                elif d["outcome"] == "NEGATIVE":
                    chips.append({"code": "date_bad", "tone": "bad"})
                elif d["status"] == "accepted":
                    chips.append({"code": "date_planned", "tone": "info"})
                elif d["status"] == "declined":
                    chips.append({"code": "date_declined", "tone": "bad"})
                elif d["status"] == "expired":
                    chips.append({"code": "date_expired", "tone": "bad"})
                else:
                    chips.append({"code": "date_proposed", "tone": "info"})
            if status in ("unmatched", "closed_block"):
                if left_reason.get(m["ended_by"]) == "churn":
                    code = "left_platform"
                elif not detail:
                    code = "ended"
                else:
                    code = "blocked" if status == "closed_block" else "unmatched"
                chips.append({"code": code, "tone": "bad"})
            if ghost is not None and not chips:
                chips.append({"code": "ghosted" if lm is not None else "no_opener", "tone": "bad"})
            elif ghost is not None:
                chips.append({"code": "ghosted" if lm is not None else "no_opener", "tone": "bad"})
            if not chips:
                chips.append({"code": "chatting" if lm is not None else "new", "tone": "neutral"})
            out[mid] = {
                "dates": ds,
                "ghost": ghost,
                "chips": chips,
                "headline": chips[0],
                "status": status,
                "messages": count.get(mid, 0),
                "last_key": lm["k"] if lm is not None else None,
            }
        return out

    def lifecycle_stats(self, user_id: str, cut: int) -> Dict[str, Any]:
        """How the relationships of an agent went (researcher view): conversations, ghosting, dates, exits."""
        journeys = self.journeys(cut, user_id, detail=True)
        matches = {
            r["id"]: r
            for r in self.c.execute(
                "SELECT id, user_a, user_b, status, ended_by, first_message_by FROM matches "
                "WHERE user_a = ? OR user_b = ?",
                (user_id, user_id),
            )
        }
        stats = {
            "matches": len(journeys),
            "active": 0,
            "started": 0,  # conversations with at least one message
            "opened": 0,  # the agent wrote first
            "ghosted_by": 0,  # the agent wrote last and the other stayed silent
            "ghosted": 0,  # the agent left the other unanswered
            "dates_proposed": 0,
            "dates_received": 0,
            "dates_accepted": 0,  # of the proposals the agent made or answered, accepted
            "dates_declined": 0,
            "dates_expired": 0,
            "dates_positive": 0,
            "dates_neutral": 0,
            "dates_negative": 0,
            "paired": 0,
            "unmatched_by_me": 0,
            "unmatched_by_other": 0,
            "blocked_by_me": 0,
            "blocked_by_other": 0,
        }
        for mid, j in journeys.items():
            row = matches.get(mid)
            if row is None:
                continue
            if j["status"] == "active":
                stats["active"] += 1
            if j["messages"]:
                stats["started"] += 1
            if row["first_message_by"] == user_id and j["messages"]:
                stats["opened"] += 1
            g = j["ghost"]
            if g and g["sender"] == user_id:
                stats["ghosted_by"] += 1
            if g and g["silent"] == user_id:
                stats["ghosted"] += 1
            for d in j["dates"]:
                if d["proposer_id"] == user_id:
                    stats["dates_proposed"] += 1
                else:
                    stats["dates_received"] += 1
                if d["status"] == "accepted":
                    stats["dates_accepted"] += 1
                elif d["status"] == "declined":
                    stats["dates_declined"] += 1
                elif d["status"] == "expired":
                    stats["dates_expired"] += 1
                if d["outcome"]:
                    stats["dates_" + d["outcome"].lower()] += 1
            if j["status"] == "closed_paired":
                stats["paired"] += 1
            elif j["status"] in ("unmatched", "closed_block"):
                mine = row["ended_by"] == user_id
                kind = "blocked" if j["status"] == "closed_block" else "unmatched"
                stats["%s_by_%s" % (kind, "me" if mine else "other")] += 1
        return stats

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
        journeys = self.journeys(
            cut, viewer_id if vp.kind == ACCOUNT else None, detail=vp.kind == OVERVIEW
        )
        out = []
        for m in self.c.execute(sql, params).fetchall():
            journey = journeys.get(m["id"])
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
                "photo": self._photo_url(other_id, cut),
                "active": not ended,
                "chips": journey["chips"] if journey else [],
                "dates": len(journey["dates"]) if journey else 0,
                "messages": journey["messages"] if journey else 0,
            }
            if vp.kind == OVERVIEW:
                item["a"] = names.get(m["user_a"], "?")
                item["b"] = names.get(m["user_b"], "?")
                item["a_avatar"] = _avatar(
                    m["user_a"],
                    names.get(m["user_a"]),
                    self._photo_url(m["user_a"], cut),
                )
                item["b_avatar"] = _avatar(
                    m["user_b"],
                    names.get(m["user_b"]),
                    self._photo_url(m["user_b"], cut),
                )
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
        journey = self.journeys(
            cut, vp.account_id if vp.kind == ACCOUNT else None, detail=vp.kind == OVERVIEW, match_id=m["id"]
        ).get(m["id"])
        events: List[Dict[str, Any]] = []
        if journey:
            for d in journey["dates"]:
                if d["status"] in ("declined", "expired"):
                    events.append({"code": "date_" + d["status"], "tone": "bad", "key": d["key"]})
                elif d["outcome"]:
                    code = {"POSITIVE": "date_good", "NEUTRAL": "date_neutral"}.get(
                        d["outcome"], "date_bad"
                    )
                    tone = {"POSITIVE": "good", "NEUTRAL": "neutral"}.get(d["outcome"], "bad")
                    events.append({"code": code, "tone": tone, "key": d["outcome_key"] or d["key"]})
            tail = [c for c in journey["chips"] if c["code"] in _END_CODES]
            for c in tail:
                events.append({"code": c["code"], "tone": c["tone"], "key": 10**9})
        for e in events:
            e["day"], e["hour"] = (e["key"] // 10000, e["key"] % 10000) if e["key"] < 10**9 else (None, None)
        return {
            "id": m["id"],
            "events": events,
            "journey": journey["chips"] if journey else [],
            "a": {
                "id": m["user_a"],
                "name": names.get(m["user_a"], "?"),
                **_avatar(
                    m["user_a"],
                    names.get(m["user_a"]),
                    self._photo_url(m["user_a"], cut),
                ),
            },
            "b": {
                "id": m["user_b"],
                "name": names.get(m["user_b"], "?"),
                **_avatar(
                    m["user_b"],
                    names.get(m["user_b"]),
                    self._photo_url(m["user_b"], cut),
                ),
            },
            "messages": msgs,
        }

    # ------------------------------------------------------------------ notifications of an account
    def notifications(
        self, viewer_id: str, vp: Viewpoint, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """New matches and messages addressed to the account, newest first (what its app would notify).

        ``unread`` is true for a message the account has not opened yet and for a match nobody has written
        in. Only the matches of the account are read, through their indexes.
        """
        cut = self._cut(vp.round)
        matches = self.c.execute(
            "SELECT m.id, m.user_a, m.user_b, r.day, r.hour FROM matches m "
            "JOIN rounds r ON r.id = m.created_round AND r.day * 10000 + r.hour <= ? "
            "WHERE m.user_a = ? OR m.user_b = ?",
            (cut, viewer_id, viewer_id),
        ).fetchall()
        if not matches:
            return []
        others = {m["id"]: (m["user_b"] if m["user_a"] == viewer_id else m["user_a"]) for m in matches}
        names = {
            r["id"]: r["username"]
            for r in self.c.execute(
                "SELECT id, username FROM user_mgmt WHERE id IN (%s)" % ",".join("?" * len(set(others.values()))),
                tuple(set(others.values())),
            )
        }
        written = set()
        items: List[Dict[str, Any]] = []
        ids = list(others)
        for i in range(0, len(ids), 400):  # SQLite caps the number of parameters
            chunk = ids[i : i + 400]
            marks = ",".join("?" * len(chunk))
            for ms in self.c.execute(
                "SELECT ms.match_id, ms.sender_id, ms.read_round, ms.deleted, rr.day, rr.hour FROM messages ms "
                "JOIN rounds rr ON rr.id = ms.round_id AND rr.day * 10000 + rr.hour <= ? "
                "WHERE ms.match_id IN (%s)" % marks,
                (cut, *chunk),
            ):
                written.add(ms["match_id"])
                if ms["sender_id"] == viewer_id or ms["deleted"]:
                    continue
                items.append(
                    {
                        "kind": "message",
                        "match_id": ms["match_id"],
                        "other": names.get(ms["sender_id"], "?"),
                        "day": ms["day"],
                        "hour": ms["hour"],
                        "unread": ms["read_round"] is None,
                    }
                )
        for m in matches:
            items.append(
                {
                    "kind": "match",
                    "match_id": m["id"],
                    "other": names.get(others[m["id"]], "?"),
                    "day": m["day"],
                    "hour": m["hour"],
                    "unread": m["id"] not in written,
                }
            )
        items.sort(key=lambda i: (i["unread"], i["day"], i["hour"]), reverse=True)
        return items[:limit]

    def unread_count(self, viewer_id: str, vp: Viewpoint) -> int:
        """How many notifications of the account are still to be read (a badge on every page)."""
        return sum(1 for n in self.notifications(viewer_id, vp, limit=10**6) if n["unread"])

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
