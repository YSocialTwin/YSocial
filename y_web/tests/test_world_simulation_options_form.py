"""World Simulation parameters as explicit form fields: defaults, round trip of every option, unknown keys, validation, no JSON box."""

import copy
import json
import os
import re
from pathlib import Path

import pytest

from y_web.src.federation import options_schema as schema
from y_web.src.federation import service
from y_web.tests.test_federation_service import world  # noqa: F401  (fixture)
from y_web.tests.test_world_simulation_ui import _post, login, site  # noqa: F401  (fixtures)

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "admin" / "world_simulation"


class Form(dict):
    def getlist(self, key):
        v = self.get(key, [])
        return v if isinstance(v, list) else [v]


def form_of(values, **extra):
    """What a browser posts for the given form values (unchecked boxes are absent, markers are always there)."""
    out = Form(topics_present="1", crosspost_content_present="1", provisioning_present="1")
    for key, value in values.items():
        if isinstance(value, bool):
            if value:
                out[key] = "1"
        elif isinstance(value, list):
            if value or key == "crosspost_content":
                out[key] = list(value) if value else []
            if key == "crosspost_content" and not value:
                out[key] = ["all"]
        else:
            out[key] = value
    out.update(extra)
    return out


def federation_json(fed):
    return json.loads(open(os.path.join(fed.folder, "federation.json")).read())


# ------------------------------------------------------------------------------------------------ defaults
def test_defaults_are_the_sdk_defaults():
    allocator = pytest.importorskip("ysocial_federation.coordinator.allocator")
    discovery = pytest.importorskip("ysocial_federation.coordinator.discovery")
    leave = pytest.importorskip("ysocial_federation.coordinator.leave")
    for module, block in ((allocator, "attention"), (discovery, "discovery"), (leave, "leave")):
        for key, default in module.DEFAULTS.items():
            if key == "beta":
                assert default == schema.BETA_DEFAULTS
            else:
                assert schema.BY_PATH[(block, key)].default == default, (block, key)
    assert set(schema.BETA_DEFAULTS) == set(discovery.BETA_KEYS)
    # every key of the three blocks has a field
    assert {p.path[1] for p in schema.PARAMS if p.block == "attention"} == set(allocator.DEFAULTS)
    assert {p.path[1] for p in schema.PARAMS if p.block == "leave"} == set(leave.DEFAULTS)
    assert {p.path[1] for p in schema.PARAMS if p.block == "discovery" and len(p.path) == 2} == set(discovery.DEFAULTS) - {"beta"}


def test_a_form_left_at_its_defaults_stores_nothing():
    """Unset stays unset: the default values shown in the form are not written."""
    options, errors = schema.apply_form(form_of(schema.values_from_options({})), {})
    assert errors == [] and options == {}


def test_the_defaults_reproduce_the_previous_behaviour_for_the_four_switches():
    form = Form(attention_enabled="on", discovery_enabled="on", leave_enabled="on", pseudonyms_enabled="on")
    options, errors = schema.apply_form(form, {})
    assert errors == [] and options == {k: {"enabled": True} for k in ("attention", "discovery", "leave", "pseudonyms")}
    assert schema.apply_form(Form(topics_present="1"), {})[0] == {"topics": {"migration": False}}  # only the opt-out is stored


# ------------------------------------------------------------------------------------------------ every option
def _other_value(p):
    if p.kind == "bool":
        return not p.default
    if p.kind == "choice":
        return next(v for v, _label in p.choices if v != p.default)
    if p.kind == "int":
        return int(p.default) + 2
    top = p.maximum if p.maximum is not None else 10.0
    low = p.minimum if p.minimum is not None else 0.0
    value = round(float(p.default) + 0.25, 3)
    if value > top or value < low or value == p.default:
        value = round((top + low) / 2 + 0.05, 3)
    return value


