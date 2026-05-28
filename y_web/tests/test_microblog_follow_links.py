from pathlib import Path


def test_suggested_friend_follow_link_targets_profile_owner():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/suggested_friends.html"
    ).read_text(encoding="utf-8")
    assert "/follow/{{ friend['id'] }}/{{ user_id }}" in template
    assert "ys-suggestion-card" in template
    assert "People worth following right now" in template


def test_suggested_page_follow_link_targets_page_owner():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/suggested_pages.html"
    ).read_text(encoding="utf-8")
    assert "/follow/{{ page['id'] }}/{{ user_id }}" in template
    assert "ys-suggestion-card" in template
    assert "Pages aligned with your feed" in template


def test_profile_follow_button_targets_viewed_user():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")
    assert 'method="post"' in template
    assert 'action="/{{exp_id}}/follow/{{ user_id }}/{{ logged_id }}"' in template
    assert "ys-profile-follow-menu-form" in template
    assert "ys-profile-follow-menu-btn" in template
    assert "ys-profile-hero-shell" in template
    assert "ys-profile-hero-actions-row" in template
    assert "People Following Me" in template
    assert "People I Follow" in template
    assert ".ys-profile-hero-actions-row" in css
    assert ".ys-profile-hero-stat__value" in css
    assert ".ys-profile-hero-actions-row {\n  position: absolute;" in css
    assert "ys-profile-hero-kicker" not in template
    assert (
        "data-demo-src=\"{{ cover_image if cover_image else url_for('static', filename='assets/img/demo/bg/4.png') }}\""
        in template
    )
    assert "Unfollow" in template
    assert "Follow" in template


def test_profile_activity_tabs_are_single_row_async_controls():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")
    js = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/mb-profile.js"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert "ys-profile-activity-tabs" in template
    assert 'data-profile-mode="recent"' in template
    assert 'data-profile-mode="comments"' in template
    assert "data-profile-url=" in template
    assert "fetch(apiEndpointFor(config, requestedMode) + '/1'" in js
    assert "window.history.pushState" in js
    assert ".ys-profile-activity-tabs" in css
    assert "flex-wrap: nowrap" in css


def test_microblog_header_search_wires_profiles_hashtags_and_topics():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/header.html"
    ).read_text(encoding="utf-8")
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/microblogging.py"
    ).read_text(encoding="utf-8")
    js = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/mb-header-search.js"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert "data-mb-global-search" in template
    assert 'data-search-endpoint="/{{ exp_id }}/api/header_search"' in template
    assert "Search profiles, hashtags, topics" in template
    assert "mb-header-search.js" in template
    assert "def api_header_search(exp_id):" in source
    assert "User_mgmt.username.ilike" in source
    assert "User_mgmt.is_page != 1" not in source
    assert "Hashtags.hashtag.ilike" in source
    assert "Interests.interest.ilike" in source
    assert '"/{exp_id}/profile/{match.id}/recent/1"' in source
    assert '"Page" if getattr(match, "is_page", 0) == 1 else "Profile"' in source
    assert '"/{exp_id}/hashtag_posts/{match.id}/1"' in source
    assert '"/{exp_id}/interest/{match.iid}/1"' in source
    assert "window.location.href = selected.url" in js
    assert "data-search-url" in js
    assert ".ys-mb-header-search__results" in css
    assert ".ys-mb-header-search__option" in css


def test_profile_template_renders_stress_reward_indicators():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")

    assert "Stress / Reward" in template
    assert "ys-profile-panel-card" in template
    assert "ys-profile-panel-head" in template
    assert "mdi-star-outline" in template
    assert "mdi-alert-circle-outline" in template
    assert 'style="color: #d4a017;"' in template
    assert 'style="color: #d64545;"' in template
    assert "Latest aggregate score" not in template


def test_profile_route_wires_latest_stress_reward_aggregate_context():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text(encoding="utf-8")

    assert "def _stress_reward_enabled_for_exp(exp):" in source
    assert (
        'StressReward.query.filter_by(uid=user_id, variable=variable, type="aggregate")'
        in source
    )
    assert "stress_reward_active=stress_reward_active" in source
    assert "stress_reward_indicator=stress_reward_indicator" in source


def test_profile_about_me_supports_agent_custom_feature_rows():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text(encoding="utf-8")

    assert (
        "{% for custom_key, custom_value in agent_custom_features.items() %}"
        in template
    )
    assert "mdi-tag-outline" in template
    assert "summarize_agent_custom_features(dashboard_agent.id)" in source
    assert "agent_custom_features=agent_custom_features" in source


def test_profile_template_uses_shared_ranked_card_and_profile_panels():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert (
        '{% include "microblogging/components/sidebar_ranked_list_card.html" %}'
        in template
    )
    assert 'ranked_card_title = "Frequently Used Hashtags"' in template
    assert "ys-profile-section-heading__subtitle" in template
    assert "{% if username != logged_username and is_page!=1 and mutual %}" in template
    assert ".ys-profile-section-heading" in css
    assert ".ys-profile-panel-card" in css
    assert ".ys-profile-info-card" in css
    assert ".ys-profile-panel-head" in css


