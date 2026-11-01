"""P13: the content of the agents that can be cross-posted (own content, news, images) is a World Simulation parameter."""

import importlib
import json
import os
import re

import pytest

from y_web.src.federation import lifecycle, service
from y_web.src.federation.service import WorldSimulationError
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_lifecycle import copy_of  # noqa: E402
from y_web.tests.test_world_simulation_ui import _post, login, site  # noqa: E402,F401  (fixtures)

ws = importlib.import_module("y_web.routes.admin.sub.world_simulation")


class Form(dict):
    """The part of a werkzeug form the option parser uses."""

    def getlist(self, key):
        v = self.get(key, [])
        return v if isinstance(v, list) else [v]


def federation_json(fed):
    return json.loads(open(os.path.join(fed.folder, "federation.json")).read())


def test_the_form_checkboxes_become_the_crosspost_content_in_a_fixed_order():
    got = ws._options_from_form(Form(crosspost_content_present="1", crosspost_content=["images", "own_content"]))
    assert got == {"crosspost": {"content": ["own_content", "images"]}}


def test_nothing_checked_is_the_default_and_stores_nothing():
    assert ws._options_from_form(Form(crosspost_content_present="1")) == {}
    assert ws._options_from_form(Form()) == {}  # a form without the control (an older page) leaves the setting alone


def test_the_form_wins_over_a_stale_copy_in_the_advanced_json_and_keeps_the_other_crosspost_keys():
    advanced = json.dumps({"crosspost": {"mode": "agent_action", "propensity": 0.5, "content": ["news"]}})
    got = ws._options_from_form(Form(crosspost_content_present="1", crosspost_content=["images"], advanced=advanced))
    assert got["crosspost"] == {"mode": "agent_action", "propensity": 0.5, "content": ["images"]}
    cleared = ws._options_from_form(Form(crosspost_content_present="1", advanced=advanced))
    assert cleared["crosspost"] == {"mode": "agent_action", "propensity": 0.5}


def test_the_setting_reaches_federation_json_and_the_member_sections(world):  # noqa: F811
    app, exps, tmp = world
    fed = service.create_federation("p", list(exps.values()), owner="admin", seed=3,
                                    options={"crosspost": {"mode": "agent_action", "content": ["news", "own_content"]}})
    assert federation_json(fed)["crosspost"] == {"mode": "agent_action", "content": ["own_content", "news"]}
    for row, exp in service.members_of(fed):
        assert service.member_section(fed, row, exp)["crosspost_content"] == ["own_content", "news"]


def test_unset_or_all_changes_nothing_in_either_file(world):  # noqa: F811
    app, exps, tmp = world
    plain = service.create_federation("a", list(exps.values()), owner="admin", seed=3, options={"crosspost": {"mode": "agent_action"}})
    assert "content" not in federation_json(plain)["crosspost"]
    for row, exp in service.members_of(plain):
        assert "crosspost_content" not in service.member_section(plain, row, exp)
    cleaned = service._clean_options({"crosspost": {"mode": "agent_action", "content": ["all"]}})
    assert cleaned == {"crosspost": {"mode": "agent_action"}} and service._clean_options({"crosspost": {"content": ["all"]}}) == {}


@pytest.mark.parametrize("bad", [[], "news", ["video"], ["all", "news"], 3])
def test_invalid_values_are_refused(bad):
    with pytest.raises(WorldSimulationError):
        service._clean_options({"crosspost": {"content": bad}})


def test_editing_while_stopped_is_written_at_save_and_again_at_every_start(site, monkeypatch):
    from y_web.src.simulation import execution_backend as eb
    from y_web.src.federation import coordinator_process as cp

    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin", seed=1)
    client = login(app, "admin")
    assert "content" not in (federation_json(fed).get("crosspost") or {})
    assert _post(client, f"/admin/world_simulation/{fed.id}/configuration", seed="1", crosspost_content_present="1",
                 crosspost_content=["own_content", "news"]).status_code == 302
    assert federation_json(fed)["crosspost"]["content"] == ["own_content", "news"]
    # a start regenerates the file from the saved parameters, even if the file on disk is stale
    open(os.path.join(fed.folder, "federation.json"), "w").write("{}")
    seen = {}
    monkeypatch.setattr(cp, "start_coordinator", lambda f: seen.update(file=federation_json(f)) or 1)
    monkeypatch.setattr(service, "write_member_configs", lambda f: [])
    monkeypatch.setattr(eb, "start_server_for_experiment", lambda e: None)
    monkeypatch.setattr(eb, "_start_federation_clients", lambda e, resume=True: None)
    eb.start_federation(fed)
    assert seen["file"]["crosspost"]["content"] == ["own_content", "news"] and fed.status == "running"


