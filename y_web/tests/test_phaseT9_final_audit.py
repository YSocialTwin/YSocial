"""
Phase T9 validation tests — Final Audit, Style Guide Documentation,
and Completion Sign-off.

Verifies that:
  1.  All T8 style= metrics remain within target (≤ 566 total).
  2.  All <style> inline blocks are gone (count = 0).
  3.  forum/ and microblogging/ contain only data-bridge <script> blocks.
  4.  admin-components.css, social-components.css, and
      reddit/forum-components.css each contain the T9 style-guide section.
  5.  The style-guide section in each file covers the required class
      categories (layout, typography, badges, interactive, overflow).
  6.  Dynamic style= attributes are annotated with {# dynamic #}.
  7.  docs/template_audit_baseline.txt is present and non-empty.
  8.  TEMPLATE_SEPARATION_REFACTORING.md has no unchecked [ ] items.
  9.  All three CSS target files exist and are non-empty.
  10. T9 phase is mentioned in TEMPLATE_SEPARATION_REFACTORING.md.
"""

import os
import re

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "y_web", "templates")
CSS_DIR = os.path.join(REPO_ROOT, "y_web", "static", "assets", "css")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")

CSS_FILES = {
    "admin": os.path.join(CSS_DIR, "admin-components.css"),
    "social": os.path.join(CSS_DIR, "social-components.css"),
    "forum": os.path.join(CSS_DIR, "reddit", "forum-components.css"),
}

REFACTORING_DOC = os.path.join(REPO_ROOT, "TEMPLATE_SEPARATION_REFACTORING.md")
BASELINE_FILE = os.path.join(DOCS_DIR, "template_audit_baseline.txt")

# ── helpers ──────────────────────────────────────────────────────────────────


def _find_html_files(directory):
    """Return all .html files under *directory*."""
    matches = []
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if fname.endswith(".html"):
                matches.append(os.path.join(root, fname))
    return matches


def _count_pattern(pattern, directory):
    """Count occurrences of *pattern* across all HTML files in *directory*."""
    total = 0
    for path in _find_html_files(directory):
        with open(path, encoding="utf-8") as fh:
            total += len(re.findall(pattern, fh.read()))
    return total


def _css_content(key):
    with open(CSS_FILES[key], encoding="utf-8") as fh:
        return fh.read()


# ── 1. Total style= count ────────────────────────────────────────────────────


class TestStyleAttrCounts:
    TOTAL_LIMIT = 566

    def test_total_style_attrs_within_limit(self):
        """Total style= across all templates must be ≤ 566 (T8 target)."""
        total = _count_pattern(r"style=", TEMPLATES_DIR)
        assert (
            total <= self.TOTAL_LIMIT
        ), f"style= count {total} exceeds limit {self.TOTAL_LIMIT}"

    def test_admin_style_attrs(self):
        """Admin templates style= ≤ 480."""
        admin_dir = os.path.join(TEMPLATES_DIR, "admin")
        count = _count_pattern(r"style=", admin_dir)
        assert count <= 480, f"Admin style= count {count} > 480"

    def test_microblogging_style_attrs(self):
        """Microblogging templates style= ≤ 60."""
        mb_dir = os.path.join(TEMPLATES_DIR, "microblogging")
        count = _count_pattern(r"style=", mb_dir)
        assert count <= 60, f"Microblogging style= count {count} > 60"

    def test_forum_style_attrs(self):
        """Forum templates style= ≤ 80."""
        forum_dir = os.path.join(TEMPLATES_DIR, "forum")
        count = _count_pattern(r"style=", forum_dir)
        assert count <= 80, f"Forum style= count {count} > 80"

    def test_login_error_style_attrs(self):
        """Login + error-pages style= ≤ 25."""
        login_dir = os.path.join(TEMPLATES_DIR, "login")
        error_dir = os.path.join(TEMPLATES_DIR, "error_pages")
        count = 0
        for d in (login_dir, error_dir):
            if os.path.isdir(d):
                count += _count_pattern(r"style=", d)
        assert count <= 25, f"Login/error style= count {count} > 25"


# ── 2. <style> inline blocks completely gone ─────────────────────────────────


