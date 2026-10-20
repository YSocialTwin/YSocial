"""Per-language smoke test: pilot pages answer 200 and ``lang`` matches (F1-8)."""

import pathlib
import re
import shutil
import sys

import pytest
from flask import Flask, render_template
from flask_login import LoginManager

import y_web.i18n as i18n

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "y_web" / "templates"
sys.path.insert(0, str(ROOT / "scripts" / "i18n"))

import catalogs  # noqa: E402

LANGS = ["en", "it", "en-XA"]


@pytest.fixture(scope="module")
def smoke_app(tmp_path_factory):
    translations = tmp_path_factory.mktemp("translations")
    shutil.copytree(ROOT / "y_web" / "translations" / "it", translations / "it")
    # Build the pseudo catalog into the temporary directory (never into the repo).
    original = catalogs.TRANSLATIONS
    catalogs.TRANSLATIONS = translations
    try:
        catalogs.pseudo()
    finally:
        catalogs.TRANSLATIONS = original

    flask_app = Flask("smoke", template_folder=str(TEMPLATES))
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="t",
        SUPPORTED_LANGUAGES=("en", "it"),
        PSEUDO_LOCALE_ENABLED=True,
        BABEL_TRANSLATION_DIRECTORIES=str(translations),
    )
    LoginManager(flask_app).user_loader(lambda uid: None)

    @flask_app.route("/login")
    def login():
        return render_template("login/login.html")

    @flask_app.route("/missing")
    def missing():
        return render_template("error_pages/404.html"), 404

    i18n.init_i18n(flask_app)
    return flask_app


def _get(app, path, lang):
    client = app.test_client()
    client.set_cookie(i18n.ADMIN_COOKIE, lang)
    return client.get(path)


@pytest.mark.parametrize("lang", LANGS)
def test_login_page_renders_in_every_language(smoke_app, lang):
    response = _get(smoke_app, "/login", lang)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert re.search(rf'<html lang="{lang}" dir="ltr"', html)


@pytest.mark.parametrize("lang", LANGS)
def test_error_page_renders_in_every_language(smoke_app, lang):
    response = _get(smoke_app, "/missing", lang)
    assert response.status_code == 404
    assert f'lang="{lang}"' in response.get_data(as_text=True)


def test_login_text_follows_language(smoke_app):
    assert "Welcome back" in _get(smoke_app, "/login", "en").get_data(as_text=True)
    assert "Bentornato" in _get(smoke_app, "/login", "it").get_data(as_text=True)
    pseudo = _get(smoke_app, "/login", "en-XA").get_data(as_text=True)
    assert "Welcome back" not in pseudo and "[Ŵéļçómé" in pseudo


def test_unknown_cookie_falls_back_to_english(smoke_app):
    html = _get(smoke_app, "/login", "xx").get_data(as_text=True)
    assert 'lang="en"' in html and "Welcome back" in html
