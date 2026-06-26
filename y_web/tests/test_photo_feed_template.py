from pathlib import Path

from y_web import create_app
from y_web.src.experiment.helpers import get_experiment_engine_uri
from y_web.src.models import Exps


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

    assert "photos p" in route_source
    assert "stories s" in route_source
    assert "photo_media" in route_source
    assert "recsys_type" not in route_source
    assert "photo_sharing" in auth_source
    assert "photo_sharing" in common_source
    assert "photo_sharing" in admin_source
    assert "ensure_experiment_user" in route_source
    assert (
        "open_experiment_session" in admin_source
        or "ensure_experiment_user" in admin_source
    )


def test_photo_experiment_uses_yphotosharing_database_file():
    app = create_app()
    with app.app_context():
        exp = Exps.query.filter_by(idexp=1).first()
        assert exp is not None
        uri = get_experiment_engine_uri(exp)
        assert uri is not None
        assert uri.endswith("/yphotosharing.db")
