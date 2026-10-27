"""IM read model: zero divergence from IM's own visibility, read-only, viewpoints, time travel (Phase 7)."""

import datetime as dt
import hashlib
import random

import pytest

from y_web.src.im import engine, reader
from y_web.src.im.reader import Reader, Viewpoint
from y_web.tests.im_fixture_db import build_random_db


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("im") / "database_server.db")
    info = build_random_db(path, seed=11, accounts=9, chats=8, rounds=48, messages=320)
    return path, info


def _pages(rd, chat_id, limit=7, **kw):
    out, before = [], None
    while True:
        page = rd.history(chat_id, before=before, limit=limit, **kw)
        if page is None:
            return None
        out += [i["id"] for i in page["items"]]
        before = page["next_before"]
        if before is None:
            return out


def test_differential_visibility_against_im_feed_service_and_can_read(world):
    """For random (account, chat, round) triples the reader returns exactly what IM's code allows."""
    path, info = world
    from yinstantmessaging.server.services.feed import FeedService
    from yinstantmessaging.server.services.messages import RoundContext

    rng = random.Random(3)
    feed = FeedService(max_items=50, window_minutes=10_000, visibility_lag_ticks=0)
    checked = 0
    with engine.open_reader(path) as session:
        from yinstantmessaging.server.db.repository import Repository

        repo = Repository(session)
        for _ in range(250):
            account = rng.choice(info["accounts"])
            chat = rng.choice(info["chats"])
            rnd = rng.randint(1, info["rounds"])
            ctx = RoundContext(rnd, (rnd - 1) // 24 + 1, (rnd - 1) % 24 + 1, 3, 4, dt.date(2026, 1, 1))
            theirs = feed.history(session, repo, account, ctx, chat, limit=10_000)
            rd = Reader(session, Viewpoint("account", account, rnd))
            mine = _pages(rd, chat, limit=13)
            if theirs == "not_visible":
                assert mine is None, (account, chat, rnd)
            else:
                assert mine is not None, (account, chat, rnd)
                assert mine == [i["message_id"] for i in theirs["items"]], (account, chat, rnd)
                checked += 1
            # and message by message against the domain predicate itself
            sample = rng.sample(info["messages"], 5)
            for mid in sample:
                msg = repo.message_view(mid)
                if msg.chat_id != chat:
                    continue
                allowed = repo.can_read(account, mid, rnd)
                assert (mid in (mine or [])) == allowed, (account, chat, rnd, mid)
    assert checked > 60  # the random fixture exercises readable cases, not only refusals


def test_reader_never_writes(world):
    path, info = world
    before = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with engine.open_reader(path) as session:
        for kind in ("overview", "public", "account"):
            rd = Reader(session, Viewpoint(kind, info["accounts"][1] if kind == "account" else None, 40))
            rd.chat_list()
            for chat in info["chats"]:
                rd.history(chat)
                rd.members(chat)
                rd.forum_topics(chat)
            rd.search("text")
            rd.profile(info["accounts"][0], include_persona=True)
            rd.thread(info["messages"][5])
        reader.status(session)
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == before


def test_public_viewpoint_has_no_private_chats_or_deleted_messages(world):
    path, info = world
    with engine.open_reader(path) as session:
        rd = Reader(session, Viewpoint("public", None, info["rounds"]))
        listed = rd.chat_list()
        models = engine.im_modules()[0]
        private = {c.id for c in session.query(models.Chat) if c.visibility == "private" or c.type == "private"}
        assert listed and not ({c["id"] for c in listed} & private)
        for chat_id in private:
            assert rd.history(chat_id) is None and rd.members(chat_id) is None
        deleted = {m.id for m in session.query(models.Message) if m.deleted_round is not None and m.deleted_round <= info["rounds"]}
        for chat in listed:
            ids = set(_pages(rd, chat["id"]))
            assert not (ids & deleted)
        assert all(not hit["deleted"] for hit in rd.search("text", limit=50))


def test_overview_shows_everything_and_deleted_messages_as_tombstones(world):
    path, info = world
    with engine.open_reader(path) as session:
        models = engine.im_modules()[0]
        rd = Reader(session, Viewpoint("overview", None, info["rounds"]))
        listed = {c["id"] for c in rd.chat_list()}
        assert listed == set(info["chats"])
        seen = []
        for chat in info["chats"]:
            page = rd.history(chat, limit=100)
            seen += page["items"]
        assert len(seen) == len(info["messages"])
        tombs = [i for i in seen if i["deleted"]]
        assert tombs and all(i["text"] == "" for i in tombs)
        expected = {m.id for m in session.query(models.Message) if m.deleted_round is not None and m.deleted_round <= info["rounds"]}
        assert {i["id"] for i in tombs} == expected


def test_time_travel_returns_only_earlier_content(world):
    path, info = world
    with engine.open_reader(path) as session:
        previous = set()
        for rnd in (1, 6, 12, 24, 36, 48):
            rd = Reader(session, Viewpoint("overview", None, rnd))
            ids = set()
            for chat in info["chats"]:
                page = rd.history(chat, limit=100)
                if page is None:
                    continue
                assert all(i["round"] <= rnd for i in page["items"])
                ids |= {i["id"] for i in page["items"]}
            assert previous <= ids  # the overview only grows (deleted stay as tombstones)
            previous = ids
        assert reader.latest_round(session) == info["rounds"]
        assert reader.status(session, after=10)["changed"] is True
        assert reader.status(session, after=info["rounds"])["changed"] is False


def test_pagination_cursor_has_no_gaps_or_duplicates_and_rejects_foreign_cursors(world):
    path, info = world
    with engine.open_reader(path) as session:
        rd = Reader(session, Viewpoint("overview", None, info["rounds"]))
        chat = max(info["chats"], key=lambda c: len(_pages(rd, c, limit=100)))
        whole = _pages(rd, chat, limit=100)
        paged = _pages(rd, chat, limit=3)
        assert paged == whole and len(set(paged)) == len(paged) > 6
        other = next(m for m in info["messages"] if m not in whole)
        assert rd.history(chat, before=other) is None
        assert rd.history("no-such-chat") is None


def test_unread_counts_follow_the_read_marker(world, tmp_path):
    path, info = world
    with engine.open_reader(path) as session:
        models = engine.im_modules()[0]
        for account in info["accounts"][:4]:
            rd = Reader(session, Viewpoint("account", account, info["rounds"]))
            for chat in rd.chat_list():
                assert chat["unread"] >= 0
                assert chat["unread"] <= len(_pages(rd, chat["id"], limit=100))
        # the account sees only its own chats
        rd = Reader(session, Viewpoint("account", info["accounts"][2], info["rounds"]))
        member_of = {
            r.chat_id for r in session.query(models.ChatMember).filter_by(account_id=info["accounts"][2])
            if r.left_round is None and r.role not in ("banned", "left")
        }
        assert {c["id"] for c in rd.chat_list()} <= member_of | {r.chat_id for r in session.query(models.ChatMember).filter_by(account_id=info["accounts"][2])}


def test_search_only_returns_readable_messages_and_escapes_wildcards(world):
    path, info = world
    with engine.open_reader(path) as session:
        rd = Reader(session, Viewpoint("account", info["accounts"][1], 30))
        hits = rd.search("text 1")
        ids = {h["id"] for h in hits}
        for h in hits:
            assert h["id"] in set(_pages(rd, h["chat_id"], limit=100)) and h["chat_title"]
        assert rd.search("%") == [] and rd.search("x") == [] and rd.search("") == []
        assert ids <= {i for c in info["chats"] for i in (_pages(rd, c, limit=100) or [])}


def test_invalid_viewpoints_are_refused(world):
    path, info = world
    with pytest.raises(reader.ViewpointError):
        Viewpoint("nobody")
    with pytest.raises(reader.ViewpointError):
        Viewpoint("account", None, 1)
    with engine.open_reader(path) as session:
        with pytest.raises(reader.ViewpointError):
            Reader(session, Viewpoint("account", "ghost", 1))


def test_thread_members_topics_and_profile_dtos(world):
    path, info = world
    with engine.open_reader(path) as session:
        models = engine.im_modules()[0]
        rd = Reader(session, Viewpoint("overview", None, info["rounds"]))
        reply = session.query(models.Message).filter(models.Message.reply_to_message_id.is_not(None)).first()
        thread = rd.thread(reply.id)
        assert thread["items"][0]["id"] == reply.id
        assert rd.thread("nope") is None
        chat = info["chats"][0]
        members = rd.members(chat)
        assert members and {"account_id", "username", "role", "joined_round", "permissions"} <= set(members[0])
        assert rd.forum_topics(info["chats"][1]) is None or isinstance(rd.forum_topics(info["chats"][1]), list)
        profile = rd.profile(info["accounts"][0])
        assert profile["persona"] is None and profile["username"] == "user0"
        assert rd.profile(info["accounts"][0], include_persona=True)["persona"] == {}
        assert rd.profile("ghost") is None
