"""
RSS feed parsing utilities.

Provides functions to fetch and parse RSS feeds for news article extraction
and content generation in the social media simulation.
"""

import feedparser


def get_feed(url):
    """
    Fetch and parse an RSS feed from a given URL.

    Args:
        url: RSS feed URL to fetch

    Returns:
        List of dictionaries with keys: 'title', 'summary', 'link'
        Returns empty list if entries lack required fields
    """
    feed = feedparser.parse(url)

    res = []

    for entry in feed.entries:
        try:
            res.append(
                {"title": entry.title, "summary": entry.summary, "link": entry.link}
            )
        except:
            pass

    return res
