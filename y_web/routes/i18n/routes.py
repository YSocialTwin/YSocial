"""Serve ``/i18n/<domain>/<lang>.json``.

Catalogs use symbolic keys (``login.show``) and live in
``y_web/translations/js/<domain>/<lang>.json``. English is always the base:
missing keys of the requested language fall back to it.
"""

import json
import re
from pathlib import Path

from flask import Blueprint, abort, jsonify

from y_web.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES

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
    if not _DOMAIN_RE.match(domain) or lang not in SUPPORTED_LOCALES:
        abort(404)
    if not (JS_CATALOG_DIR / domain / f"{DEFAULT_LOCALE}.json").is_file():
        abort(404)
    resp = jsonify(load_js_catalog(domain, lang))
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp
