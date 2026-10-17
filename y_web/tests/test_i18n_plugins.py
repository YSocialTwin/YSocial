"""Plugin translation interface (F1-7)."""

import json
import types

import pytest
from babel.messages import Catalog
from babel.messages.mofile import write_mo
from flask import Flask, render_template_string
from flask_login import LoginManager

import y_web.i18n as i18n
from y_web.routes.i18n import i18n_bp
from y_web.src.external_runtime import plugin_i18n
from y_web.src.external_runtime.backend_plugins import (
    _validate_optional_extension_keys,
)


def _make_plugin(root, domain="demo", with_catalog=True):
    """A throw-away plugin with an Italian catalog and JS catalogs."""
    if with_catalog:
        mo_dir = root / "translations" / "it" / "LC_MESSAGES"
        mo_dir.mkdir(parents=True)
        catalog = Catalog(locale="it", domain=domain)
        catalog.add("Modules", string="Moduli")
        catalog.add("Hello %(name)s", string="Ciao %(name)s")
        catalog.add(
            ("%(num)d step", "%(num)d steps"), string=("%(num)d passo", "%(num)d passi")
        )
        with (mo_dir / f"{domain}.mo").open("wb") as fh:
            write_mo(fh, catalog)
    js = root / "translations" / "js" / domain
    js.mkdir(parents=True, exist_ok=True)
    (js / "en.json").write_text(json.dumps({"k": "Key", "only_en": "Only English"}))
    (js / "it.json").write_text(json.dumps({"k": "Chiave"}))
    return root


@pytest.fixture
def plugin_app(tmp_path):
    plugin = _make_plugin(tmp_path / "demo_plugin")
    config, problems = plugin_i18n.normalize_i18n_manifest(
        "demo_plugin", plugin, {"domain": "demo"}
    )
    assert problems == []
    assert plugin_i18n.register_plugin_i18n("demo_plugin", config)
    flask_app = Flask("y_web")
    flask_app.config.update(
        TESTING=True, SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it")
    )
    LoginManager(flask_app).user_loader(lambda uid: None)
    flask_app.register_blueprint(i18n_bp)
    i18n.init_i18n(flask_app)
    yield flask_app
    plugin_i18n.unregister_plugin_i18n("demo_plugin")


def _render(app, template, lang):
    with app.test_request_context("/", headers={"Accept-Language": lang}):
        return render_template_string(template)


def test_plugin_template_translates_with_its_own_domain(plugin_app):
    tpl = "{{ plugin_gettext('demo', 'Modules') }}|{{ plugin_gettext('demo', 'Hello %(name)s', name='Ann') }}"
    assert _render(plugin_app, tpl, "it") == "Moduli|Ciao Ann"
    assert _render(plugin_app, tpl, "en") == "Modules|Hello Ann"


def test_manifest_string_filter(plugin_app):
    assert _render(plugin_app, "{{ 'Modules'|plugin_text('demo') }}", "it") == "Moduli"


def test_untranslated_message_and_unknown_domain_fall_back_to_english(plugin_app):
    assert (
        _render(plugin_app, "{{ plugin_gettext('demo', 'Not in catalog') }}", "it")
        == "Not in catalog"
    )
    assert (
        _render(
            plugin_app,
            "{{ plugin_gettext('nope', 'Hello %(name)s', name='Bo') }}",
            "it",
        )
        == "Hello Bo"
    )


def test_plugin_plurals(plugin_app):
    tpl = "{{ plugin_ngettext('demo', '%(num)d step', '%(num)d steps', n) }}"
    with plugin_app.test_request_context("/", headers={"Accept-Language": "it"}):
        assert render_template_string(tpl, n=1) == "1 passo"
        assert render_template_string(tpl, n=3) == "3 passi"


def test_a_variable_may_be_named_message_or_domain(plugin_app):
    with plugin_app.test_request_context("/", headers={"Accept-Language": "it"}):
        assert (
            plugin_i18n.plugin_gettext("demo", "Hello %(name)s", name="Ann")
            == "Ciao Ann"
        )
        assert (
            plugin_i18n.plugin_gettext("demo", "Say %(message)s", message="hi")
            == "Say hi"
        )
        assert plugin_i18n.plugin_gettext("demo", "In %(domain)s", domain="d") == "In d"
        assert (
            plugin_i18n.plugin_ngettext("demo", "%(num)d step", "%(num)d steps", 3)
            == "3 passi"
        )


