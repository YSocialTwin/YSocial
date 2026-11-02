"""Silent no-cross-post warning: a configuration that cannot produce any cross-post is flagged in the form (live and on first
render), on the detail page, and the Execution tab counts the cross-posts and explains a run that has none."""

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import options_schema as schema  # noqa: E402
from y_web.src.federation import service  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_ui import login, site  # noqa: E402,F401  (fixtures and helper)

BASE = "/admin/world_simulation"
JS = Path(__file__).resolve().parents[1] / "static" / "assets" / "js" / "admin-world-simulation.js"
MEMBERS = {"microblogging", "forum"}


# -------------------------------------------------------------------------------------------------- the rule
@pytest.mark.parametrize(
    "options, causes",
    [
        ({}, []),  # the YWeb defaults (propensity 0.2, 0.3 for every pair) can cross-post
        ({"crosspost": {"propensity": 0}}, ["propensity"]),  # an explicit 0 is respected
        ({"crosspost": {"probability": {"microblogging->forum": 0, "forum->microblogging": 0}}}, ["probability"]),
        ({"crosspost": {"probability": {"microblogging->forum": 0}}}, []),  # the other pair keeps the default
        ({"crosspost": {"propensity": 0, "probability": {"microblogging->forum": 0, "forum->microblogging": 0}}}, ["propensity", "probability"]),
        ({"crosspost": {"propensity": 0.3, "probability": {"microblogging->forum": 0.5}}}, []),
        ({"crosspost": {"mode": "agent_action"}}, []),
        ({"crosspost": {"mode": "agent_action", "propensity": 0.0}}, ["propensity"]),
        ({"crosspost": {"mode": "agent_action", "propensity": 0.0, "probability": {"microblogging->forum": 1}}}, ["propensity"]),
        ({"crosspost": {"probability": {"microblogging->dating": 0.9, "microblogging->forum": 0, "forum->microblogging": 0}}}, ["probability"]),
    ],
)
def test_the_rule_on_stored_options(options, causes):
    assert schema.crosspost_causes_from_options(options, MEMBERS) == causes
    assert bool(schema.crosspost_warning(causes)) is bool(causes)


def test_the_rule_on_the_values_of_the_form():
    values = schema.values_from_options({})
    platforms = ["microblogging", "forum"]
    assert values["opt__crosspost__propensity"] == "0.2" and values["prob__forum__microblogging"] == "0.3"  # pre-filled
    assert schema.crosspost_causes_from_values(values, platforms) == []
    values["opt__crosspost__propensity"] = "0"
    assert schema.crosspost_causes_from_values(values, platforms) == ["propensity"]
    values["opt__crosspost__propensity"] = ""  # blank is the default
    assert schema.crosspost_causes_from_values(values, platforms) == []
    values["prob__forum__microblogging"] = "0"
    values["prob__microblogging__forum"] = "0"
    assert schema.crosspost_causes_from_values(values, platforms) == ["probability"]
    values["prob__microblogging__forum"] = ""
    assert schema.crosspost_causes_from_values(values, platforms) == []
    values["prob__microblogging__forum"] = "abc"  # a text that is not a number counts as nothing
    assert schema.crosspost_causes_from_values(values, platforms) == ["probability"]
    values["opt__crosspost__mode"] = "agent_action"
    assert schema.crosspost_causes_from_values(values, platforms) == []


def test_the_message_says_what_to_set():
    both = schema.crosspost_warning(["propensity", "probability"])
    assert both == ("No cross-post can happen with this configuration. Set the propensity (the share of posts the agents mark for "
                    "cross-posting) and the probability for at least one pair of platforms.")
    assert "propensity" in schema.crosspost_warning(["propensity"]) and "probability" in schema.crosspost_warning(["probability"])
    assert schema.crosspost_warning([]) == ""


def test_the_yweb_defaults_are_0_2_and_0_3():
    assert schema.BY_PATH[("crosspost", "propensity")].default == 0.2 and schema.DEFAULT_PAIR_PROBABILITY == 0.3
    assert schema.BY_PATH[("crosspost", "mode")].default == "coordinator_rule"
    assert schema.default_options()["crosspost"] == {"mode": "coordinator_rule", "propensity": 0.2, "decision": "random",
                                                     "decision_max_per_day": 5}  # P14: the random draw, 5 model decisions a day if it is switched on


def federation_json(fed):
    return json.load(open(os.path.join(fed.folder, "federation.json")))


def sections(fed):
    return [service.member_section(fed, row, exp) for row, exp in service.members_of(fed)]


BOTH = {"microblogging->forum": 0.3, "forum->microblogging": 0.3}


def test_a_new_world_simulation_without_values_carries_the_defaults_in_both_files(world):
    app, exps, tmp = world
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    assert json.loads(fed.config_json) == {"exposures": False} or "crosspost" not in json.loads(fed.config_json)  # nothing stored
    crosspost = federation_json(fed)["crosspost"]
    assert crosspost["propensity"] == 0.2 and crosspost["probability"] == BOTH
    assert [s["crosspost_propensity"] for s in sections(fed)] == [0.2, 0.2]
    assert all("seed" in s for s in sections(fed))