def test_the_detail_page_shows_the_setting_and_it_is_locked_while_running(site):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin",
                                    options={"crosspost": {"content": ["news"]}})
    client = login(app, "admin")
    html = client.get(f"/admin/world_simulation/{fed.id}").get_data(as_text=True)
    box = lambda value: re.search(rf'<input type="checkbox" name="crosspost_content" value="{value}"([^>]*)>', html).group(1)
    assert "checked" in box("news") and "checked" not in box("own_content") and "checked" not in box("images")
    assert "takes effect at the next start or restart" in html
    fed.status = "running"
    running = client.get(f"/admin/world_simulation/{fed.id}").get_data(as_text=True)
    assert re.search(r"<fieldset disabled>", running) and "only while the World Simulation is stopped" in running
    before = fed.config_json
    _post(client, f"/admin/world_simulation/{fed.id}/configuration", crosspost_content_present="1", crosspost_content="images")
    assert fed.config_json == before  # refused while it runs


def test_a_new_simulation_created_from_the_form_stores_the_setting(site):
    from y_web.src.models.admin import Federation

    app, exps, tmp = site
    client = login(app, "admin")
    response = _post(client, "/admin/world_simulation/new", name="W2", experiments=[str(i) for i in exps.values()],
                     crosspost_content_present="1", crosspost_content=["images", "news"])
    assert response.status_code == 302
    assert json.loads(Federation.query.one().config_json)["crosspost"] == {"content": ["news", "images"]}


def test_clone_and_export_carry_the_setting(world):  # noqa: F811
    app, exps, tmp = world
    fed = service.create_federation("one", list(exps.values()), owner="admin", seed=5,
                                    options={"crosspost": {"mode": "agent_action", "content": ["images"]}})
    new = lifecycle.clone(fed, "two", copy=copy_of)
    assert json.loads(new.config_json)["crosspost"]["content"] == ["images"]
    assert federation_json(new)["crosspost"]["content"] == ["images"]
    assert lifecycle.manifest(fed)["options"]["crosspost"]["content"] == ["images"]  # import creates from this very block


def test_the_forms_and_the_italian_catalog_carry_the_control():
    from babel.messages.pofile import read_po

    root = os.path.join(os.path.dirname(__file__), "..")
    for name in ("new.html", "detail.html"):
        text = open(os.path.join(root, "templates", "admin", "world_simulation", name)).read()
        for value in ("own_content", "news", "images"):
            assert f'name="crosspost_content" value="{value}"' in text
        assert 'name="crosspost_content_present"' in text
    po = {m.id: m.string for m in read_po(open(os.path.join(root, "translations", "it", "LC_MESSAGES", "messages.po"), "rb")) if m.id}
    for text in ("Agent content that can be cross-posted", "Only the agent's own content", "Only content with news (a link)", "Only content with images"):
        assert po[text]


def test_own_posts_is_a_legacy_alias_everywhere(world):  # noqa: F811
    assert ws._options_from_form(Form(crosspost_content_present="1", crosspost_content=["own_posts"])) == {"crosspost": {"content": ["own_content"]}}
    assert service._clean_options({"crosspost": {"content": ["own_posts", "news"]}}) == {"crosspost": {"content": ["own_content", "news"]}}
    with pytest.raises(WorldSimulationError):
        service._clean_options({"crosspost": {"content": ["all", "own_posts"]}})
    app, exps, tmp = world
    fed = service.create_federation("legacy", list(exps.values()), owner="admin", options={"crosspost": {"content": ["own_posts"]}})
    assert federation_json(fed)["crosspost"]["content"] == ["own_content"]
    fed.config_json = json.dumps({"crosspost": {"content": ["own_posts", "images"]}})  # saved by an earlier build
    assert service.crosspost_content_of(json.loads(fed.config_json)) == ["own_content", "images"]
    for row, exp in service.members_of(fed):
        assert service.member_section(fed, row, exp)["crosspost_content"] == ["own_content", "images"]


def test_the_detail_page_checks_the_box_of_a_legacy_saved_value(site):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    fed.config_json = json.dumps({"crosspost": {"content": ["own_posts"]}})
    html = login(app, "admin").get(f"/admin/world_simulation/{fed.id}").get_data(as_text=True)
    assert re.search(r'name="crosspost_content" value="own_content" checked', html)
