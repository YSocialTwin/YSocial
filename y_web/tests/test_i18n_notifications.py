"""Stored (English) notification texts are translated when displayed."""

import pathlib

import pytest
from flask import Flask
from flask_babel import force_locale

import y_web.i18n as i18n
from y_web.routes.admin.sub.experiments._helpers import _localize_notification_text


@pytest.fixture
def it_app():
    app = Flask("y_web")
    app.config.update(SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"), TESTING=True)
    i18n.init_i18n(app)
    return app


@pytest.mark.parametrize(
    "stored, expected",
    [
        ("Notification cancelled.", "Notifica annullata."),
        ("Export My Exp", "Esporta My Exp"),
        ("Experiment shared: Foo", "Esperimento condiviso: Foo"),
        ("Preparing archive for 3 experiment(s) in background...", "Preparazione in background dell'archivio per 3 esperimento/i..."),
        ("bob granted you visibility to experiment 'Foo'.", "bob ti ha concesso la visibilità sull'esperimento «Foo»."),
        ("Something unknown stays as is", "Something unknown stays as is"),
    ],
)
def test_localize_notification_text(it_app, stored, expected):
    with it_app.test_request_context("/", headers={"Accept-Language": "it"}):
        assert _localize_notification_text(stored) == expected


def test_english_is_unchanged(it_app):
    with it_app.test_request_context("/", headers={"Accept-Language": "en"}):
        assert _localize_notification_text("Export Foo") == "Export Foo"
