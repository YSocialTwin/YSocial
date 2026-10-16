"""F4-1/F4-2: the interface language is a per-experiment setting that drives the participant pages."""

import pytest

import y_web.i18n as i18n
from y_web.tests.test_frontend_settings_generic_suite_panel import (  # noqa: F401  (fixtures + helpers)
    _login,
    _make_admin_login_user,
    suites_app,
)
from y_web.tests.test_frontend_settings_platforms import _exp


@pytest.fixture
def logged(suites_app):
    suites_app.config["SUPPORTED_LANGUAGES"] = ("en", "it")
    client = suites_app.test_client()
    _login(client, _make_admin_login_user(suites_app))
    return client


def _save(client, exp_id, **settings):
    r = client.post("/admin/frontend_settings/save", json={"exp_id": exp_id, "settings": settings})
    assert r.get_json()["ok"]


def _resolve(app, exp_id):
    with app.test_request_context(f"/{exp_id}/feed"):
        from flask import request

        request.view_args = {"exp_id": exp_id}
        return i18n.resolve_experiment_language()


def test_language_defaults_to_unset_and_fixed(suites_app, logged):
    exp = _exp(suites_app, "microblogging", "lang-default")
    data = logged.get(f"/admin/frontend_settings/get_settings?exp_id={exp}").get_json()
    assert data["settings"]["language"] == "" and data["settings"]["language_switch_allowed"] is False
    assert _resolve(suites_app, exp) == (None, False)


@pytest.mark.parametrize("platform", ["microblogging", "forum", "photo_sharing"])
def test_saved_language_reaches_the_resolver(suites_app, logged, platform):
    exp = _exp(suites_app, platform, f"lang-{platform}")
    _save(logged, exp, language="it", language_switch_allowed=True)
    assert _resolve(suites_app, exp) == ("it", True)
    _save(logged, exp, language_switch_allowed=False)
    assert _resolve(suites_app, exp) == ("it", False)


def test_unsupported_language_is_discarded(suites_app, logged):
    exp = _exp(suites_app, "forum", "lang-bad")
    _save(logged, exp, language="xx")
    assert logged.get(f"/admin/frontend_settings/get_settings?exp_id={exp}").get_json()["settings"]["language"] == ""


def test_admin_page_offers_the_supported_languages(suites_app, logged):
    html = logged.get("/admin/frontend_settings").get_data(as_text=True)
    assert 'id="language"' in html and '<option value="it">Italiano</option>' in html


def test_experiment_language_selects_the_locale_and_cookie_override_follows_the_switch(suites_app, logged):
    exp = _exp(suites_app, "microblogging", "lang-locale")
    _save(logged, exp, language="it", language_switch_allowed=False)
    with suites_app.test_request_context(f"/{exp}/feed", headers={"Accept-Language": "en"}) as ctx:
        ctx.request.view_args = {"exp_id": exp}
        ctx.request.blueprint  # noqa: B018
        assert i18n._experiment_language() == ("it", False)


# ---- F4-3..F4-9: simulation templates and scripts ----------------------------------------------
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM_DIRS = ("microblogging", "forum", "photo", "login", "shared", "error_pages")
# Interface labels derived from a field: the only dynamic values that may go through _().
LABEL_FIELDS = {"author_type_badge", "adhoc_agent_badge"}


def test_user_generated_text_never_goes_through_the_catalogs():
    """Posts, comments, agent replies and profile bios are data: ``_(item['content'])`` would be a leak."""
    pattern = re.compile(r"_\(\s*(?:item|cm|thread|post|comment|message|user|agent)\s*(?:\[|\.get\()\s*['\"](\w+)")
    offenders = []
    for folder in SIM_DIRS:
        for path in (ROOT / "y_web" / "templates" / folder).rglob("*.html"):
            for field in pattern.findall(path.read_text(encoding="utf-8")):
                if field not in LABEL_FIELDS:
                    offenders.append((path.name, field))
    assert not offenders


def test_simulation_javascript_catalog_is_complete_and_consistent():
    base = ROOT / "y_web" / "translations" / "js" / "simulation"
    en = json.loads((base / "en.json").read_text(encoding="utf-8"))
    it = json.loads((base / "it.json").read_text(encoding="utf-8"))
    assert en.keys() == it.keys() and len(en) > 100
    placeholder = re.compile(r"\{(\w+)\}")
    for key, text in it.items():
        assert text and sorted(placeholder.findall(key)) == sorted(placeholder.findall(text)), key
    call = re.compile(r"YI18n\.tn?\(\s*'((?:\\.|[^'\\])*)'")
    used = set()
    for path in (ROOT / "y_web" / "static" / "assets" / "js").rglob("*.js"):
        if path.name.startswith("admin") or path.name in {"i18n.js", "app.js"}:
            continue
        used |= {k.replace("\\'", "'") for k in call.findall(path.read_text(encoding="utf-8", errors="ignore"))}
    admin_or_core = json.loads((ROOT / "y_web" / "translations" / "js" / "core" / "en.json").read_text(encoding="utf-8")).keys()
    missing = {k for k in used if k not in en and k not in admin_or_core}
    # keys of other domains (admin, tutorials) live in their own catalogs
    other = set()
    for domain in ("admin", "tutorials"):
        for f in (ROOT / "y_web" / "translations" / "js" / domain).glob("en.json"):
            other |= set(json.loads(f.read_text(encoding="utf-8")))
    assert not (missing - other), sorted(missing - other)[:10]


def test_simulation_pages_load_the_simulation_catalog():
    for page in ("microblogging/header.html", "forum/header.html", "photo/base.html", "login/scene_base.html"):
        assert 'data-domains="simulation"' in (ROOT / "y_web" / "templates" / page).read_text(encoding="utf-8")


def test_italian_catalog_translates_the_participant_labels():
    from flask import Flask

    app = Flask("y_web")
    app.config.update(SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"), TESTING=True)
    i18n.init_i18n(app)

    def render(source):
        with app.test_request_context("/", headers={"Accept-Language": "it"}):
            return app.jinja_env.from_string(source).render()

    assert render("{{ _('Unfollow') }}") == "Non seguire pi\u00f9"
    assert render("{{ _('Day %(day)s - %(hour)s:00', day=3, hour=7) }}") == "Giorno 3 - 7:00"
    assert render("{{ ngettext('%(num)s photo', '%(num)s photos', 2) }}") == "2 foto"
    assert render("{{ _('AI Agent') }}") == "Agente IA"


def test_participant_language_selector_follows_the_experiment_switch():
    from flask import Blueprint, Flask, render_template

    app = Flask("y_web")
    app.config.update(SECRET_KEY="t", SUPPORTED_LANGUAGES=("en", "it"), TESTING=True)
    sim = Blueprint("main", __name__)

    @sim.route("/<int:exp_id>/x")
    def x(exp_id):
        return render_template("shared/language_switcher.html")

    app.register_blueprint(sim)
    app.template_folder = str(ROOT / "y_web" / "templates")
    i18n.init_i18n(app)
    try:
        i18n.experiment_language_resolver = lambda: ("it", False)
        assert 'name="lang"' not in app.test_client().get("/1/x").get_data(as_text=True)
        i18n.experiment_language_resolver = lambda: ("it", True)
        html = app.test_client().get("/1/x").get_data(as_text=True)
        assert 'name="scope" value="sim"' in html and '<option value="it" selected>Italiano</option>' in html
    finally:
        i18n.experiment_language_resolver = None
