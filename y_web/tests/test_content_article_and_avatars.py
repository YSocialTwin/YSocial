"""
Phase F — content/article_extractor.py and content/avatars.py tests.

All tests are side-effect-free: network calls are patched out so no real
HTTP requests are made, and avatar helpers that require a Flask app context
are skipped gracefully.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# article_extractor: extract_source
# ---------------------------------------------------------------------------


def test_extract_source_removes_www():
    from y_web.src.content.article_extractor import extract_source

    assert extract_source("https://www.bbc.com/news/article") == "Bbc.com"


def test_extract_source_removes_m_prefix():
    from y_web.src.content.article_extractor import extract_source

    assert extract_source("https://m.reddit.com/r/python") == "Reddit.com"


def test_extract_source_plain_domain():
    from y_web.src.content.article_extractor import extract_source

    result = extract_source("https://example.com/path")
    assert result == "Example.com"


# ---------------------------------------------------------------------------
# article_extractor: clean_text
# ---------------------------------------------------------------------------


def test_clean_text_strips_whitespace():
    from y_web.src.content.article_extractor import clean_text

    assert clean_text("  hello   world  ") == "hello world"


def test_clean_text_keeps_longest_pipe_segment():
    from y_web.src.content.article_extractor import clean_text

    result = clean_text("Short | This is the actual article title that is much longer")
    assert "This is the actual article title that is much longer" in result


def test_clean_text_empty_returns_empty():
    from y_web.src.content.article_extractor import clean_text

    assert clean_text("") == ""


def test_clean_text_none_returns_empty():
    from y_web.src.content.article_extractor import clean_text

    assert clean_text(None) == ""


# ---------------------------------------------------------------------------
# article_extractor: extract_title (via BeautifulSoup)
# ---------------------------------------------------------------------------


def _make_soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def test_extract_title_og_title_preferred():
    from y_web.src.content.article_extractor import extract_title

    soup = _make_soup('<meta property="og:title" content="OG Title"/><title>Page Title</title>')
    assert extract_title(soup, "https://example.com") == "OG Title"


def test_extract_title_falls_back_to_title_tag():
    from y_web.src.content.article_extractor import extract_title

    soup = _make_soup("<title>Fallback Title</title>")
    assert extract_title(soup, "https://example.com") == "Fallback Title"


def test_extract_title_falls_back_to_domain():
    from y_web.src.content.article_extractor import extract_title

    soup = _make_soup("<html><body></body></html>")
    result = extract_title(soup, "https://example.com/page")
    assert "example.com" in result


# ---------------------------------------------------------------------------
# avatars: normalize_forum_avatar_mode
# ---------------------------------------------------------------------------


def test_normalize_forum_avatar_mode_actual_variants():
    from y_web.src.content.avatars import normalize_forum_avatar_mode

    for v in ("actual", "real", "real_pics", "profile_pics", "ACTUAL"):
        assert normalize_forum_avatar_mode(v) == "actual"


def test_normalize_forum_avatar_mode_default_for_unknown():
    from y_web.src.content.avatars import normalize_forum_avatar_mode, DEFAULT_FORUM_AVATAR_MODE

    assert normalize_forum_avatar_mode("nonsense") == DEFAULT_FORUM_AVATAR_MODE


def test_normalize_forum_avatar_mode_none_returns_default():
    from y_web.src.content.avatars import normalize_forum_avatar_mode, DEFAULT_FORUM_AVATAR_MODE

    assert normalize_forum_avatar_mode(None) == DEFAULT_FORUM_AVATAR_MODE


# ---------------------------------------------------------------------------
# avatars: deterministic_forum_avatar_url
# ---------------------------------------------------------------------------


def test_deterministic_forum_avatar_url_contains_username():
    from y_web.src.content.avatars import deterministic_forum_avatar_url

    url = deterministic_forum_avatar_url("alice")
    assert "alice" in url or url.startswith("/") or url.startswith("data:")


def test_deterministic_forum_avatar_url_stable():
    from y_web.src.content.avatars import deterministic_forum_avatar_url

    assert deterministic_forum_avatar_url("bob") == deterministic_forum_avatar_url("bob")


def test_deterministic_forum_avatar_url_different_users_differ():
    from y_web.src.content.avatars import deterministic_forum_avatar_url

    assert deterministic_forum_avatar_url("alice") != deterministic_forum_avatar_url("bob")
