"""Web interface of the member experiments of a World Simulation: the option, the activation at start, the buttons of the
Execution tab (any state, idempotent, per member reports) and the cases of Instant messaging, dating and other owners."""

import json
import os
from types import SimpleNamespace

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import frontends, service  # noqa: E402
from y_web.src.federation import options_schema as schema  # noqa: E402
from y_web.tests.test_experiment_activation import exp_row, extra, flashes, make_user, toggle  # noqa: E402,F401  (fixture and helpers)
from y_web.tests.test_federation_lifecycle import needs_sdk, running_world  # noqa: E402,F401  (fixtures)
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_options_form import Form, form_of  # noqa: E402
from y_web.tests.test_world_simulation_ui import _post, login, site  # noqa: E402,F401  (fixture)

BASE = "/admin/world_simulation"


def admin_of(name="toggler"):
    from y_web import db
    from y_web.src.models import Admin_users

    return db.session.query(Admin_users).filter_by(username=name).one()


def world_of(exps, **kw):
    return service.create_federation("W", list(exps.values()), owner="toggler", **kw)


# --------------------------------------------------------------------------------------------------------------- the option
def test_the_option_is_on_by_default_and_only_yweb_reads_it():
    assert schema.BY_PATH[("frontends", "activate_on_start")].default is True
    assert schema.values_from_options({})["frontends_activate_on_start"] is True
    assert frontends.activate_on_start({}) is True and frontends.activate_on_start({"frontends": {}}) is True
    assert frontends.activate_on_start({"frontends": {"activate_on_start": False}}) is False
    assert "frontends" in service.OPTION_BLOCKS and "frontends" in service.LOCAL_BLOCKS


def test_the_option_is_written_only_when_switched_off_and_otherwise_left_alone():
    base = {"attention": {"enabled": True}}
    on = form_of(schema.values_from_options(base))
    assert schema.apply_form(on, base)[0] == base  # on = default: nothing written
    off = form_of(schema.values_from_options(base))
    off.pop("frontends_activate_on_start")  # an unchecked box is absent
    options, errors = schema.apply_form(off, base)
    assert errors == [] and options["frontends"] == {"activate_on_start": False}
    assert schema.values_from_options(options)["frontends_activate_on_start"] is False
    # an older page without the control leaves the stored option as it is
    assert schema.apply_form(Form(), options)[0]["frontends"] == {"activate_on_start": False}
    # switching it on again removes the key (the default)
    again = schema.values_from_options(options)
    again["frontends_activate_on_start"] = True
    assert "frontends" not in schema.apply_form(form_of(again), options)[0]
    # an explicit true that is already stored stays as it is
    kept = {"frontends": {"activate_on_start": True}}
    assert schema.apply_form(form_of(schema.values_from_options(kept)), kept)[0] == kept


def test_the_option_never_reaches_federation_json(toggle):
    app, exps, calls = toggle
    fed = world_of(exps, options={"frontends": {"activate_on_start": False}})
    assert "frontends" not in json.load(open(os.path.join(fed.folder, "federation.json")))
    assert json.loads(fed.config_json)["frontends"] == {"activate_on_start": False}  # stored for YWeb
    assert schema.unknown_paths(json.loads(fed.config_json)) == []


def test_the_form_has_the_field_with_its_help(toggle):
    app, exps, calls = toggle
    fed = world_of(exps)
    page = login(app, "toggler").get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert 'name="frontends_activate_on_start"' in page and 'name="frontends_present"' in page
    assert "Activate the web interface of the member experiments when the simulation starts" in page
    assert "Stopping the World Simulation does not deactivate them" in page
    assert "checked" in page.split('name="frontends_activate_on_start"')[1].split("</label>")[0]  # on by default
    new = login(app, "toggler").get(f"{BASE}/new").get_data(as_text=True)
    assert 'name="frontends_activate_on_start"' in new


def test_saving_the_form_with_the_box_unchecked_stores_the_option(toggle):
    app, exps, calls = toggle
    fed = world_of(exps)
    client = login(app, "toggler")
    values = schema.values_from_options({})
    values["frontends_activate_on_start"] = False
    data = {k: v for k, v in form_of(values).items() if not isinstance(v, list)}
    data["crosspost_content"] = ["all"]
    assert client.post(f"{BASE}/{fed.id}/configuration", data=data).status_code == 302
    assert json.loads(fed.config_json)["frontends"] == {"activate_on_start": False}


# ------------------------------------------------------------------------------------------------------------- start
def spy_on_server_start(monkeypatch):
    from y_web.src.simulation import execution_backend as eb

    seen = []
    original = eb.start_server_for_experiment
    monkeypatch.setattr(eb, "start_server_for_experiment", lambda exp: seen.append((exp.platform_type, exp.status)) or original(exp))
    return seen


