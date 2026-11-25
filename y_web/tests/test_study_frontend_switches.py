"""The ``show_search`` / ``show_profile_links`` frontend switches (YServer / YSimulator microblogging templates).

The templates are rendered with a stub environment: only the switch logic is under test, not the whole page.
"""

from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parents[2] / "external"
REPOS = [r for r in ("YServer", "YSimulator") if (ROOT / r / "ysocial_platform").is_dir()]
pytestmark = pytest.mark.skipif(not REPOS, reason="microblogging repositories not installed")


def _env(repo):
    loader = jinja2.FileSystemLoader(str(ROOT / repo / "ysocial_platform" / "templates"))
    env = jinja2.Environment(loader=loader, extensions=["jinja2.ext.i18n"])
    env.install_null_translations(newstyle=True)
    env.filters["display_name"] = lambda v: v
    env.filters["user_image_id"] = lambda v: "1"
    env.globals.update(len=len, url_for=lambda *a, **k: "/static/x", str=str)
    return env


def _render(repo, name, ui, **ctx):
    ctx.setdefault("exp_id", 7)
    if ui is not None:
        ctx["ui"] = ui
    return _env(repo).get_template(name).render(**ctx)


@pytest.mark.parametrize("repo", REPOS)
@pytest.mark.parametrize(
    "ui, linked",
    [(None, True), ({}, True), ({"show_profile_links": True}, True), ({"show_profile_links": False}, False)],
)
def test_suggested_friends_profile_links(repo, ui, linked):
    html = _render(
        repo,
        "microblogging/components/suggested_friends.html",
        ui,
        sfollow=[{"id": 3, "username": "ann", "profile_pic": ""}],
        user_id=1,
    )
    assert ("/7/profile/3/recent/1" in html) is linked
    assert "ann" in html
    assert "/7/follow/3/1" in html  # unrelated links stay


@pytest.mark.parametrize("repo", REPOS)
def test_every_gated_template_compiles(repo):
    env = _env(repo)
    base = ROOT / repo / "ysocial_platform" / "templates" / "microblogging"
    for rel in (
        "header.html",
        "explore.html",
        "profile.html",
        "notifications.html",
        "components/bsky_shell.html",
        "components/posts.html",
        "components/thread-post.html",
        "components/friends_panel.html",
        "components/suggested_pages.html",
        "components/suggested_friends.html",
    ):
        src = (base / rel).read_text(encoding="utf-8")
        env.parse(src)  # a broken {% if %}/{% endif %} pairing raises here


@pytest.mark.parametrize("repo", REPOS)
def test_search_boxes_are_wrapped_in_the_switch(repo):
    base = ROOT / repo / "ysocial_platform" / "templates" / "microblogging"
    for rel, needle in (
        ("header.html", "ys-mb-header-search-shell"),
        ("header.html", "ys-mb-header-mobile-search-item"),
        ("components/bsky_shell.html", "bsky-searchslot"),
        ("explore.html", "bsky-explore-search"),
    ):
        lines = (base / rel).read_text(encoding="utf-8").split("\n")
        i = next(k for k, l in enumerate(lines) if needle in l)
        assert "show_search" in lines[i - 1], (rel, needle)


@pytest.mark.parametrize("repo", REPOS)
def test_provider_declares_the_switches(repo):
    src = (ROOT / repo / "ysocial_platform" / "provider.py").read_text(encoding="utf-8")
    slot = (ROOT / repo / "ysocial_platform" / "templates" / "slots" / "frontend_settings_feed.html").read_text(
        encoding="utf-8"
    )
    for key in ("show_search", "show_profile_links"):
        assert f'FrontendSetting("{key}", True)' in src
        assert f'id="{key}"' in slot
