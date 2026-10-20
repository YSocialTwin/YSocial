"""Forum 'My profile' page: shape of the rendered template."""

import pathlib
from types import SimpleNamespace

import jinja2
from flask import Blueprint, Flask, render_template

import y_web.i18n as i18n

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "y_web" / "templates"


def _app():
    app = Flask("y_web")
    app.config.update(SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"), TESTING=True)
    app.register_blueprint(Blueprint("main", __name__))
    app.jinja_loader = jinja2.ChoiceLoader(
        [
            jinja2.DictLoader({"forum/header.html": "<!--header-->"}),
            jinja2.FileSystemLoader(str(TEMPLATES)),
        ]
    )
    app.jinja_env.filters["user_image_id"] = lambda value: "1"
    i18n.init_i18n(app)
    return app


def _render(app, lang):
    user = SimpleNamespace(
        id=7,
        username="alice",
        email="a@b.c",
        age=30,
        gender="female",
        nationality="Italian",
        language="Italian",
        leaning="Centrist",
        education_level="bachelor",
        password="x",
        is_page=0,
    )
    with app.test_request_context(
        "/1/edit_profile/7", headers={"Accept-Language": lang}
    ):
        return render_template(
            "forum/edit_profile.html",
            user=user,
            profile_pic="",
            available_profile_pics=["a.png"],
            cover_image="",
            available_cover_images=["b.png"],
            is_page=0,
            username="alice",
            user_id=7,
            logged_username="alice",
            logged_id=7,
            is_admin=False,
            exp_id=1,
            forum_memory_enabled=False,
        )


def test_forum_edit_profile_has_no_topics_or_recommenders():
    html = _render(_app(), "en")
    assert 'name="profile_pic"' not in html and 'name="cover_image"' not in html
    assert 'name="new_password"' in html
    assert "update_topic_preferences" not in html
    assert 'name="frecsys_type"' not in html
    assert 'name="recsys_type"' not in html
    assert "Topics" not in html


def test_forum_edit_profile_is_translated():
    html = _render(_app(), "it")
    assert "Impostazioni" in html
    assert "Salva le modifiche" in html


def test_forum_menu_points_to_the_edit_profile_page():
    source = (TEMPLATES / "forum" / "header.html").read_text(encoding="utf-8")
    assert source.count("/edit_profile/{{ logged_id }}") == 2
