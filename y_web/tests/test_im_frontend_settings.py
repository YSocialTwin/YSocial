"""/admin/frontend_settings for instant-messaging experiments (plan section 7)."""

import json

import pytest

from y_web import db
from y_web.tests.test_frontend_settings_generic_suite_panel import (  # noqa: F401
    _login,
    _make_admin_login_user,
    suites_app,
)
from y_web.tests.test_frontend_settings_platforms import _exp, logged  # noqa: F401

IM_KEYS = {
    "im_show_forward_origin": True,
    "im_show_reactions": True,
    "im_show_member_roles": True,
    "im_default_view": "latest",
    "im_allow_time_travel": True,
    "im_public_observer_enabled": True,
    "im_participant_mode_enabled": True,
    "im_participant_poll_seconds": 3,
}


def _get(client, exp_id):
    return client.get(
        f"/admin/frontend_settings/get_settings?exp_id={exp_id}"
    ).get_json()


def _save(client, exp_id, settings):
    return client.post(
        "/admin/frontend_settings/save",
        data=json.dumps({"exp_id": exp_id, "settings": settings}),
        content_type="application/json",
    )


def test_page_lists_instant_messaging(suites_app, logged):
    _exp(suites_app, "instant_messaging", "im-a", "g")
    html = logged.get("/admin/frontend_settings").get_data(as_text=True)
    assert '"type": "instant_messaging"' in html
    assert "Instant messaging" in html
    assert 'id="box-im"' in html


def test_defaults_and_capabilities(suites_app, logged):
    exp = _exp(suites_app, "instant_messaging", "im-b")
    data = _get(logged, exp)
    assert data["platform_type"] == "instant_messaging"
    caps = set(data["capabilities"])
    assert set(IM_KEYS) <= caps
    assert {
        "interaction_post",
        "interaction_comment",
        "interaction_like",
        "interaction_share",
    } <= caps
    for absent in (
        "interaction_dislike",
        "show_trending_hashtags",
        "show_suggested_friends",
        "show_recsys_info",
        "show_annotation_stats",
        "default_content_recsys",
        "onboarding_enabled",
        "filter_bubble_alpha",
        "default_forum_feed_type",
        "default_photo_feed_tab",
    ):
        assert absent not in caps
    for key, value in IM_KEYS.items():
        assert data["settings"][key] == value


def test_im_keys_are_not_offered_to_other_platforms(suites_app, logged):
    for platform in ("forum", "photo_sharing"):
        exp = _exp(suites_app, platform, f"x-{platform}")
        assert not set(IM_KEYS) & set(_get(logged, exp)["capabilities"])


def test_save_load_and_coercion(suites_app, logged):
    exp = _exp(suites_app, "instant_messaging", "im-c")
    assert _save(
        logged,
        exp,
        {
            "im_show_reactions": False,
            "im_default_view": "start",
            "im_participant_poll_seconds": "7",
            "im_allow_time_travel": 0,
        },
    ).get_json() == {"ok": True}
    s = _get(logged, exp)["settings"]
    assert s["im_show_reactions"] is False
    assert s["im_default_view"] == "start"
    assert s["im_participant_poll_seconds"] == 7
    assert s["im_allow_time_travel"] is False
    assert s["im_show_member_roles"] is True  # untouched keys keep their value


@pytest.mark.parametrize(
    "raw,expected", [(0, 1), (-5, 1), (999, 60), ("abc", 3), (None, 3), (12, 12)]
)
def test_poll_seconds_is_clamped(suites_app, logged, raw, expected):
    exp = _exp(suites_app, "instant_messaging", f"im-p{abs(hash(str(raw)))%1000}")
    _save(logged, exp, {"im_participant_poll_seconds": raw})
    assert _get(logged, exp)["settings"]["im_participant_poll_seconds"] == expected


def test_unknown_enum_value_falls_back(suites_app, logged):
    exp = _exp(suites_app, "instant_messaging", "im-d")
    _save(logged, exp, {"im_default_view": "sideways"})
    assert _get(logged, exp)["settings"]["im_default_view"] == "latest"


def test_posts_per_page_is_not_clamped_elsewhere(suites_app, logged):
    exp = _exp(suites_app, "microblogging", "m-keep")
    _save(logged, exp, {"posts_per_page": 500})
    assert _get(logged, exp)["settings"]["posts_per_page"] == 500
