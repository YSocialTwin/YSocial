"""The photo sidebar links back to the admin panel for admins and researchers,
like the microblogging and forum menus."""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.unit

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def _render(**context) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.globals["_"] = lambda text, **kw: text
    env.globals["url_for"] = lambda endpoint, **kw: f"/static/{kw.get('filename', '')}"
    env.filters["user_image_id"] = lambda value: value
    base = {
        "exp_id": 7,
        "logged_id": 3,
        "logged_username": "alice",
        "photo_active_nav": "home",
    }
    base.update(context)
    return env.get_template("photo/components/sidebar.html").render(**base)


@pytest.mark.parametrize("role", ["admin", "researcher"])
def test_admin_and_researcher_get_the_admin_dashboard_link(role):
    html = _render(current_user_role=role)
    assert 'href="/admin/dashboard"' in html
    assert "Admin Dashboard" in html


def test_admin_flag_also_shows_it():
    assert "/admin/dashboard" in _render(is_admin=True, current_user_role=None)


@pytest.mark.parametrize("role", ["user", "student", None])
def test_participants_do_not_see_it(role):
    assert "/admin/dashboard" not in _render(current_user_role=role)
