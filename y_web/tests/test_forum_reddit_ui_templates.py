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
    assert "id=\"child-{{ thread['post_id'] }}\"" in _read("components/list.html")
    assert "fr-collapse" in _read("components/list.html")
    assert "toggle-reply-button" in _read("components/thread-post.html")
    assert "forum-thread.js" in _read("thread.html")
    assert (ROOT / "static/assets/js/reddit/forum-thread.js").exists()


def test_profile_css_moves_sidebar_to_right():
    css = (ROOT / "static/assets/css/reddit/forum-reddit.css").read_text()
    assert '"main side"' in css


def test_feed_toolbar_menus_drive_native_select_and_compact_view():
    feed = _read("feed.html")
    assert 'id="feed-type-select"' in feed  # legacy hook kept for async_updates.js
    assert "data-fr-sort" in feed and 'data-fr-view="compact"' in feed
    assert "forum-feed-menus.js" in feed
    js = (ROOT / "static/assets/js/reddit/forum-feed-menus.js").read_text()
    assert "fr-view-compact" in js and "feed-type-select" in js
    css = (ROOT / "static/assets/css/reddit/forum-reddit.css").read_text()
    assert ".fr-view-compact .reddit-post" in css


def test_feed_has_recent_posts_column_fed_by_thread_visits():
    assert "components/recent_posts.html" in _read("feed.html")
    assert 'id="fr-recent-entry"' in _read("thread.html")
    js = (ROOT / "static/assets/js/reddit/forum-recent-posts.js").read_text()
    assert "ysocial.forum.recent." in js and "textContent" in js


def test_profile_tabs_load_in_place():
    assert "forum-profile-tabs.js" in _read("profile.html")
    js = (ROOT / "static/assets/js/forum-profile-tabs.js").read_text()
    assert "pushState" in js and "posts-container" in js and "InfiniteScroll" in js


def test_media_is_kept_in_compact_view_and_thread():
    css = (ROOT / "static/assets/css/reddit/forum-reddit.css").read_text()
    assert ".fr-view-compact .reddit-post:not(.fr-expanded) .article-preview" in css
    assert "post-image" in _read("components/thread-post.html")


def test_compact_rows_can_be_expanded_individually():
    css = (ROOT / "static/assets/css/reddit/forum-reddit.css").read_text()
    assert ".reddit-post:not(.fr-expanded)" in css
    js = (ROOT / "static/assets/js/reddit/forum-feed-menus.js").read_text()
    assert "fr-expand-button" in js and "fr-expanded" in js


def test_post_header_has_single_meta_line_markup():
    posts = _read("components/posts.html")
    assert (
        posts.index("forum-post-community-link")
        < posts.index("post-author-link")
        < posts.index("forum-post-time")
    )
    js = (ROOT / "static/assets/js/reddit/async_updates.js").read_text()
    assert "communityMeta," in js and "more-horizontal" in js


def test_crosspost_button_dialog_and_api_are_wired():
    for page in ("feed.html", "thread.html", "profile.html"):
        assert "crosspost_modal.html" in _read(page)
    assert "fr-crosspost-button" in _read("components/posts.html")
    assert "fr-crosspost-button" in _read("components/thread-post.html")
    js = (ROOT / "static/assets/js/reddit/async_updates.js").read_text()
    assert "fr-crosspost-button" in js
    api = (ROOT / "routes/api/reddit.py").read_text()
    assert "/crosspost/targets" in api and 'post("/<int:exp_id>/crosspost")' in api


def test_crosspost_origin_is_shown_in_cards_and_thread():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    macro = (root / "templates/forum/components/crosspost_origin.html").read_text()
    assert "Crossposted from" in macro and "subforum" in macro
    for rel in ("posts.html", "thread-post.html"):
        src = (root / "templates/forum/components" / rel).read_text()
        assert "crosspost_origin" in src
    js = (root / "static/assets/js/reddit/async_updates.js").read_text()
    assert "fr-crosspost-origin" in js
    css = (root / "static/assets/css/reddit/forum-reddit.css").read_text()
    assert re.search(r"fr-view-compact[^{]*p\.fr-crosspost-origin", css)


def test_federated_repost_wiring():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    forum_js = (root / "static/assets/js/reddit/forum-crosspost.js").read_text()
    assert "federation/repost_targets" in forum_js and "federation/repost" in forum_js
    routes = (root / "routes/interactions/common.py").read_text()
    assert (
        "def federation_repost(" in routes
        and "def federation_repost_targets(" in routes
    )
    for rel in (
        "microblogging/components/posts.html",
        "photo/components/posts.html",
        "im/_message.html",
    ):
        assert "ws_repost_button" in (root / "templates" / rel).read_text(), rel
    assert (root / "static/assets/js/world-simulation-repost.js").exists()


def test_create_community_wiring():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sidebar = (root / "templates/forum/components/sidebar.html").read_text()
    assert "data-fr-create-community" in sidebar and "forum-create-community.js" in sidebar
    assert "/communities" in (root / "static/assets/js/reddit/forum-create-community.js").read_text()
    assert "def api_create_community(" in (root / "routes/api/reddit.py").read_text()
    from y_web.src.forum.actions.posts import COMMUNITY_NAME_RE

    assert COMMUNITY_NAME_RE.fullmatch("linux_2") and not COMMUNITY_NAME_RE.fullmatch("a b")
    assert not COMMUNITY_NAME_RE.fullmatch("ab") and not COMMUNITY_NAME_RE.fullmatch("x" * 21)


def test_available_communities_include_joined_ones():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src/forum/service/queries.py").read_text()
    assert "User_interest.interest_id == Interests.iid" in src
