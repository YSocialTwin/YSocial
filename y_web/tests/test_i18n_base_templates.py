"""Base templates, formatting filters and the language switch route (F1-4)."""

import datetime
import pathlib

import pytest
from flask import Flask, render_template_string
from flask_login import LoginManager

import y_web.i18n as i18n
from y_web.routes.i18n import i18n_bp

TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"


@pytest.fixture
def i18n_app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True, SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it", "ar")
    )
    manager = LoginManager(flask_app)
    manager.user_loader(lambda uid: None)
    flask_app.register_blueprint(i18n_bp)
    i18n.init_i18n(flask_app)
    return flask_app


def test_no_template_hardcodes_html_lang():
    offenders = [
        str(p.relative_to(TEMPLATES))
        for p in TEMPLATES.rglob("*.html")
        if '<html lang="en"' in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_base_templates_set_lang_and_dir():
    for name in (
        "admin/head.html",
        "microblogging/header.html",
        "forum/header.html",
        "photo/base.html",
        "login/onboarding.html",
        "login/scene_base.html",
    ):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        assert 'lang="{{ html_lang() }}"' in text, name
        assert 'dir="{{ text_direction() }}"' in text, name


def test_text_direction_follows_locale(i18n_app):
    with i18n_app.test_request_context("/", headers={"Accept-Language": "it"}):
        assert i18n.text_direction() == "ltr"
    with i18n_app.test_request_context("/", headers={"Accept-Language": "ar"}):
        assert i18n.text_direction() == "rtl"


def test_date_and_number_filters_follow_locale(i18n_app):
    tpl = "{{ d|localdate }}|{{ n|localnumber }}"
    ctx = {"d": datetime.date(2026, 10, 16), "n": 1234567.5}
    with i18n_app.test_request_context("/", headers={"Accept-Language": "en"}):
        en = render_template_string(tpl, **ctx)
    with i18n_app.test_request_context("/", headers={"Accept-Language": "it"}):
        it = render_template_string(tpl, **ctx)
    assert en != it
    assert "1,234,567" in en
    assert "1.234.567" in it


def test_set_language_sets_cookie_and_redirects(i18n_app):
    c = i18n_app.test_client()
    r = c.post("/set-language", data={"lang": "it", "next": "/admin/x"})
    assert r.status_code == 302 and r.headers["Location"] == "/admin/x"
    assert c.get_cookie(i18n.ADMIN_COOKIE).value == "it"


def test_set_language_rejects_open_redirect(i18n_app):
    r = i18n_app.test_client().post(
        "/set-language", data={"lang": "it", "next": "//evil.example"}
    )
    assert r.headers["Location"] == "/"


def test_set_language_rejects_unsupported_language(i18n_app):
    assert (
        i18n_app.test_client().post("/set-language", data={"lang": "xx"}).status_code
        == 400
    )


def test_set_language_empty_clears_cookie(i18n_app):
    c = i18n_app.test_client()
    c.post("/set-language", data={"lang": "it"})
    c.post("/set-language", data={"lang": ""})
    assert c.get_cookie(i18n.ADMIN_COOKIE) is None


def test_set_language_simulation_scope_uses_simulation_cookie(i18n_app):
    c = i18n_app.test_client()
    c.post("/set-language", data={"lang": "it", "scope": "sim"})
    assert c.get_cookie(i18n.SIMULATION_COOKIE).value == "it"
    assert c.get_cookie(i18n.ADMIN_COOKIE) is None