@needs_sdk
def test_start_activates_the_members_before_their_servers(running_world, toggle, monkeypatch):
    from y_web.src.simulation import execution_backend as eb

    fed, fake, tmp = running_world
    app, exps, calls = toggle
    seen = spy_on_server_start(monkeypatch)
    eb.start_federation(fed, admin_user=admin_of())
    assert sorted(seen) == [("forum", 1), ("microblogging", 1)]  # active when each server starts
    assert fed.status == "running" and fed.frontend_warnings == []
    assert {exp_row(i).status for i in exps.values()} == {1}
    assert sorted(e for e, _kw in calls["ensure"]) == sorted(exps.values())
    # not undone at stop
    eb.stop_federation(fed)
    assert {exp_row(i).status for i in exps.values()} == {1}


@needs_sdk
def test_start_without_a_user_activates_for_the_owner(running_world, toggle):
    from y_web.src.simulation import execution_backend as eb

    fed, fake, tmp = running_world
    app, exps, calls = toggle
    fed.owner = "toggler"
    eb.start_federation(fed)
    assert {exp_row(i).status for i in exps.values()} == {1}
    assert {kw["account_id"] for _e, kw in calls["ensure"]} == {admin_of().id}
    eb.stop_federation(fed)


@needs_sdk
def test_start_leaves_the_experiments_alone_when_the_option_is_off(running_world, toggle):
    import json as _json

    from y_web.src.simulation import execution_backend as eb

    fed, fake, tmp = running_world
    app, exps, calls = toggle
    fed.config_json = _json.dumps({"frontends": {"activate_on_start": False}})
    eb.start_federation(fed, admin_user=admin_of())
    assert fed.status == "running" and {exp_row(i).status for i in exps.values()} == {0} and calls["ensure"] == []
    eb.stop_federation(fed)


@needs_sdk
def test_a_member_that_cannot_be_activated_is_a_warning_and_the_start_goes_on(running_world, toggle, monkeypatch):
    import y_web.src.experiment.helpers as helpers
    from y_web.src.simulation import execution_backend as eb

    fed, fake, tmp = running_world
    app, exps, calls = toggle
    monkeypatch.setattr(helpers, "ensure_experiment_user", lambda exp, **kw: (None, False) if exp.platform_type == "forum" else (SimpleNamespace(id=1), True))
    eb.start_federation(fed, admin_user=admin_of())
    assert fed.status == "running"
    assert exp_row(exps["microblogging"]).status == 1 and exp_row(exps["forum"]).status == 0
    assert fed.frontend_warnings == ["forum: Unable to prepare the experiment user."]
    eb.stop_federation(fed)


@needs_sdk
def test_an_unexpected_error_in_the_activation_never_stops_the_start(running_world, toggle, monkeypatch):
    from y_web.src.federation import frontends as fe
    from y_web.src.simulation import execution_backend as eb

    fed, fake, tmp = running_world

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(fe, "activate_frontends", boom)
    eb.start_federation(fed, admin_user=SimpleNamespace(id=1))
    assert fed.status == "running" and fed.frontend_warnings == ["disk on fire"]
    eb.stop_federation(fed)


# ----------------------------------------------------------------------------------------------------------- buttons
def test_the_buttons_activate_and_deactivate_every_member_in_any_state(toggle):
    app, exps, calls = toggle
    fed = world_of(exps)
    client = login(app, "toggler")
    for state in ("stopped", "running", "paused", "failed"):
        fed.status = state
        response = _post(client, f"{BASE}/{fed.id}/frontends/activate")
        assert response.status_code == 302 and response.headers["Location"].endswith(f"{BASE}/{fed.id}#execution"), state
        assert {exp_row(i).status for i in exps.values()} == {1}
        assert flashes(client)[-1] == ("success", "Web interfaces activated: 2 (already active: 0).")
        assert _post(client, f"{BASE}/{fed.id}/frontends/deactivate").status_code == 302
        assert {exp_row(i).status for i in exps.values()} == {0}
        client = login(app, "toggler")


def test_activating_twice_changes_nothing_the_second_time(toggle):
    app, exps, calls = toggle
    fed = world_of(exps)
    client = login(app, "toggler")
    _post(client, f"{BASE}/{fed.id}/frontends/activate")
    first = list(calls["ensure"])
    client = login(app, "toggler")
    _post(client, f"{BASE}/{fed.id}/frontends/activate")
    assert calls["ensure"] == first and flashes(client) == [("success", "Web interfaces activated: 0 (already active: 2).")]
    client = login(app, "toggler")
    _post(client, f"{BASE}/{fed.id}/frontends/deactivate")
    client = login(app, "toggler")
    _post(client, f"{BASE}/{fed.id}/frontends/deactivate")
    assert flashes(client) == [("success", "Web interfaces deactivated: 0 (already inactive: 2).")]