@pytest.mark.parametrize("p", schema.PARAMS, ids=lambda p: p.dotted)
def test_every_option_round_trips_through_its_field(p):
    base = {"attention": {"enabled": True}}  # the leave rule needs it
    value = _other_value(p)
    form = form_of(schema.values_from_options(base))
    form[p.name] = ("1" if value else None) if p.kind == "bool" else str(value)
    if form.get(p.name) is None:
        form.pop(p.name)
    options, errors = schema.apply_form(form, base)
    assert errors == [], errors
    stored = options
    for key in p.path:
        stored = stored[key]
    assert stored == value
    # showing the stored options again gives the same value, and saving them unchanged changes nothing
    again = schema.values_from_options(options)
    assert schema.apply_form(form_of(again), options)[0] == options


def test_stored_values_equal_to_the_default_are_left_as_they_are():
    base = {"attention": {"enabled": True, "temperature": 1.0, "inertia": 0.3}, "discovery": {"decay": 0.1, "beta": {"A": 1.0}}}
    options, errors = schema.apply_form(form_of(schema.values_from_options(base)), base)
    assert errors == [] and options == base
    # blank = back to the SDK default: the key goes away
    form = form_of(schema.values_from_options(base), opt__attention__temperature="")
    assert "temperature" not in schema.apply_form(form, base)[0]["attention"]


def test_membership_probabilities_provisioning_and_topics_round_trip():
    form = form_of(schema.values_from_options({}), membership_initial="custom", membership_p__microblogging="0.7", membership_p__forum="0.4",
                   prob__microblogging__forum="0.3", prob__forum__microblogging="0")
    form["provisioning_members"] = ["microblogging"]
    options, errors = schema.apply_form(form, {}, members={"microblogging", "forum"})
    assert errors == []
    assert options["membership"] == {"initial": {"microblogging": 0.7, "forum": 0.4}}
    assert options["crosspost"] == {"probability": {"microblogging->forum": 0.3}}  # 0 is the default: not written
    assert options["provisioning"] == {"members": ["microblogging"]}
    assert schema.apply_form(form_of(schema.values_from_options(options)), options, members={"microblogging", "forum"})[0] == options
    one = form_of(schema.values_from_options({}), membership_initial="one_random")
    assert schema.apply_form(one, {})[0] == {"membership": {"initial": "one_random"}}
    back = form_of(schema.values_from_options(options), membership_initial="all")
    assert "membership" not in schema.apply_form(back, options)[0]


def test_platforms_outside_the_world_simulation_are_not_stored():
    form = form_of(schema.values_from_options({}), membership_initial="custom", membership_p__dating="0.5", membership_p__forum="0.5",
                   prob__dating__forum="0.2")
    options, _errors = schema.apply_form(form, {}, members={"forum", "microblogging"})
    assert options["membership"]["initial"] == {"forum": 0.5} and "crosspost" not in options


# ------------------------------------------------------------------------------------------------ unknown keys
def test_unknown_keys_are_kept_and_listed():
    base = {"attention": {"enabled": True, "legacy": 3}, "discovery": {"beta": {"A": 2.0, "Z": 9}}, "membership": {"initial": "all", "x": 1},
            "crosspost": {"mode": "agent_action", "future": [1]}, "quoted": {"require_exposure": False}}
    options, errors = schema.apply_form(form_of(schema.values_from_options(base), attention_enabled="1"), base)
    assert errors == [] and options == base
    assert schema.unknown_paths({**base, "exposures": True}) == ["attention.legacy", "crosspost.future", "discovery.beta.Z", "membership.x", "quoted"]
    values = schema.values_from_options(base)
    values["attention_enabled"] = False  # switched off
    cleared = schema.apply_form(form_of(values), base)[0]
    assert cleared["attention"] == {"legacy": 3} and cleared["quoted"] == {"require_exposure": False}


