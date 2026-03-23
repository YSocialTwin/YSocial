"""
Phase T5 validation tests.

Verifies that:
  1. Both new CSS files exist and are non-empty.
  2. grep -r '<style>' y_web/templates/forum/ --include="*.html" returns zero results.
  3. grep -r '<style>' y_web/templates/microblogging/ --include="*.html" returns zero results.
  4. forum/header.html has a <link> to reddit/forum-components.css.
  5. microblogging/header.html has a <link> to social-components.css.
  6. Key CSS rules are present in the appropriate CSS files (spot checks).
  7. The <link> tags use the url_for('static', ...) pattern.
"""

import os
import subprocess

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TEMPLATES_FORUM = os.path.join(REPO_ROOT, "y_web", "templates", "forum")
TEMPLATES_MB = os.path.join(REPO_ROOT, "y_web", "templates", "microblogging")
CSS_DIR = os.path.join(REPO_ROOT, "y_web", "static", "assets", "css")

NEW_CSS_FILES = [
    os.path.join(CSS_DIR, "reddit", "forum-components.css"),
    os.path.join(CSS_DIR, "social-components.css"),
]

# CSS rules that must appear in each new file
CSS_SPOT_CHECKS = {
    os.path.join(CSS_DIR, "reddit", "forum-components.css"): [
        ".sim-clock-pill",
        ".reply-notif-bell",
        ".forum-profile-shell",
        ".forum-profile-hero",
        ".interview-side-stack",
        ".reply-notif-item",
        ".feed-content",
        ".thread-content",
        ".comment-content",
    ],
    os.path.join(CSS_DIR, "social-components.css"): [
        ".interview-shell",
        ".interview-card",
        ".interview-side-stack",
        ".interview-persona-name",
        ".interview-json-tree",
    ],
}


# ---------------------------------------------------------------------------
# 1. New CSS files exist and are non-empty
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("css_path", NEW_CSS_FILES)
def test_css_file_exists(css_path):
    assert os.path.isfile(css_path), f"Expected CSS file not found: {css_path}"


@pytest.mark.parametrize("css_path", NEW_CSS_FILES)
def test_css_file_non_empty(css_path):
    assert os.path.getsize(css_path) > 0, f"CSS file is empty: {css_path}"


# ---------------------------------------------------------------------------
# 2 & 3. No <style> blocks remain in forum/ or microblogging/ templates
# ---------------------------------------------------------------------------

def test_no_style_blocks_in_forum_templates():
    result = subprocess.run(
        ["grep", "-r", "<style>", TEMPLATES_FORUM, "--include=*.html"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 or result.stdout.strip() == "", (
        f"Found <style> blocks in forum templates:\n{result.stdout}"
    )


def test_no_style_blocks_in_microblogging_templates():
    result = subprocess.run(
        ["grep", "-r", "<style>", TEMPLATES_MB, "--include=*.html"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 or result.stdout.strip() == "", (
        f"Found <style> blocks in microblogging templates:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# 4. forum/header.html links to forum-components.css
# ---------------------------------------------------------------------------

def test_forum_header_links_forum_components_css():
    path = os.path.join(TEMPLATES_FORUM, "header.html")
    content = open(path).read()
    assert "forum-components.css" in content, (
        "forum/header.html is missing <link> to forum-components.css"
    )


def test_forum_header_link_uses_url_for():
    path = os.path.join(TEMPLATES_FORUM, "header.html")
    content = open(path).read()
    expected = "url_for('static', filename='assets/css/reddit/forum-components.css')"
    assert expected in content, (
        f"forum/header.html link tag does not use url_for pattern: {expected!r}"
    )


# ---------------------------------------------------------------------------
# 5. microblogging/header.html links to social-components.css
# ---------------------------------------------------------------------------

def test_microblogging_header_links_social_components_css():
    path = os.path.join(TEMPLATES_MB, "header.html")
    content = open(path).read()
    assert "social-components.css" in content, (
        "microblogging/header.html is missing <link> to social-components.css"
    )


def test_microblogging_header_link_uses_url_for():
    path = os.path.join(TEMPLATES_MB, "header.html")
    content = open(path).read()
    expected = "url_for('static', filename='assets/css/social-components.css')"
    assert expected in content, (
        f"microblogging/header.html link tag does not use url_for pattern: {expected!r}"
    )


# ---------------------------------------------------------------------------
# 6. Key CSS rules present in CSS files (spot checks)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("css_path,expected", [
    (css, rule)
    for css, rules in CSS_SPOT_CHECKS.items()
    for rule in rules
])
def test_css_spot_check(css_path, expected):
    content = open(css_path).read()
    assert expected in content, (
        f"Expected CSS rule {expected!r} not found in {os.path.basename(css_path)}"
    )


# ---------------------------------------------------------------------------
# 7. Verify source templates no longer contain the extracted style blocks
# ---------------------------------------------------------------------------

FORUM_TEMPLATES_WITHOUT_STYLE = [
    "header.html",
    "profile.html",
    "interview.html",
    "notifications.html",
    os.path.join("components", "posts.html"),
    os.path.join("components", "thread-post.html"),
    os.path.join("components", "comment.html"),
]


@pytest.mark.parametrize("rel_path", FORUM_TEMPLATES_WITHOUT_STYLE)
def test_forum_template_has_no_style_block(rel_path):
    path = os.path.join(TEMPLATES_FORUM, rel_path)
    assert os.path.isfile(path), f"Template not found: {path}"
    content = open(path).read()
    assert "<style>" not in content, (
        f"forum/{rel_path} still contains a <style> block"
    )


def test_microblogging_interview_has_no_style_block():
    path = os.path.join(TEMPLATES_MB, "interview.html")
    content = open(path).read()
    assert "<style>" not in content, (
        "microblogging/interview.html still contains a <style> block"
    )
