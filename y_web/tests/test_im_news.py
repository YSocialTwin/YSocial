"""RSS collection and news pages of an IM experiment."""

import json

import pytest

from y_web.src.im import news

pytestmark = pytest.mark.unit


def _folder(tmp_path, feeds):
    (tmp_path / "rss_feeds.json").write_text(json.dumps(feeds))
    return str(tmp_path)


def test_selected_feeds_read_the_forum_file(tmp_path):
    folder = _folder(tmp_path, [{"name": "BBC", "feed_url": "http://a/rss"}, {"feed_url": "http://a/rss"}, {"feed_url": ""}])
    assert news.selected_feeds(folder) == [{"name": "BBC", "feed_url": "http://a/rss"}]
    assert news.selected_feeds(str(tmp_path / "none")) == []


def test_each_new_feed_becomes_a_news_page_and_known_feeds_do_not_repeat():
    feeds = [{"name": "BBC News", "feed_url": "http://a/rss"}, {"name": "BBC News", "feed_url": "http://b/rss"}, {"name": "Known", "feed_url": "http://k/rss"}]
    pages = news.feed_pages(
        feeds, used_urls=["http://k/rss"], used_usernames=[], topics=["politics"], activity_profile="Always On"
    )
    assert [p["feed_url"] for p in pages] == ["http://a/rss", "http://b/rss"]
    assert pages[0]["username"] == "BBC_News" and pages[1]["username"].startswith("BBC_News_")
    assert all(p["is_page"] == 1 and p["interests"] == {"politics": 1.0} for p in pages)
    assert len({p["id"] for p in pages}) == 2


def test_snapshot_is_written_with_the_runtime_format_and_survives_a_dead_feed(tmp_path):
    rows = {"http://a/rss": [{"title": "t", "summary": "s", "link": "http://a/1", "published": "2026-01-02"}]}

    def fetch(url):
        if url not in rows:
            raise OSError("down")
        return rows[url]

    out = news.write_snapshot(str(tmp_path), ["http://a/rss", "http://dead/rss"], fetch=fetch)
    assert out["written"] and out["feeds"] == {"http://a/rss": 1, "http://dead/rss": 0}
    line = json.loads((tmp_path / "news_snapshot.jsonl").read_text().splitlines()[0])
    assert line["feed_url"] == "http://a/rss" and line["link"] == "http://a/1"
    # an existing snapshot is kept unless asked
    assert news.write_snapshot(str(tmp_path), ["http://a/rss"], fetch=fetch)["written"] is False
    assert news.write_snapshot(str(tmp_path), ["http://a/rss"], fetch=fetch, replace=True)["written"] is True