def test_the_configuration_route_keeps_unknown_keys_and_blocks(site):
    from y_web.src.models.admin import Federation  # noqa: F401

    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin", seed=3)
    stored = {"attention": {"enabled": True, "legacy": 3}, "quoted": {"require_exposure": False}, "future_block": {"a": 1}, "exposures": False}
    fed.config_json = json.dumps(stored)
    client = login(app, "admin")
    data = dict(form_of(schema.values_from_options(stored)), seed="3", granularity="slot")
    assert _post(client, f"/admin/world_simulation/{fed.id}/configuration", **data).status_code == 302
    saved = json.loads(fed.config_json)
    assert saved["attention"] == {"enabled": True, "legacy": 3} and saved["quoted"] == {"require_exposure": False} and saved["future_block"] == {"a": 1}
    page = client.get(f"/admin/world_simulation/{fed.id}").get_data(as_text=True)
    assert "attention.legacy" in page and "future_block" in page and 'id="ws-config-preview"' in page


# ------------------------------------------------------------------------------------------------ validation
@pytest.mark.parametrize("p", [p for p in schema.PARAMS if p.kind in ("int", "float") and (p.minimum is not None or p.maximum is not None)],
                         ids=lambda p: p.dotted)
def test_out_of_range_values_are_refused_with_the_label(p):
    base = {"attention": {"enabled": True}}
    bad = (p.maximum + 1) if p.maximum is not None else (p.minimum - 1)
    form = form_of(schema.values_from_options(base))
    form[p.name] = str(bad)
    _options, errors = schema.apply_form(form, base)
    assert errors and any(schema._(p.label) in e for e in errors), errors


def test_wrong_types_and_dependencies_are_refused():
    base = {}
    assert "must be a number" in schema.apply_form(Form(opt__attention__temperature="abc"), base)[1][0]
    assert "must be an integer" in schema.apply_form(Form(opt__leave__consecutive_days="2.5", attention_enabled="1"), base)[1][0]
    assert schema.apply_form(Form(opt__crosspost__mode="nope"), base)[1]
    assert schema.apply_form(Form(leave_enabled="1"), base)[1] == ["The leave rule needs the attention sharing: switch Attention on, or switch Leave off."]
    assert schema.apply_form(Form(attention_enabled="1", opt__attention__min_multiplier="5"), base)[1] == ["The largest multiplier cannot be smaller than the smallest."]
    assert schema.apply_form(Form(membership_initial="custom"), base)[1]
    assert schema.apply_form(Form(prob__forum__microblogging="1.5"), base)[1]


def test_service_level_validation_covers_stored_values(world):  # noqa: F811
    app, exps, tmp = world
    with pytest.raises(service.WorldSimulationError) as err:
        service.create_federation("W", list(exps.values()), owner="admin", options={"discovery": {"decay": 3}})
    assert "Daily decay of awareness" in str(err.value)


# ------------------------------------------------------------------------------------------------ pages
def test_the_pages_have_a_control_for_every_option_and_no_json_box(site):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    client = login(app, "admin")
    pages = [client.get("/admin/world_simulation/new").get_data(as_text=True), client.get(f"/admin/world_simulation/{fed.id}").get_data(as_text=True)]
    for html in pages:
        assert "<textarea" not in html and 'name="advanced"' not in html
        for p in schema.PARAMS:
            assert f'name="{p.name}"' in html, p.dotted
        for name in ("seed", "granularity", "membership_initial", "crosspost_content", "provisioning_members", "prob__microblogging__forum",
                     "membership_p__forum"):
            assert f'name="{name}"' in html, name
    assert 'id="ws-config-preview"' in pages[1] and 'id="ws-config-preview"' not in pages[0]
    assert "Advanced attention parameters" in pages[0] and "<details" in pages[0]


def test_the_defaults_are_prefilled_in_the_collapsed_groups(site):
    app, exps, tmp = site
    html = login(app, "admin").get("/admin/world_simulation/new").get_data(as_text=True)
    assert re.search(r'name="opt__attention__temperature" value="1.0"', html) and re.search(r'name="opt__discovery__w_interact" value="3.0"', html)
    assert re.search(r'name="opt__discovery__beta__0" value="-3.0"', html)
    assert "open" not in re.search(r'<details class="ws-advanced"[^>]*>', html).group(0)  # collapsed


