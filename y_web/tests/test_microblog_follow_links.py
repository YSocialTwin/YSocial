from pathlib import Path


def test_suggested_friend_follow_link_targets_profile_owner():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/suggested_friends.html"
    ).read_text(encoding="utf-8")
    assert '/follow/{{ friend[\'id\'] }}/{{ user_id }}' in template


def test_suggested_page_follow_link_targets_page_owner():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/microblogging/components/suggested_pages.html"
    ).read_text(encoding="utf-8")
    assert '/follow/{{ page[\'id\'] }}/{{ user_id }}' in template