def test_a_world_simulation_stored_before_the_defaults_gets_them_at_the_next_start(world):
    from y_web import db

    app, exps, tmp = world
    fed = service.create_federation("old", list(exps.values()), owner="admin", options={"attention": {"enabled": True}})
    fed.config_json = json.dumps({"attention": {"enabled": True}, "exposures": False})  # as stored by an earlier release
    db.session.commit()
    service.write_federation_files(fed)  # what a (re)start does
    assert federation_json(fed)["crosspost"] == {"propensity": 0.2, "probability": BOTH}
    assert [s["crosspost_propensity"] for s in sections(fed)] == [0.2, 0.2]
    # the form shows them
    values = schema.values_from_options(json.loads(fed.config_json))
    assert values["opt__crosspost__propensity"] == "0.2" and values["prob__microblogging__forum"] == "0.3"


def test_an_explicit_zero_is_always_respected(world):
    app, exps, tmp = world
    fed = service.create_federation("zero", list(exps.values()), owner="admin",
                                    options={"crosspost": {"propensity": 0, "probability": {"microblogging->forum": 0}}})
    crosspost = federation_json(fed)["crosspost"]
    assert crosspost["propensity"] == 0 and crosspost["probability"] == {"microblogging->forum": 0, "forum->microblogging": 0.3}
    assert [s["crosspost_propensity"] for s in sections(fed)] == [0.0, 0.0]
    assert schema.crosspost_causes_from_options(json.loads(fed.config_json), MEMBERS) == ["propensity"]  # the warning shows again


def test_the_form_round_trip_writes_a_zero_and_not_the_defaults():
    base = {}
    form = schema.values_from_options(base)
    form["opt__crosspost__propensity"] = "0"
    form["prob__forum__microblogging"] = "0"
    posted = {k: (v if not isinstance(v, bool) else ("1" if v else None)) for k, v in form.items()}
    posted = type("F", (dict,), {"getlist": lambda self, k: self.get(k, [])})({k: v for k, v in posted.items() if v is not None and not isinstance(v, list)})
    options, errors = schema.apply_form(posted, base, members=MEMBERS)
    assert errors == [] and options["crosspost"] == {"propensity": 0.0, "probability": {"forum->microblogging": 0.0}}
    again = schema.values_from_options(options)
    assert again["opt__crosspost__propensity"] == "0.0" and again["prob__forum__microblogging"] == "0.0"
    assert again["prob__microblogging__forum"] == "0.3"


# -------------------------------------------------------------------------------------------------- the pages
def warning_tag(page):
    start = page.index('id="ws-crosspost-warning"')
    return page[page.rindex("<p", 0, start): page.index("</p>", start)]


def test_the_forms_are_prefilled_and_warn_only_for_an_explicit_zero(site):
    app, exps, tmp = site
    creation = login(app, "admin").get(f"{BASE}/new").get_data(as_text=True)
    assert 'name="opt__crosspost__propensity" value="0.2"' in creation and 'name="prob__forum__microblogging" value="0.3"' in creation
    assert " hidden" in warning_tag(creation).split(">")[0]  # with the defaults nothing is wrong
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    page = login(app, "admin").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert 'name="opt__crosspost__propensity" value="0.2"' in page and 'name="prob__forum__microblogging" value="0.3"' in page
    assert " hidden" in warning_tag(page).split(">")[0] and "ws-saved-crosspost-warning" not in page
    fed.config_json = json.dumps({"crosspost": {"propensity": 0}, "exposures": False})  # an explicit 0, stored
    page = login(app, "admin").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert " hidden" not in warning_tag(page).split(">")[0] and "Set the propensity" in page.split('id="ws-saved-crosspost-warning"')[1][:400]


def test_the_detail_page_of_a_configured_simulation_has_no_warning(site):
    app, exps, tmp = site
    fed = service.create_federation(
        "W", list(exps.values()), owner="admin",
        options={"crosspost": {"propensity": 0.3, "probability": {"microblogging->forum": 0.5}}})
    page = login(app, "admin").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert "ws-saved-crosspost-warning" not in page
    assert " hidden" in warning_tag(page).split(">")[0]  # the live warning exists but is hidden


def test_the_live_script_covers_the_same_rule():
    text = JS.read_text()
    assert "function initCrosspostWarning" in text and "initCrosspostWarning();" in text
    assert "agent_action" in text and "data-text-" in text and "ws-probability-matrix input" in text
    if shutil.which("node"):
        assert subprocess.run(["node", "--check", str(JS)], capture_output=True).returncode == 0


