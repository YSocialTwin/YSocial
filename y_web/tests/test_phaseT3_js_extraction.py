"""
Phase T3 validation tests.

Verifies that:
  T3a — Alert-dismissal and sidebar-toggle JS extracted to admin-layout.js;
        inline <script> blocks removed from admin/head.html;
        admin/footer.html loads admin-layout.js.
  T3b — Navigation helper functions extracted to admin-nav.js;
        inline <script> blocks removed from admin/dash_head.html;
        admin/footer.html loads admin-nav.js.
  T3c — BrowserSync block deduplicated into templates/shared/browser_sync.html;
        all 5 originating templates now use
        ``{% include 'shared/browser_sync.html' %}``.
"""

import os

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TEMPLATES_DIR = os.path.join(REPO_ROOT, "y_web", "templates")
STATIC_JS_DIR = os.path.join(REPO_ROOT, "y_web", "static", "assets", "js")

HEAD_HTML = os.path.join(TEMPLATES_DIR, "admin", "head.html")
DASH_HEAD_HTML = os.path.join(TEMPLATES_DIR, "admin", "dash_head.html")
FOOTER_HTML = os.path.join(TEMPLATES_DIR, "admin", "footer.html")
BROWSER_SYNC_PARTIAL = os.path.join(TEMPLATES_DIR, "shared", "browser_sync.html")
ADMIN_LAYOUT_JS = os.path.join(STATIC_JS_DIR, "admin-layout.js")
ADMIN_NAV_JS = os.path.join(STATIC_JS_DIR, "admin-nav.js")

# The 5 templates that previously had the inline BrowserSync block
BROWSERSYNC_TEMPLATE_FILES = [
    os.path.join(TEMPLATES_DIR, "admin", "head.html"),
    os.path.join(TEMPLATES_DIR, "forum", "header.html"),
    os.path.join(TEMPLATES_DIR, "microblogging", "header.html"),
    os.path.join(TEMPLATES_DIR, "login", "login.html"),
    os.path.join(TEMPLATES_DIR, "login", "register.html"),
]


# ---------------------------------------------------------------------------
# T3a — admin-layout.js
# ---------------------------------------------------------------------------

class TestAdminLayoutJs:
    """admin-layout.js must exist and contain alert + sidebar functions."""

    def test_file_exists(self):
        assert os.path.isfile(ADMIN_LAYOUT_JS), \
            "y_web/static/assets/js/admin-layout.js not found"

    def test_file_non_empty(self):
        assert os.path.getsize(ADMIN_LAYOUT_JS) > 0

    def test_contains_alert_dismissal(self):
        js = open(ADMIN_LAYOUT_JS, encoding="utf-8").read()
        assert 'data-dismiss="alert"' in js, \
            "admin-layout.js must contain the alert dismissal handler"

    def test_contains_toggle_sidebar_function(self):
        js = open(ADMIN_LAYOUT_JS, encoding="utf-8").read()
        assert "function toggleSidebar" in js, \
            "admin-layout.js must contain toggleSidebar()"

    def test_contains_close_sidebar_function(self):
        js = open(ADMIN_LAYOUT_JS, encoding="utf-8").read()
        assert "function closeSidebar" in js, \
            "admin-layout.js must contain closeSidebar()"


class TestHeadHtmlScriptBlocks:
    """admin/head.html must have no inline <script> blocks."""

    def test_head_html_has_no_inline_script_block(self):
        content = open(HEAD_HTML, encoding="utf-8").read()
        # Count <script> without src=
        import re
        inline = [line for line in content.splitlines()
                  if re.search(r'<script(?![^>]*\bsrc\b)', line)]
        assert len(inline) == 0, (
            f"admin/head.html must have zero inline <script> blocks after T3a, "
            f"found: {inline}"
        )

    def test_head_html_has_no_toggle_sidebar_definition(self):
        content = open(HEAD_HTML, encoding="utf-8").read()
        assert "function toggleSidebar" not in content, \
            "admin/head.html must not contain toggleSidebar() definition after T3a"

    def test_head_html_has_no_alert_dismissal_definition(self):
        content = open(HEAD_HTML, encoding="utf-8").read()
        assert 'data-dismiss="alert"' not in content, \
            "admin/head.html must not contain the alert dismissal handler inline"


# ---------------------------------------------------------------------------
# T3b — admin-nav.js
# ---------------------------------------------------------------------------

