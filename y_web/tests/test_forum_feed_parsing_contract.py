from pathlib import Path

import pytest

from y_web.routes.admin.sub.experiments._feeds import _parse_admin_feed_metadata
from y_web.routes.admin.sub.experiments._helpers import _normalize_subreddit_input

pytestmark = pytest.mark.unit

REPO_ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")


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
