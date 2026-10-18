"""Usernames are shown with spaces between the words of a camel case name; tags and links keep the username."""

import re
from pathlib import Path

import pytest

from y_web.src.system.display_names import display_name


@pytest.mark.parametrize(
    "username,shown",
    [
        ("MariaRossi", "Maria Rossi"),
        ("Sig.RiccardoFagiani", "Sig. Riccardo Fagiani"),
        ("GiovanniDeLuca", "Giovanni De Luca"),
        ("JohnDOEJunior", "John DOE Junior"),
        ("mario_rossi", "mario_rossi"),
        ("mario", "mario"),
        ("ALLCAPS", "ALLCAPS"),
        ("Maria Rossi", "Maria Rossi"),
        ("@MariaRossi", "@MariaRossi"),
        ("#BreakingNews", "#BreakingNews"),
        ("", ""),
        (None, None),
    ],
)
def test_display_name(username, shown):
    assert display_name(username) == shown


def test_filter_is_registered_on_the_app():
    from y_web import create_app

    app = create_app(db_type="sqlite")
    assert app.jinja_env.filters["display_name"]("MariaRossi") == "Maria Rossi"


TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "microblogging"


def test_mention_prefilled_replies_keep_the_username():
    """The reply boxes start with ``@username``: a tag, never split."""
    for path in TEMPLATES.rglob("*.html"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "reply_comment" in line and "@{{" in line:
                assert (
                    "display_name" not in line
                ), f"{path.name}: mention uses display_name"


def test_displayed_author_names_use_the_filter():
    text = (TEMPLATES / "components" / "posts.html").read_text(encoding="utf-8")
    assert re.search(r'item\["author"\]\|display_name', text)
    assert re.search(r'cm\["author"\]\|display_name', text)