def test_friends_template_uses_compact_cards_and_tab_aware_pagination():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/friends.html"
    ).read_text(encoding="utf-8")
    panel_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/friends_panel.html"
    ).read_text(encoding="utf-8")
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/microblogging.py"
    ).read_text(encoding="utf-8")
    js = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/mb-friends.js"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert "ys-friends-hero-card" in template
    assert 'id="friends-panel"' in template
    assert 'data-friends-api="/{{exp_id}}/api/friends/{{ user_id }}"' in template
    assert "?tab=followers" in panel_template
    assert "?tab=followees" in panel_template
    assert "?tab={{ active_tab }}" in panel_template
    assert 'active_tab = str(request.args.get("tab", "followers")' in source
    assert "def _build_friends_view_model(user_id, page, active_tab):" in source
    assert (
        'active_cards = followers if active_tab == "followers" else followees' in source
    )
    assert "has_next_page = current_page < total_pages" in source
    assert "def api_friends(exp_id, user_id, page=1):" in source
    assert "data-friends-url=" in panel_template
    assert "window.history.pushState" in js
    assert "fetch(apiUrl" in js
    assert ".ys-friends-grid" in css
    assert ".ys-friends-pagination" in css


def test_edit_profile_template_uses_shared_profile_style_sections():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/edit_profile.html"
    ).read_text(encoding="utf-8")
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert "ys-edit-profile-page" in template
    assert "ys-edit-profile-hero" in template
    assert "ys-edit-profile-section" in template
    assert "ys-edit-profile-grid" in template
    assert "Recommendation Preferences" in template
    assert "available_profile_pics" in template
    assert "available_cover_images" in template
    assert "data-profile-pic-gallery" in template
    assert "data-cover-image-gallery" in template
    assert "profile-pic-preview" in template
    assert "cover-image-preview" in template
    assert "mountScrollableImagePicker" in template
    assert "available_profile_pics=available_profile_pics" in source
    assert "available_cover_images=available_cover_images" in source
    assert "cover_image=_get_user_cover_image(user.id)" in source
    assert "_set_user_cover_image(user.id, cover_image)" in source
    assert ".ys-edit-profile-page" in css
    assert ".ys-edit-profile-section" in css
    assert ".ys-edit-profile-grid" in css
    assert ".ys-edit-profile-avatar-selector" in css
    assert ".ys-edit-profile-avatar-gallery" in css
    assert ".ys-edit-profile-cover-selector" in css
    assert ".ys-edit-profile-cover-preview" in css


def test_microblog_templates_render_adhoc_agent_badges():
    posts_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/posts.html"
    ).read_text(encoding="utf-8")
    thread_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/thread-post.html"
    ).read_text(encoding="utf-8")

    assert "item.get('adhoc_agent_badge')" in posts_template
    assert "cm.get('adhoc_agent_badge')" in posts_template
    assert "thread.get('adhoc_agent_badge')" in thread_template
    assert "background: #ebf4ff" in posts_template


def test_microblog_helper_wires_adhoc_agent_badges():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/helpers.py"
    ).read_text(encoding="utf-8")
    thread_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/microblogging.py"
    ).read_text(encoding="utf-8")
    posts_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/src/data_access/posts.py"
    ).read_text(encoding="utf-8")

    assert "_ADHOC_AGENT_BADGE_LABELS" in source
    assert '"stress_attacker": "Stress Attacker"' in source
    assert '"comic_relief": "Comic Relief Agent"' in source
    assert '"adhoc_agent_badge": get_adhoc_agent_badge(user)' in source
    assert '"adhoc_agent_badge": get_adhoc_agent_badge(aa)' in source
    assert '"adhoc_agent_badge": get_adhoc_agent_badge(user)' in thread_source
    assert "_ADHOC_AGENT_BADGE_LABELS" in posts_source
    assert '"adhoc_agent_badge": _adhoc_agent_badge(author)' in posts_source
    assert '"adhoc_agent_badge": _adhoc_agent_badge(user)' in posts_source


def test_sidebar_ranked_list_card_is_shared_and_styled():
    component = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/sidebar_ranked_list_card.html"
    ).read_text(encoding="utf-8")
    feed_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/feed.html"
    ).read_text(encoding="utf-8")
    thread_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/thread.html"
    ).read_text(encoding="utf-8")
    hashtag_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/hashtag.html"
    ).read_text(encoding="utf-8")
    interest_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/interest.html"
    ).read_text(encoding="utf-8")
    emotions_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/emotions.html"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert (
        '{% include "microblogging/components/sidebar_ranked_list_card.html" %}'
        in feed_template
    )
    assert (
        '{% include "microblogging/components/sidebar_ranked_list_card.html" %}'
        in thread_template
    )
    assert (
        '{% include "microblogging/components/sidebar_ranked_list_card.html" %}'
        in hashtag_template
    )
    assert (
        '{% include "microblogging/components/sidebar_ranked_list_card.html" %}'
        in interest_template
    )
    assert (
        '{% include "microblogging/components/sidebar_ranked_list_card.html" %}'
        in emotions_template
    )
    assert "ranked_card_title" in component
    assert "ys-trending-row" in component
    assert ".ys-trending-card" in css
    assert ".ys-trending-tag" in css


