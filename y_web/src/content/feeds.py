"""
RSS feed parsing utilities.

Provides functions to fetch and parse RSS feeds for news article extraction
and content generation in the social media simulation.
"""

import feedparser
import requests

from y_web.src.commons.reddit_feeds import (  # noqa: F401
    REDDIT_FEED_USER_AGENT,
    is_reddit_feed_url,
    request_variants,
)

BROWSER_FEED_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


def feed_request_variants(feed_url, browser_headers=None):
    """(url, headers) attempts for a feed.

    Sites that block scripts have their own sequence of attempts; the others keep the browser-like headers that
    avoid generic blocks.
    """
    browser_headers = browser_headers or BROWSER_FEED_HEADERS
    if not is_reddit_feed_url(feed_url):
        return [(feed_url, browser_headers)]
    return request_variants(feed_url, browser_headers)


def fetch_feed_content(feed_url, timeout=15):
    """Raw feed bytes, trying the request variants; None when none answers 200."""
    for url, headers in feed_request_variants(feed_url):
        try:
            response = requests.get(
                url, headers=headers, timeout=timeout, allow_redirects=True
            )
        except requests.RequestException:
            continue
        if response.status_code == 200 and response.content:
            return response.content
    return None


def get_feed(url):
    """
    Fetch and parse an RSS feed from a given URL.

    Args:
        url: RSS feed URL to fetch

    Returns:
        List of dictionaries with keys: 'title', 'summary', 'link'
        Returns empty list if entries lack required fields
    """
    content = fetch_feed_content(url)
    feed = feedparser.parse(content if content is not None else url)

    res = []

    for entry in feed.entries:
        try:
            res.append(
                {"title": entry.title, "summary": entry.summary, "link": entry.link}
            )
        except:
            pass

    return res
