"""Template ``_()``: parity with Jinja's gettext and caching (F1-8)."""

import pytest
from flask import Flask
from flask_login import LoginManager

import y_web.i18n as i18n


@pytest.fixture
def gettext_app():
    flask_app = Flask("y_web")
    flask_app.config.update(
        SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"), TESTING=True
    )
    LoginManager(flask_app).user_loader(lambda uid: None)
    i18n.init_i18n(flask_app)
    return flask_app


def _render(app, source, lang="it", **ctx):
    with app.test_request_context("/", headers={"Accept-Language": lang}):
        template = app.jinja_env.from_string(source)
        return template.render(**ctx)


def test_translates_with_active_language(gettext_app):
    assert _render(gettext_app, "{{ _('Welcome back') }}", "it") == "Bentornato"
    assert _render(gettext_app, "{{ _('Welcome back') }}", "en") == "Welcome back"
    assert _render(gettext_app, "{{ gettext('Welcome back') }}", "it") == "Bentornato"


def test_named_variables_are_substituted_and_escaped(gettext_app):
    out = _render(gettext_app, "{{ _('Hi %(n)s', n=who) }}", "en", who="<b>x</b>")
    assert out == "Hi &lt;b&gt;x&lt;/b&gt;"


def test_percent_sign_must_be_doubled_like_in_jinja(gettext_app):
    assert _render(gettext_app, "{{ _('100%%') }}", "en") == "100%"


def test_trans_blocks_and_ngettext_still_work(gettext_app):
    assert (
        _render(gettext_app, "{% trans %}Welcome back{% endtrans %}", "it")
        == "Bentornato"
    )
    out = _render(
        gettext_app,
        "{% trans n=n %}{{ n }} post{% pluralize %}{{ n }} posts{% endtrans %}",
        "en",
        n=3,
    )
    assert out == "3 posts"
    assert (
        _render(
            gettext_app,
            "{{ ngettext('%(n)d post', '%(n)d posts', n, n=n) }}",
            "en",
            n=1,
        )
        == "1 post"
    )


def test_switching_language_between_requests(gettext_app):
    for lang, expected in (
        ("it", "Bentornato"),
        ("en", "Welcome back"),
        ("it", "Bentornato"),
    ):
        assert _render(gettext_app, "{{ _('Welcome back') }}", lang) == expected


def test_translations_are_resolved_once_per_request(gettext_app, monkeypatch):
    calls = []
    real = i18n.get_translations

    def counting():
        calls.append(1)
        return real()

    monkeypatch.setattr(i18n, "get_translations", counting)
    _render(gettext_app, "{{ _('Welcome back') }}" * 20, "it")
    assert len(calls) == 1
