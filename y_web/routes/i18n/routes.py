"""Serve ``/i18n/<domain>/<lang>.json``.

Catalogs use symbolic keys (``login.show``) and live in
``y_web/translations/js/<domain>/<lang>.json``. English is always the base:
missing keys of the requested language fall back to it.
"""

import json
import re
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, request
from flask_login import current_user

from y_web import db
from y_web.i18n import (
    ADMIN_COOKIE,
    DEFAULT_LOCALE,
    SIMULATION_COOKIE,
    normalize_language,
)
from y_web.src.external_runtime.plugin_hooks import is_local_redirect

i18n_bp = Blueprint("i18n", __name__)

JS_CATALOG_DIR = Path(__file__).resolve().parents[2] / "translations" / "js"
_DOMAIN_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def load_js_catalog(domain, lang):
    """Return the merged catalog for *domain*/*lang* (English as fallback)."""
    merged = {}
    for code in (DEFAULT_LOCALE, lang):
        path = JS_CATALOG_DIR / domain / f"{code}.json"
        if path.is_file():
            merged.update(json.loads(path.read_text(encoding="utf-8")))
    return merged


@i18n_bp.route("/i18n/<domain>/<lang>.json")
def js_catalog(domain, lang):
    """Return the JSON catalog; 404 for unknown domain or language."""
    if not _DOMAIN_RE.match(domain) or normalize_language(lang) != lang:
        abort(404)
    if not (JS_CATALOG_DIR / domain / f"{DEFAULT_LOCALE}.json").is_file():
        abort(404)
    resp = jsonify(load_js_catalog(domain, lang))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@i18n_bp.route("/set-language", methods=["POST"])
def set_language():
    """Remember the chosen language (cookie, plus the user profile for admins).

    Form fields: ``lang`` (a supported code; empty = automatic), ``next`` (a local
    path to return to) and ``scope`` (``admin``, the default, or ``sim`` for the
    participant override cookie).
    """
    raw = (request.form.get("lang") or "").strip()
    lang = normalize_language(raw) if raw else None
    if raw and lang != raw:
        abort(400)

    target = request.form.get("next") or request.referrer or "/"
    if not is_local_redirect(target):
        target = "/"
    response = redirect(target)

    if request.form.get("scope") == "sim":
        cookie = SIMULATION_COOKIE
    else:
        cookie = ADMIN_COOKIE
        if current_user.is_authenticated and hasattr(current_user, "lang"):
            current_user.lang = lang
            db.session.commit()

    if lang:
        response.set_cookie(cookie, lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
    else:
        response.delete_cookie(cookie)
    return response
