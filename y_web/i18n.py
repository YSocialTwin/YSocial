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

from flask import current_app, g, request

try:  # Flask >= 2.2
    from flask.globals import _cv_app
except ImportError:  # pragma: no cover
    _cv_app = None
from flask_babel import (
    Babel,
    format_date,
    format_datetime,
    format_decimal,
    format_number,
    format_time,
    get_locale,
    get_translations,
    gettext as _babel_gettext,
)
from flask_login import current_user
from jinja2 import pass_eval_context
from markupsafe import Markup, escape

from y_web.i18n_pseudo import PSEUDO_CARRIER, PSEUDO_LANGUAGE

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


def pseudo_enabled():
    """True when the ``en-XA`` pseudo-locale is switched on (development/CI only)."""
    return bool(current_app.config.get("PSEUDO_LOCALE_ENABLED"))


def available_languages():
    """Return ``[(code, native name), ...]`` for the supported languages."""
    return [(code, LANGUAGE_NAMES.get(code, code)) for code in supported_languages()]



def N_(message):
    """Mark *message* for extraction without translating it (translate later with ``_(value)``)."""
    return message


def gettext(message, **variables):
    """Request-time gettext for Python code (flash messages, JSON errors).

    Falls back to the untranslated message when Flask-Babel is not
    initialised (bare Flask apps used in unit tests or scripts).
    """
    try:
        return _babel_gettext(message, **variables)
    except (KeyError, RuntimeError):
        return message % variables if variables else message


def wrap(tag, text, **attrs):
    """Markup for ``<tag attrs>text</tag>``, used as a placeholder value in sentences.

    ``{{ _('Open %(link)s first.', link=wrap('a', _('Settings'), href=url_for('x'))) }}``
    keeps the markup out of the translated string, so translators only see words.
    Attribute names use ``_`` for ``-`` (``data_x`` becomes ``data-x``).
    """
    rendered = "".join(
        ' %s="%s"' % (name.replace("_", "-"), escape(value))
        for name, value in attrs.items()
    )
    return Markup("<%s%s>%s</%s>") % (Markup(tag), Markup(rendered), text, Markup(tag))


def _locale_info():
    """``(html lang, direction)`` of the active locale, computed once per request."""
    app_g = _cv_app.get().g if _cv_app is not None else g
    info = app_g.__dict__.get("_ys_locale_info")
    if info is None:
        locale = get_locale()
        if locale is None:
            info = (DEFAULT_LOCALE, "ltr")
        else:
            code = str(locale)
            if code == PSEUDO_CARRIER:
                lang = PSEUDO_LANGUAGE
            else:
                lang = code.replace("_", "-")
            info = (lang, "rtl" if locale.text_direction == "rtl" else "ltr")
        app_g._ys_locale_info = info
    return info


def html_lang():
    """Value for ``<html lang>``: a BCP-47 tag (``en-XA`` for the pseudo-locale)."""
    return _locale_info()[0]


def text_direction():
    """Return ``"rtl"`` or ``"ltr"`` for the active locale (``<html dir>``)."""
    return _locale_info()[1]


def normalize_language(code):
    """Return *code* if it is a supported language, else ``None``."""
    if not code:
        return None
    code = str(code).strip().replace("_", "-")
    if code.lower() == PSEUDO_LANGUAGE.lower():
        return PSEUDO_LANGUAGE if pseudo_enabled() else None
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


def _current_experiment_id():
    """Experiment of the current simulation request (URL ``exp_id``, else the request context)."""
    raw = (request.view_args or {}).get("exp_id")
    if raw is None:
        try:
            from y_web.src.experiment.context import get_current_experiment_id

            raw = get_current_experiment_id()
        except Exception:  # pragma: no cover - defensive
            raw = None
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def resolve_experiment_language():
    """Default ``experiment_language_resolver``: ``(language, allow_override)`` from the experiment's frontend settings.

    ``None`` when the request has no experiment or the experiment sets no language
    (the participant then gets English, plus the optional override cookie).
    """
    exp_id = _current_experiment_id()
    if exp_id is None:
        return None
    from y_web.routes.social.helpers import _load_ui_settings

    ui = _load_ui_settings(exp_id)
    return ui.get("language") or None, bool(ui.get("language_switch_allowed", False))


