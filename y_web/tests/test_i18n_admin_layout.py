"""Admin layout, login and error pages are translated (F2-1)."""

import pathlib

import pytest
from flask import Flask, render_template, url_for
from flask_login import LoginManager

import y_web.i18n as i18n

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def i18n_app():
    flask_app = Flask(__name__, template_folder=str(ROOT / "templates"))
    flask_app.config.update(TESTING=True, SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"),
        BABEL_TRANSLATION_DIRECTORIES=str(ROOT / "translations"),
    )
    manager = LoginManager(flask_app)
    manager.user_loader(lambda uid: None)
    i18n.init_i18n(flask_app)
    return flask_app


@pytest.mark.parametrize("code", [400, 403, 404, 500])
def test_error_pages_in_italian(i18n_app, code):
    with i18n_app.test_request_context("/", headers={"Accept-Language": "it"}):
        html = render_template(f"error_pages/{code}.html", error=None)
    assert "Vai alla home page" in html
    assert "Go to Homepage" not in html
    assert f"Errore {code}" in html


def test_error_pages_default_to_english(i18n_app):
    with i18n_app.test_request_context("/"):
        html = render_template("error_pages/404.html", error=None)
    assert "Go to Homepage" in html and "Page Not Found" in html


def test_admin_menu_templates_have_no_unmarked_labels():
    for name in ("head.html", "dash_head.html"):
        text = (ROOT / "templates" / "admin" / name).read_text(encoding="utf-8")
        for label in (">Home<", ">Users<", ">Populations<", ">Plugin Manager<", ">Account<"):
            assert label not in text, (name, label)


def test_onboarding_labels_are_json_encoded():
    text = (ROOT / "templates" / "login" / "onboarding.html").read_text(encoding="utf-8")
    assert "'Not Interested', 'Low Interest'" not in text
    assert "|tojson" in text
