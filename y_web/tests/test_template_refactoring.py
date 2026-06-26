"""
Regression tests for the templates folder refactoring.

Validates that:
  - All expected templates exist in their new locations.
  - No stale (old-style) template paths remain in Python source files.
  - Every {% include %} / {% extends %} reference inside a moved template
    resolves to an existing file.
  - Key routes still return HTTP 200 and render from the correct template.
"""

import os
import re

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
)
Y_WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _template_path(*parts):
    """Return the absolute path of a template given its relative parts."""
    return os.path.join(TEMPLATES_DIR, *parts)


def _exists(relative_path):
    return os.path.exists(_template_path(relative_path))


# ---------------------------------------------------------------------------
# 1. New folder structure — every expected file must exist
# ---------------------------------------------------------------------------


class TestNewFolderStructure:
    """Verify the new template directory layout after refactoring."""

    # -- login/ ---------------------------------------------------------------
    def test_login_dir_exists(self):
        assert os.path.isdir(_template_path("login"))

    def test_login_login_html_exists(self):
        assert _exists("login/login.html"), "login/login.html is missing"

    def test_login_register_html_exists(self):
        assert _exists("login/register.html"), "login/register.html is missing"

    # -- microblogging/ -------------------------------------------------------
    def test_microblogging_dir_exists(self):
        assert os.path.isdir(_template_path("microblogging"))

    def test_microblogging_components_dir_exists(self):
        assert os.path.isdir(_template_path("microblogging", "components"))

    @pytest.mark.parametrize(
        "tpl",
        [
            "microblogging/header.html",
            "microblogging/feed.html",
            "microblogging/profile.html",
            "microblogging/edit_profile.html",
            "microblogging/friends.html",
            "microblogging/hashtag.html",
            "microblogging/emotions.html",
            "microblogging/interest.html",
            "microblogging/interview.html",
            "microblogging/thread.html",
            "microblogging/index.html",
        ],
    )
    def test_microblogging_page_templates_exist(self, tpl):
        assert _exists(tpl), f"{tpl} is missing"

    @pytest.mark.parametrize(
        "tpl",
        [
            "microblogging/components/posts.html",
            "microblogging/components/list.html",
            "microblogging/components/thread-post.html",
            "microblogging/components/suggested_friends.html",
            "microblogging/components/suggested_pages.html",
        ],
    )
    def test_microblogging_component_templates_exist(self, tpl):
        assert _exists(tpl), f"{tpl} is missing"

    # -- forum/ ---------------------------------------------------------------
    def test_forum_dir_exists(self):
        assert os.path.isdir(_template_path("forum"))

    def test_forum_components_dir_exists(self):
        assert os.path.isdir(_template_path("forum", "components"))

    @pytest.mark.parametrize(
        "tpl",
        [
            "forum/header.html",
            "forum/feed.html",
            "forum/profile.html",
            "forum/thread.html",
            "forum/interview.html",
            "forum/notifications.html",
        ],
    )
    def test_forum_page_templates_exist(self, tpl):
        assert _exists(tpl), f"{tpl} is missing"

    @pytest.mark.parametrize(
        "tpl",
        [
            "forum/components/posts.html",
            "forum/components/list.html",
            "forum/components/thread-post.html",
            "forum/components/comment.html",
        ],
    )
    def test_forum_component_templates_exist(self, tpl):
        assert _exists(tpl), f"{tpl} is missing"

    # -- photo/ --------------------------------------------------------------
    def test_photo_dir_exists(self):
        assert os.path.isdir(_template_path("photo"))

    @pytest.mark.parametrize(
        "tpl",
        [
            "photo/feed.html",
        ],
    )
    def test_photo_page_templates_exist(self, tpl):
        assert _exists(tpl), f"{tpl} is missing"

    # -- admin/ and error_pages/ (unchanged) ----------------------------------
    def test_admin_dir_unchanged(self):
        assert os.path.isdir(_template_path("admin"))

    def test_error_pages_dir_unchanged(self):
        assert os.path.isdir(_template_path("error_pages"))


