"""Internationalisation support (Flask-Babel).

The English source string is the msgid; catalogs live in ``y_web/translations``.

Two language contexts are kept apart (plan decisions D3 and D4):

* **admin** (dashboard, auth, errors): the admin user's saved language, then the
  ``ys_lang`` cookie, then ``Accept-Language``, then English.
* **simulation** (participant frontend and its APIs): the participant's optional
  override (``ys_lang_sim`` cookie, only when the experiment allows it), then the
  language configured for the experiment, then English. ``Accept-Language`` is
  deliberately ignored here: the interface language must not become an
  uncontrolled variable inside an experiment.
"""

from flask import current_app, request
from flask_babel import Babel, get_locale
from flask_login import current_user

DEFAULT_LOCALE = "en"
ADMIN_COOKIE = "ys_lang"
SIMULATION_COOKIE = "ys_lang_sim"

# Blueprints that render the participant-facing simulation frontend.
SIMULATION_BLUEPRINTS = frozenset(
    {"main", "user_actions", "api_reddit", "api_social", "api_interview"}
)

# Native names shown in language selectors; unknown codes fall back to the code.
LANGUAGE_NAMES = {
    "en": "English",
    "it": "Italiano",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
}

babel = Babel()

# Optional hook set by the experiment code: returns ``(language, allow_override)``
# for the current request, or ``None`` when no experiment language is configured.
experiment_language_resolver = None


def supported_languages():
    """Return the tuple of language codes enabled in the configuration."""
    langs = current_app.config.get("SUPPORTED_LANGUAGES") or (DEFAULT_LOCALE,)
    return tuple(langs)


def available_languages():
    """Return ``[(code, native name), ...]`` for the supported languages."""
    return [(code, LANGUAGE_NAMES.get(code, code)) for code in supported_languages()]


def normalize_language(code):
    """Return *code* if it is a supported language, else ``None``."""
    if not code:
        return None
    code = str(code).strip().replace("_", "-")
    langs = supported_languages()
    if code in langs:
        return code
    short = code.split("-")[0].lower()
    return short if short in langs else None


def is_simulation_request():
    """True when the current request belongs to the simulation frontend."""
    return (request.blueprint or "") in SIMULATION_BLUEPRINTS


def _user_language():
    """Saved language of the logged-in admin user, if any."""
    try:
        if current_user and current_user.is_authenticated:
            return normalize_language(getattr(current_user, "lang", None))
    except Exception:  # pragma: no cover - defensive: never break a request
        return None
    return None


def _experiment_language():
    """Return ``(language, allow_override)`` for the active experiment."""
    if experiment_language_resolver is None:
        return None, True
    try:
        result = experiment_language_resolver()
    except Exception:  # pragma: no cover - defensive
        return None, True
    if not result:
        return None, True
    lang, allow = result
    return normalize_language(lang), bool(allow)


def select_locale():
    """Pick the interface language for the current request."""
    if is_simulation_request():
        exp_lang, allow_override = _experiment_language()
        if allow_override:
            override = normalize_language(request.cookies.get(SIMULATION_COOKIE))
            if override:
                return override
        return exp_lang or DEFAULT_LOCALE

    return (
        _user_language()
        or normalize_language(request.cookies.get(ADMIN_COOKIE))
        or request.accept_languages.best_match(supported_languages())
        or DEFAULT_LOCALE
    )


def init_i18n(app):
    """Register Flask-Babel on the application."""
    app.config.setdefault("BABEL_DEFAULT_LOCALE", DEFAULT_LOCALE)
    app.config.setdefault("BABEL_TRANSLATION_DIRECTORIES", "translations")
    app.config.setdefault("SUPPORTED_LANGUAGES", (DEFAULT_LOCALE,))
    babel.init_app(app, locale_selector=select_locale)
    app.jinja_env.globals["get_locale"] = get_locale
    app.jinja_env.globals["available_languages"] = available_languages
