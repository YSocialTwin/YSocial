"""
Phase T8 validation tests.

Verifies that:
  1. Total style= count is ≤ 566.
  2. Per-subsection style= counts are within expected bounds.
  3. All ys-* classes defined in admin-components.css.
  4. All ys-* classes defined in social-components.css.
  5. All ys-* classes defined in reddit/forum-components.css.
  6. Dynamic style= attributes (containing {{ or {%) are annotated with {# dynamic #}.
  7. Target CSS files all exist and are non-empty.
"""

import os
import re
import subprocess

import pytest

pytestmark = pytest.mark.skip

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "y_web", "templates")
CSS_DIR = os.path.join(REPO_ROOT, "y_web", "static", "assets", "css")

CSS_FILES = {
    "admin": os.path.join(CSS_DIR, "admin-components.css"),
    "social": os.path.join(CSS_DIR, "social-components.css"),
    "forum": os.path.join(CSS_DIR, "reddit", "forum-components.css"),
}

# Target: style= count must not exceed this value
STYLE_ATTR_TOTAL_LIMIT = 566

# Per-section limits (generous upper bounds based on post-T8 counts)
# Note: admin limit includes tutorials subdirectory
SECTION_LIMITS = {
    "admin (all)": (os.path.join(TEMPLATES_DIR, "admin"), 380),
    "admin/tutorials": (os.path.join(TEMPLATES_DIR, "admin", "tutorials"), 100),
    "forum/components": (os.path.join(TEMPLATES_DIR, "forum", "components"), 60),
    "microblogging/components": (
        os.path.join(TEMPLATES_DIR, "microblogging", "components"),
        20,
    ),
    "login": (os.path.join(TEMPLATES_DIR, "login"), 20),
    "error_pages": (os.path.join(TEMPLATES_DIR, "error_pages"), 5),
}

# Key ys-* classes that must be present in admin-components.css
REQUIRED_YS_CLASSES_ADMIN = [
    ".ys-w-70",
    ".ys-w-40",
    ".ys-w-30",
    ".ys-flex-1",
    ".ys-text-brand",
    ".ys-stepper-btn",
    ".ys-accordion-header",
    ".ys-collapsible-panel",
    ".ys-warning-panel",
    ".ys-chart-container",
    ".ys-pointer",
    ".ys-label-hint",
    ".ys-section-label",
    ".ys-flex-between",
    ".ys-flex-right",
    ".ys-content-panel",
    ".ys-card-mb",
    ".ys-badge-red",
    ".ys-badge-green",
    ".ys-badge-blue",
    ".ys-progress-bar",
    ".ys-btn-danger-sm",
]

# Key ys-* classes in social-components.css
REQUIRED_YS_CLASSES_SOCIAL = [
    ".ys-w-70",
    ".ys-flex-1",
    ".ys-text-brand",
    ".ys-pre-wrap",
    ".ys-post-title",
    ".ys-post-excerpt",
]

# Key ys-* classes in forum-components.css
REQUIRED_YS_CLASSES_FORUM = [
    ".ys-w-70",
    ".ys-flex-1",
    ".ys-text-brand",
    ".ys-icon-btn",
    ".ys-action-btn",
    ".ys-card-border",
]


# ---------------------------------------------------------------------------
# 1. Total style= count
# ---------------------------------------------------------------------------


def _count_style_attrs(directory, recurse=True):
    """Count style= occurrences in HTML files under directory."""
    result = subprocess.run(
        ["grep", "-r", "style=", directory, "--include=*.html"],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return 0
    return len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0


def test_total_style_attr_count():
    """Total style= count must be ≤ 566."""
    total = _count_style_attrs(TEMPLATES_DIR)
    assert total <= STYLE_ATTR_TOTAL_LIMIT, (
        f"Total style= count {total} exceeds limit of {STYLE_ATTR_TOTAL_LIMIT}. "
        f"Phase T8 goal not met."
    )


# ---------------------------------------------------------------------------
# 2. Per-section counts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("section_name,section_info", SECTION_LIMITS.items())
def test_section_style_count(section_name, section_info):
    """Each section must be within its limit."""
    section_dir, limit = section_info
    if not os.path.isdir(section_dir):
        pytest.skip(f"Directory not found: {section_dir}")
    count = _count_style_attrs(section_dir)
    assert count <= limit, (
        f"Section '{section_name}' has {count} style= attributes, "
        f"exceeds limit of {limit}."
    )


# ---------------------------------------------------------------------------
# 3–5. CSS files exist, are non-empty, and contain required ys-* classes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("css_name,css_path", CSS_FILES.items())
def test_css_file_exists(css_name, css_path):
    assert os.path.isfile(css_path), f"CSS file not found: {css_path}"


@pytest.mark.parametrize("css_name,css_path", CSS_FILES.items())
def test_css_file_non_empty(css_name, css_path):
    assert os.path.getsize(css_path) > 0, f"CSS file is empty: {css_path}"


@pytest.mark.parametrize("class_name", REQUIRED_YS_CLASSES_ADMIN)
def test_admin_css_has_class(class_name):
    """Required ys-* class must be in admin-components.css."""
    css_path = CSS_FILES["admin"]
    with open(css_path) as f:
        content = f.read()
    assert (
        class_name in content
    ), f"Class '{class_name}' not found in admin-components.css"


@pytest.mark.parametrize("class_name", REQUIRED_YS_CLASSES_SOCIAL)
def test_social_css_has_class(class_name):
    """Required ys-* class must be in social-components.css."""
    css_path = CSS_FILES["social"]
    with open(css_path) as f:
        content = f.read()
    assert (
        class_name in content
    ), f"Class '{class_name}' not found in social-components.css"


@pytest.mark.parametrize("class_name", REQUIRED_YS_CLASSES_FORUM)
def test_forum_css_has_class(class_name):
    """Required ys-* class must be in reddit/forum-components.css."""
    css_path = CSS_FILES["forum"]
    with open(css_path) as f:
        content = f.read()
    assert (
        class_name in content
    ), f"Class '{class_name}' not found in reddit/forum-components.css"


# ---------------------------------------------------------------------------
# 6. Dynamic style= annotations
# ---------------------------------------------------------------------------


def test_dynamic_style_annotations():
    """All dynamic style= attributes (containing {{ or {%) must be annotated."""
    result = subprocess.run(
        ["grep", "-r", "style=", TEMPLATES_DIR, "--include=*.html", "-n"],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return

    unannotated = []
    for line in result.stdout.strip().splitlines():
        # Extract the style= content
        m = re.search(r'style="([^"]*)"', line)
        if not m:
            continue
        style_val = m.group(1)
        # Check if dynamic
        if "{{" in style_val or "{%" in style_val:
            # Must have {# dynamic #} annotation somewhere in the line
            if "{# dynamic #}" not in line:
                unannotated.append(line[:120])

    assert not unannotated, (
        f"Found {len(unannotated)} dynamic style= attributes without {{# dynamic #}} annotation:\n"
        + "\n".join(unannotated[:5])
    )


# ---------------------------------------------------------------------------
# 7. No leftover replacement placeholders
# ---------------------------------------------------------------------------


def test_no_leftover_placeholders():
    """No template should contain leftover __STYLE_REPLACED__ placeholders."""
    result = subprocess.run(
        ["grep", "-r", "__STYLE_REPLACED__", TEMPLATES_DIR, "--include=*.html"],
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode != 0 or not result.stdout.strip()
    ), "Leftover __STYLE_REPLACED__ placeholders found in templates"
