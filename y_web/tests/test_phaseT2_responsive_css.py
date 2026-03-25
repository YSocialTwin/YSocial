"""
Phase T2 validation tests.

Verifies that:
  - ``y_web/static/assets/css/admin-responsive.css`` exists, is non-empty, and
    contains the key CSS rules that were extracted from the two template files.
  - ``admin/head.html`` no longer contains a ``<style>`` block.
  - ``admin/head.html`` links ``admin-responsive.css``.
  - ``admin/dash_head.html`` no longer contains a ``<style>`` block.
  - The total ``<style>``-block count across all templates has decreased to ≤ 71
    (from the Phase T1 baseline of 73).
"""

import os
import re

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "y_web", "templates")
STATIC_CSS_DIR = os.path.join(REPO_ROOT, "y_web", "static", "assets", "css")

HEAD_HTML = os.path.join(TEMPLATES_DIR, "admin", "head.html")
DASH_HEAD_HTML = os.path.join(TEMPLATES_DIR, "admin", "dash_head.html")
RESPONSIVE_CSS = os.path.join(STATIC_CSS_DIR, "admin-responsive.css")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_style_blocks(path):
    """Return the number of ``<style>`` tags in a file."""
    return open(path, encoding="utf-8").read().count("<style>")


def _count_style_blocks_in_dir(directory):
    """Recursively count all ``<style>`` tags in .html files under *directory*."""
    total = 0
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if fname.endswith(".html"):
                total += _count_style_blocks(os.path.join(root, fname))
    return total


# ---------------------------------------------------------------------------
# 1. admin-responsive.css must exist with expected content
# ---------------------------------------------------------------------------


class TestResponsiveCssFile:
    """y_web/static/assets/css/admin-responsive.css must exist and contain
    the rules extracted from admin/head.html and admin/dash_head.html."""

    def test_css_file_exists(self):
        assert os.path.isfile(RESPONSIVE_CSS), (
            "y_web/static/assets/css/admin-responsive.css not found. "
            "Phase T2 requires this file to be created."
        )

    def test_css_file_non_empty(self):
        assert (
            os.path.getsize(RESPONSIVE_CSS) > 0
        ), "admin-responsive.css must not be empty"

    # ---- Rules from head.html (sidebar) ------------------------------------

    def test_css_contains_sidebar_toggle_rule(self):
        css = open(RESPONSIVE_CSS, encoding="utf-8").read()
        assert (
            ".sidebar-toggle-btn" in css
        ), "admin-responsive.css must contain .sidebar-toggle-btn rule"

    def test_css_contains_sidebar_overlay_rule(self):
        css = open(RESPONSIVE_CSS, encoding="utf-8").read()
        assert (
            ".sidebar-overlay" in css
        ), "admin-responsive.css must contain .sidebar-overlay rule"

    def test_css_contains_mobile_media_query_768(self):
        css = open(RESPONSIVE_CSS, encoding="utf-8").read()
        assert (
            "max-width: 768px" in css
        ), "admin-responsive.css must contain the @media max-width:768px breakpoint"

    def test_css_contains_tutorial_highlighted_rule(self):
        css = open(RESPONSIVE_CSS, encoding="utf-8").read()
        assert (
            ".dashboard-aside-link.tutorial-highlighted" in css
        ), "admin-responsive.css must contain .dashboard-aside-link.tutorial-highlighted"

    # ---- Rules from dash_head.html (toolbar / download notifications) ------

    def test_css_contains_download_notification_badge_rule(self):
        css = open(RESPONSIVE_CSS, encoding="utf-8").read()
        assert (
            ".download-notification-badge" in css
        ), "admin-responsive.css must contain .download-notification-badge rule"

    def test_css_contains_dashboard_toolbar_rule(self):
        css = open(RESPONSIVE_CSS, encoding="utf-8").read()
        assert (
            ".dashboard-toolbar" in css
        ), "admin-responsive.css must contain .dashboard-toolbar rule"

    def test_css_contains_mobile_media_query_1024(self):
        css = open(RESPONSIVE_CSS, encoding="utf-8").read()
        assert (
            "max-width: 1024px" in css
        ), "admin-responsive.css must contain the @media max-width:1024px breakpoint"


# ---------------------------------------------------------------------------
# 2. admin/head.html must reference admin-responsive.css and have no <style>
# ---------------------------------------------------------------------------


class TestHeadHtml:
    """admin/head.html must link admin-responsive.css and have no inline <style>."""

    def test_head_html_has_no_style_block(self):
        blocks = _count_style_blocks(HEAD_HTML)
        assert blocks == 0, (
            f"admin/head.html must contain zero <style> blocks after Phase T2, "
            f"found {blocks}"
        )

    def test_head_html_links_responsive_css(self):
        content = open(HEAD_HTML, encoding="utf-8").read()
        assert (
            "admin-responsive.css" in content
        ), "admin/head.html must have a <link> to admin-responsive.css"

    def test_head_html_link_uses_url_for(self):
        content = open(HEAD_HTML, encoding="utf-8").read()
        assert (
            "url_for('static', filename='assets/css/admin-responsive.css')" in content
        ), "The admin-responsive.css link must use url_for('static', …)"


# ---------------------------------------------------------------------------
# 3. admin/dash_head.html must have no <style>
# ---------------------------------------------------------------------------


class TestDashHeadHtml:
    """admin/dash_head.html must contain no inline <style> block after Phase T2."""

    def test_dash_head_html_has_no_style_block(self):
        blocks = _count_style_blocks(DASH_HEAD_HTML)
        assert blocks == 0, (
            f"admin/dash_head.html must contain zero <style> blocks after Phase T2, "
            f"found {blocks}"
        )


# ---------------------------------------------------------------------------
# 4. Global style-block count must have decreased
# ---------------------------------------------------------------------------


class TestGlobalStyleBlockCount:
    """The total <style>-block count across all templates must be ≤ 71."""

    def test_total_style_blocks_at_most_71(self):
        total = _count_style_blocks_in_dir(TEMPLATES_DIR)
        assert total <= 71, (
            f"Expected ≤ 71 total <style> blocks across all templates after "
            f"Phase T2, but found {total}. "
            "Two blocks should have been removed (one from head.html, one from "
            "dash_head.html)."
        )

    def test_total_style_blocks_decreased_by_at_least_2(self):
        """The Phase T1 baseline was 73; after T2 we expect a drop of ≥ 2."""
        PHASE_T1_BASELINE = 73
        total = _count_style_blocks_in_dir(TEMPLATES_DIR)
        decrease = PHASE_T1_BASELINE - total
        assert decrease >= 2, (
            f"Expected a decrease of at least 2 <style> blocks from the T1 "
            f"baseline of 73, but only found {decrease} (current: {total})."
        )
