"""Forum frontend queries accept opaque (UUID string) ids as produced by YForum."""

import uuid

import pytest
from flask import Flask

from y_web import db
from y_web.src.forum.hot_rank import rank_posts_longtail
from y_web.src.forum.ids import opaque_id


def test_opaque_id_keeps_ints_and_uuids():
    u = str(uuid.uuid4())
    assert opaque_id(5) == 5
    assert opaque_id("12") == 12
    assert opaque_id(u) == u
    assert opaque_id(None) is None
    assert opaque_id(" " + u + " ") == u


def _use_string_primary_keys(tables):
    """Recreate tables the way YForum stores them: string ids instead of INTEGER rowids."""
    from sqlalchemy.schema import CreateTable

    engine = db.engines["db_exp"]
    with engine.begin() as conn:
        for name in tables:
            table = db.metadatas["db_exp"].tables[name]
            ddl = str(CreateTable(table).compile(engine))
            ddl = ddl.replace("\n\tid INTEGER NOT NULL", "\n\tid VARCHAR(36) NOT NULL")
            conn.exec_driver_sql(f"DROP TABLE {name}")
            conn.exec_driver_sql(ddl)


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    exp = f"sqlite:///{tmp_path / 'exp.db'}"
    app.config["SQLALCHEMY_DATABASE_URI"] = exp
    app.config["SQLALCHEMY_BINDS"] = {
        "db_exp": exp,
        "db_admin": f"sqlite:///{tmp_path / 'admin.db'}",
    }
    db.init_app(app)
    with app.app_context():
        db.create_all(bind_key=["db_exp", "db_admin"])
        _use_string_primary_keys(("rounds", "user_mgmt", "post", "reactions", "follow"))
        yield app
        db.session.remove()


def test_feed_pages_with_uuid_ids(app):
    from y_web.src.forum.service import queries as q
    from y_web.src.models import Post, Rounds, User_mgmt

    uid = str(uuid.uuid4())
    rid = str(uuid.uuid4())
    db.session.add(Rounds(id=rid, day=0, hour=1))
    db.session.add(
        User_mgmt(
            id=uid, username="u", password="x", joined_on=0, user_type="agent"
        )
    )
    pids = [str(uuid.uuid4()) for _ in range(3)]
    for pid in pids:
        db.session.add(
            Post(id=pid, tweet=f"post {pid}", round=rid, user_id=uid, thread_id=pid)
        )
    db.session.commit()

    for feed_type in ("new", "hot", "top"):
        page = q.fetch_feed_page(
            viewer_id=uid, page=1, per_page=10, feed_type=feed_type
        )
        assert {p.id for p in page.posts} == set(pids)
    assert q._fetch_report_count_map(pids) == {}
    assert q._fetch_viewer_report_map(uid, pids) == {}
    assert q.fetch_user_communities(uid) == []


def test_rank_posts_uuid_without_day_hour():
    class P:
        def __init__(self, i):
            self.id = i
            self.round = str(uuid.uuid4())

    posts = [P(str(uuid.uuid4())) for _ in range(3)]
    out = rank_posts_longtail(
        posts, reaction_map={}, viewer_id="v", current_time_index=5
    )
    assert len(out) == 3


def test_reply_inbox_rebuilt_with_text_key_for_uuid_users(app):
    from sqlalchemy import text

    from y_web.src.experiment.schema import ensure_text_key_reply_inbox

    engine = db.engines["db_exp"]
    assert ensure_text_key_reply_inbox(engine) is True  # table was INTEGER-keyed
    uid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO reply_inbox_state (user_id, last_seen_reply_id) VALUES (:u, 3)"),
            {"u": uid},
        )
        row = conn.execute(text("SELECT user_id, last_seen_reply_id FROM reply_inbox_state")).one()
    assert tuple(row) == (uid, 3)
    assert ensure_text_key_reply_inbox(engine) is False  # already text: untouched


def test_reply_inbox_untouched_for_integer_users(tmp_path):
    from sqlalchemy import create_engine, text

    from y_web.src.experiment.schema import ensure_text_key_reply_inbox

    engine = create_engine(f"sqlite:///{tmp_path / 'std.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE user_mgmt (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE reply_inbox_state (user_id INTEGER PRIMARY KEY, last_seen_reply_id INTEGER)"
            )
        )
    assert ensure_text_key_reply_inbox(engine) is False


