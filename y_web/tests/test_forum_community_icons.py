import re
from pathlib import Path

from y_web.src.forum.community_icons import (
    DEFAULT_ICON,
    ICON_POOL,
    KEYWORD_ICONS,
    assign_icons,
    icon_for,
)

MDI_CSS = (
    Path(__file__).resolve().parents[1]
    / "static/assets/vendor/mdi/css/materialdesignicons.css"
)


def test_keyword_icons_and_uniqueness():
    icons = assign_icons(
        ["linux", "windows", "macos", "programming", "cats", "dogs", "linux"]
    )
    assert icons["linux"] == "mdi-linux"
    assert icons["windows"] == "mdi-microsoft-windows"
    assert len(set(icons.values())) == len(icons)


def test_assignment_is_stable_and_unknown_slug_has_default():
    a = assign_icons(["alpha", "beta", "gamma"])
    assert a == assign_icons(["gamma", "beta", "alpha"])
    assert icon_for("missing", a) == DEFAULT_ICON


def test_all_icons_exist_in_the_bundled_mdi_font():
    css = MDI_CSS.read_text()
    known = set(re.findall(r"\.(mdi-[a-z0-9-]+)::before", css))
    wanted = {i for _, i in KEYWORD_ICONS} | set(ICON_POOL) | {DEFAULT_ICON}
    assert not (wanted - known), sorted(wanted - known)
