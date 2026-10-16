"""Internationalisation support (Flask-Babel). Spike F0-2.

The English source string is the msgid; catalogs live in ``y_web/translations``.
"""

from flask import request, session
from flask_babel import Babel, get_locale

SUPPORTED_LOCALES = ("en", "it")
DEFAULT_LOCALE = "en"

babel = Babel()


def select_locale():
    """Pick the UI language: session choice, then Accept-Language, then default."""
    chosen = session.get("lang")
    if chosen in SUPPORTED_LOCALES:
        return chosen
    return request.accept_languages.best_match(SUPPORTED_LOCALES) or DEFAULT_LOCALE


def init_i18n(app):
    """Register Flask-Babel on the application."""
    app.config.setdefault("BABEL_DEFAULT_LOCALE", DEFAULT_LOCALE)
    app.config.setdefault("BABEL_TRANSLATION_DIRECTORIES", "translations")
    babel.init_app(app, locale_selector=select_locale)
    app.jinja_env.globals["get_locale"] = get_locale