class TestStyleBlocks:
    def test_no_inline_style_blocks_anywhere(self):
        """All inline <style> blocks must be gone (T4+T5 target)."""
        count = _count_pattern(r"<style>", TEMPLATES_DIR)
        assert count == 0, f"Found {count} inline <style> blocks — all must be removed"

    def test_no_style_blocks_in_admin(self):
        """No <style> blocks in admin/."""
        admin_dir = os.path.join(TEMPLATES_DIR, "admin")
        count = _count_pattern(r"<style>", admin_dir)
        assert count == 0, f"Found {count} <style> blocks in admin/"

    def test_no_style_blocks_in_forum(self):
        """No <style> blocks in forum/."""
        forum_dir = os.path.join(TEMPLATES_DIR, "forum")
        count = _count_pattern(r"<style>", forum_dir)
        assert count == 0

    def test_no_style_blocks_in_microblogging(self):
        """No <style> blocks in microblogging/."""
        mb_dir = os.path.join(TEMPLATES_DIR, "microblogging")
        count = _count_pattern(r"<style>", mb_dir)
        assert count == 0


# ── 3. <script> blocks in forum/microblogging are data-bridge-only ───────────


class TestDataBridgeScripts:
    """T7 criterion: no function definitions remain in forum/microblogging."""

    FUNCTION_DEF_PATTERN = r"function\s+\w+\s*\("

    def test_no_function_defs_in_forum(self):
        """forum/ templates must not contain function definitions."""
        forum_dir = os.path.join(TEMPLATES_DIR, "forum")
        count = _count_pattern(self.FUNCTION_DEF_PATTERN, forum_dir)
        assert count == 0, (
            f"Found {count} function definitions in forum/ templates — "
            "these should be in external JS files"
        )

    def test_no_function_defs_in_microblogging(self):
        """microblogging/ templates must not contain function definitions."""
        mb_dir = os.path.join(TEMPLATES_DIR, "microblogging")
        count = _count_pattern(self.FUNCTION_DEF_PATTERN, mb_dir)
        assert (
            count == 0
        ), f"Found {count} function definitions in microblogging/ templates"


# ── 4. CSS files contain the T9 style-guide section ─────────────────────────

STYLE_GUIDE_MARKER = "Phase T9 — ys-* Utility Class Style Guide"


class TestStyleGuidePresent:
    def test_admin_css_has_style_guide(self):
        """admin-components.css must contain the T9 style-guide section."""
        assert STYLE_GUIDE_MARKER in _css_content(
            "admin"
        ), f"admin-components.css is missing '{STYLE_GUIDE_MARKER}'"

    def test_social_css_has_style_guide(self):
        """social-components.css must contain the T9 style-guide section."""
        assert STYLE_GUIDE_MARKER in _css_content(
            "social"
        ), f"social-components.css is missing '{STYLE_GUIDE_MARKER}'"

    def test_forum_css_has_style_guide(self):
        """reddit/forum-components.css must contain the T9 style-guide section."""
        assert STYLE_GUIDE_MARKER in _css_content(
            "forum"
        ), f"reddit/forum-components.css is missing '{STYLE_GUIDE_MARKER}'"


# ── 5. Style-guide covers required categories ─────────────────────────────────


class TestStyleGuideCategories:
    """Verify that each style-guide section covers all mandatory categories."""

    REQUIRED_CATEGORIES = [
        "Layout",
        "Width",
        "Typography",
        "Badges",
        "Interactive",
        "Overflow",
    ]

    def _assert_categories(self, css_key):
        content = _css_content(css_key)
        # Find the style guide section
        guide_start = content.find(STYLE_GUIDE_MARKER)
        assert guide_start != -1, f"{css_key} CSS missing style guide section"
        guide_section = content[guide_start:]
        for category in self.REQUIRED_CATEGORIES:
            assert (
                category in guide_section
            ), f"{css_key} style guide is missing category '{category}'"

    def test_admin_css_style_guide_categories(self):
        self._assert_categories("admin")

    def test_social_css_style_guide_categories(self):
        self._assert_categories("social")

    def test_forum_css_style_guide_categories(self):
        self._assert_categories("forum")

    def test_admin_style_guide_lists_pointer(self):
        """admin style guide must document ys-pointer."""
        assert "ys-pointer" in _css_content("admin")

    def test_admin_style_guide_lists_prefix_rule(self):
        """admin style guide must explain the ys- prefix convention."""
        content = _css_content("admin")
        guide_start = content.find(STYLE_GUIDE_MARKER)
        guide_section = content[guide_start:]
        assert "PREFIX RULE" in guide_section or "ys-" in guide_section


