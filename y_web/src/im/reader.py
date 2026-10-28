"""Read model of the instant messaging observer (plan, 4.4, 6.2, 6.3).

Every function takes a :class:`Viewpoint` (who looks, as of which round) and answers from a read-only session
(``engine.open_reader``). Visibility is **IM's own** ``visibility.can_read``, reached through IM's
``Repository`` views, so there is no second implementation of who may read what; a differential test compares
the result with IM's ``FeedService.history``. Three viewpoints (6.3):

* ``account``: exactly what that account can read at the round (admin and researcher);
* ``public``: public chats only, deleted messages gone, no private chats or DMs;
* ``overview``: everything, deleted messages as tombstones without their text (researchers).
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from y_web.src.im.engine import im_modules
from y_web.src.im.timeline import day_slot

VIEWPOINT_KINDS = ("account", "public", "overview")
PREVIEW_CHARS = 80


def avatar_hue(key: str) -> int:
    """A stable hue (0-359) for the placeholder avatar of a chat or an account."""
    import hashlib

    return int(hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:6], 16) % 360
REPLY_PREVIEW_CHARS = 160
DEFAULT_PAGE = 30
MAX_PAGE = 100
MAX_SEARCH = 50


class ViewpointError(ValueError):
    """The viewpoint is invalid (unknown kind, unknown account)."""


@dataclass(frozen=True)
class Viewpoint:
    kind: str = "public"
    account_id: Optional[str] = None
    round: int = 0  # 0 = nothing exists yet; the routes pass the latest round when none is requested

    def __post_init__(self):
        if self.kind not in VIEWPOINT_KINDS:
            raise ViewpointError(f"unknown viewpoint {self.kind!r}")
        if self.kind == "account" and not self.account_id:
            raise ViewpointError("the account viewpoint needs an account")


def _models():
    return im_modules()[0]


def latest_round(session: Session) -> int:
    m = _models()
    return int(session.scalar(select(func.max(m.Round.id))) or 0)


def status(session: Session, after: int = 0) -> Dict[str, Any]:
    """Round, lifecycle and the rounds that passed since ``after`` (the polling answer)."""
    m = _models()
    latest = latest_round(session)
    lifecycle = session.scalar(select(m.RunInfo.lifecycle).limit(1))
    day, slot = day_slot(latest) if latest else (0, 0)
    return {"round": latest, "day": day, "slot": slot, "lifecycle": lifecycle, "changed": latest > after}


class Reader:
    """Queries of one viewpoint on one session."""

    def __init__(self, session: Session, viewpoint: Viewpoint):
        self.s = session
        self.vp = viewpoint
        self.m, self.visibility, self.views, _ = im_modules()
        from yinstantmessaging.server.db.repository import Repository

        self.repo = Repository(session)
        if viewpoint.kind == "account" and self.repo.account_view(viewpoint.account_id) is None:
            raise ViewpointError("unknown account")
        self._chats: Dict[str, Any] = {}

    # -- visibility ------------------------------------------------------------------------
    def _chat(self, chat_id: str):
        if chat_id not in self._chats:
            self._chats[chat_id] = self.s.get(self.m.Chat, chat_id)
        return self._chats[chat_id]

    def _chat_visible(self, chat) -> bool:
        """May the viewpoint open this chat at all (a probe message with the chat's own rules)."""
        if chat is None or chat.created_round > self.vp.round:
            return False
        if self.vp.kind == "overview":
            return True
        if self.vp.kind == "public":
            return chat.visibility == "public" and chat.type != "private"
        probe = self.views.MessageView("-", chat.id, 0, None)
        return self.visibility.can_read(
            self.repo.account_view(self.vp.account_id),
            self.repo.chat_view(chat.id),
            self.repo.member_view(chat.id, self.vp.account_id),
            probe,
            self.vp.round,
        )

    def _message_state(self, chat, msg) -> Optional[str]:
        """``"visible"``, ``"deleted"`` (a tombstone, overview only) or ``None`` (not readable)."""
        r = self.vp.round
        if msg.round_id > r:
            return None
        deleted = msg.deleted_round is not None and msg.deleted_round <= r
        if self.vp.kind == "overview":
            return "deleted" if deleted else "visible"
        if self.vp.kind == "public":
            if deleted or chat.visibility != "public" or chat.type == "private":
                return None
            return "visible"
        ok = self.visibility.can_read(
            self.repo.account_view(self.vp.account_id),
            self.repo.chat_view(chat.id),
            self.repo.member_view(chat.id, self.vp.account_id),
            self.views.MessageView(msg.id, msg.chat_id, msg.round_id, msg.deleted_round),
            r,
        )
        return "visible" if ok else None

    # -- helpers ---------------------------------------------------------------------------
    def _accounts(self, ids: Iterable[str]) -> Dict[str, Any]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.s.scalars(select(self.m.Account).where(self.m.Account.id.in_(ids)))
        return {row.id: row for row in rows}

    def _titles(self, ids: Iterable[str]) -> Dict[str, str]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = self.s.execute(
            select(self.m.Chat.id, self.m.Chat.title).where(self.m.Chat.id.in_(ids))
        )
        return {cid: (title or cid) for cid, title in rows}

    def _text_as_of(self, msg) -> str:
        r = self.vp.round
        if msg.edited_round is not None and msg.edited_round > r:
            original = self.s.scalar(
                select(self.m.MessageRevision.text)
                .where(self.m.MessageRevision.message_id == msg.id)
                .order_by(self.m.MessageRevision.revision.asc())
                .limit(1)
            )
            if original is not None:
                return original
        return msg.text or ""

    def _item(self, msg, state, accounts, titles, reactions, urls, parents, extras=None) -> Dict[str, Any]:
        day, slot = day_slot(msg.round_id)
        sender = accounts.get(msg.sender_account_id)
        parent = parents.get(msg.reply_to_message_id)
        tomb = state == "deleted"
        origin = msg.fwd_origin_chat_id
        return {
            "id": msg.id,
            "chat_id": msg.chat_id,
            "round": msg.round_id,
            "day": day,
            "slot": slot,
            "hour": slot - 1,
            "minute": int(msg.sim_minute or 0) % 60,  # the start of the interval (tick) it was posted in: an estimate
            "sim_ts": msg.sim_ts.isoformat() if msg.sim_ts else None,
            "sender": (
                {"id": sender.id, "username": sender.username, "kind": sender.kind, "hue": avatar_hue(sender.id)}
                if sender is not None
                else None
            ),
            "posted_as": titles.get(msg.posted_as_chat_id),
            "text": "" if tomb else self._text_as_of(msg),
            "deleted": tomb,
            "edited": bool(msg.edited_round is not None and msg.edited_round <= self.vp.round),
            "media_type": msg.media_type if msg.media_type != "none" else None,
            "reply_to": (
                {
                    "id": parent.id,
                    "author": getattr(accounts.get(parent.sender_account_id), "username", None),
                    "text": (parent.text or "")[:REPLY_PREVIEW_CHARS],
                }
                if parent is not None and parent.round_id <= self.vp.round
                else None
            ),
            "forwarded": (
                {
                    "chat": titles.get(msg.fwd_from_chat_id) or titles.get(origin),
                    "origin_chat": titles.get(origin),
                    "chained": bool(msg.fwd_from_message_id and msg.fwd_from_message_id != msg.fwd_origin_message_id),
                }
                if (msg.fwd_from_message_id or origin)
                else None
            ),
            "reactions": reactions.get(msg.id, {}),
            "urls": urls.get(msg.id, []),
            "forum_topic_id": msg.forum_topic_id,
            "thread_root_id": msg.thread_root_id,
            "discussion_root_of": msg.discussion_root_of,
            "origin": msg.origin,
            "off_topic": bool(msg.off_topic),
            "views": int(msg.views or 0),
            **({} if tomb else (extras or {}).get(msg.id, {})),
        }

    def _extras(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Topics, hashtags, mentions and the annotations (toxicity, sentiment, emotion) of the given messages."""
        m = self.m
        out: Dict[str, Dict[str, Any]] = {i: {} for i in ids}
        topic_rows = self.s.execute(
            select(m.MessageTopic.message_id, m.Topic.label, m.TopicCandidate.label, m.MessageTopic.source)
            .outerjoin(m.Topic, m.Topic.id == m.MessageTopic.topic_id)
            .outerjoin(m.TopicCandidate, m.TopicCandidate.id == m.MessageTopic.candidate_id)
            .where(m.MessageTopic.message_id.in_(ids))
            .order_by(m.MessageTopic.id)
        )
        for mid, label, candidate, source in topic_rows:
            name = label or candidate
            if name:
                out[mid].setdefault("topics", []).append({"label": name, "source": source})
        for mid, tag in self.s.execute(
            select(m.MessageHashtag.message_id, m.Hashtag.hashtag)
            .join(m.Hashtag, m.Hashtag.id == m.MessageHashtag.hashtag_id)
            .where(m.MessageHashtag.message_id.in_(ids))
            .order_by(m.Hashtag.hashtag)
        ):
            out[mid].setdefault("hashtags", []).append(tag)
        for mid, name, account_id in self.s.execute(
            select(m.Mention.message_id, m.Mention.username, m.Mention.mentioned_account_id)
            .where(m.Mention.message_id.in_(ids))
            .order_by(m.Mention.id)
        ):
            out[mid].setdefault("mentions", []).append(name)
            if account_id:  # the profile the tag points to (an unknown username stays plain text)
                out[mid].setdefault("mention_ids", {})[name] = account_id
        seen = set()
        for mid, method, value in self.s.execute(
            select(m.Annotation.message_id, m.Annotation.method_ref, m.Annotation.value)
            .where(m.Annotation.message_id.in_(ids), m.Annotation.status == "ok")
            .order_by(m.Annotation.method_ref)
        ):
            kind = next((k for k in ("toxicity", "sentiment", "emotion") if str(method).startswith(k)), None)
            if kind is None or (mid, kind) in seen or not isinstance(value, dict):
                continue
            seen.add((mid, kind))  # the first method by name wins when several ran
            ann = out[mid].setdefault("annotations", {})
            if kind == "toxicity":
                score = value.get("toxicity")
                if isinstance(score, (int, float)):
                    ann["toxicity"] = round(float(score), 3)
            elif kind == "sentiment":
                compound = value.get("compound")
                if isinstance(compound, (int, float)):
                    label = "positive" if compound >= 0.05 else "negative" if compound <= -0.05 else "neutral"
                    ann["sentiment"] = {"label": label, "compound": round(float(compound), 3)}
            else:
                emotion = value.get("emotion") or value.get("label")
                if not emotion and isinstance(value.get("emotions"), list):  # the LLM annotator's labels
                    emotion = ", ".join(str(e) for e in value["emotions"][:3]) or None
                if not emotion:
                    scores = {k: v for k, v in value.items() if isinstance(v, (int, float))}
                    emotion = max(scores, key=scores.get) if scores else None
                if emotion:
                    ann["emotion"] = str(emotion)
        return out

    def _items(self, rows: List[Any]) -> List[Dict[str, Any]]:
        """Message DTOs for rows that are already known to be readable (state per row)."""
        if not rows:
            return []
        msgs = [m for m, _state in rows]
        ids = [m.id for m in msgs]
        parents = {
            p.id: p
            for p in self.s.scalars(
                select(self.m.Message).where(
                    self.m.Message.id.in_({m.reply_to_message_id for m in msgs if m.reply_to_message_id})
                )
            )
        } if any(m.reply_to_message_id for m in msgs) else {}
        everyone = msgs + list(parents.values())
        accounts = self._accounts(x.sender_account_id for x in everyone)
        titles = self._titles(
            [x.posted_as_chat_id for x in msgs]
            + [x.fwd_origin_chat_id for x in msgs]
            + [x.fwd_from_chat_id for x in msgs]
        )
        reactions: Dict[str, Dict[str, int]] = {}
        for message_id, emoji, count in self.s.execute(
            select(self.m.Reaction.message_id, self.m.Reaction.emoji, func.count())
            .where(self.m.Reaction.message_id.in_(ids), self.m.Reaction.round_id <= self.vp.round)
            .group_by(self.m.Reaction.message_id, self.m.Reaction.emoji)
        ):
            reactions.setdefault(message_id, {})[emoji] = count
        urls: Dict[str, List[Dict[str, Any]]] = {}
        for row in self.s.scalars(select(self.m.MessageUrl).where(self.m.MessageUrl.message_id.in_(ids))):
            urls.setdefault(row.message_id, []).append({"url": row.url, "domain": row.domain})
        extras = self._extras(ids)
        return [self._item(m, state, accounts, titles, reactions, urls, parents, extras) for m, state in rows]

    # -- chat list -------------------------------------------------------------------------
    def _member_counts(self, chat_ids: List[str]) -> Dict[str, int]:
        r = self.vp.round
        m = self.m
        rows = self.s.execute(
            select(m.ChatMember.chat_id, func.count())
            .where(
                m.ChatMember.chat_id.in_(chat_ids),
                m.ChatMember.role.in_(tuple(self.views.ACTIVE_ROLES)),
                m.ChatMember.joined_round <= r,
                or_(m.ChatMember.left_round.is_(None), m.ChatMember.left_round > r),
            )
            .group_by(m.ChatMember.chat_id)
        )
        return {cid: n for cid, n in rows}

    def _readable_after(self, chat, ordered_desc: bool, limit: int, after_key=None, skip_own=False):
        """Readable messages of a chat newest (or oldest) first, optionally after a (sim_ts, id) key."""
        m = self.m
        query = select(m.Message).where(m.Message.chat_id == chat.id, m.Message.round_id <= self.vp.round)
        if after_key is not None:
            ts, mid = after_key
            query = query.where(or_(m.Message.sim_ts > ts, and_(m.Message.sim_ts == ts, m.Message.id > mid)))
        order = (m.Message.sim_ts.desc(), m.Message.id.desc()) if ordered_desc else (m.Message.sim_ts, m.Message.id)
        out = []
        for row in self.s.scalars(query.order_by(*order).execution_options(yield_per=100)):
            state = self._message_state(chat, row)
            if state is None:
                continue
            if skip_own and self.vp.kind == "account" and row.sender_account_id == self.vp.account_id:
                continue
            out.append((row, state))
            if limit and len(out) >= limit:
                break
        return out

    def chat_list(self) -> List[Dict[str, Any]]:
        m = self.m
        chats = list(self.s.scalars(select(m.Chat).order_by(m.Chat.title, m.Chat.id)))
        if self.vp.kind == "account":
            member_of = {
                row.chat_id
                for row in self.s.scalars(
                    select(m.ChatMember).where(m.ChatMember.account_id == self.vp.account_id)
                )
                if self.visibility.is_active_member(
                    self.views.MemberView(row.role, {}, row.joined_round, row.left_round), self.vp.round
                )
            }
            chats = [c for c in chats if c.id in member_of]
        visible = [c for c in chats if self._chat_visible(c)]
        counts = self._member_counts([c.id for c in visible])
        markers = {}
        if self.vp.kind == "account":
            markers = {
                row.chat_id: row
                for row in self.s.scalars(
                    select(m.ReadMarker).where(m.ReadMarker.account_id == self.vp.account_id)
                )
            }
        out = []
        for chat in visible:
            last = self._readable_after(chat, True, 1)
            item = {
                "id": chat.id,
                "title": chat.title or chat.id,
                "type": chat.type,
                "visibility": chat.visibility,
                "is_forum": bool(chat.is_forum),
                "linked_discussion_chat_id": chat.linked_discussion_chat_id,
                "members": counts.get(chat.id, 0),
                "last": None,
                "hue": avatar_hue(chat.id),
            }
            if last:
                row, state = last[0]
                dto = self._items(last)[0]
                item["last"] = {
                    "id": row.id,
                    "round": row.round_id,
                    "sim_ts": dto["sim_ts"],
                    "day": dto["day"],
                    "slot": dto["slot"],
                    "author": (dto["sender"] or {}).get("username"),
                    "text": "" if state == "deleted" else dto["text"][:PREVIEW_CHARS],
                    "deleted": state == "deleted",
                }
            if self.vp.kind == "account":
                item["unread"] = self._unread(chat, markers.get(chat.id))
            out.append(item)
        out.sort(key=lambda i: (i["last"]["round"] if i["last"] else 0, i["id"]), reverse=True)
        return out

    def _unread(self, chat, marker) -> int:
        key = None
        if marker is not None and marker.last_read_message_id:
            last = self.s.get(self.m.Message, marker.last_read_message_id)
            if last is not None:
                key = (last.sim_ts, last.id)
        return len(self._readable_after(chat, False, 0, key, skip_own=True))

    # -- history ---------------------------------------------------------------------------
    def history(self, chat_id: str, before: Optional[str] = None, limit: int = DEFAULT_PAGE,
                forum_topic_id: Optional[int] = None, after: Optional[str] = None,
                from_start: bool = False) -> Optional[Dict[str, Any]]:
        """A page of the chat, newest first (the page is shown oldest first by the template).

        ``None`` when the chat does not exist or the viewpoint cannot open it; ``before`` is the id of the
        oldest message of the previous page. ``from_start`` (or ``after``, the id of the newest message already
        shown) pages forward from the beginning of the conversation instead; ``items`` stay newest first and
        ``next_after`` is set when newer messages remain.
        """
        chat = self._chat(chat_id)
        if not self._chat_visible(chat):
            return None
        limit = max(1, min(int(limit), MAX_PAGE))
        m = self.m
        query = select(m.Message).where(m.Message.chat_id == chat_id, m.Message.round_id <= self.vp.round)
        if forum_topic_id is not None:
            query = query.where(m.Message.forum_topic_id == forum_topic_id)
        if before is not None:
            pivot = self.s.get(m.Message, before)
            if pivot is None or pivot.chat_id != chat_id:
                return None
            query = query.where(
                or_(m.Message.sim_ts < pivot.sim_ts, and_(m.Message.sim_ts == pivot.sim_ts, m.Message.id < pivot.id))
            )
        if from_start or after is not None:
            return self._history_forward(chat, query, limit, after)
        picked: List[Tuple[Any, str]] = []
        exhausted = True
        for row in self.s.scalars(
            query.order_by(m.Message.sim_ts.desc(), m.Message.id.desc()).execution_options(yield_per=100)
        ):
            if len(picked) == limit:
                exhausted = False
                break
            state = self._message_state(chat, row)
            if state is not None:
                picked.append((row, state))
        return {
            "chat_id": chat_id,
            "title": chat.title or chat.id,
            "items": self._items(picked),
            "next_before": None if exhausted or not picked else picked[-1][0].id,
            "next_after": None,
        }

    def _history_forward(self, chat, query, limit, after):
        """Oldest-first page of the chat (``after`` is the newest message already shown)."""
        m = self.m
        if after is not None:
            pivot = self.s.get(m.Message, after)
            if pivot is None or pivot.chat_id != chat.id:
                return None
            query = query.where(
                or_(m.Message.sim_ts > pivot.sim_ts, and_(m.Message.sim_ts == pivot.sim_ts, m.Message.id > pivot.id))
            )
        picked: List[Tuple[Any, str]] = []
        exhausted = True
        for row in self.s.scalars(
            query.order_by(m.Message.sim_ts.asc(), m.Message.id.asc()).execution_options(yield_per=100)
        ):
            if len(picked) == limit:
                exhausted = False
                break
            state = self._message_state(chat, row)
            if state is not None:
                picked.append((row, state))
        picked.reverse()  # callers show ``items`` newest first, like the backward pages
        return {
            "chat_id": chat.id,
            "title": chat.title or chat.id,
            "items": self._items(picked),
            "next_before": None,
            "next_after": None if exhausted or not picked else picked[0][0].id,
        }

    # -- thread ----------------------------------------------------------------------------
    def thread(self, message_id: str) -> Optional[Dict[str, Any]]:
        """The root and its replies; for a channel post, also the comments of its discussion group."""
        m = self.m
        root = self.s.get(m.Message, message_id)
        if root is None:
            return None
        chat = self._chat(root.chat_id)
        if not self._chat_visible(chat) or self._message_state(chat, root) is None:
            return None
        rows = [(root, self._message_state(chat, root))]
        candidates = list(
            self.s.scalars(
                select(m.Message)
                .where(
                    m.Message.id != root.id,
                    or_(m.Message.thread_root_id == root.thread_root_id, m.Message.discussion_root_of == root.id),
                    m.Message.round_id <= self.vp.round,
                )
                .order_by(m.Message.sim_ts, m.Message.id)
            )
        )
        for row in candidates:
            row_chat = self._chat(row.chat_id)
            if not self._chat_visible(row_chat):
                continue
            state = self._message_state(row_chat, row)
            if state is not None:
                rows.append((row, state))
        return {"root_id": root.id, "items": self._items(rows)}

    # -- members ---------------------------------------------------------------------------
    def members(self, chat_id: str) -> Optional[List[Dict[str, Any]]]:
        chat = self._chat(chat_id)
        if not self._chat_visible(chat):
            return None
        m = self.m
        r = self.vp.round
        rows = list(
            self.s.scalars(
                select(m.ChatMember)
                .where(m.ChatMember.chat_id == chat_id, m.ChatMember.joined_round <= r)
                .order_by(m.ChatMember.joined_round, m.ChatMember.id)
            )
        )
        accounts = self._accounts(row.account_id for row in rows)
        out = []
        for row in rows:
            left = row.left_round is not None and row.left_round <= r
            role = "left" if left and row.role not in ("banned",) else row.role
            if self.vp.kind != "overview" and role in ("banned", "left"):
                continue
            account = accounts.get(row.account_id)
            out.append(
                {
                    "account_id": row.account_id,
                    "username": getattr(account, "username", row.account_id),
                    "kind": getattr(account, "kind", None),
                    "hue": avatar_hue(row.account_id),
                    "role": role,
                    "joined_round": row.joined_round,
                    "left_round": row.left_round if left else None,
                    "permissions": sorted(k for k, v in (row.permissions or {}).items() if v),
                }
            )
        return out

    def chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """What the info panel of a chat shows (``None`` when the viewpoint cannot open it)."""
        chat = self._chat(chat_id)
        if not self._chat_visible(chat):
            return None
        m = self.m
        owner = self.s.get(m.Account, chat.owner_account_id) if chat.owner_account_id else None
        topics = [
            label
            for (label,) in self.s.execute(
                select(m.Topic.label)
                .join(m.ChatTopic, m.ChatTopic.topic_id == m.Topic.id)
                .where(m.ChatTopic.chat_id == chat_id)
                .order_by(m.Topic.label)
            )
        ]
        discussion = (
            self.s.get(m.Chat, chat.linked_discussion_chat_id) if chat.linked_discussion_chat_id else None
        )
        return {
            "id": chat.id,
            "title": chat.title or chat.id,
            "type": chat.type,
            "visibility": chat.visibility,
            "username": chat.username,
            "description": chat.description,
            "is_forum": bool(chat.is_forum),
            "origin": chat.origin,
            "created_round": chat.created_round,
            "members": self._member_counts([chat.id]).get(chat.id, 0),
            "owner": {"id": owner.id, "username": owner.username} if owner is not None else None,
            "topics": topics,
            "discussion": (
                {"id": discussion.id, "title": discussion.title or discussion.id}
                if discussion is not None and self._chat_visible(discussion)
                else None
            ),
            "hue": avatar_hue(chat.id),
        }

    # -- forum topics ----------------------------------------------------------------------
    def forum_topics(self, chat_id: str) -> Optional[List[Dict[str, Any]]]:
        chat = self._chat(chat_id)
        if not self._chat_visible(chat) or not chat.is_forum:
            return None
        m = self.m
        r = self.vp.round
        out = []
        for row in self.s.scalars(
            select(m.ForumTopic).where(m.ForumTopic.chat_id == chat_id).order_by(m.ForumTopic.topic_number)
        ):
            if row.created_round is not None and row.created_round > r:
                continue
            deleted = row.deleted_round is not None and row.deleted_round <= r
            if deleted and self.vp.kind != "overview":
                continue
            out.append({"id": row.id, "number": row.topic_number, "title": row.title, "deleted": deleted})
        return out

    # -- search ----------------------------------------------------------------------------
    def search(self, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Messages whose text contains ``query``, among the messages the viewpoint can read."""
        query = (query or "").strip()
        if len(query) < 2:
            return []
        m = self.m
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        limit = max(1, min(int(limit), MAX_SEARCH))
        picked: List[Tuple[Any, str]] = []
        stmt = (
            select(m.Message)
            .where(m.Message.round_id <= self.vp.round, m.Message.text.ilike(pattern, escape="\\"))
            .order_by(m.Message.sim_ts.desc(), m.Message.id.desc())
            .execution_options(yield_per=100)
        )
        for row in self.s.scalars(stmt):
            chat = self._chat(row.chat_id)
            if not self._chat_visible(chat):
                continue
            state = self._message_state(chat, row)
            if state == "visible":  # a tombstone has no text to match
                picked.append((row, state))
                if len(picked) >= limit:
                    break
        titles = self._titles(row.chat_id for row, _ in picked)
        items = self._items(picked)
        for item in items:
            item["chat_title"] = titles.get(item["chat_id"], item["chat_id"])
        return items

    def _like(self, query: str) -> str:
        return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

    def find_chats(self, query: str, kinds: Tuple[str, ...] = ("channel", "supergroup", "group"), limit: int = 20):
        """Chats the viewpoint can open whose title, @username or description contain ``query``.

        Unlike the chat list, an account's search also finds public chats it has not joined.
        """
        query = (query or "").strip()
        if len(query) < 1:
            return []
        m = self.m
        pattern = self._like(query)
        stmt = (
            select(m.Chat)
            .where(
                m.Chat.type.in_(kinds),
                or_(
                    m.Chat.title.ilike(pattern, escape="\\"),
                    m.Chat.username.ilike(pattern, escape="\\"),
                    m.Chat.description.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(m.Chat.title, m.Chat.id)
        )
        found = [c for c in self.s.scalars(stmt) if self._chat_visible(c)][: max(1, min(int(limit), 50))]
        counts = self._member_counts([c.id for c in found])
        mine = set()
        if self.vp.kind == "account":
            mine = {
                row.chat_id
                for row in self.s.scalars(
                    select(m.ChatMember).where(m.ChatMember.account_id == self.vp.account_id)
                )
                if row.role not in ("banned", "left")
                and row.joined_round <= self.vp.round
                and (row.left_round is None or row.left_round > self.vp.round)
            }
        return [
            {
                "id": c.id,
                "title": c.title or c.id,
                "type": c.type,
                "username": c.username,
                "visibility": c.visibility,
                "members": counts.get(c.id, 0),
                "hue": avatar_hue(c.id),
                "joined": c.id in mine,
            }
            for c in found
        ]

    def find_accounts(self, query: str, limit: int = 20):
        """Accounts whose username contains ``query`` and who belong to a chat the viewpoint can open."""
        query = (query or "").strip()
        if len(query) < 1:
            return []
        m = self.m
        pattern = self._like(query)
        rows = []
        for acc in self.s.scalars(
            select(m.Account).where(m.Account.username.ilike(pattern, escape="\\")).order_by(m.Account.username)
        ):
            if acc.status == "removed":
                continue
            rows.append(acc)
            if len(rows) >= 200:
                break
        out = []
        for acc in rows:
            chats = self.s.scalars(
                select(m.ChatMember.chat_id).where(
                    m.ChatMember.account_id == acc.id, m.ChatMember.role.notin_(("banned", "left"))
                )
            ).all()
            if any(self._chat_visible(self._chat(cid)) for cid in chats):
                out.append({"id": acc.id, "username": acc.username, "kind": acc.kind, "hue": avatar_hue(acc.id)})
            if len(out) >= max(1, min(int(limit), 50)):
                break
        return out

    # -- profile ---------------------------------------------------------------------------
    def profile(self, account_id: str, include_persona: bool = False) -> Optional[Dict[str, Any]]:
        account = self.s.get(self.m.Account, account_id)
        if account is None:
            return None
        r = self.vp.round
        chats = []
        for row in self.s.scalars(
            select(self.m.ChatMember).where(self.m.ChatMember.account_id == account_id)
        ):
            chat = self._chat(row.chat_id)
            active = row.joined_round <= r and (row.left_round is None or row.left_round > r)
            if not active or row.role in ("banned", "left") or not self._chat_visible(chat):
                continue
            chats.append({"id": chat.id, "title": chat.title or chat.id, "type": chat.type, "role": row.role})
        return {
            "id": account.id,
            "username": account.username,
            "kind": account.kind,
            "status": account.status,
            "language": account.language,
            "persona": (account.persona or {}) if include_persona else None,
            "archetype": account.archetype if include_persona else None,
            "cluster": account.cluster if include_persona else None,
            "opinions": self._opinions(account_id) if include_persona else [],
            "stress_reward": self._stress_reward(account_id) if include_persona else {},
            "hue": avatar_hue(account.id),
            "chats": sorted(chats, key=lambda c: c["title"]),
        }

    def _stress_reward(self, account_id: str, points: int = 30) -> Dict[str, Any]:
        """Stress and reward (0..1) of an account as of the viewpoint's round: the latest value and a short history.

        Empty when the run does not compute them. ``spark`` is ready for an SVG polyline in a 100 x 24 box.
        """
        m = self.m
        rows: Dict[str, List[Tuple[int, float]]] = {}
        for variable, value, tid in self.s.execute(
            select(m.StressReward.variable, m.StressReward.value, m.StressReward.tid)
            .where(
                m.StressReward.uid == account_id,
                m.StressReward.type == "aggregate",
                m.StressReward.tid <= self.vp.round,
            )
            .order_by(m.StressReward.tid)
        ):
            rows.setdefault(variable, []).append((tid, float(value)))
        out: Dict[str, Any] = {}
        for variable, series in rows.items():
            series = series[-points:]
            n = max(1, len(series) - 1)
            spark = " ".join(f"{(i / n * 100):.1f},{(22 - v * 20):.1f}" for i, (_t, v) in enumerate(series))
            out[variable] = {"value": round(series[-1][1], 3), "round": series[-1][0], "spark": spark if len(series) > 1 else ""}
        return out

    def _opinions(self, account_id: str) -> List[Dict[str, Any]]:
        """The latest opinion of an account on every topic it has one on, as of the viewpoint's round."""
        m = self.m
        latest: Dict[str, Any] = {}
        for topic_id, label, value, rnd in self.s.execute(
            select(m.AgentOpinion.topic_id, m.Topic.label, m.AgentOpinion.value, m.AgentOpinion.round_id)
            .join(m.Topic, m.Topic.id == m.AgentOpinion.topic_id)
            .where(m.AgentOpinion.account_id == account_id, m.AgentOpinion.round_id <= self.vp.round)
            .order_by(m.AgentOpinion.round_id, m.AgentOpinion.id)
        ):
            latest[topic_id] = {"topic": label, "value": round(float(value), 3), "round": rnd}
        return sorted(latest.values(), key=lambda o: o["topic"])
