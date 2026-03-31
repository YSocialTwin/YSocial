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
