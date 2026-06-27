from pathlib import Path

from y_web import create_app
from y_web.routes.social.photo import (
    _build_photo_follower_items,
    _build_photo_recommended_items,
    _photo_active_contact_ids,
    _photo_latest_recommendation_ids,
    _photo_media_root,
    _photo_media_url,
    _photo_linkify_text,
    _photo_build_item,
    _photo_search_payload,
    _photo_profile_pic_url,
    _photo_suggested_contacts,
)
from y_web.src.experiment.helpers import get_experiment_engine_uri
from y_web.src.models import Exps


def test_photo_feed_template_uses_collapsible_left_sidebar_and_instagram_layout():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/feed.html"
    ).read_text(encoding="utf-8")
    base_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/base.html"
    ).read_text(encoding="utf-8")

    assert "photo-shell" in base_template
    assert "data-photo-sidebar-toggle" in base_template
    assert "photo-sidebar__item{% if photo_active_nav == 'home' %} is-active{% endif %}" in Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/components/sidebar.html"
    ).read_text(encoding="utf-8")
    assert "photo_home_url" in Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/components/sidebar.html"
    ).read_text(encoding="utf-8")
    assert "photo-stories" in template
    sidebar_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/components/sidebar.html"
    ).read_text(encoding="utf-8")
    assert "YSocial_purple.png" in sidebar_template
    assert "YSocial_l_purple.png" in sidebar_template
    assert "photo-feed-layout" in template
    assert "microblogging/components/chat_panel.html" in base_template
    assert "photo/feed" in template
    assert "photo/components/sidebar.html" in base_template
    assert "photo-overlays.js" in base_template
    assert "data-photo-share-overlay" in base_template
    assert "photo-feed-tab" in template
    assert "Previous</a>" not in template
    assert "Next</a>" not in template
    assert "Experiment notes" not in template
    assert "Experiment details" not in template
    assert "Mostra tutto" not in template
    assert "See all" in template
    assert "photo-feed-body" in template
    assert "photo-base-body" in base_template
    assert "background: #fff" in base_template
    assert "position: fixed" in base_template
    assert "margin-left: 244px" not in template
    assert "Suggestions for you" in template
    posts_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/components/posts.html"
    ).read_text(encoding="utf-8")
    assert "data-photo-open-post" in posts_template
    assert "data-photo-post-like" in posts_template
    assert "data-photo-post-bookmark" in posts_template
    assert "data-photo-post-share" in posts_template


def test_photo_routes_do_not_rely_on_recsys_type_for_feed_rendering():
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/photo.py"
    ).read_text(encoding="utf-8")
    template_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/feed.html"
    ).read_text(encoding="utf-8")
    auth_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/auth/routes.py"
    ).read_text(encoding="utf-8")
    common_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/common.py"
    ).read_text(encoding="utf-8")
    admin_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py"
    ).read_text(encoding="utf-8")

    assert "photos p" in route_source
    assert "stories s" in route_source
    assert "photo_media" in route_source
    assert "api/photo/feed" in route_source
    assert "recommendations" in route_source
    assert "follow" in route_source
    assert "recsys_type" not in route_source
    assert "photo_sharing" in auth_source
    assert "photo_sharing" in common_source
    assert "photo_sharing" in admin_source
    assert "ensure_experiment_user" in route_source
    assert "photo/profile" in route_source
    assert "api/photo/share" in route_source
    assert "_photo_store_uploaded_media" in route_source
    assert (
        "open_experiment_session" in admin_source
        or "ensure_experiment_user" in admin_source
    )
    assert "photo-feed.js" in template_source


def test_photo_infinite_scroll_uses_query_safe_page_urls_and_custom_end_message():
    infinite_scroll_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/infinite-scroll.js"
    ).read_text(encoding="utf-8")
    photo_feed_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/photo-feed.js"
    ).read_text(encoding="utf-8")

    assert "buildPageUrl" in infinite_scroll_source
    assert "No more posts available." in infinite_scroll_source
    assert "buildPageUrl" in photo_feed_source


def test_photo_experiment_uses_yphotosharing_database_file():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        uri = get_experiment_engine_uri(exp)
        assert uri is not None
        assert uri.endswith("/yphotosharing.db")


def test_photo_media_and_avatar_helpers_resolve_browser_safe_urls():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        media_url = _photo_media_url(
            exp,
            "file:////Users/rossetti/PycharmProjects/YWeb/y_web/experiments/8bd5081e_535f_4cd7_8214_64ffb57de8bc/media/19680620-f4a8-4eac-bf8b-c4901d70fc74.jpg",
        )
        assert media_url == "/1/photo/media/19680620-f4a8-4eac-bf8b-c4901d70fc74.jpg"

        avatar_url = _photo_profile_pic_url(
            exp,
            username="KatherineJones",
            user_id="b49b2daa-0560-466e-bd45-95222c7a4a10",
            raw_profile_pic="",
        )
        assert avatar_url.startswith("/static/assets/img/users/")
        assert avatar_url.endswith(".png")


def test_photo_media_url_preserves_static_profile_assets():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        assert _photo_media_url(exp, "/static/assets/img/users/1081.png") == "/static/assets/img/users/1081.png"


