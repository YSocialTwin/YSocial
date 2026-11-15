"""
RSS feed parsing utilities.

Provides functions to fetch and parse RSS feeds for news article extraction
and content generation in the social media simulation.
"""

from urllib.error import HTTPError, URLError

import feedparser
import requests

from y_web.src.commons.reddit_feeds import (  # noqa: F401
    REDDIT_FEED_USER_AGENT,
    is_reddit_feed_url,
    normalize_subreddit,
    parse_json_listing,
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


def normalize_image_feed_item(item):
    """Normalize an image feed definition."""
    if not isinstance(item, dict):
        return None

    subreddit = normalize_subreddit(item.get("subreddit", ""))
    if not subreddit:
        return None

    interests = item.get("interests") or []
    if not isinstance(interests, list):
        interests = [interests]

    cleaned_interests = []
    seen_interests = set()
    for interest in interests:
        label = str(interest).strip()
        if not label or label in seen_interests:
            continue
        seen_interests.add(label)
        cleaned_interests.append(label)

    return {"subreddit": subreddit, "interests": cleaned_interests}


def normalize_image_feeds_payload(feeds):
    """Validate and sanitize the stored image feeds payload."""
    if not isinstance(feeds, list):
        raise ValueError("Image feeds payload must be a JSON array.")

    normalized_feeds = []
    seen_subreddits = set()
    for item in feeds:
        normalized = normalize_image_feed_item(item)
        if normalized is None:
            continue
        subreddit = (
            str(normalized.get("subreddit")).strip().lower()
            if isinstance(normalized, dict)
            else ""
        )
        if not subreddit:
            continue
        if subreddit in seen_subreddits:
            continue
        seen_subreddits.add(subreddit)
        normalized_feeds.append(normalized)

    return normalized_feeds


def read_feed_with_headers(feed_url):
    """Fetch a feed with explicit headers to avoid upstream blocks."""
    last_http_error = None
    for url, headers in feed_request_variants(feed_url, BROWSER_FEED_HEADERS):
        try:
            response = requests.get(
                url, headers=headers, timeout=15, allow_redirects=True
            )
            if response.status_code in (403, 429) and is_reddit_feed_url(feed_url):
                last_http_error = response
                continue  # try the next variant
            response.raise_for_status()
            return response.content
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None:
                raise HTTPError(
                    feed_url,
                    response.status_code,
                    response.reason,
                    response.headers,
                    None,
                ) from exc
            raise
        except requests.RequestException as exc:
            raise URLError(str(exc)) from exc
    response = last_http_error
    raise HTTPError(
        feed_url, response.status_code, response.reason, response.headers, None
    )