def test_sidebar_user_card_is_shared_and_styled():
    component = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/sidebar_user_card.html"
    ).read_text(encoding="utf-8")
    feed_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/feed.html"
    ).read_text(encoding="utf-8")
    thread_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/thread.html"
    ).read_text(encoding="utf-8")
    hashtag_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/hashtag.html"
    ).read_text(encoding="utf-8")
    interest_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/interest.html"
    ).read_text(encoding="utf-8")
    emotions_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/emotions.html"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert (
        '{% include "microblogging/components/sidebar_user_card.html" %}'
        in feed_template
    )
    assert (
        '{% include "microblogging/components/sidebar_user_card.html" %}'
        in thread_template
    )
    assert (
        '{% include "microblogging/components/sidebar_user_card.html" %}'
        in hashtag_template
    )
    assert (
        '{% include "microblogging/components/sidebar_user_card.html" %}'
        in interest_template
    )
    assert (
        '{% include "microblogging/components/sidebar_user_card.html" %}'
        in emotions_template
    )
    assert "Your Profile" in component
    assert "sidebar-current-date" in component
    assert ".ys-sidebar-user-card" in css
    assert ".ys-suggestion-card" in css


def test_context_hero_is_shared_and_styled():
    component = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/context_hero_card.html"
    ).read_text(encoding="utf-8")
    thread_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/thread.html"
    ).read_text(encoding="utf-8")
    hashtag_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/hashtag.html"
    ).read_text(encoding="utf-8")
    interest_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/interest.html"
    ).read_text(encoding="utf-8")
    emotions_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/emotions.html"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert (
        '{% include "microblogging/components/context_hero_card.html" %}'
        in thread_template
    )
    assert (
        '{% include "microblogging/components/context_hero_card.html" %}'
        in hashtag_template
    )
    assert (
        '{% include "microblogging/components/context_hero_card.html" %}'
        in interest_template
    )
    assert (
        '{% include "microblogging/components/context_hero_card.html" %}'
        in emotions_template
    )
    assert "ys-context-hero__eyebrow" in component
    assert "ys-context-hero__focus" in component
    assert ".ys-context-hero" in css
    assert ".ys-context-hero__title" in css


def test_infinite_scroll_supports_profile_mode_reset():
    js = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/infinite-scroll.js"
    ).read_text(encoding="utf-8")

    assert "destroyInfiniteScroll" in js
    assert "window.InfiniteScroll = {" in js
    assert "destroy: destroyInfiniteScroll" in js


def test_microblog_feed_supports_live_refresh_with_existing_recsys_api():
    js = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/mb-feed.js"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/social-components.css"
    ).read_text(encoding="utf-8")

    assert "function probeForNewPosts()" in js
    assert "function startAutoRefresh()" in js
    assert "state.liveRefreshEnabled = Number(config.page || 1) === 1;" in js
    assert (
        "return '/' + config.expId + '/api/feed/' + config.userId + '/' + config.timeline + '/' + config.mode;"
        in js
    )
    assert "InfiniteScroll.init({" in js
    assert "ys-feed-refresh-notice" in js
    assert ".ys-feed-refresh-notice" in css
    assert ".ys-feed-refresh-notice__button" in css


def test_build_thread_tree_handles_uuid_out_of_order_replies():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/helpers.py"
    ).read_text(encoding="utf-8")
    expand_start = source.index("def _expand_tree(")
    recursive_start = source.index("def recursive_visit(")
    helper_scope = {}
    exec(source[expand_start:recursive_start], helper_scope)
    build_thread_tree = helper_scope["build_thread_tree"]

    root_id = "root"
    parent_lookup = {
        "root": None,
        "child-b": "child-a",
        "child-a": "root",
        "child-c": "missing-parent",
    }
    post_to_data = {
        "root": {"post_id": "root", "children": []},
        "child-a": {"post_id": "child-a", "children": []},
        "child-b": {"post_id": "child-b", "children": []},
        "child-c": {"post_id": "child-c", "children": []},
    }

    tree = build_thread_tree(root_id, post_to_data, parent_lookup)

    assert [child["post_id"] for child in tree["children"]] == ["child-a", "child-c"]
    assert [child["post_id"] for child in tree["children"][0]["children"]] == [
        "child-b"
    ]