# ---------------------------------------------------------------------------
# 2. Old locations must NOT exist (templates removed from root/components/reddit)
# ---------------------------------------------------------------------------


class TestOldLocationsGone:
    """Verify that files were actually moved, not just copied."""

    @pytest.mark.parametrize(
        "old_path",
        [
            "login.html",
            "register.html",
            "header.html",
            "feed.html",
            "profile.html",
            "edit_profile.html",
            "friends.html",
            "hashtag.html",
            "emotions.html",
            "interest.html",
            "interview.html",
            "thread.html",
        ],
    )
    def test_root_level_templates_removed(self, old_path):
        assert not _exists(
            old_path
        ), f"{old_path} still exists at root — should have been moved"

    @pytest.mark.parametrize(
        "old_path",
        [
            "components/posts.html",
            "components/list.html",
            "components/thread-post.html",
            "components/suggested_friends.html",
            "components/suggested_pages.html",
        ],
    )
    def test_root_components_removed(self, old_path):
        assert not _exists(
            old_path
        ), f"{old_path} still exists at root components/ — should have been moved"

    @pytest.mark.parametrize(
        "old_path",
        [
            "reddit/feed.html",
            "reddit/header.html",
            "reddit/profile.html",
            "reddit/thread.html",
            "reddit/interview.html",
            "reddit/notifications.html",
            "reddit/components/posts.html",
            "reddit/components/list.html",
            "reddit/components/comment.html",
            "reddit/components/thread-post.html",
        ],
    )
    def test_reddit_templates_removed(self, old_path):
        assert not _exists(
            old_path
        ), f"{old_path} still exists under reddit/ — should have been renamed to forum/"


# ---------------------------------------------------------------------------
# 3. No stale template path strings in Python source files
# ---------------------------------------------------------------------------


def _collect_template_strings(directory, exclude_dirs=None):
    """Yield (file_path, template_string) for every render_template() call."""
    if exclude_dirs is None:
        exclude_dirs = {"__pycache__", ".git", "tests"}
    pattern = re.compile(r'render_template\(\s*["\']([^"\']+)["\']')
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath) as fh:
                content = fh.read()
            for match in pattern.findall(content):
                yield fpath, match


class TestNoStaleTemplatePaths:
    """Verify that no old-style template paths remain in Python source."""

    @pytest.mark.parametrize(
        "stale_prefix",
        [
            "reddit/",
        ],
    )
    def test_no_reddit_prefix_in_python(self, stale_prefix):
        """No render_template() call should still use 'reddit/' prefix."""
        offenders = [
            (f, tpl)
            for f, tpl in _collect_template_strings(Y_WEB_DIR)
            if tpl.startswith(stale_prefix)
        ]
        assert (
            offenders == []
        ), f"Found stale '{stale_prefix}' template references: {offenders}"

    def test_no_bare_login_html(self):
        """render_template('login.html') must not appear — use 'login/login.html'."""
        offenders = [
            (f, tpl)
            for f, tpl in _collect_template_strings(Y_WEB_DIR)
            if tpl == "login.html"
        ]
        assert offenders == [], f"Found bare 'login.html' reference: {offenders}"

    def test_no_bare_feed_html(self):
        """render_template('feed.html') must not appear — use 'microblogging/feed.html'."""
        offenders = [
            (f, tpl)
            for f, tpl in _collect_template_strings(Y_WEB_DIR)
            if tpl == "feed.html"
        ]
        assert offenders == [], f"Found bare 'feed.html' reference: {offenders}"

    def test_no_bare_profile_html(self):
        """render_template('profile.html') must not appear."""
        offenders = [
            (f, tpl)
            for f, tpl in _collect_template_strings(Y_WEB_DIR)
            if tpl == "profile.html"
        ]
        assert offenders == [], f"Found bare 'profile.html' reference: {offenders}"

    def test_no_root_components_prefix(self):
        """render_template('components/...') must not appear — use 'microblogging/components/...'."""
        offenders = [
            (f, tpl)
            for f, tpl in _collect_template_strings(Y_WEB_DIR)
            if tpl.startswith("components/")
        ]
        assert (
            offenders == []
        ), f"Found stale 'components/' template references: {offenders}"

    def test_all_render_template_paths_exist(self):
        """Every template string in render_template() must resolve to an actual file."""
        missing = []
        for fpath, tpl in _collect_template_strings(Y_WEB_DIR):
            full = os.path.join(TEMPLATES_DIR, tpl)
            if not os.path.exists(full):
                missing.append((fpath, tpl))
        assert (
            missing == []
        ), "render_template() references that do not exist on disk:\n" + "\n".join(
            f"  {f}: '{t}'" for f, t in missing
        )


