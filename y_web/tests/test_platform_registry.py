"""The registry of the simulation platforms (plan, phase F1)."""

import pytest

from y_web.platforms import PlatformProvider, registry


def test_the_built_in_platforms_are_registered_in_menu_order():
    assert registry.keys() == [
        "microblogging",
        "forum",
        "photo_sharing",
        "instant_messaging",
        "dating",
    ]


def test_an_unknown_or_empty_platform_has_no_provider():
    assert registry.get("video_chat") is None
    assert registry.get(None) is None
    assert registry.get("") is None


def test_a_platform_key_cannot_be_registered_twice(monkeypatch):
    monkeypatch.setattr(registry, "_PROVIDERS", dict(registry._PROVIDERS))

    class Another(PlatformProvider):
        key = "forum"

    with pytest.raises(ValueError, match="already provided"):
        registry.register(Another())


def test_a_provider_needs_a_key():
    with pytest.raises(ValueError, match="no platform key"):
        registry.register(PlatformProvider())


@pytest.mark.parametrize(
    "key, expected",
    [
        ("microblogging", "/3/feed/7/feed/rf/1"),
        ("forum", "/3/rfeed/7/rfeed/rf/1"),
        ("photo_sharing", "/3/photo/feed/all/feed/rf/1"),
        ("instant_messaging", None),
        ("dating", None),
    ],
)
def test_entry_url_of_each_built_in_platform(key, expected):
    assert registry.get(key).entry_url(3, 7) == expected


def test_landing_redirect_follows_the_platform_of_the_experiment(app):
    from types import SimpleNamespace as NS

    from y_web.routes.social.common import _landing_redirect

    with app.test_request_context():
        forum = _landing_redirect(NS(platform_type="forum", idexp=3), 7)
        assert forum.status_code == 302
        assert forum.location == "/3/rfeed/7/rfeed/rf/1"
        for without_landing in ("instant_messaging", "dating", "video_chat", None):
            assert (
                _landing_redirect(NS(platform_type=without_landing, idexp=3), 7) is None
            )
