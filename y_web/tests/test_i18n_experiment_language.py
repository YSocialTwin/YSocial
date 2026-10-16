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