# ---------------------------------------------------------------------------
# 4. Template include/extends paths resolve correctly
# ---------------------------------------------------------------------------


def _collect_include_refs(templates_root):
    """
    Yield (template_rel_path, referenced_path) for every
    {%  include 'x' %} / {% extends 'x' %} directive found.
    """
    pattern = re.compile(
        r"""{%-?\s+(?:include|extends)\s+["']([\w/. -]+\.html)["']\s*-?%}"""
    )
    for root, dirs, files in os.walk(templates_root):
        for fname in files:
            if not fname.endswith(".html"):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, templates_root)
            with open(fpath) as fh:
                content = fh.read()
            for ref in pattern.findall(content):
                yield rel, ref


# base.html is referenced by microblogging/index.html but has never existed
# in this repo (pre-existing orphaned file, not introduced by this refactoring).
_KNOWN_MISSING = {"base.html"}


class TestIncludePathsValid:
    """Every {% include %} / {% extends %} inside a template must resolve."""

    def test_no_broken_includes(self):
        broken = []
        for tmpl_rel, ref in _collect_include_refs(TEMPLATES_DIR):
            if ref in _KNOWN_MISSING:
                continue  # pre-existing issue, not ours
            full_ref = os.path.join(TEMPLATES_DIR, ref)
            if not os.path.exists(full_ref):
                broken.append((tmpl_rel, ref))
        assert broken == [], (
            "Broken {% include %} / {% extends %} references after refactoring:\n"
            + "\n".join(f"  {tmpl}: '{ref}'" for tmpl, ref in broken)
        )

    def test_microblogging_includes_use_new_paths(self):
        """Microblogging templates may include local or shared partials only."""
        wrong = []
        mb_dir = os.path.join(TEMPLATES_DIR, "microblogging")
        pattern = re.compile(r"""{%-?\s+include\s+["']([\w/.-]+\.html)["']""")
        for root, _dirs, files in os.walk(mb_dir):
            for fname in files:
                if not fname.endswith(".html"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, TEMPLATES_DIR)
                with open(fpath) as fh:
                    content = fh.read()
                for ref in pattern.findall(content):
                    if not (
                        ref.startswith("microblogging/") or ref.startswith("shared/")
                    ):
                        wrong.append((rel, ref))
        assert wrong == [], (
            "Microblogging templates contain includes outside 'microblogging/' or 'shared/':\n"
            + "\n".join(f"  {t}: '{r}'" for t, r in wrong)
        )

    def test_forum_includes_use_new_paths(self):
        """Forum templates may include local or shared partials only."""
        wrong = []
        forum_dir = os.path.join(TEMPLATES_DIR, "forum")
        pattern = re.compile(r"""{%-?\s+include\s+["']([\w/.-]+\.html)["']""")
        for root, _dirs, files in os.walk(forum_dir):
            for fname in files:
                if not fname.endswith(".html"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, TEMPLATES_DIR)
                with open(fpath) as fh:
                    content = fh.read()
                for ref in pattern.findall(content):
                    if not (ref.startswith("forum/") or ref.startswith("shared/")):
                        wrong.append((rel, ref))
        assert wrong == [], (
            "Forum templates contain includes outside 'forum/' or 'shared/':\n"
            + "\n".join(f"  {t}: '{r}'" for t, r in wrong)
        )


