"""Text, article and annotation helpers the pages and the actions of a platform share."""

from __future__ import annotations

from y_web.src.llm import Annotator, ContentAnnotator  # noqa: F401
from y_web.src.llm.url_summarizer import UrlSummarizer  # noqa: F401


def extract_article_info(url):
    """Extract comprehensive metadata from a web page URL."""
    from y_web.src.content.article_extractor import extract_article_info as target

    return target(url)


def process_reddit_post(text, allow_legacy_blankline_title=True):
    """Process and format Reddit-style post text."""
    from y_web.src.content.text_utils import process_reddit_post as target

    return target(text, allow_legacy_blankline_title)


def strip_tags(html):
    """Remove all HTML tags from text content."""
    from y_web.src.content.text_utils import strip_tags as target

    return target(html)


def toxicity(text, username, post_id, db):
    """Calculate toxicity scores using Google's Perspective API."""
    from y_web.src.content.text_utils import toxicity as target

    return target(text, username, post_id, db)


def vader_sentiment(text):
    """Calculate sentiment scores using VADER sentiment analysis."""
    from y_web.src.content.text_utils import vader_sentiment as target

    return target(text)


def normalize_hashtag(tag):
    """``tag`` as it is stored: no leading ``#``, NFC, no surrounding spaces or apostrophes; ``""`` if nothing is left."""
    from y_web.hashtag_text import normalize_hashtag as target

    return target(tag)


__all__ = [
    "Annotator",
    "ContentAnnotator",
    "UrlSummarizer",
    "extract_article_info",
    "normalize_hashtag",
    "process_reddit_post",
    "strip_tags",
    "toxicity",
    "vader_sentiment",
]
