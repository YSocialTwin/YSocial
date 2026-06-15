from pathlib import Path


def test_forum_profile_template_renders_stress_reward_card():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/forum/profile.html"
    ).read_text(encoding="utf-8")
    css = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/css/reddit/forum-components.css"
    ).read_text(encoding="utf-8")

    assert "Stress / Reward" in template
    assert "forum-profile-scale-dot reward" in template
    assert "forum-profile-scale-dot stress" in template
    assert ">★<" not in template
    assert ">●<" not in template
    assert ".forum-profile-scale-dot.reward {" in css
    assert ".forum-profile-scale-dot.stress {" in css
    assert ".forum-profile-scale-dot.reward.is-active" in css
    assert ".forum-profile-scale-dot.stress.is-active" in css


def test_forum_profile_template_renders_agent_custom_feature_rows():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/forum/profile.html"
    ).read_text(encoding="utf-8")
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text(encoding="utf-8")

    assert (
        "{% for custom_key, custom_value in agent_custom_features.items() %}"
        in template
    )
    assert "agent_custom_features=agent_custom_features" in source
    assert "summarize_agent_custom_features(dashboard_agent.id)" in source


def test_forum_profile_route_allows_stress_reward_context():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text(encoding="utf-8")

    assert (
        'getattr(exp, "platform_type", "") not in {"microblogging", "forum"}' in source
    )
    assert "stress_reward_active=stress_reward_active" in source
    assert "stress_reward_indicator=stress_reward_indicator" in source


def test_forum_interview_route_supports_uuid_backed_users():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/forum.py"
    ).read_text(encoding="utf-8")

    assert (
        'logged_id = exp_user.id if exp_user else (getattr(current_user, "id", 0) or 0)'
        in source
    )
    assert "mentions = get_unanswered_mentions(mention_username)" in source
    assert "int(exp_user.id)" not in source


def test_stress_reward_scale_marks_any_positive_value():
    from y_web.routes.social.common import _stress_reward_scale_level

    assert _stress_reward_scale_level(0.0) == 0
    assert _stress_reward_scale_level(0.01) == 1
    assert _stress_reward_scale_level(0.06) == 1
    assert _stress_reward_scale_level(0.21) == 2


def test_admin_schedule_no_longer_caps_hpc_groups():
    schedule_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_schedule.py"
    ).read_text(encoding="utf-8")
    settings_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/admin/settings.html"
    ).read_text(encoding="utf-8")

    assert "hpc_count >= MAX_HPC_PER_GROUP" not in schedule_source
    assert "min(MAX_HPC_PER_GROUP, experiments_per_group)" not in schedule_source
    assert "grouped up to 4 per group" not in settings_template