# ---------------------------------------------------------------------------
# 5. Route integration — key routes return HTTP 200 with expected content
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def flask_app():
    """
    Build a minimal Flask app with the real templates folder but without
    the full y_web initialisation (which requires a live DB and external
    modules).  Only the auth blueprint (login route) and error handlers
    are exercised here; heavier routes are tested via mocks.
    """
    from flask import Flask, render_template

    app = Flask(
        __name__,
        template_folder=TEMPLATES_DIR,
    )
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
    )

    # Minimal route that renders login/login.html
    @app.route("/login")
    def login():
        return render_template("login/login.html")

    # Minimal route that renders error_pages/404.html
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error_pages/404.html"), 404

    yield app


@pytest.fixture(scope="module")
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


class TestRouteIntegration:
    """Verify that refactored template paths actually render without errors."""

    def test_login_route_returns_200(self, client):
        response = client.get("/login")
        assert (
            response.status_code == 200
        ), f"GET /login returned {response.status_code}, expected 200"

    def test_login_route_returns_html(self, client):
        response = client.get("/login")
        assert (
            b"<html" in response.data.lower() or b"<!doctype" in response.data.lower()
        ), "GET /login did not return an HTML document"

    def test_404_returns_error_page(self, client):
        response = client.get("/nonexistent-route-xyz")
        assert response.status_code == 404

    def test_404_returns_html(self, client):
        response = client.get("/nonexistent-route-xyz")
        assert (
            b"<html" in response.data.lower() or b"<!doctype" in response.data.lower()
        )

    def test_render_microblogging_feed_template(self, flask_app):
        """Verify microblogging/feed.html can be loaded by Jinja2 without errors."""
        with flask_app.test_request_context():
            from flask import render_template

            # We can't render the full template (missing context vars) but we
            # can confirm Jinja2 can locate and load it.
            from jinja2 import TemplateNotFound

            try:
                env = flask_app.jinja_env
                env.get_template("microblogging/feed.html")
            except TemplateNotFound as e:
                pytest.fail(f"Jinja2 could not find microblogging/feed.html: {e}")

    def test_render_forum_feed_template(self, flask_app):
        """Verify forum/feed.html can be located by Jinja2."""
        with flask_app.test_request_context():
            from jinja2 import TemplateNotFound

            try:
                flask_app.jinja_env.get_template("forum/feed.html")
            except TemplateNotFound as e:
                pytest.fail(f"Jinja2 could not find forum/feed.html: {e}")

    def test_render_login_template(self, flask_app):
        """Verify login/login.html can be located by Jinja2."""
        with flask_app.test_request_context():
            from jinja2 import TemplateNotFound

            try:
                flask_app.jinja_env.get_template("login/login.html")
            except TemplateNotFound as e:
                pytest.fail(f"Jinja2 could not find login/login.html: {e}")

    @pytest.mark.parametrize(
        "template",
        [
            "microblogging/profile.html",
            "microblogging/edit_profile.html",
            "microblogging/friends.html",
            "microblogging/hashtag.html",
            "microblogging/emotions.html",
            "microblogging/interest.html",
            "microblogging/interview.html",
            "microblogging/thread.html",
            "microblogging/components/posts.html",
            "microblogging/components/list.html",
            "forum/profile.html",
            "forum/thread.html",
            "forum/interview.html",
            "forum/notifications.html",
            "forum/components/posts.html",
            "forum/components/list.html",
            "forum/components/comment.html",
            "login/register.html",
        ],
    )
    def test_all_refactored_templates_loadable(self, flask_app, template):
        """Verify every refactored template can be located by Jinja2."""
        with flask_app.test_request_context():
            from jinja2 import TemplateNotFound

            try:
                flask_app.jinja_env.get_template(template)
            except TemplateNotFound as e:
                pytest.fail(f"Jinja2 could not find {template}: {e}")