def test_the_json_answer_reports_each_member(toggle):
    app, exps, calls = toggle
    fed = world_of(exps)
    response = login(app, "toggler").post(f"{BASE}/{fed.id}/frontends/activate", headers={"Accept": "application/json"})
    data = response.get_json()
    assert response.status_code == 200 and data["ok"] is True and data["problems"] == []
    assert {m["member"]: m["state"] for m in data["members"]} == {"microblogging": "activated", "forum": "activated"}
    assert all(row["active"] and row["url"] == f"/admin/join_experiment/{row['exp_id']}" for row in data["frontends"])


def test_a_failure_is_reported_for_its_member_and_the_others_are_done(toggle, monkeypatch):
    import y_web.src.experiment.helpers as helpers

    app, exps, calls = toggle
    fed = world_of(exps)
    good = helpers.ensure_experiment_user
    monkeypatch.setattr(helpers, "ensure_experiment_user", lambda exp, **kw: (None, False) if exp.platform_type == "forum" else good(exp, **kw))
    response = login(app, "toggler").post(f"{BASE}/{fed.id}/frontends/activate", headers={"Accept": "application/json"})
    data = response.get_json()
    assert response.status_code == 207 and data["ok"] is False
    assert data["problems"] == ["forum: Unable to prepare the experiment user."]
    assert exp_row(exps["microblogging"]).status == 1 and exp_row(exps["forum"]).status == 0


def test_a_member_of_another_owner_is_skipped_with_a_message(toggle):
    from y_web import db

    app, exps, calls = toggle
    fed = world_of(exps)
    exp_row(exps["microblogging"]).owner = "toggler-researcher"
    db.session.commit()
    other = exp_row(exps["forum"])
    other.owner = "someone-else"
    db.session.commit()
    fed.owner = "toggler-researcher"
    client = login(app, "toggler-researcher")
    _post(client, f"{BASE}/{fed.id}/frontends/activate")
    assert exp_row(exps["forum"]).status == 0
    messages = [m for _c, m in flashes(client)]
    assert "forum: You are not allowed to access this experiment." in messages
    assert any(m.startswith("Web interfaces activated: 1") for m in messages)


def test_ordinary_users_and_unknown_simulations_are_refused(toggle):
    app, exps, calls = toggle
    fed = world_of(exps)
    assert app.test_client().post(f"{BASE}/{fed.id}/frontends/activate").status_code in (302, 401)
    assert login(app, "teacher").post(f"{BASE}/{fed.id}/frontends/activate").status_code == 302
    assert {exp_row(i).status for i in exps.values()} == {0}
    assert login(app, "toggler").post(f"{BASE}/999/frontends/activate").status_code == 404


def test_the_execution_tab_shows_the_buttons_the_state_and_the_link_of_each_member(toggle):
    app, exps, calls = toggle
    fed = world_of(exps)
    client = login(app, "toggler")
    page = client.get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert f'action="{BASE}/{fed.id}/frontends/activate"' in page and f'action="{BASE}/{fed.id}/frontends/deactivate"' in page
    assert "Activate frontends" in page and "Deactivate frontends" in page
    assert "/admin/join_experiment/" not in page and page.count("Inactive") >= 2
    _post(client, f"{BASE}/{fed.id}/frontends/activate")
    page = client.get(f"{BASE}/{fed.id}").get_data(as_text=True)
    for exp_id in exps.values():
        assert f'href="/admin/join_experiment/{exp_id}"' in page
    assert page.count("ws-state-running\">Active") == 2


def test_instant_messaging_and_dating_members_only_get_the_access_row(toggle, monkeypatch):
    from y_web import db
    from y_web.src.models import User_Experiment

    app, exps, calls = toggle
    im, dating = extra("instant_messaging", "HPC"), extra("dating", "HPC")
    rows = [(SimpleNamespace(member="instant_messaging", platform_type="instant_messaging"), exp_row(im)),
            (SimpleNamespace(member="dating", platform_type="dating"), exp_row(dating))]
    monkeypatch.setattr(service, "members_of", lambda fed: rows)
    outcomes = frontends.activate_frontends(SimpleNamespace(), admin_of())
    assert [o["state"] for o in outcomes] == ["activated", "activated"]
    assert calls["ensure"] == [] and calls["register"] == []
    assert db.session.query(User_Experiment).filter(User_Experiment.exp_id.in_([im, dating]), User_Experiment.user_id == admin_of().id).count() == 2
    assert [o["state"] for o in frontends.activate_frontends(SimpleNamespace(), admin_of())] == ["already_active"] * 2
    assert [o["state"] for o in frontends.deactivate_frontends(SimpleNamespace(), admin_of())] == ["deactivated"] * 2
    assert frontends.activate_frontends(SimpleNamespace(), None)[0]["state"] == "failed"
