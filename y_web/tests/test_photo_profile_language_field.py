"""The photo profile editor offers the spoken language as a list (like microblogging/forum), not free text."""
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_photo_profile_language_is_a_select_of_known_languages():
    html = (ROOT / "templates" / "photo" / "base.html").read_text(encoding="utf-8")
    assert not re.search(r'<input[^>]*name="language"', html)
    block = re.search(r'<select[^>]*name="language"[^>]*>(.*?)</select>', html, re.S)
    assert block, "language select missing"
    assert 'value="English"' in block.group(1) and 'value="Italian"' in block.group(1)
    assert "Spoken Language" in html


def test_overlay_script_keeps_a_value_the_list_does_not_offer():
    js = (ROOT / "static" / "assets" / "js" / "photo-overlays.js").read_text(encoding="utf-8")
    assert "tagName === 'SELECT'" in js and "createElement('option')" in js