class TestAdminNavJs:
    """admin-nav.js must exist and contain the navigation helper functions."""

    def test_file_exists(self):
        assert os.path.isfile(ADMIN_NAV_JS), \
            "y_web/static/assets/js/admin-nav.js not found"

    def test_file_non_empty(self):
        assert os.path.getsize(ADMIN_NAV_JS) > 0

    def test_contains_open_external_url(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "function openExternalUrl" in js, \
            "admin-nav.js must contain openExternalUrl()"

    def test_contains_mark_blog_post_as_read(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "function markBlogPostAsRead" in js

    def test_contains_dismiss_blog_post(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "function dismissBlogPost" in js

    def test_contains_replay_page_tutorial(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "function replayPageTutorial" in js, \
            "admin-nav.js must contain replayPageTutorial()"

    def test_contains_tutorial_functions_list(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "startDashboardTutorial" in js, \
            "admin-nav.js must contain the tutorial function list"

    def test_contains_escape_html(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "function escapeHtml" in js, \
            "admin-nav.js must contain escapeHtml()"

    def test_contains_render_download_notifications(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "function renderDownloadNotifications" in js

    def test_contains_refresh_download_notifications(self):
        js = open(ADMIN_NAV_JS, encoding="utf-8").read()
        assert "refreshDownloadNotifications" in js


class TestDashHeadHtmlScriptBlocks:
    """admin/dash_head.html must have no inline <script> blocks."""

    def test_dash_head_has_no_inline_script_block(self):
        content = open(DASH_HEAD_HTML, encoding="utf-8").read()
        import re
        inline = [line for line in content.splitlines()
                  if re.search(r'<script(?![^>]*\bsrc\b)', line)]
        assert len(inline) == 0, (
            f"admin/dash_head.html must have zero inline <script> blocks after T3b, "
            f"found: {inline}"
        )

    def test_dash_head_has_no_function_definitions(self):
        content = open(DASH_HEAD_HTML, encoding="utf-8").read()
        assert "function openExternalUrl" not in content
        assert "function markBlogPostAsRead" not in content
        assert "function dismissBlogPost" not in content
        assert "function replayPageTutorial" not in content
        assert "function escapeHtml" not in content
        assert "function renderDownloadNotifications" not in content


# ---------------------------------------------------------------------------
# Footer loads both JS files
# ---------------------------------------------------------------------------

class TestFooterHtml:
    """admin/footer.html must load admin-layout.js and admin-nav.js."""

    def test_footer_loads_admin_layout_js(self):
        content = open(FOOTER_HTML, encoding="utf-8").read()
        assert "admin-layout.js" in content, \
            "admin/footer.html must include a <script src> for admin-layout.js"

    def test_footer_loads_admin_nav_js(self):
        content = open(FOOTER_HTML, encoding="utf-8").read()
        assert "admin-nav.js" in content, \
            "admin/footer.html must include a <script src> for admin-nav.js"

    def test_footer_uses_url_for_for_admin_layout(self):
        content = open(FOOTER_HTML, encoding="utf-8").read()
        assert "url_for('static', filename='assets/js/admin-layout.js')" in content

    def test_footer_uses_url_for_for_admin_nav(self):
        content = open(FOOTER_HTML, encoding="utf-8").read()
        assert "url_for('static', filename='assets/js/admin-nav.js')" in content


# ---------------------------------------------------------------------------
# T3c — BrowserSync shared partial
# ---------------------------------------------------------------------------

class TestBrowserSyncPartial:
    """shared/browser_sync.html must exist and contain the BrowserSync snippet."""

    def test_partial_exists(self):
        assert os.path.isfile(BROWSER_SYNC_PARTIAL), \
            "y_web/templates/shared/browser_sync.html not found"

    def test_partial_contains_bs_script_id(self):
        content = open(BROWSER_SYNC_PARTIAL, encoding="utf-8").read()
        assert 'id="__bs_script__"' in content, \
            "shared/browser_sync.html must contain the BrowserSync <script> block"

    def test_partial_contains_browser_sync_client(self):
        content = open(BROWSER_SYNC_PARTIAL, encoding="utf-8").read()
        assert "browser-sync-client.js" in content

    def test_bs_script_id_appears_exactly_once_in_templates(self):
        """The raw __bs_script__ id must appear in exactly one file (the shared partial)."""
        found = []
        for root, _dirs, files in os.walk(TEMPLATES_DIR):
            for fname in files:
                if fname.endswith(".html"):
                    path = os.path.join(root, fname)
                    if 'id="__bs_script__"' in open(path, encoding="utf-8").read():
                        found.append(path.replace(TEMPLATES_DIR + os.sep, ""))
        assert found == ["shared/browser_sync.html"], (
            f'Expected id="__bs_script__" to appear only in shared/browser_sync.html, '
            f"but found it in: {found}"
        )

    def test_all_five_templates_include_browser_sync_partial(self):
        """All 5 templates that had BrowserSync must now include the shared partial."""
        include_directive = "{% include 'shared/browser_sync.html' %}"
        missing = []
        for fpath in BROWSERSYNC_TEMPLATE_FILES:
            rel = os.path.relpath(fpath, TEMPLATES_DIR)
            content = open(fpath, encoding="utf-8").read()
            if include_directive not in content:
                missing.append(rel)
        assert not missing, (
            f"The following templates should include 'shared/browser_sync.html' "
            f"but do not: {missing}"
        )


# ---------------------------------------------------------------------------
# Global inline-script reduction
# ---------------------------------------------------------------------------

class TestGlobalInlineScriptReduction:
    """Total pure-inline <script> count must have decreased from the T2 baseline."""

    # Pre-T3 baseline value for total_inline_scripts (post-T2 state, pure <script> without any attributes)
    # as measured by the audit script using grep -rP '<script(?![^>]*src)>'
    T2_BASELINE_INLINE = 148

    def _count_pure_inline_scripts(self):
        """Count bare <script> tags (no attributes at all) — same regex as audit script."""
        import re
        # Pattern equivalent to audit script: <script(?![^>]*src)>
        # This matches ONLY '<script>' (the closing '>' must immediately follow 'script').
        # Case-insensitive to handle any case variation in templates.
        pattern = re.compile(r'<script(?![^>]*src)>', re.IGNORECASE)
        total = 0
        for root, _dirs, files in os.walk(TEMPLATES_DIR):
            for fname in files:
                if fname.endswith(".html"):
                    text = open(os.path.join(root, fname), encoding="utf-8").read()
                    total += len(pattern.findall(text))
        return total

    def test_inline_script_count_decreased(self):
        current = self._count_pure_inline_scripts()
        decrease = self.T2_BASELINE_INLINE - current
        assert decrease >= 5, (
            f"Expected pure inline <script> count to decrease by at least 5 from "
            f"T2 baseline of {self.T2_BASELINE_INLINE}, but decrease was only "
            f"{decrease} (current: {current})"
        )