def test_notifications_and_thread_order_follow_seq(app):
    from sqlalchemy import text

    from y_web.src.forum import ordering
    from y_web.src.forum.service import queries as q
    from y_web.src.models import Post, Rounds, User_mgmt

    engine = db.engines["db_exp"]
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE post ADD COLUMN seq INTEGER"))
        conn.execute(text("ALTER TABLE reactions ADD COLUMN seq INTEGER"))
    ordering.forget_cached_schema()

    uid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    db.session.add(Rounds(id=rid, day=0, hour=1))
    db.session.add(User_mgmt(id=uid, username="u", password="x", joined_on=0))
    root = Post(id=str(uuid.uuid4()), tweet="root", round=rid, user_id=uid, comment_to=-1)
    root.thread_id = root.id
    db.session.add(root)
    db.session.commit()
    ids = sorted(str(uuid.uuid4()) for _ in range(4))
    # insertion order is the REVERSE of the (random) id order
    for seq, cid in enumerate(reversed(ids), start=1):
        db.session.add(
            Post(id=cid, tweet=f"c{seq}", round=rid, user_id=uid, comment_to=root.id, thread_id=root.id)
        )
    db.session.commit()
    with engine.begin() as conn:
        for seq, cid in enumerate(reversed(ids), start=1):
            conn.execute(text("UPDATE post SET seq=:s WHERE id=:i"), {"s": seq, "i": cid})

    # the aliased tables of the feed (viewer vote) must resolve ``seq`` too
    page = q.fetch_feed_page(viewer_id=uid, page=1, per_page=10, feed_type="new")
    assert [p.id for p in page.posts] == [root.id]
    comments, _total = q._build_comment_payload(root, uid)
    assert [c["post_id"] for c in comments][:4] == list(reversed(ids))
    ordering.forget_cached_schema()


def test_human_actions_get_uuid_ids_and_seq_in_a_yforum_database(app):
    """Inserts written like the forum actions do (no id, no seq) work on a database that numbers rows itself."""
    from sqlalchemy import text

    from y_web.src.forum import ordering
    from y_web.src.models import Follow, Post, Reactions, Rounds, User_mgmt

    engine = db.engines["db_exp"]
    with engine.begin() as conn:
        for table in ("user_mgmt", "rounds", "post", "follow", "reactions"):
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN seq INTEGER"))
    ordering.forget_cached_schema()

    rid = str(uuid.uuid4())
    db.session.add(Rounds(id=rid, day=0, hour=0))
    u1 = User_mgmt(username="a", password="x", joined_on=0)
    u2 = User_mgmt(username="b", password="x", joined_on=0)
    db.session.add_all([u1, u2])
    db.session.commit()
    post = Post(tweet="hello", round=rid, user_id=u1.id, comment_to=-1)
    db.session.add(post)
    db.session.commit()
    comment = Post(tweet="reply", round=rid, user_id=u2.id, comment_to=post.id, thread_id=post.id)
    like = Reactions(round=rid, user_id=u2.id, post_id=post.id, type="like")
    follow = Follow(user_id=u1.id, follower_id=u2.id, round=rid, action="follow")
    db.session.add_all([comment, like, follow])
    db.session.commit()

    for row in (u1, u2, post, comment, like, follow):
        assert isinstance(row.id, str) and uuid.UUID(row.id)
    with engine.connect() as conn:
        seqs = [r[0] for r in conn.execute(text("SELECT seq FROM post ORDER BY seq"))]
        user_seqs = [r[0] for r in conn.execute(text("SELECT seq FROM user_mgmt ORDER BY seq"))]
    assert seqs == [1, 2] and user_seqs == [1, 2]
    ordering.forget_cached_schema()


def test_standard_databases_are_left_alone(tmp_path):
    """Integer ids and no seq column: the hook changes nothing (the id stays the autoincrement one)."""
    from flask import Flask

    from y_web.src.models import Post, Rounds, User_mgmt

    app = Flask(__name__)
    exp = f"sqlite:///{tmp_path / 'std.db'}"
    app.config["SQLALCHEMY_DATABASE_URI"] = exp
    app.config["SQLALCHEMY_BINDS"] = {"db_exp": exp, "db_admin": f"sqlite:///{tmp_path / 'a.db'}"}
    db.init_app(app)
    with app.app_context():
        db.create_all(bind_key=["db_exp", "db_admin"])
        db.session.add(Rounds(day=0, hour=0))
        db.session.add(User_mgmt(username="a", password="x", joined_on=0))
        db.session.commit()
        user = db.session.query(User_mgmt).first()
        db.session.add(Post(tweet="t", round=1, user_id=user.id, comment_to=-1))
        db.session.commit()
        assert user.id == 1 and db.session.query(Post).first().id == 1
        db.session.remove()


def test_forum_templates_never_write_ids_unquoted_into_javascript():
    """``loggedUserId: {{ logged_id }}`` breaks the whole config object when the id is a UUID."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "templates" / "forum"
    bad = []
    for path in root.glob("*.html"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?i)\b\w*userid\s*:\s*\{\{\s*\w+\s*\}\}", line):
                bad.append(f"{path.name}:{number}: {line.strip()}")
    assert not bad, bad


def test_api_routes_accept_uuid_ids():
    from y_web.routes.api.reddit import _opaque_payload_id

    u = str(uuid.uuid4())
    assert _opaque_payload_id(u) == u
    assert _opaque_payload_id(7) == 7 and _opaque_payload_id("7") == 7
    assert _opaque_payload_id(None) is None and _opaque_payload_id("") is None
    assert _opaque_payload_id(True) is None and _opaque_payload_id([1]) is None
