"""
Phase T4 validation tests.

Verifies that:
  1. Each of the 4 new CSS files exists and is non-empty.
  2. grep -r '<style>' y_web/templates/admin/ --include="*.html" returns zero results.
  3. Each template that had style blocks now has a <link> to its corresponding CSS file.
  4. Key CSS rules are present in the appropriate CSS files (spot checks).
  5. The <link> tags use the url_for('static', ...) pattern.
"""

import os
import subprocess

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TEMPLATES_ADMIN = os.path.join(REPO_ROOT, "y_web", "templates", "admin")
CSS_DIR = os.path.join(REPO_ROOT, "y_web", "static", "assets", "css")

NEW_CSS_FILES = [
    "admin-settings.css",
    "admin-clients.css",
    "admin-components.css",
    "admin-tutorials.css",
]

# Templates that should have a <link> to each CSS file
CSS_TEMPLATE_MAP = {
    "admin-settings.css": [
        "settings.html",
    ],
    "admin-clients.css": [
        "clients.html",
        "clients_forum.html",
        "clients_hpc.html",
        "experiment_details.html",
        "experiment_details_forum.html",
        "client_details.html",
        "client_details_forum.html",
        "client_details_hpc.html",
    ],
    "admin-components.css": [
        "populations.html",
        "agents.html",
        "opinion_configuration.html",
        "opinion_configuration_forum.html",
        "opinion_configuration_hpc.html",
        "opinion_evolution.html",
        "pages.html",
        "dashboard.html",
        "miscellanea.html",
        "user_details.html",
        "users.html",
        "jupyter.html",
        "select_experiment.html",
    ],
    # admin-tutorials.css is linked from head.html (global)
    "admin-tutorials.css": [],
}

# Spot-check CSS rules: {css_filename: [list of expected substrings]}
CSS_SPOT_CHECKS = {
    "admin-settings.css": [
        ".sidebar-box",
        ".file-upload-wrapper-exp",
    ],
    "admin-clients.css": [
        ".form-section-header",
        ".tutorial-section",
    ],
    "admin-components.css": [
        ".form-section-header",
        ".multi-select-wrapper",
    ],
    "admin-tutorials.css": [
        ".tutorial-tag",
        ".page-tutorial-overlay",
    ],
}


# ---------------------------------------------------------------------------
# 1. CSS files exist and are non-empty
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("css_file", NEW_CSS_FILES)
def test_css_file_exists_and_nonempty(css_file):
    path = os.path.join(CSS_DIR, css_file)
    assert os.path.isfile(path), f"CSS file not found: {path}"
    assert os.path.getsize(path) > 0, f"CSS file is empty: {path}"


# ---------------------------------------------------------------------------
# 2. No <style> blocks remain in admin templates
# ---------------------------------------------------------------------------

def test_no_style_blocks_in_admin_templates():
    result = subprocess.run(
        ["grep", "-r", "<style>", TEMPLATES_ADMIN, "--include=*.html"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 or result.stdout.strip() == "", (
        f"Found <style> blocks in admin templates:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# 3. Templates have <link> to the correct CSS file
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("css_file,templates", [
    (css, tmpl)
    for css, tmpl_list in CSS_TEMPLATE_MAP.items()
    for tmpl in tmpl_list
])
def test_template_has_link_to_css(css_file, templates):
    path = os.path.join(TEMPLATES_ADMIN, templates)
    assert os.path.isfile(path), f"Template not found: {path}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert css_file in content, (
        f"Template {templates} is missing <link> to {css_file}"
    )


def test_admin_tutorials_css_linked_from_head():
    """admin-tutorials.css must be linked from head.html (global include)."""
    head_path = os.path.join(TEMPLATES_ADMIN, "head.html")
    with open(head_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "admin-tutorials.css" in content, (
        "admin-tutorials.css link not found in head.html"
    )


# ---------------------------------------------------------------------------
# 4. Key CSS rules present in CSS files (spot checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("css_file,expected", [
    (css, rule)
    for css, rules in CSS_SPOT_CHECKS.items()
    for rule in rules
])
def test_css_spot_check(css_file, expected):
    path = os.path.join(CSS_DIR, css_file)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert expected in content, (
        f"Expected CSS rule '{expected}' not found in {css_file}"
    )


# ---------------------------------------------------------------------------
# 5. <link> tags use url_for('static', ...) pattern
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("css_file,templates", [
    (css, tmpl)
    for css, tmpl_list in CSS_TEMPLATE_MAP.items()
    for tmpl in tmpl_list
])
def test_link_tag_uses_url_for(css_file, templates):
    path = os.path.join(TEMPLATES_ADMIN, templates)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    expected = f"url_for('static', filename='assets/css/{css_file}')"
    assert expected in content, (
        f"Template {templates} link tag does not use url_for pattern for {css_file}"
    )


def test_head_link_uses_url_for_for_tutorials():
    head_path = os.path.join(TEMPLATES_ADMIN, "head.html")
    with open(head_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "url_for('static', filename='assets/css/admin-tutorials.css')" in content
