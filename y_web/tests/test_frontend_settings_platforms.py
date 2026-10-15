"""/admin/frontend_settings for forum and photo-sharing experiments.

Covers the Type -> Group -> Name selector data, the per-platform capability list, the platform-specific
feed defaults (which replace the microblogging recommenders), the plugin-module platform filter and the
forum/photo template gating (`shared/platform_ui_gating.html`).
"""

import json
from pathlib import Path

import pytest

from y_web import db
from y_web.tests.test_frontend_settings_generic_suite_panel import (  # noqa: F401  (fixtures + helpers)
    _login,
    _make_admin_login_user,
    suites_app,
)


def _exp(app, platform, name, group=""):
    from y_web.src.models import Exps

    with app.app_context():
        exp = Exps(
            platform_type=platform,
            exp_name=name,
            db_name=f"experiments/{name}/database_server.db",
            owner="admin",
            exp_descr="t",
            status=1,
            running=0,
            port=5000,
            exp_group=group,
        )
        db.session.add(exp)
        db.session.commit()
        return exp.idexp


@pytest.fixture
def logged(suites_app):
    client = suites_app.test_client()
    _login(client, _make_admin_login_user(suites_app))
    return client


def test_page_lists_all_three_platforms_with_groups(suites_app, logged):
    _exp(suites_app, "forum", "f-exp", "grpA")
    _exp(suites_app, "photo_sharing", "p-exp", "")
    html = logged.get("/admin/frontend_settings").get_data(as_text=True)
    assert 'id="group-select"' in html
    assert '"type": "forum"' in html and '"group": "grpA"' in html
    assert '"type": "photo_sharing"' in html
    assert "Photo sharing" in html


def test_get_settings_reports_capabilities(suites_app, logged):
    forum = _exp(suites_app, "forum", "f2")
    photo = _exp(suites_app, "photo_sharing", "p2")
    micro = _exp(suites_app, "microblogging", "m2")
    f = logged.get(f"/admin/frontend_settings/get_settings?exp_id={forum}").get_json()
    p = logged.get(f"/admin/frontend_settings/get_settings?exp_id={photo}").get_json()
    m = logged.get(f"/admin/frontend_settings/get_settings?exp_id={micro}").get_json()
    assert f["platform_type"] == "forum" and "interaction_dislike" in f["capabilities"]
    assert (
        "interaction_share" not in f["capabilities"]
        and "annotation_sentiment" not in f["capabilities"]
    )
    assert (
        p["platform_type"] == "photo_sharing"
        and "interaction_share" in p["capabilities"]
    )
    assert (
        "interaction_dislike" not in p["capabilities"]
        and "default_photo_feed_tab" in p["capabilities"]
    )
    assert m["capabilities"] is None  # microblogging keeps everything
    assert [x["name"] for x in f["forum_feed_types"]] == [
        "new",
        "hot",
        "top",
        "most_commented",
    ]


def test_platform_specific_defaults_are_saved_and_validated(suites_app, logged):
    forum = _exp(suites_app, "forum", "f3")
    r = logged.post(
        "/admin/frontend_settings/save",
        json={
            "exp_id": forum,
            "settings": {
                "default_forum_feed_type": "hot",
                "default_photo_feed_tab": "nonsense",
            },
        },
    )
    assert r.get_json()["ok"] is True
    data = logged.get(
        f"/admin/frontend_settings/get_settings?exp_id={forum}"
    ).get_json()
    assert data["settings"]["default_forum_feed_type"] == "hot"
    assert (
        data["settings"]["default_photo_feed_tab"] == "for_you"
    )  # invalid value falls back to the default


def test_modules_declare_platforms(suites_app, logged):
    photo = _exp(suites_app, "photo_sharing", "p3")
    data = logged.get(
        f"/admin/frontend_settings/suite/frontend_adds_on/get?exp_id={photo}"
    ).get_json()
    assert data["ok"] is True and data["platform_type"] == "photo_sharing"
    for module in data["modules"]:
        assert isinstance(module["platforms"], list) and "supported" in module


def _gating(app, platform, **ui):
    base = {
        "interaction_post": True,
        "interaction_comment": True,
        "interaction_like": True,
        "interaction_dislike": True,
        "interaction_share": True,
        "notifications_menu": True,
        "show_post_time": True,
    }
    base.update(ui)
    with app.test_request_context("/"):
        return app.jinja_env.get_template("shared/platform_ui_gating.html").render(
            ui=base, platform_ui=platform
        )


