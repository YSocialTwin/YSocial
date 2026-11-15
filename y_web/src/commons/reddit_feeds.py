"""Reddit as a source of feeds: the listing JSON of a subreddit, read as the metadata of a feed.

Reddit is a place content comes from (a host, an address layout), not a platform of the simulation; the names stay
fixed by that data.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, quote, urlparse

# Reddit answers 403 to browser-like (and to feedparser's default) User-Agents sent by scripts; this is the
# descriptive one the simulation client uses.
REDDIT_FEED_USER_AGENT = "YSocial/1.0 RSS Feed Reader"


def is_reddit_feed_url(feed_url):
    host = (urlparse(feed_url).hostname or "").lower()
    return host == "reddit.com" or host.endswith(".reddit.com")


def request_variants(feed_url, browser_headers):
    """(url, headers) attempts for a Reddit feed: the descriptive User-Agent, then through old.reddit.com, then with
    browser-like headers."""
    parsed = urlparse(feed_url)
    accept = (
        "application/json, application/rss+xml;q=0.9, application/xml;q=0.8, */*;q=0.5"
        if parsed.path.lower().endswith(".json")
        else "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"
    )
    descriptive = {"User-Agent": REDDIT_FEED_USER_AGENT, "Accept": accept}
    old_url = parsed._replace(netloc="old.reddit.com").geturl()
    variants = [(feed_url, descriptive)]
    if old_url != feed_url:
        variants.append((old_url, descriptive))
    variants.append((feed_url, {**browser_headers, "Accept": accept}))
    return variants


def normalize_subreddit(value):
    """Normalize a subreddit identifier from a slug, /r/ path, or Reddit URL."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    lowered = raw_value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        parsed = urlparse(raw_value)
        host = parsed.netloc.lower()
        if host.endswith("reddit.com"):
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0].lower() == "r":
                return parts[1].strip().lower()
        return ""

    lowered = lowered[2:] if lowered.startswith("r/") else lowered
    lowered = lowered.strip("/")
    return lowered


def parse_json_listing(feed_url, feed_content):
    """Metadata of a Reddit listing JSON, keeping the original source URL; ``None`` when it is not one."""
    subreddit = normalize_subreddit(feed_url)
    if not subreddit:
        return None

    parsed_url = urlparse(feed_url)
    if not parsed_url.path.lower().endswith(".json"):
        return None

    try:
        payload = json.loads(feed_content.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    children = data.get("children")
    if not isinstance(children, list):
        return None

    site_url = f"https://www.reddit.com/r/{quote(subreddit)}/"

    first_entry = children[0] if children else {}
    first_entry_data = (
        first_entry.get("data", {}) if isinstance(first_entry, dict) else {}
    )
    display_name = str(
        first_entry_data.get("subreddit_name_prefixed") or f"r/{subreddit}"
    ).strip()

    return {
        "name": display_name or f"r/{subreddit}",
        "feed_url": feed_url,
        "url_site": site_url,
        "description": f"Reddit subreddit JSON listing for r/{subreddit}",
        "entries_count": len(children),
    }


def unwrap_media_url(url: str) -> str:
    """The image address inside a ``reddit.com/media?url=...`` wrapper, or ``url`` itself when it is not wrapped."""
    if url and "reddit.com/media?url=" in url:
        wrapped = parse_qs(urlparse(url).query, keep_blank_values=True).get(
            "url", [""]
        )[0]
        if wrapped:
            return wrapped
    return url
