"""Fixed-order content recommenders: reading the order the experiment authors defined (``fixed_recsys_order``)."""

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import Session, declarative_base

from y_web.sdk import fixed_recsys as fr

Base = declarative_base()


class FakePost(Base):
    __tablename__ = "post"
    id = Column(Integer, primary_key=True)
    comment_to = Column(Integer, default=-1)
    tweet = Column(String)


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    for i, c in ((1, -1), (2, -1), (3, -1), (4, 1), (5, -1)):
        session.add(FakePost(id=i, comment_to=c, tweet=f"p{i}"))
    session.commit()
    monkeypatch.setattr(fr, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(fr, "Post", SimpleNamespace(id=FakePost.id, query=session.query(FakePost)))
    return session


def define(session, name, ids):
    session.execute(text(f"CREATE TABLE IF NOT EXISTS {fr.TABLE} (recsys_name TEXT, position INTEGER, post_id TEXT)"))
    for pos, pid in enumerate(ids):
        session.execute(text(f"INSERT INTO {fr.TABLE} VALUES (:n, :p, :i)"), {"n": name, "p": pos, "i": str(pid)})
    session.commit()


def paginate(items, page, per_page, total):
    return SimpleNamespace(items=items, page=page, per_page=per_page, total=total)


def test_mode_names():
    assert fr.is_fixed_mode("fixed:Alpha") and fr.is_fixed_mode(" FIXED: Alpha ")
    assert not fr.is_fixed_mode("fixed:") and not fr.is_fixed_mode("ReverseChrono") and not fr.is_fixed_mode(None)
    assert fr.canonical(" FIXED:  Alpha ") == "fixed:Alpha"


def test_no_definition_means_no_recommenders(env):
    assert fr.fixed_recsys_names() == []
    assert fr.ordered_post_ids("x") == []


def test_feed_shows_only_the_listed_posts_in_the_authors_order(env):
    define(env, "Alpha", [3, 1, 5])
    define(env, "Beta", [2])
    assert fr.fixed_recsys_names() == ["Alpha", "Beta"]
    page = fr.fixed_posts("fixed:Alpha", 1, 10, paginate)
    assert [p.id for p in page.items] == [3, 1, 5]   # post 2 is hidden, the order is the authors'
    assert page.total == 3


def test_comments_and_missing_posts_are_skipped_and_pages_are_cut(env):
    define(env, "Alpha", [4, 99, 3, 1, 2, 5])
    assert [p.id for p in fr.fixed_posts("fixed:Alpha", 1, 2, paginate).items] == [3, 1]
    last = fr.fixed_posts("fixed:Alpha", 2, 2, paginate)
    assert [p.id for p in last.items] == [2, 5] and last.total == 4
    assert fr.fixed_posts("fixed:Alpha", 3, 2, paginate).items == []
