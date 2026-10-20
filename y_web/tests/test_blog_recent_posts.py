"""Dashboard "News from the Agents": the last blog posts are kept in the blog_posts table."""

import importlib
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Newest &amp; best</title><link href="https://y-not.social/blog/2026/new/" rel="alternate"/>
    <published>2026-07-23T10:00:00+00:00</published></entry>
  <entry><title>Middle</title><link href="https://y-not.social/blog/2025/mid/" rel="alternate"/>
    <published>2025-12-03T10:00:00+00:00</published></entry>
  <entry><title>Oldest</title><link href="https://y-not.social/blog/2024/old/" rel="alternate"/>
    <published>2024-08-01T16:00:00+00:00</published></entry>
</feed>"""


@pytest.fixture
def blog(monkeypatch):
    """check_blog wired to an in-memory database through stand-ins for ``y_web``/``BlogPost``."""
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy

    # import the real module first: the stand-ins below only replace what it imports lazily
    module = importlib.import_module("y_web.src.system.check_blog")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    db = SQLAlchemy(app)

    class BlogPost(db.Model):
        __tablename__ = "blog_posts"
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(500))
        published_at = db.Column(db.String(50))
        link = db.Column(db.String(500))
        is_read = db.Column(db.Boolean, default=False)
        latest_check_on = db.Column(db.String(50))

    monkeypatch.setitem(sys.modules, "y_web", SimpleNamespace(db=db))
    monkeypatch.setitem(sys.modules, "y_web.src", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "y_web.src.models", SimpleNamespace(BlogPost=BlogPost))
    monkeypatch.setattr(module, "_last_refresh_attempt", None)
    with app.app_context():
        db.create_all()
        yield SimpleNamespace(module=module, db=db, BlogPost=BlogPost, app=app)


def _feed(blog, monkeypatch, xml=ATOM):
    posts = blog.module.parse_blog_feed(xml)
    monkeypatch.setattr(blog.module, "fetch_blog_posts", lambda limit=6: posts[:limit])
    return posts


def test_parse_atom_and_rss_feeds():
    from y_web.src.system import check_blog

    atom = check_blog.parse_blog_feed(ATOM, 2)
    assert [p["title"] for p in atom] == ["Newest & best", "Middle"]
    rss = check_blog.parse_blog_feed(
        "<rss><channel><item><title>T</title><link>https://x/t</link>"
        "<pubDate>Wed, 02 Oct 2024 13:00:00 GMT</pubDate></item></channel></rss>"
    )
    assert rss == [{"title": "T", "link": "https://x/t", "published_at": "Wed, 02 Oct 2024 13:00:00 GMT"}]
    assert check_blog.parse_blog_feed("<feed xmlns='http://www.w3.org/2005/Atom'/>") == []


def test_parse_blog_date_handles_rss_and_iso():
    from y_web.src.system.check_blog import parse_blog_date

    assert parse_blog_date("Wed, 02 Oct 2024 13:00:00 GMT") == datetime(2024, 10, 2, 13)
    assert parse_blog_date("2026-07-23T10:00:00+02:00") == datetime(2026, 7, 23, 8)
    assert parse_blog_date("2025-12-03T10:00:00Z") == datetime(2025, 12, 3, 10)
    assert parse_blog_date("not a date") is None and parse_blog_date(None) is None


def test_first_run_stores_the_recent_posts_and_only_the_newest_is_unread(blog, monkeypatch):
    _feed(blog, monkeypatch)
    has_new, info = blog.module.update_blog_info_in_db()
    assert has_new and info["title"] == "Newest & best"
    rows = {r.link: r.is_read for r in blog.db.session.query(blog.BlogPost).all()}
    assert rows == {
        "https://y-not.social/blog/2026/new/": False,
        "https://y-not.social/blog/2025/mid/": True,
        "https://y-not.social/blog/2024/old/": True,
    }
    assert [p["title"] for p in blog.module.get_recent_blog_posts(2)] == ["Newest & best", "Middle"]


def test_second_check_adds_nothing_and_keeps_the_unread_banner(blog, monkeypatch):
    _feed(blog, monkeypatch)
    blog.module.update_blog_info_in_db()
    has_new, info = blog.module.update_blog_info_in_db()
    assert has_new and info["title"] == "Newest & best"  # still unread
    assert blog.db.session.query(blog.BlogPost).count() == 3


def test_older_post_stored_later_is_ordered_by_date(blog, monkeypatch):
    blog.db.session.add(
        blog.BlogPost(title="Newest & best", link="https://y-not.social/blog/2026/new/",
                      published_at="2026-07-23T10:00:00+00:00", is_read=True)
    )
    blog.db.session.commit()
    _feed(blog, monkeypatch)
    has_new, _ = blog.module.update_blog_info_in_db()
    assert not has_new  # the newest was already known: no new announcement
    titles = [p["title"] for p in blog.module.get_recent_blog_posts(4)]
    assert titles == ["Newest & best", "Middle", "Oldest"]


def test_unreachable_feed_keeps_what_is_stored(blog, monkeypatch):
    _feed(blog, monkeypatch)
    blog.module.update_blog_info_in_db()
    monkeypatch.setattr(blog.module, "fetch_blog_posts", lambda limit=6: [])
    assert blog.module.update_blog_info_in_db() == (False, None)
    assert len(blog.module.get_recent_blog_posts(4)) == 3


def test_background_refresh_is_throttled_and_skipped_in_tests(blog, monkeypatch):
    started = []
    monkeypatch.setattr(blog.module.threading, "Thread",
                        lambda **kw: SimpleNamespace(start=lambda: started.append(kw)))
    blog.app.config["TESTING"] = True
    assert blog.module.refresh_blog_posts_if_stale(blog.app) is False
    blog.app.config["TESTING"] = False
    assert blog.module.refresh_blog_posts_if_stale(blog.app) is True  # empty table: stale
    blog.module._refresh_lock.release()
    assert blog.module.refresh_blog_posts_if_stale(blog.app) is False  # throttled
    blog.module._last_refresh_attempt = None
    fresh = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    blog.db.session.add(blog.BlogPost(title="x", link="https://x", latest_check_on=fresh))
    blog.db.session.commit()
    assert blog.module.refresh_blog_posts_if_stale(blog.app) is False  # checked recently