# -------------------------------------------------------------------------------------------------- the run
def make_run(fed, ticks=(), messages=(), schema_sql=SCHEMA):
    db = sqlite3.connect(os.path.join(fed.folder, "federation.db"), isolation_level=None)
    db.executescript(schema_sql)
    for tick, n in ticks:
        db.execute("INSERT INTO federation_event (tick, kind, detail_json, at) VALUES (?, 'crosspost_materialized', ?, 0)",
                   (tick, json.dumps({"crossposts": n})))
    for i, kind in enumerate(messages):
        db.execute("INSERT INTO federation_message VALUES (?,?,?,?,?,?,?)", (f"m:{i}", "microblogging", "coordinator", 0, 1, kind, "{}"))
    db.close()


def status_of(app, fed, monkeypatch=None, tick=None):
    from y_web.src.federation import coordinator_process as cp

    if tick is not None:
        monkeypatch.setattr(cp, "coordinator_status", lambda f, timeout=1.5: {"global_tick": tick, "skew": 0, "members": {}})
    return login(app, "admin").get(f"{BASE}/{fed.id}/status.json").get_json()


def test_the_line_counts_the_crossposts_and_the_exported_content(site):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    make_run(fed, ticks=[(0, 0), (1, 0), (2, 3), (3, 2)], messages=["content.v1"] * 4 + ["crosspost.v1"] * 5 + ["exposure.v1"])
    data = status_of(app, fed)["crossposts"]
    assert (data["total"], data["ticks"], data["exported"]) == (5, 2, 4)
    assert data["text"] == "Cross-posts: 5 materialised (in 2 ticks) · content exported: 4" and data["hint"] is None
    assert status_of(app, fed)["bus"]["messages"] == 10  # the total of the bus is unchanged


def test_without_a_database_or_with_missing_tables_nothing_breaks(site):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    assert status_of(app, fed)["crossposts"]["text"] is None  # no database of the run yet
    sqlite3.connect(os.path.join(fed.folder, "federation.db")).close()  # an empty file: no tables
    data = status_of(app, fed)["crossposts"]
    assert (data["total"], data["ticks"], data["exported"]) == (0, 0, 0) and data["hint"] is None
    make_run(fed, schema_sql="CREATE TABLE federation_message (fed_msg_id TEXT PRIMARY KEY, source_member TEXT, target_member TEXT, "
             "tick_emitted INTEGER, deliver_at_tick INTEGER, payload_type TEXT, payload_json TEXT);")
    assert status_of(app, fed)["crossposts"]["text"].startswith("Cross-posts: 0 materialised")


def test_a_run_past_tick_6_with_nothing_exported_gets_the_hint_with_the_cause(site, monkeypatch):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin", options={"crosspost": {"propensity": 0, "probability": {"microblogging->forum": 0, "forum->microblogging": 0}}})
    make_run(fed, ticks=[(t, 0) for t in range(9)])
    fed.status = "running"
    data = status_of(app, fed, monkeypatch, tick=9)["crossposts"]
    assert data["hint"] == ("No content has been marked for cross-posting after 9 ticks. No cross-post can happen with this "
                            "configuration. Set the propensity (the share of posts the agents mark for cross-posting) and the "
                            "probability for at least one pair of platforms.")
    assert status_of(app, fed, monkeypatch, tick=6)["crossposts"]["hint"] is None  # not yet past tick 6


def test_the_hint_names_the_missing_value_and_stays_away_when_there_is_something(site, monkeypatch):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin", options={"crosspost": {"propensity": 0.4, "probability": {"microblogging->forum": 0, "forum->microblogging": 0}}})
    make_run(fed, ticks=[(t, 0) for t in range(9)])
    fed.status = "running"
    hint = status_of(app, fed, monkeypatch, tick=12)["crossposts"]["hint"]
    assert "every probability is 0 or empty" in hint
    make_run_more = sqlite3.connect(os.path.join(fed.folder, "federation.db"), isolation_level=None)
    make_run_more.execute("INSERT INTO federation_message VALUES ('c:1','forum','coordinator',3,4,'content.v1','{}')")
    make_run_more.close()
    assert status_of(app, fed, monkeypatch, tick=12)["crossposts"]["hint"] is None  # content is being exported
    fed.status = "stopped"
    assert status_of(app, fed)["crossposts"]["hint"] is None


def test_the_hint_without_a_configuration_cause_points_at_the_agents_and_the_filter(site, monkeypatch):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")  # the defaults can cross-post
    make_run(fed, ticks=[(t, 0) for t in range(9)])
    fed.status = "running"
    hint = status_of(app, fed, monkeypatch, tick=9)["crossposts"]["hint"]
    assert hint.startswith("No content has been marked for cross-posting after 9 ticks.") and "content filter" in hint


def test_the_execution_tab_has_the_line_and_the_notice(site):
    app, exps, tmp = site
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    page = login(app, "admin").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert 'id="ws-crosspost-line"' in page and 'id="ws-crosspost-hint"' in page
    assert "ws-crosspost-line" in JS.read_text() and "cps.hint" in JS.read_text()