def test_photo_text_linkification_targets_profiles_and_hashtag_search():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None

        linked = _photo_linkify_text(exp, "Hello @KatherineJones #pizza")
        assert '/1/photo/search?q=%23pizza&amp;kind=hashtags' in linked
        assert '/1/photo/profile/' in linked
        assert '@KatherineJones' in linked or 'KatherineJones' in linked


def test_photo_build_item_exposes_linked_caption_and_author_href():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None

        item = _photo_build_item(
            exp,
            {
                "id": "photo-1",
                "user_id": "b49b2daa-0560-466e-bd45-95222c7a4a10",
                "author_username": "KatherineJones",
                "author_profile_picture_url": "",
                "author_cover_image": "",
                "author_is_page": 0,
                "caption": "Hello @KatherineJones #pizza",
                "image_url": "https://example.com/photo.jpg",
            },
        )

        assert item["author_href"].endswith("/photo/profile/b49b2daa-0560-466e-bd45-95222c7a4a10/recent/1")
        assert "photo-inline-link" in item["post_html"]
        assert "/1/photo/search?q=%23pizza&amp;kind=hashtags" in item["post_html"]


def test_photo_feed_timelines_use_recommendations_and_social_contacts():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        user_id = "b49b2daa-0560-466e-bd45-95222c7a4a10"

        rec_ids = _photo_latest_recommendation_ids(exp, user_id)
        assert len(rec_ids) > 0

        contact_ids = _photo_active_contact_ids(exp, user_id)
        assert len(contact_ids) > 0

        rec_items = _build_photo_recommended_items(exp, user_id, 1, 5)
        follower_items = _build_photo_follower_items(exp, user_id, 1, 5)

        assert len(rec_items) > 0
        assert len(follower_items) > 0
        assert any(item["post_id"] in rec_ids for item in rec_items)
        assert any(item["author_id"] in contact_ids for item in rec_items)
        assert follower_items[0]["author_id"] in contact_ids
        assert contact_ids[0] == "9f0b38aa-c98e-417b-a6a7-f6a6455a1b5f"


def test_photo_media_root_matches_photo_experiment_directory():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        media_root = _photo_media_root(exp)
        assert media_root is not None
        assert media_root.exists()
        assert media_root.name == "media"
        assert media_root.parent.name == "8bd5081e_535f_4cd7_8214_64ffb57de8bc"


def test_photo_suggested_contacts_never_returns_empty_list_for_photo_experiment():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        contact_ids = set(
            _photo_active_contact_ids(exp, "b49b2daa-0560-466e-bd45-95222c7a4a10")
        )
        contacts = _photo_suggested_contacts(
            exp,
            "Admin",
            exclude_ids=contact_ids,
        )
        assert len(contacts) > 0
        assert all(item["id"] not in contact_ids for item in contacts)


def test_photo_suggestions_page_is_wired_and_english():
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/photo.py"
    ).read_text(encoding="utf-8")
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/suggestions.html"
    ).read_text(encoding="utf-8")
    feed_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/feed.html"
    ).read_text(encoding="utf-8")

    assert "photo/suggestions" in route_source
    assert "Suggested Contacts" in template
    assert "See all" in template
    assert "Mostra tutto" not in template
    assert "/{{ exp_id }}/photo/suggestions" in feed_template


def test_photo_profile_page_is_wired_and_uses_photo_shell():
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/photo.py"
    ).read_text(encoding="utf-8")
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/profile.html"
    ).read_text(encoding="utf-8")
    base_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/base.html"
    ).read_text(encoding="utf-8")

    assert "photo/profile" in route_source
    assert "photo-profile-page" in template
    assert "photo-profile-grid" in template
    assert "Saved" in template
    assert "Tagged" in template
    assert "data-photo-people-open" in template
    assert "data-photo-open-post" in template
    assert "photo-sidebar__item" in base_template
    assert "photo/components/sidebar.html" in base_template


def test_photo_search_page_is_wired_and_returns_all_search_domains():
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/photo.py"
    ).read_text(encoding="utf-8")
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/search.html"
    ).read_text(encoding="utf-8")
    sidebar_template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/components/sidebar.html"
    ).read_text(encoding="utf-8")

    assert "photo/search" in route_source
    assert "api/photo/search" in route_source
    assert "photo-search-page__grid" in template
    assert "type=\"button\" class=\"photo-search-page__tile\"" in template
    assert "photo-search.js" in template
    assert "YSPhotoOpenPost" in Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/photo-search.js"
    ).read_text(encoding="utf-8")
    assert "YS_DATA_PHOTO_SEARCH" in Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/static/assets/js/photo-overlays.js"
    ).read_text(encoding="utf-8")
    assert "data-photo-search-input" in template
    assert "data-photo-search-kind" in template
    assert "photo-sidebar__item{% if photo_active_nav == 'search' %} is-active{% endif %}" in sidebar_template
    assert "data-photo-open-share" in sidebar_template

    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        payload = _photo_search_payload(
            exp,
            "pizza",
            "all",
            "b49b2daa-0560-466e-bd45-95222c7a4a10",
        )
        assert payload["kind"] == "all"
        assert isinstance(payload["photos"], list)
        assert isinstance(payload["users"], list)
        assert isinstance(payload["hashtags"], list)
        assert payload["counts"]["photos"] >= 1
