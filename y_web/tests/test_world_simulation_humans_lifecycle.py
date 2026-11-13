"""H3: the people enrolled in a World Simulation in export, import, clone, reset and delete (round trip as F7.3b)."""

import json
import os
import zipfile

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from y_web.src.federation import humans, lifecycle, service  # noqa: E402
from y_web.tests.test_federation_humans import Offline, user  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_import import (  # noqa: E402
    export,
    logical,
    run_data,
    stub_import,
)
from y_web.tests.test_world_simulation_lifecycle import copy_of  # noqa: E402


@pytest.fixture(autouse=True)
def _members_reset_is_recorded(monkeypatch):
    """The reset of a member experiment has its own tests (test_experiment_reset.py): here it is only recorded."""
    done = []
    monkeypatch.setattr(
        lifecycle,
        "_default_reset_member",
        lambda exp: done.append(exp.idexp) or {"restored": 0},
    )
    return done


def enrolled(world_fixture):
    app, exps, tmp = world_fixture
    fed = service.create_federation(
        "my world", list(exps.values()), owner="admin", seed=9
    )
    off = Offline()  # one runner: account ids are distinct, as in a real platform
    humans.enrol(fed, user(7, "giulio"), ["forum", "microblogging"], offline=off)
    humans.enrol(fed, user(8, "ann"), ["forum"], offline=off)
    humans.unenrol(fed, 8)
    return fed, tmp


def state_of(fed):
    return [
        (h.user_id, h.human_id, h.status, humans.members_state(h))
        for h in humans.list_humans(fed)
    ]


def test_manifest_lists_the_people_and_their_links(world):
    fed, tmp = enrolled(world)
    data = lifecycle.manifest(fed)
    assert [(h["user_id"], h["human_id"], h["status"]) for h in data["humans"]] == [
        (7, "human:7", "active"),
        (8, "human:8", "inactive"),
    ]
    assert {
        (l["global_agent_id"], l["member"])
        for l in data["identity"]
        if l["global_agent_id"].startswith("human:")
    } == {("human:7", "forum"), ("human:7", "microblogging"), ("human:8", "forum")}


def test_round_trip_with_people_restores_enrolments_links_and_the_run(world, tmp_path):
    from y_web.src.models.admin import FederationIdentityLink

    fed, tmp = enrolled(world)
    run_data(fed)
    before = state_of(fed)
    bundle, original_db = export(fed, tmp_path), logical(
        os.path.join(fed.folder, "federation.db")
    )
    service.delete_federation(fed)
    assert (
        humans.list_humans(fed) == []
        and FederationIdentityLink.query.filter_by(global_agent_id="human:7").count()
        == 0
    )
    new, report = lifecycle.import_bundle(
        bundle, owner="admin", member_import=stub_import
    )
    assert report == {
        "restored_database": True,
        "federation_id_kept": True,
        "notes": [],
    }
    assert state_of(new) == before
    assert logical(os.path.join(new.folder, "federation.db")) == original_db
    config = json.load(open(os.path.join(new.folder, "federation.json")))
    assert {
        r["global_agent_id"]
        for r in config["identity"]
        if r["global_agent_id"].startswith("human:")
    } == {"human:7", "human:8"}
    again = json.loads(
        zipfile.ZipFile(export(new, tmp_path, "c.zip")).read("world_simulation.json")
    )
    first = json.loads(zipfile.ZipFile(bundle).read("world_simulation.json"))
    for data in (again, first):
        for member in data["members"]:
            member.pop("exp_name")
        data.pop("files")
    assert again == first


def test_a_bundle_without_the_key_still_imports(world, tmp_path):
    """Bundles of the first release (no ``humans``) import as before."""
    app, exps, tmp = world
    fed = service.create_federation("plain", list(exps.values()), owner="admin", seed=3)
    bundle = export(fed, tmp_path)
    data = lifecycle.read_bundle(bundle)
    assert data["humans"] == []
    service.delete_federation(fed)
    new, report = lifecycle.import_bundle(
        bundle, owner="admin", member_import=stub_import
    )
    assert humans.list_humans(new) == [] and report["federation_id_kept"] is True


def test_clone_starts_without_people_and_reset_keeps_them(world):
    fed, tmp = enrolled(world)
    copy = lifecycle.clone(fed, "twin", copy=lambda exp, name: copy_of(exp, name))
    assert humans.list_humans(copy) == [] and humans.accounts_by_member(copy) == {}
    fed.status = "completed"
    run_data(fed)
    lifecycle.reset(fed)
    assert len(humans.list_humans(fed)) == 2 and humans.accounts_by_member(fed)[
        "forum"
    ] == {"human:7": "101"}


def test_delete_removes_the_enrolments(world):
    from y_web.src.models.admin import FederationHuman

    fed, tmp = enrolled(world)
    service.delete_federation(fed)
    assert FederationHuman.query.count() == 0
