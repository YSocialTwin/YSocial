"""Admin notifications: one floating-card system for flash messages, alerts and toasts."""

import json
import pathlib
import re

import jinja2
import pytest

pytestmark = pytest.mark.unit

STATIC = pathlib.Path(__file__).resolve().parents[1] / "static" / "assets"
TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_admin_head_loads_notification_assets_after_loading_indicator():
    head = _read(TEMPLATES / "admin" / "head.html")
    assert "assets/css/ys-notify.css" in head
    assert "assets/js/ys-notify.js" in head
    # ys-notify replaces the legacy showToast defined by loading-indicator.js
    assert head.index("loading-indicator.js") < head.index("ys-notify.js")


def test_notification_cards_float_over_the_page():
    css = _read(STATIC / "css" / "ys-notify.css")
    block = css[css.index(".ys-notify {") : css.index("}", css.index(".ys-notify {"))]
    assert "position: fixed" in block
    assert "top:" in block and "right:" in block
    assert "backdrop-filter" in css  # semi-transparent cards
    for kind, colour in (("is-error", "220, 38, 38"), ("is-success", "22, 163, 74")):
        assert kind in css and colour in css


def test_notification_script_exposes_the_api_and_the_legacy_entry_points():
    js = _read(STATIC / "js" / "ys-notify.js")
    for name in ("error:", "success:", "info:", "warning:", "show:", "dismiss:"):
        assert name in js
    assert "window.alert = " in js
    assert "window.showToast = " in js
    assert "ys-flash-data" in js
    # message text is always inserted as text, never as markup
    assert "innerHTML" not in js.replace("x.innerHTML = '&times;';", "")


def test_flash_template_emits_json_and_no_layout_markup():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)))
    flashes = [
        ("success", "Saved </script><b>x</b>"),
        ("error", {"title": "T", "summary": "S", "failures": [{"source": "a", "reason": "r"}]}),
    ]
    env.globals["get_flashed_messages"] = lambda with_categories=False: flashes
    env.policies["json.dumps_function"] = json.dumps
    html = env.get_template("admin/_flash_messages.html").render()
    assert "alert alert-" not in html and "<div" not in html
    payload = re.search(r'id="ys-flash-data">(.*)</script>', html, re.S).group(1)
    assert "</script>" not in payload  # cannot break out of the script element
    data = json.loads(payload)
    assert [m["category"] for m in data] == ["success", "error"]
    assert data[0]["message"] == "Saved </script><b>x</b>"
    assert data[1]["message"]["failures"][0]["source"] == "a"


def test_flash_template_is_empty_without_messages():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)))
    env.globals["get_flashed_messages"] = lambda with_categories=False: []
    assert env.get_template("admin/_flash_messages.html").render().strip() == ""


def test_admin_scripts_do_not_use_blocking_alerts_or_inline_status_boxes():
    offenders = []
    for path in sorted((STATIC / "js").glob("admin-*.js")):
        text = _read(path)
        if re.search(r"(?<![\w.])alert\(", text):
            offenders.append((path.name, "alert("))
        if re.search(r"background: #(?:f8d7da|d4edda)", text):
            offenders.append((path.name, "inline status box"))
    assert not offenders, offenders
