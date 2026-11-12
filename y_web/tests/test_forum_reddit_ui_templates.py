"""Static checks for the Reddit-like forum UI (community, thread, profile)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "templates" / "forum"


def _read(rel):
    return (TPL / rel).read_text(encoding="utf-8")


def test_community_card_uses_real_stats_and_slug_label():
    html = _read("components/community_card.html")
    assert "community_stats['posts']" in html
    assert "{{ current_subforum_label }}" in html
    assert "y/{{ current_subforum_label" not in _read("header.html")


def test_thread_keeps_legacy_hooks_and_adds_collapse():
    assert 'id="child-{{ thread[\'post_id\'] }}"' in _read("components/list.html")
    assert "fr-collapse" in _read("components/list.html")
    assert "toggle-reply-button" in _read("components/thread-post.html")
    assert "forum-thread.js" in _read("thread.html")
    assert (ROOT / "static/assets/js/reddit/forum-thread.js").exists()


def test_profile_css_moves_sidebar_to_right():
    css = (ROOT / "static/assets/css/reddit/forum-reddit.css").read_text()
    assert '"main side"' in css
