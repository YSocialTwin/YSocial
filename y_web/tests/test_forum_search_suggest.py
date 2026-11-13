"""Ranking helpers behind the forum live search (/api/forum_search)."""

from y_web.routes.social import forum as forum_routes


def test_phrase_and_prefix_rank_above_partial_matches():
    tokens = ["linux", "kernel"]
    full = forum_routes._search_score("Linux kernel news", tokens, "linux kernel")
    partial = forum_routes._search_score("Linux desktop", tokens, "linux kernel")
    none = forum_routes._search_score("Windows update", tokens, "linux kernel")
    assert full > partial > none == 0.0


def test_fuzzy_match_tolerates_typos():
    names = ["JuliaWade", "CarlosGaines", "BrianWolf"]
    assert forum_routes._fuzzy_match("Julia Wde", names, 2) == ["JuliaWade"]
    assert forum_routes._fuzzy_match("zzzzzz", names, 2) == []


def test_search_assets_wired_in_header():
    from pathlib import Path

    root = Path(forum_routes.__file__).resolve().parents[1]
    header = (root / "templates/forum/header.html").read_text()
    assert "forum-search-suggest.js" in header and "data-i18n" in header
