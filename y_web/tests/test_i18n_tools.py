"""Pseudo-locale, catalog tooling and the unmarked-string scanner (F1-6)."""

import json
import pathlib
import sys

import pytest
from flask import Flask, render_template_string
from flask_login import LoginManager

import y_web.i18n as i18n
from y_web.i18n_pseudo import (
    PSEUDO_CARRIER,
    PSEUDO_LANGUAGE,
    pseudolocalize,
    pseudolocalize_catalog,
)
from y_web.routes.i18n import i18n_bp

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "i18n"))

import catalogs  # noqa: E402
import manifest_extractor  # noqa: E402
import scan_unmarked  # noqa: E402


def test_pseudolocalize_marks_text_and_keeps_placeholders():
    out = pseudolocalize("Hello %(name)s, you have {count} <b>new</b> items &amp; 5%d")
    assert out.startswith("[") and out.endswith("]")
    assert "%(name)s" in out and "{count}" in out and "<b>" in out and "</b>" in out
    assert "&amp;" in out and "%d" in out
    assert "Hello" not in out and "items" not in out


def test_pseudolocalize_pads_and_handles_empty():
    assert len(pseudolocalize("abcdef")) > len("abcdef") + 2
    assert pseudolocalize("") == ""


def test_pseudolocalize_catalog_handles_plurals():
    out = pseudolocalize_catalog(
        {"a": "One", "p": {"one": "{count} post", "other": "{count} posts"}}
    )
    assert out["a"].startswith("[")
    assert "{count}" in out["p"]["one"] and out["p"]["other"].startswith("[")


@pytest.fixture
def i18n_app(tmp_path):
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="t",
        SUPPORTED_LANGUAGES=("en", "it"),
        PSEUDO_LOCALE_ENABLED=True,
    )
    LoginManager(flask_app).user_loader(lambda uid: None)
    flask_app.register_blueprint(i18n_bp)
    i18n.init_i18n(flask_app)
    return flask_app


def test_pseudo_language_accepted_only_when_enabled(i18n_app):
    with i18n_app.app_context():
        assert i18n.normalize_language("en-XA") == PSEUDO_LANGUAGE
        i18n_app.config["PSEUDO_LOCALE_ENABLED"] = False
        assert i18n.normalize_language("en-XA") is None


def test_pseudo_selected_by_cookie_maps_to_carrier_and_html_lang(i18n_app):
    with i18n_app.test_request_context(
        "/", headers={"Cookie": f"{i18n.ADMIN_COOKIE}=en-XA"}
    ):
        assert i18n.select_locale() == PSEUDO_CARRIER
        assert i18n.html_lang() == "en-XA"
        assert render_template_string("{{ html_lang() }}") == "en-XA"


def test_pseudo_js_catalog_endpoint(i18n_app):
    data = i18n_app.test_client().get("/i18n/core/en-XA.json").get_json()
    assert data["login.show"].startswith("[")


def test_pseudo_endpoint_404_when_disabled(i18n_app):
    i18n_app.config["PSEUDO_LOCALE_ENABLED"] = False
    assert i18n_app.test_client().get("/i18n/core/en-XA.json").status_code == 404


def test_manifest_extractor_finds_visible_strings(tmp_path):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "p.json").write_text(
        json.dumps(
            {
                "name": "My plugin",
                "version": "1.0",
                "settings": [
                    {"label": "Threshold", "key": "thr", "help": "How strict"}
                ],
                "id": "12345",
            }
        )
    )
    found = {text for text, _ in manifest_extractor.extract_plugin_manifests(tmp_path)}
    assert found == {"My plugin", "Threshold", "How strict"}


def test_manifest_extractor_ignores_broken_json(tmp_path):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "bad.json").write_text("{not json")
    assert manifest_extractor.extract_plugin_manifests(tmp_path) == []


def test_scan_marks_gettext_calls_as_translated(tmp_path):
    py = tmp_path / "a.py"
    py.write_text(
        "from flask import flash, jsonify\n"
        "flash(_('ok'))\nflash('bad')\nflash(f'bad {x}')\n"
        "jsonify(error=_('ok'))\njsonify(error='bad')\njsonify({'message': 'bad'})\n"
    )
    assert scan_unmarked.scan_python(py, set()) == 4


def test_scan_template_ignores_jinja_marked_text(tmp_path):
    html = tmp_path / "t.html"
    html.write_text(
        "<h1>{{ _('Marked') }}</h1><p>Unmarked text</p><input placeholder=\"Search here\">"
    )
    assert scan_unmarked.scan_template(html, set()) == 2
    assert scan_unmarked.scan_template(html, {"Unmarked text"}) == 1


def test_scan_baseline_matches_current_state():
    """A file may not gain unmarked strings (the CI ratchet)."""
    baseline = json.loads(scan_unmarked.BASELINE.read_text())
    worse = {
        f: n for f, n in scan_unmarked.scan_all().items() if n > baseline.get(f, 0)
    }
    assert worse == {}


def test_catalog_languages_exclude_pseudo_carrier():
    assert PSEUDO_CARRIER not in catalogs.languages()
    assert "it" in catalogs.languages()


def test_template_gettext_literals_escape_percent_signs():
    """Template ``_()`` formats with ``%``: a literal percent sign must be ``%%``."""
    import pathlib
    import re

    call = re.compile(r"""\b_\(\s*(?P<q>['"])(?P<s>(?:\\.|(?!(?P=q)).)*)(?P=q)""", re.S)
    lone = re.compile(r"%(?!%|\([A-Za-z_]\w*\)[sdif])")
    bad = []
    for path in (pathlib.Path(__file__).resolve().parents[1] / "templates").rglob(
        "*.html"
    ):
        for m in call.finditer(path.read_text(encoding="utf-8")):
            if lone.search(m.group("s").replace("%%", "")):
                bad.append((path.name, m.group("s")[:60]))
    assert bad == []