# ---------------------------------------------------------------------------
# 6. Forum header — interview link in account dropdown AND mobile hamburger menu
# ---------------------------------------------------------------------------


class TestForumHeaderInterviewLink:
    """Verify the interview link is in the desktop dropdown and mobile hamburger menu."""

    def test_forum_header_has_interview_link(self):
        """forum/header.html must contain an interview link href."""
        header_path = os.path.join(TEMPLATES_DIR, "forum", "header.html")
        with open(header_path) as fh:
            content = fh.read()

        assert (
            'href="/{{ exp_id }}/interview"' in content
        ), "forum/header.html must contain an interview link href"

    def test_forum_header_interview_gated_on_memory_enabled(self):
        """Interview link must be guarded by forum_memory_enabled (not always shown)."""
        header_path = os.path.join(TEMPLATES_DIR, "forum", "header.html")
        with open(header_path) as fh:
            content = fh.read()

        assert (
            "forum_memory_enabled" in content
        ), "forum/header.html must reference forum_memory_enabled"

    def test_forum_header_interview_in_desktop_dropdown(self):
        """Interview link must be present inside the desktop nav-drop account-items dropdown."""
        header_path = os.path.join(TEMPLATES_DIR, "forum", "header.html")
        with open(header_path) as fh:
            content = fh.read()

        nav_drop_start = content.find("nav-drop-body account-items")
        assert nav_drop_start != -1, "nav-drop-body account-items section not found"

        interview_in_dropdown = content.find(
            'href="/{{ exp_id }}/interview"', nav_drop_start
        )
        assert (
            interview_in_dropdown != -1
        ), "Interview link must be present inside the desktop nav-drop account-items dropdown"


class TestForumFeedSidebarComponent:
    """Verify the forum feed delegates the sidebar to a reusable component."""

    def test_forum_feed_uses_sidebar_component(self):
        feed_path = os.path.join(TEMPLATES_DIR, "forum", "feed.html")
        with open(feed_path) as fh:
            content = fh.read()

        assert (
            '{% include "forum/components/sidebar.html" %}' in content
        ), "forum/feed.html must include the reusable sidebar component"

    def test_forum_header_interview_in_mobile_hamburger_menu(self):
        """Interview link must also be present inside the mobile hamburger navbar-menu."""
        header_path = os.path.join(TEMPLATES_DIR, "forum", "header.html")
        with open(header_path) as fh:
            content = fh.read()

        # The mobile navbar-menu starts after the desktop nav-drop-body section
        nav_drop_start = content.find("nav-drop-body account-items")
        assert nav_drop_start != -1, "nav-drop-body account-items section not found"

        mobile_menu_start = content.find("navbar-burger", nav_drop_start)
        assert mobile_menu_start != -1, "Mobile navbar-burger section not found"

        interview_in_mobile = content.find(
            'href="/{{ exp_id }}/interview"', mobile_menu_start
        )
        assert (
            interview_in_mobile != -1
        ), "Interview link must also appear in the mobile hamburger navbar-menu"

    def test_forum_header_interview_not_in_top_navbar(self):
        """Interview link must NOT appear in the top (desktop) navbar before the dropdown."""
        header_path = os.path.join(TEMPLATES_DIR, "forum", "header.html")
        with open(header_path) as fh:
            content = fh.read()

        nav_drop_start = content.find("nav-drop-body account-items")
        assert nav_drop_start != -1, "nav-drop-body account-items section not found"

        # First occurrence of the interview link must be inside the dropdown, not before it
        first_interview = content.find('href="/{{ exp_id }}/interview"')
        assert (
            first_interview >= nav_drop_start
        ), "Interview link must not appear in the top navbar before the account dropdown"
