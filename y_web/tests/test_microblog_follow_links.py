from pathlib import Path


def test_suggested_friend_follow_link_targets_profile_owner():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/suggested_friends.html"
    ).read_text(encoding="utf-8")
    assert "/follow/{{ friend['id'] }}/{{ user_id }}" in template


def test_suggested_page_follow_link_targets_page_owner():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/suggested_pages.html"
    ).read_text(encoding="utf-8")
    assert "/follow/{{ page['id'] }}/{{ user_id }}" in template


def test_profile_follow_button_targets_viewed_user():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")
    assert 'method="post"' in template
    assert 'action="/{{exp_id}}/follow/{{ user_id }}/{{ logged_id }}"' in template
    assert "ys-profile-follow-menu-form" in template
    assert "ys-profile-follow-menu-btn" in template
    assert "Unfollow" in template
    assert "Follow" in template


def test_profile_template_renders_stress_reward_indicators():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")

    assert "Stress / Reward" in template
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
    assert 'StressReward.query.filter_by(uid=user_id, variable=variable, type="aggregate")' in source
    assert "stress_reward_active=stress_reward_active" in source
    assert "stress_reward_indicator=stress_reward_indicator" in source


def test_profile_about_me_supports_agent_custom_feature_rows():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/profile.html"
    ).read_text(encoding="utf-8")
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text(encoding="utf-8")

    assert "{% for custom_key, custom_value in agent_custom_features.items() %}" in template
    assert "mdi-tag-outline" in template
    assert "summarize_agent_custom_features(dashboard_agent.id)" in source
    assert "agent_custom_features=agent_custom_features" in source