def test_create_then_open_then_save_unchanged_leaves_the_files_identical(site):
    app, exps, tmp = site
    client = login(app, "admin")
    data = dict(form_of(schema.values_from_options({})), name="W", experiments=[str(i) for i in exps.values()], seed="11", granularity="day",
                attention_enabled="1", opt__attention__temperature="2.5", opt__attention__normalization="zscore", discovery_enabled="1",
                opt__discovery__quoted_weight="0.4", opt__discovery__beta__A="1.5", opt__crosspost__mode="agent_action",
                opt__crosspost__propensity="0.2", pseudonyms_enabled="1", membership_initial="one_random")
    data["crosspost_content"] = ["news", "images"]
    response = client.post("/admin/world_simulation/new", data=data)
    assert response.status_code == 302
    from y_web.src.models.admin import Federation

    fed = Federation.query.one()
    first, first_json = federation_json(fed), fed.config_json
    assert first["attention"] == {"enabled": True, "temperature": 2.5, "normalization": "zscore"}
    assert first["discovery"] == {"enabled": True, "quoted_weight": 0.4, "beta": {"A": 1.5}}
    assert first["crosspost"] == {"mode": "agent_action", "propensity": 0.2, "content": ["news", "images"]}
    assert first["membership"] == {"initial": "one_random"} and first["pseudonyms"] == {"enabled": True} and first["quoted"] == {"require_exposure": True}
    stored = json.loads(first_json)
    resave = dict(form_of(schema.values_from_options(stored)), seed="11", granularity="day", discovery_enabled="1")
    assert _post(client, f"/admin/world_simulation/{fed.id}/configuration", **resave).status_code == 302
    assert federation_json(fed) == first and json.loads(fed.config_json) == stored


def test_a_refused_creation_shows_what_was_typed(site):
    from y_web.src.models.admin import Federation

    app, exps, tmp = site
    client = login(app, "admin")
    data = dict(form_of(schema.values_from_options({})), name="W", experiments=[str(i) for i in exps.values()], attention_enabled="1",
                opt__attention__inertia="7", opt__attention__temperature="3")
    html = client.post("/admin/world_simulation/new", data=data).get_data(as_text=True)
    assert "Inertia must be between 0 and 1." in html and Federation.query.count() == 0
    assert re.search(r'name="opt__attention__temperature" value="3"', html)


def test_the_templates_use_the_shared_styles_and_have_no_json_box():
    for path in TEMPLATES.glob("*.html"):
        text = path.read_text()
        assert "<textarea" not in text, path.name
        assert "<style" not in text, path.name  # one stylesheet: admin-world-simulation.css
        assert "options_text" not in text and "Advanced parameters (JSON)" not in text
    for page in ("new", "list", "detail", "agents", "schedule", "analytics"):
        assert "admin-world-simulation.css" in (TEMPLATES / f"{page}.html").read_text()
    assert (Path(__file__).resolve().parents[1] / "static" / "assets" / "css" / "admin-world-simulation.css").is_file()


def test_the_list_agents_and_schedule_pages_render_with_the_admin_look(site):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    client = login(app, "admin")
    for path in ("", f"/{fed.id}/agents", "/schedule", "/analytics"):
        html = client.get("/admin/world_simulation" + path).get_data(as_text=True)
        assert 'class="dashboard-box' in html and "ws-crumb" in html and ("exp-tag" in html or path == "/schedule"), path
    listing = client.get("/admin/world_simulation").get_data(as_text=True)
    assert "ws-state-stopped" in listing and "mdi-play" in listing and "mdi-forum-outline" in listing
    empty = login(app, "researcher").get("/admin/world_simulation").get_data(as_text=True)
    assert "No World Simulation yet." in empty


def test_create_page_lists_the_populations_and_blocks_what_cannot_be_chosen(site):
    app, exps, tmp = site
    html = login(app, "admin").get("/admin/world_simulation/new").get_data(as_text=True)
    assert "Population:" in html and "(3 agents)" in html and 'data-platform="microblogging"' in html
    service.create_federation("Taken", list(exps.values()), owner="admin")
    html = login(app, "admin").get("/admin/world_simulation/new").get_data(as_text=True)
    assert "Already part of the World Simulation Taken." in html