def test_gating_hides_only_switched_off_controls(suites_app):
    assert "<style>" not in _gating(suites_app, "forum")
    out = _gating(
        suites_app, "forum", interaction_dislike=False, notifications_menu=False
    )
    assert 'data-action="dislike"' in out and "reply-notif-bell" in out
    assert 'data-action="like"' not in out
    photo = _gating(
        suites_app, "photo", interaction_share=False, interaction_comment=False
    )
    assert "data-photo-post-share" in photo and "data-photo-comment-reply" in photo
    assert "data-photo-post-like" not in photo
    assert (
        _gating(suites_app, "photo", show_post_time=False).count("data-photo-post-time")
        == 1
    )


def test_plugin_loader_included_in_forum_and_photo_templates():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "templates"
    for rel in (
        "forum/feed.html",
        "forum/thread.html",
        "forum/profile.html",
        "photo/base.html",
    ):
        assert "plugin_loader.html" in (root / rel).read_text(encoding="utf-8"), rel


def test_plugin_core_and_photo_overlay_expose_platform_hooks():
    from pathlib import Path

    js = Path(__file__).resolve().parents[1] / "static" / "assets" / "js"
    assert "platform" in (js / "plugin-core.js").read_text(encoding="utf-8")
    overlay = (js / "photo-overlays.js").read_text(encoding="utf-8")
    assert "data-photo-post-id" in overlay and "ys:photo-post-rendered" in overlay


def test_manifest_for_platform_drops_scoped_parameters_and_empty_sections():
    from y_web.routes.admin.sub.experiments._frontend_settings import (
        _manifest_for_platform,
    )

    manifest = {
        "parameter_sections": [{"key": "a"}, {"key": "b", "platforms": ["forum"]}],
        "parameters": [
            {"name": "x", "section": "a"},
            {"name": "y", "section": "b", "platforms": ["forum"]},
        ],
    }
    sections, params = _manifest_for_platform(manifest, "photo_sharing")
    assert [s["key"] for s in sections] == ["a"] and [p["name"] for p in params] == [
        "x"
    ]
    sections, params = _manifest_for_platform(manifest, "forum")
    assert [s["key"] for s in sections] == ["a", "b"] and len(params) == 2


def test_dispatch_platform_event_is_inert_without_suites(monkeypatch):
    from y_web.src.external_runtime import plugin_loader

    monkeypatch.setattr(plugin_loader, "_REGISTERED_SUITES", {})
    assert plugin_loader.dispatch_platform_event(object(), 1, "photo_created", {}) == 0


def test_show_suggested_friends_setting(suites_app, logged):
    forum = _exp(suites_app, "forum", "f9")
    photo = _exp(suites_app, "photo_sharing", "p9")
    micro = _exp(suites_app, "microblogging", "m9")
    g = lambda e: logged.get(
        f"/admin/frontend_settings/get_settings?exp_id={e}"
    ).get_json()
    assert (
        "show_suggested_friends" not in g(forum)["capabilities"]
    )  # forum has no such box
    assert "show_suggested_friends" in g(photo)["capabilities"]
    assert g(micro)["capabilities"] is None
    assert g(photo)["settings"]["show_suggested_friends"] is True  # default on
    r = logged.post(
        "/admin/frontend_settings/save",
        json={"exp_id": photo, "settings": {"show_suggested_friends": False}},
    )
    assert r.get_json()["ok"] is True
    assert g(photo)["settings"]["show_suggested_friends"] is False


def test_suggested_friends_templates_are_gated():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "templates"
    assert "ui.show_suggested_friends" in (root / "microblogging/feed.html").read_text(
        encoding="utf-8"
    )
    photo = (root / "photo/feed.html").read_text(encoding="utf-8")
    assert (
        "photo-feed-layout--no-rail" in photo and "ui.show_suggested_friends" in photo
    )
    admin = (root / "admin/frontend_settings.html").read_text(encoding="utf-8")
    assert "<h3>Annotations</h3>" in admin and "<h3>Post Annotations</h3>" not in admin