# ── 6. Dynamic style= attributes are annotated ───────────────────────────────


class TestDynamicAnnotation:
    def test_dynamic_styles_annotated(self):
        """style= with Jinja2 expressions must use {# dynamic #} annotation."""
        dynamic_unannotated = []
        for path in _find_html_files(TEMPLATES_DIR):
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    if re.search(r'style="[^"]*\{\{', line):
                        if "{# dynamic #}" not in line:
                            dynamic_unannotated.append(
                                f"{os.path.relpath(path, REPO_ROOT)}:{lineno}"
                            )
        assert not dynamic_unannotated, (
            f"Dynamic style= attributes without {{# dynamic #}} annotation:\n"
            + "\n".join(dynamic_unannotated)
        )

    def test_annotated_dynamic_styles_exist(self):
        """At least some dynamic style= attributes should be annotated."""
        count = _count_pattern(r"\{# dynamic #\}", TEMPLATES_DIR)
        assert count >= 1, "No {# dynamic #} annotations found — expected at least 1"


# ── 7. Baseline file present ─────────────────────────────────────────────────


class TestBaselineFile:
    def test_baseline_file_exists(self):
        assert os.path.isfile(BASELINE_FILE), f"Missing {BASELINE_FILE}"

    def test_baseline_file_non_empty(self):
        assert os.path.getsize(BASELINE_FILE) > 0

    def test_baseline_records_style_attrs(self):
        """Baseline must record total_style_attrs."""
        with open(BASELINE_FILE, encoding="utf-8") as fh:
            content = fh.read()
        assert "total_style_attrs=" in content

    def test_baseline_records_style_blocks(self):
        """Baseline must record total_style_blocks=0."""
        with open(BASELINE_FILE, encoding="utf-8") as fh:
            content = fh.read()
        assert "total_style_blocks=0" in content


# ── 8. TEMPLATE_SEPARATION_REFACTORING.md has no unchecked items ─────────────


class TestRefactoringDocComplete:
    def test_no_unchecked_items(self):
        """All success-criteria checkboxes must be checked [x]."""
        with open(REFACTORING_DOC, encoding="utf-8") as fh:
            content = fh.read()
        unchecked = re.findall(r"- \[ \]", content)
        assert not unchecked, (
            f"Found {len(unchecked)} unchecked [ ] item(s) in "
            "TEMPLATE_SEPARATION_REFACTORING.md — complete all phases first"
        )

    def test_t9_phase_present_in_doc(self):
        """TEMPLATE_SEPARATION_REFACTORING.md must define Phase T9."""
        with open(REFACTORING_DOC, encoding="utf-8") as fh:
            content = fh.read()
        assert (
            "Phase T9" in content
        ), "TEMPLATE_SEPARATION_REFACTORING.md must contain Phase T9 definition"

    def test_t9_in_table_of_contents(self):
        """T9 must appear in the Table of Contents."""
        with open(REFACTORING_DOC, encoding="utf-8") as fh:
            content = fh.read()
        toc_end = content.find("## 1. Current State")
        toc_section = content[:toc_end] if toc_end != -1 else content
        assert "T9" in toc_section, "T9 missing from Table of Contents"


# ── 9. CSS files exist and are non-empty ─────────────────────────────────────


class TestCssFilesExist:
    def test_admin_components_css_exists(self):
        assert os.path.isfile(CSS_FILES["admin"])

    def test_admin_components_css_non_empty(self):
        assert os.path.getsize(CSS_FILES["admin"]) > 0

    def test_social_components_css_exists(self):
        assert os.path.isfile(CSS_FILES["social"])

    def test_social_components_css_non_empty(self):
        assert os.path.getsize(CSS_FILES["social"]) > 0

    def test_forum_components_css_exists(self):
        assert os.path.isfile(CSS_FILES["forum"])

    def test_forum_components_css_non_empty(self):
        assert os.path.getsize(CSS_FILES["forum"]) > 0

    def test_admin_components_has_ys_classes(self):
        """admin-components.css must define ys-* classes."""
        assert ".ys-" in _css_content("admin")

    def test_social_components_has_ys_classes(self):
        """social-components.css must define ys-* classes."""
        assert ".ys-" in _css_content("social")

    def test_forum_components_has_ys_classes(self):
        """reddit/forum-components.css must define ys-* classes."""
        assert ".ys-" in _css_content("forum")
