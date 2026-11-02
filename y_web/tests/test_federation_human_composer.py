"""H6: the composers offer 'Also post on' to an enrolled person and send the selection."""

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)


def _render(app, dests):
    import jinja2

    env = jinja2.Environment(loader=jinja2.FileSystemLoader("y_web/templates"), autoescape=True)
    env.globals.update(ws_destinations=lambda exp_id: dests, _=lambda s, **k: s, url_for=lambda endpoint, **k: "/static/" + k["filename"])
    return env.get_template("shared/world_simulation_crosspost.html").render(ws_exp=1)


def test_the_also_post_on_box_shows_only_enrolled_destinations(world):
    app, _, _ = world
    html = _render(app, [])
    assert "ws-crosspost" not in html and html.strip() == ""
    html = _render(app, [{"member": "photo_sharing", "platform_type": "photo_sharing", "label": "PW"}, {"member": "forum", "platform_type": "forum", "label": "FW"}])
    assert html.count('type="checkbox"') == 2 and 'value="forum"' in html and "PW" in html and "FW" in html and "Photo sharing" not in html and "Also post on" in html
    assert "world-simulation-crosspost.js" in html


def test_the_composers_include_the_box_and_the_scripts_send_the_selection():
    import pathlib

    for template, anchor in (("microblogging/feed.html", "ws_exp = exp_id"), ("forum/feed.html", "ws_exp = exp_id"), ("photo/base.html", "ws_exp = exp_id"),
                             ("im/_menu.html", "ws_exp = exp.idexp"), ("dating/base.html", "ws_exp = exp.idexp")):
        assert anchor in pathlib.Path("y_web/templates", template).read_text(encoding="utf-8"), template
    for script in ("async_updates.js", "photo-overlays.js", "im-participant.js", "dating-participant.js", "reddit/api_client.js"):
        assert "wsCrosspost" in pathlib.Path("y_web/static/assets/js", script).read_text(encoding="utf-8"), script