def simulation_language_options():
    """``[(code, name), ...]`` for the participant language selector; empty when the experiment fixes the language."""
    try:
        if not is_simulation_request() or len(supported_languages()) < 2:
            return []
        _lang, allow = _experiment_language()
        return available_languages() if allow else []
    except Exception:  # pragma: no cover - the selector must never break a page
        return []


def _experiment_language():
    """Return ``(language, allow_override)`` for the active experiment."""
    resolver = experiment_language_resolver or resolve_experiment_language
    try:
        result = resolver()
    except Exception:  # pragma: no cover - defensive
        return None, True
    if not result:
        return None, True
    lang, allow = result
    return normalize_language(lang), bool(allow)


def select_locale():
    """Pick the interface language for the current request (a Babel locale code)."""
    chosen = _chosen_language()
    return PSEUDO_CARRIER if chosen == PSEUDO_LANGUAGE else chosen


def _chosen_language():
    """Resolve the language code (``en-XA`` included) for the current request."""
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


def _request_translations():
    """Translations of the active language, resolved once per request.

    Flask-Babel looks the translations up on every call, which costs several
    microseconds; a page with hundreds of marked strings would pay that hundreds
    of times, so the template ``_()`` uses this per-request cache instead.
    """
    # ``g`` is a LocalProxy (about 0.4 us per access); the context's own object is not.
    app_g = _cv_app.get().g if _cv_app is not None else g
    cached = app_g.__dict__.get("_ys_translations")
    if cached is None:
        cached = get_translations()
        app_g._ys_translations = cached
    return cached


def _template_gettext(message):
    return _request_translations().ugettext(message)


@pass_eval_context
def _fast_template_gettext(eval_ctx, message, **variables):
    """Template ``_()``: same result as Jinja's new-style gettext, with less overhead.

    Like Jinja's version, ``%`` in a message must be written ``%%`` and variables
    are HTML-escaped when autoescape is on.
    """
    translations = _request_translations()
    if variables:
        rv = translations.ugettext(message)
        return (Markup(rv) if eval_ctx.autoescape else rv) % variables
    # Messages without variables never change for a given catalog: keep the final
    # (``%%`` collapsed, already marked safe) result on the catalog object itself,
    # so a reloaded or different catalog never serves stale text.
    cache = translations.__dict__.get("_ys_final")
    if cache is None:
        cache = translations._ys_final = ({}, {})
    table = cache[0 if eval_ctx.autoescape else 1]
    rv = table.get(message)
    if rv is None:
        rv = translations.ugettext(message)
        if "%" in rv:
            rv = rv.replace("%%", "%")
        rv = table[message] = Markup(rv) if eval_ctx.autoescape else rv
    return rv


def _template_ngettext(singular, plural, n):
    return _request_translations().ungettext(singular, plural, n)


def init_i18n(app):
    """Register Flask-Babel on the application."""
    app.config.setdefault("BABEL_DEFAULT_LOCALE", DEFAULT_LOCALE)
    app.config.setdefault("BABEL_TRANSLATION_DIRECTORIES", "translations")
    app.config.setdefault("SUPPORTED_LANGUAGES", (DEFAULT_LOCALE,))
    app.config.setdefault("PSEUDO_LOCALE_ENABLED", False)
    babel.init_app(app, locale_selector=select_locale)
    app.jinja_env.globals["get_locale"] = get_locale
    # Faster ``_()``/``ngettext()`` for templates (same behaviour, cached per request).
    app.jinja_env.install_gettext_callables(
        _template_gettext, _template_ngettext, newstyle=True
    )
    app.jinja_env.globals["_"] = _fast_template_gettext
    app.jinja_env.globals["gettext"] = _fast_template_gettext
    app.jinja_env.globals["available_languages"] = available_languages
    app.jinja_env.globals["simulation_language_options"] = simulation_language_options
    app.jinja_env.globals["text_direction"] = text_direction
    app.jinja_env.globals["html_lang"] = html_lang
    app.jinja_env.globals["wrap"] = wrap
    # Locale-aware formatting for dates and numbers: {{ value|localdate }}.
    from y_web.src.external_runtime.plugin_i18n import init_plugin_i18n

    init_plugin_i18n(app)
    app.jinja_env.filters["localdate"] = format_date
    app.jinja_env.filters["localtime"] = format_time
    app.jinja_env.filters["localdatetime"] = format_datetime
    app.jinja_env.filters["localnumber"] = format_number
    app.jinja_env.filters["localdecimal"] = format_decimal
