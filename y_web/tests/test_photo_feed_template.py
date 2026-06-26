from pathlib import Path


def test_photo_feed_template_uses_collapsible_left_sidebar_and_instagram_layout():
    template = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/templates/photo/feed.html"
    ).read_text(encoding="utf-8")

    assert "photo-feed-shell" in template
    assert "data-photo-sidebar-toggle" in template
    assert "photo-sidebar__item is-active" in template
    assert "photo-stories" in template
    assert "YPhotoSharing" in template
    assert "microblogging/components/chat_panel.html" in template
    assert "photo/feed" in template


def test_photo_routes_do_not_rely_on_recsys_type_for_feed_rendering():
    route_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/social/photo.py"
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

    assert "ReverseChrono" in route_source
    assert "recsys_type" not in route_source
    assert "_build_photo_stories" in route_source
    assert "photo_sharing" in auth_source
    assert "photo_sharing" in common_source
    assert "photo_sharing" in admin_source