def test_core_gettext_is_not_affected_by_plugin_catalogs(plugin_app):
    # "Modules" exists only in the plugin catalog: the core domain must not see it.
    assert _render(plugin_app, "{{ _('Modules') }}", "it") == "Modules"


def test_language_without_catalog_falls_back(tmp_path):
    plugin = _make_plugin(tmp_path / "p2", domain="two", with_catalog=False)
    config, _ = plugin_i18n.normalize_i18n_manifest("p2", plugin, {"domain": "two"})
    plugin_i18n.register_plugin_i18n("p2", config)
    try:
        flask_app = Flask("y_web")
        flask_app.config.update(SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"))
        LoginManager(flask_app).user_loader(lambda uid: None)
        i18n.init_i18n(flask_app)
        assert (
            _render(flask_app, "{{ plugin_gettext('two', 'Modules') }}", "it")
            == "Modules"
        )
    finally:
        plugin_i18n.unregister_plugin_i18n("p2")


def test_plugin_js_catalog_served_with_english_fallback(plugin_app):
    data = plugin_app.test_client().get("/i18n/demo/it.json").get_json()
    assert data == {"k": "Chiave", "only_en": "Only English"}


def test_unregistered_plugin_domain_is_404(plugin_app):
    assert plugin_app.test_client().get("/i18n/other/it.json").status_code == 404


def test_domain_clash_between_plugins_is_refused(tmp_path):
    cfg = {"domain": "dup", "translations": "t", "path": str(tmp_path)}
    assert plugin_i18n.register_plugin_i18n("a", cfg)
    try:
        assert not plugin_i18n.register_plugin_i18n("b", cfg)
        assert plugin_i18n.register_plugin_i18n("a", cfg)  # idempotent for the owner
    finally:
        plugin_i18n.unregister_plugin_i18n("a")


@pytest.mark.parametrize(
    "value",
    [
        "text",
        {"domain": "Bad Domain"},
        {"domain": "x"},
        {"domain": "ok_domain", "translations": "../escape"},
        {"domain": "ok_domain", "translations": "/abs"},
    ],
)
def test_invalid_manifest_values_are_reported(tmp_path, value):
    config, problems = plugin_i18n.normalize_i18n_manifest("p", tmp_path, value)
    assert config is None and problems


def test_manifest_defaults(tmp_path):
    config, problems = plugin_i18n.normalize_i18n_manifest("my_plugin", tmp_path, {})
    assert problems == []
    assert config["domain"] == "my_plugin"
    assert config["path"] == str(tmp_path / "translations")


def test_absent_i18n_key_changes_nothing(tmp_path):
    assert plugin_i18n.normalize_i18n_manifest("p", tmp_path, None) == (None, [])
    report = {"errors": []}
    spec = types.SimpleNamespace(key="p", path=tmp_path)
    _validate_optional_extension_keys(spec, {}, report)
    assert report == {"errors": []}


def test_backend_validation_picks_up_i18n_key(tmp_path):
    report = {"errors": []}
    spec = types.SimpleNamespace(key="p", path=tmp_path)
    _validate_optional_extension_keys(spec, {"i18n": {"domain": "my_dom"}}, report)
    assert report["errors"] == []
    assert report["i18n"]["domain"] == "my_dom"


def test_backend_validation_reports_bad_i18n_key(tmp_path):
    report = {"errors": []}
    spec = types.SimpleNamespace(key="p", path=tmp_path)
    _validate_optional_extension_keys(spec, {"i18n": {"domain": "Bad"}}, report)
    assert report["errors"] and "i18n" not in report


def test_localize_manifest_translates_visible_text_only(plugin_app):
    manifest = {
        "display_name": "Modules",
        "description": "Hello %(name)s",
        "parameters": [
            {"name": "Modules", "type": "str", "label": "Modules", "default": "Modules"}
        ],
        "module_id": "Modules",
    }
    with plugin_app.test_request_context("/", headers={"Accept-Language": "it"}):
        out = plugin_i18n.localize_manifest("demo_plugin", manifest)
        assert plugin_i18n.localize_text("demo_plugin", "Modules") == "Moduli"
    assert out["display_name"] == "Moduli"
    assert out["parameters"][0]["label"] == "Moduli"
    # identifiers and defaults are data, not text
    assert out["parameters"][0]["name"] == "Modules"
    assert out["parameters"][0]["default"] == "Modules"
    assert out["module_id"] == "Modules"
    assert manifest["display_name"] == "Modules"  # the input is not modified
    assert plugin_i18n.localize_manifest("unknown_plugin", manifest) is manifest
