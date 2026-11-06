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
        _use_string_primary_keys(("rounds", "user_mgmt", "post"))
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
