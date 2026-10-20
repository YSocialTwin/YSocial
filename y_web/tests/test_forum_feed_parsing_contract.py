from pathlib import Path

import pytest

from y_web.routes.admin.sub.experiments._feeds import _parse_admin_feed_metadata
from y_web.routes.admin.sub.experiments._helpers import _normalize_subreddit_input

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_normalize_subreddit_input_accepts_slug_and_reddit_urls():
    assert _normalize_subreddit_input("memes") == "memes"
    assert _normalize_subreddit_input("r/memes") == "memes"
    assert _normalize_subreddit_input("https://www.reddit.com/r/memes/") == "memes"
    assert (
        _normalize_subreddit_input(
            "https://old.reddit.com/r/space/comments/abc123/post"
        )
        == "space"
    )
    assert _normalize_subreddit_input("https://example.com/feed") == ""


def test_admin_feeds_js_uses_normalized_subreddit_from_backend():
    content = (
        REPO_ROOT / "y_web" / "static" / "assets" / "js" / "admin-feeds.js"
    ).read_text(encoding="utf-8")

    assert "_currentSubreddit = res.data.subreddit || '';" in content


def test_image_feeds_template_allows_reddit_urls():
    content = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "image_feeds.html"
    ).read_text(encoding="utf-8")

    assert "Reddit subreddit URL" in content
    assert "https://www.reddit.com/r/memes/" in content


def test_forum_image_resource_template_keeps_parse_preview_flow():
    content = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "forum_image_resources.html"
    ).read_text(encoding="utf-8")

    assert 'onclick="parseSubreddit()"' in content
    assert 'id="sample_images"' in content


def test_rss_feed_parser_prefers_feed_metadata_link():
    content = (
        REPO_ROOT / "y_web" / "routes" / "admin" / "sub" / "experiments" / "_feeds.py"
    ).read_text(encoding="utf-8")

    assert 'site_url = str(feed.feed.get("link") or "").strip()' in content
    assert '"url_site": site_url or site_host' in content


def test_forum_rss_resource_template_mentions_json_and_direct_urls():
    content = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "forum_rss_resources.html"
    ).read_text(encoding="utf-8")

    assert "Reddit JSON listing feeds" in content
    assert "Direct article URLs remain experiment-specific" in content


def test_parse_admin_feed_metadata_accepts_reddit_listing_json():
    feed_url = "https://www.reddit.com/r/politics/new.json?limit=100"
    feed_content = b"""
    {
      "data": {
        "children": [
          {
            "data": {
              "subreddit_name_prefixed": "r/politics"
            }
          },
          {
            "data": {
              "subreddit_name_prefixed": "r/politics"
            }
          }
        ]
      }
    }
    """

    parsed = _parse_admin_feed_metadata(feed_url, feed_content)

    assert parsed == {
        "name": "r/politics",
        "feed_url": "https://www.reddit.com/r/politics/new.json?limit=100",
        "url_site": "https://www.reddit.com/r/politics/",
        "description": "Reddit subreddit JSON listing for r/politics",
        "entries_count": 2,
    }


def test_reddit_feed_fetch_uses_descriptive_user_agent_and_falls_back(monkeypatch):
    from y_web.routes.admin.sub.experiments import _helpers

    calls = []

    class Resp:
        def __init__(self, status):
            self.status_code = status
            self.reason = "x"
            self.headers = {}
            self.content = b"{}"

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError("must not be called for handled statuses")

    def fake_get(url, headers=None, **kwargs):
        calls.append((url, headers["User-Agent"]))
        return Resp(403 if len(calls) < 2 else 200)

    monkeypatch.setattr(_helpers.requests, "get", fake_get)
    url = "https://www.reddit.com/r/politics/new.json?limit=100"
    assert _helpers._read_feed_with_headers(url) == b"{}"
    assert calls[0] == (url, _helpers.REDDIT_FEED_USER_AGENT)
    assert calls[1][0].startswith("https://old.reddit.com/r/politics/")

    calls.clear()
    other = "https://example.com/feed.xml"
    monkeypatch.setattr(
        _helpers.requests,
        "get",
        lambda u, headers=None, **k: (calls.append(headers["User-Agent"]), Resp(200))[
            1
        ],
    )
    _helpers._read_feed_with_headers(other)
    assert calls and "Mozilla" in calls[0]


def test_page_feed_fetch_uses_variants_and_parses_content(monkeypatch):
    from y_web.src.content import feeds

    seen = []
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>A</title><link>http://x/a</link><description>S</description></item>
    </channel></rss>"""

    class Resp:
        def __init__(self, status, content=b""):
            self.status_code, self.content = status, content

    def fake_get(url, headers=None, **kwargs):
        seen.append(headers["User-Agent"])
        return Resp(403) if len(seen) == 1 else Resp(200, rss)

    monkeypatch.setattr(feeds.requests, "get", fake_get)
    items = feeds.get_feed("https://www.reddit.com/r/politics/new.rss")
    assert items == [{"title": "A", "summary": "S", "link": "http://x/a"}]
    assert seen[0] == feeds.REDDIT_FEED_USER_AGENT and len(seen) == 2