def test_recsys_info_and_annotation_stats_settings(suites_app, logged):
    from y_web.src.models import FrontendAddsOnExpModuleSettings

    photo = _exp(suites_app, "photo_sharing", "p10")
    forum = _exp(suites_app, "forum", "f10")
    g = lambda e: logged.get(
        f"/admin/frontend_settings/get_settings?exp_id={e}"
    ).get_json()
    s = lambda e, **kw: logged.post(
        "/admin/frontend_settings/save", json={"exp_id": e, "settings": kw}
    )
    caps = g(photo)["capabilities"]
    assert "show_recsys_info" in caps and "show_annotation_stats" in caps
    assert "show_recsys_info" not in g(forum)["capabilities"]
    data = g(photo)
    assert (
        data["settings"]["show_recsys_info"] is False
        and data["settings"]["show_annotation_stats"] is False
    )
    assert data["annotation_module_enabled"] is False
    # the statistics toggle cannot be switched on while the annotation add-on is off for the experiment
    assert (
        s(photo, show_recsys_info=True, show_annotation_stats=True).get_json()["ok"]
        is True
    )
    st = g(photo)["settings"]
    assert st["show_recsys_info"] is True and st["show_annotation_stats"] is False
    with suites_app.app_context():
        db.session.add(
            FrontendAddsOnExpModuleSettings(
                exp_id=photo,
                module_id="post_annotation",
                enabled=True,
                config_json="{}",
            )
        )
        db.session.commit()
    assert g(photo)["annotation_module_enabled"] is True
    s(photo, show_annotation_stats=True)
    assert g(photo)["settings"]["show_annotation_stats"] is True


def test_side_boxes_render_recsys_and_stats_only_when_asked(suites_app):
    from y_web.routes.social.helpers import _content_recsys_info

    def render(**ctx):
        with suites_app.test_request_context("/"):
            return suites_app.jinja_env.get_template(
                "shared/annotation_side_boxes.html"
            ).render(**ctx)

    module = [
        {
            "module_id": "post_annotation",
            "api_base": "/7/api/plugins/frontend_adds_on/post_annotation",
        }
    ]
    assert "ys-recsys-box" not in render(
        ui={}, recsys_info=None
    ) and "ys-annostats-box" not in render(ui={})
    info = {
        "name": "ReverseChrono",
        "label": "Reverse chronological",
        "description": "Newest first.",
    }
    out = render(ui={}, recsys_info=info)
    assert (
        "Reverse chronological" in out
        and "Newest first." in out
        and "ys-annostats-box" not in out
    )
    # statistics need the toggle AND the add-on module
    assert "ys-annostats-box" not in render(
        ui={"show_annotation_stats": True}, frontend_adds_on_modules=[]
    )
    out = render(ui={"show_annotation_stats": True}, frontend_adds_on_modules=module)
    assert 'data-api="/7/api/plugins/frontend_adds_on/post_annotation/my_stats"' in out
    # the behaviour lives in a static file (no new inline script: see test_phaseT6_js_extraction)
    assert "ys-annotation-stats.js" in out and "<script>" not in out
    js = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "assets"
        / "js"
        / "ys-annotation-stats.js"
    ).read_text(encoding="utf-8")
    assert "ys:annotation-saved" in js and "ys-annostats-box" in js
    assert "ys-annostats-box" not in render(
        ui={"show_annotation_stats": False}, frontend_adds_on_modules=module
    )
    with suites_app.app_context():
        assert (
            _content_recsys_info("ReverseChrono", {"show_recsys_info": False}) is None
        )
        got = _content_recsys_info("rcp", {"show_recsys_info": True})
        assert (
            got["name"] == "ReverseChronoPopularity"
            and "reacted" in got["description"].lower()
        )
        unknown = _content_recsys_info("Whatever", {"show_recsys_info": True})
        assert unknown["description"] and unknown["name"] == "Whatever"


def test_feed_templates_with_side_boxes_compile(suites_app):
    suites_app.jinja_env.filters.setdefault(
        "user_image_id", lambda v: v
    )  # registered by the real app only
    for name in (
        "photo/feed.html",
        "microblogging/feed.html",
        "microblogging/hashtag.html",
        "microblogging/thread.html",
        "admin/frontend_settings.html",
    ):
        assert suites_app.jinja_env.get_template(name) is not None


def test_show_trending_hashtags_setting(suites_app, logged):
    micro = _exp(suites_app, "microblogging", "m11")
    photo = _exp(suites_app, "photo_sharing", "p11")
    g = lambda e: logged.get(
        f"/admin/frontend_settings/get_settings?exp_id={e}"
    ).get_json()
    assert (
        g(micro)["capabilities"] is None
        and g(micro)["settings"]["show_trending_hashtags"] is True
    )
    assert (
        "show_trending_hashtags" not in g(photo)["capabilities"]
    )  # only microblogging has the box
    logged.post(
        "/admin/frontend_settings/save",
        json={"exp_id": micro, "settings": {"show_trending_hashtags": False}},
    )
    assert g(micro)["settings"]["show_trending_hashtags"] is False
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "templates" / "microblogging"
    for name in ("feed.html", "hashtag.html", "thread.html"):
        assert "ui.show_trending_hashtags is not false" in (root / name).read_text(
            encoding="utf-8"
        )
