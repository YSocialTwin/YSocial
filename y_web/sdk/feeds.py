"""What the feed pages of a platform take from the core: reading and checking the feeds an experiment is given.

The functions look the core up when called, so what the core (or a test) replaces is what a platform gets.
"""

from __future__ import annotations


def _helper(name):
    from y_web.routes.admin.sub.experiments import _helpers

    return getattr(_helpers, name)


def default_feed_limits() -> dict:
    """The feed limits an experiment starts with."""
    from y_web.routes.admin.sub.experiments._blueprint import DEFAULT_FEED_LIMITS

    return dict(DEFAULT_FEED_LIMITS)


def parse_admin_feed_metadata(feed_url, feed_content):
    from y_web.routes.admin.sub.experiments._feeds import (
        _parse_admin_feed_metadata as target,
    )

    return target(feed_url, feed_content)


def normalize_rss_feed_item(item):
    return _helper("_normalize_rss_feed_item")(item)


def normalize_image_feed_item(item):
    return _helper("_normalize_image_feed_item")(item)


def normalize_image_feeds_payload(feeds):
    return _helper("_normalize_image_feeds_payload")(feeds)


def normalize_subreddit_input(value):
    from y_web.src.content.feeds import normalize_subreddit

    return normalize_subreddit(value)


def parse_required_feed_limit(form_key, cast, label, minimum=None):
    return _helper("_parse_required_feed_limit")(form_key, cast, label, minimum)


def read_feed_with_headers(feed_url):
    return _helper("_read_feed_with_headers")(feed_url)


def unwrap_media_url(url):
    from y_web.src.commons.reddit_feeds import unwrap_media_url as target

    return target(url)


__all__ = [
    "unwrap_media_url",
    "default_feed_limits",
    "normalize_image_feed_item",
    "normalize_image_feeds_payload",
    "normalize_rss_feed_item",
    "normalize_subreddit_input",
    "parse_admin_feed_metadata",
    "parse_required_feed_limit",
    "read_feed_with_headers",
]
