"""The "Instant messaging pages" and "Dating pages" boxes of /admin/frontend_settings belong to their own
platform, and the page works whichever platforms (and plugin suites) are installed.

Unlike test_frontend_settings_platforms.py this needs no plugin suite and no external repository, so it also
runs in a clean checkout.
"""

import os

import pytest
from jinja2 import FileSystemLoader

from y_web import db
from y_web.tests import _platform_alias
from y_web.tests.test_frontend_settings_generic_suite_panel import (
    _login,
    _make_admin_login_user,
)
from y_web.tests.test_frontend_settings_platforms import _exp

pytestmark = pytest.mark.integration

PLATFORMS = [
    "microblogging",
    "forum",
    "photo_sharing",
    pytest.param(
        "instant_messaging",
        marks=pytest.mark.skipif(
            not _platform_alias.installed(_platform_alias.INSTANT_MESSAGING),
            reason="YInstantMessaging is not installed",
        ),
    ),
    pytest.param(
        "dating",
        marks=pytest.mark.skipif(
            not _platform_alias.installed(_platform_alias.DATING),
            reason="YDating is not installed",
        ),
    ),
]


@pytest.fixture
def panel_app(app):
    import y_web as pkg
    from y_web.i18n import init_i18n
    from y_web.routes.admin.sub.experiments import experiments

    with app.app_context():
        try:
            db.create_all(bind_key="__all__")
        except TypeError:
            db.create_all()
    if "experiments" not in app.blueprints:
        app.register_blueprint(experiments)
    app.jinja_loader = FileSystemLoader(
        os.path.join(os.path.dirname(pkg.__file__), "templates")
    )
    init_i18n(app)
    # the real create_app() registers it; the page only lists it
    app.jinja_env.globals.setdefault("world_simulation_of", lambda *a, **k: None)
    return app


@pytest.fixture
def logged(panel_app):
    client = panel_app.test_client()
    _login(client, _make_admin_login_user(panel_app))
    return client


def _settings(client, exp):
    response = client.get(f"/admin/frontend_settings/get_settings?exp_id={exp}")
    assert response.status_code == 200
    return response.get_json()


def _shown(data, keys):
    """What the page's applyPlatform() does with a data-cap-any box."""
    caps, excluded = data["capabilities"], set(data["excluded_capabilities"])
    if caps is None:
        return any(k not in excluded for k in keys)
    return any(k in set(caps) for k in keys)


def _box_keys(page, box_id):
    """Capabilities a box of the page is for (none when the page has no such box: its platform is not installed)."""
    if f'id="{box_id}"' not in page:
        return []
    start = page.index(f'id="{box_id}"')
    tag = page[page.rindex("<div", 0, start) : page.index(">", start)]
    return tag.split('data-cap-any="')[1].split('"')[0].split()


@pytest.mark.parametrize("platform", PLATFORMS)
def test_each_box_is_shown_only_for_its_own_platform(panel_app, logged, platform):
    exp = _exp(panel_app, platform, f"box_{platform}")
    page = logged.get("/admin/frontend_settings")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    data = _settings(logged, exp)
    assert _shown(data, _box_keys(html, "box-im")) == (platform == "instant_messaging")
    assert _shown(data, _box_keys(html, "box-dating")) == (platform == "dating")


@pytest.mark.parametrize("platform", PLATFORMS)
def test_the_page_works_whichever_platform_the_experiment_has(
    panel_app, logged, platform
):
    # no external repository, no plugin suite: every answer is a page, never a server error
    exp = _exp(panel_app, platform, f"smoke_{platform}")
    for url in (
        "/admin/frontend_settings",
        f"/admin/frontend_settings/get_settings?exp_id={exp}",
    ):
        assert logged.get(url).status_code == 200, url
