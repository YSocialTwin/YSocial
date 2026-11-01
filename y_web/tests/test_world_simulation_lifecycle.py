"""F7.3: export, clone and reset of a World Simulation. The archive and the copy of each member are the ones of the
single experiment; here they are replaced by small stand-ins."""

import hashlib
import json
import os
import sqlite3
import zipfile

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import lifecycle, service  # noqa: E402
from y_web.src.federation.service import WorldSimulationError  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_ui import login, site  # noqa: E402,F401  (fixtures and helper)

BASE = "/admin/world_simulation"


def fake_zip(exp_id, path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("experiment.txt", f"experiment {exp_id}")
    return "x.zip"


def with_run(fed):
    db = sqlite3.connect(os.path.join(fed.folder, "federation.db"), isolation_level=None)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO federation_event (tick, kind, detail_json, at) VALUES (1,'ready','{}',0)")
    db.close()
    for name in ("analytics_federation.db", "coordinator.log"):
        open(os.path.join(fed.folder, name), "w").write("x")


def copy_of(exp, name):
    from y_web import db
    from y_web.src.models.admin import Exps, Population_Experiment

    new = Exps(platform_type=exp.platform_type, exp_name=name, db_name=f"experiments/{name}/db.db", owner=exp.owner,
               exp_descr="", status=0, running=0, port=5000, simulator_type=exp.simulator_type, exp_status="stopped")
    db.session.add(new)
    db.session.flush()
    for link in db.session.query(Population_Experiment).filter_by(id_exp=exp.idexp).all():
        db.session.add(Population_Experiment(id_population=link.id_population, id_exp=new.idexp))
    return new


def test_the_bundle_holds_manifest_database_analytics_and_every_member(world, tmp_path):
    app, exps, tmp = world
    fed = service.create_federation("my world", list(exps.values()), owner="admin", seed=9,
                                    options={"crosspost": {"mode": "agent_action"}}, exposures=True)
    with_run(fed)
    out = str(tmp_path / "bundle.zip")
    assert lifecycle.export_bundle(fed, out, member_zip=fake_zip) == "my_world.zip"
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        data = json.loads(z.read("world_simulation.json"))
        assert names == {"world_simulation.json", "federation.db", "analytics_federation.db",
                         "members/forum.zip", "members/microblogging.zip"}
        assert not any("token" in n for n in names) and "token" not in json.dumps(data).lower()
        assert data["seed"] == 9 and data["options"] == {"crosspost": {"mode": "agent_action"}} and data["exposures"] is True
        assert sorted(m["member"] for m in data["members"]) == ["forum", "microblogging"]
        assert len(data["identity"]) == 6
        assert set(data["files"]) == names - {"world_simulation.json"}
        for name, digest in data["files"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
        z.extract("federation.db", tmp_path)
    assert sqlite3.connect(tmp_path / "federation.db").execute("SELECT COUNT(*) FROM federation_event").fetchone()[0] == 1


def test_the_manifest_is_the_same_on_two_exports(world, tmp_path):
    app, exps, tmp = world
    fed = service.create_federation("w", list(exps.values()), owner="admin")
    with_run(fed)
    a, b = str(tmp_path / "a.zip"), str(tmp_path / "b.zip")
    lifecycle.export_bundle(fed, a, member_zip=fake_zip)
    lifecycle.export_bundle(fed, b, member_zip=fake_zip)
    with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
        assert za.read("world_simulation.json") == zb.read("world_simulation.json")


def test_clone_makes_new_experiments_and_a_stopped_world_simulation_with_the_same_parameters(world):
    from y_web.src.models.admin import Exps, Federation, FederationIdentityLink

    app, exps, tmp = world
    fed = service.create_federation("one", list(exps.values()), owner="admin", seed=5, granularity="day",
                                    options={"attention": {"enabled": True}}, exposures=True)
    with_run(fed)
    new = lifecycle.clone(fed, "two", copy=copy_of)
    assert new.id != fed.id and new.status == "stopped" and new.seed == 5 and new.granularity == "day"
    assert json.loads(new.config_json) == json.loads(fed.config_json)
    assert not os.path.exists(os.path.join(new.folder, "federation.db")) and new.folder != fed.folder
    assert {e.exp_name for e in Exps.query.all()} >= {"two_forum", "two_microblogging"}
    old_ids = set(exps.values())
    assert {row.exp_id for row, _ in service.members_of(new)}.isdisjoint(old_ids)
    assert FederationIdentityLink.query.filter_by(federation_pk=new.id).count() == 6
    assert Federation.query.count() == 2
    with pytest.raises(WorldSimulationError):
        lifecycle.clone(fed, "  ", copy=copy_of)


def test_reset_removes_the_run_and_refuses_while_active(world):
    app, exps, tmp = world
    fed = service.create_federation("one", list(exps.values()), owner="admin")
    with_run(fed)
    fed.status = "running"
    with pytest.raises(WorldSimulationError):
        lifecycle.reset(fed)
    assert os.path.exists(os.path.join(fed.folder, "federation.db"))
    fed.status = "failed"
    assert set(lifecycle.reset(fed)) == {"federation.db", "analytics_federation.db", "coordinator.log"}
    assert fed.status == "stopped" and not os.path.exists(os.path.join(fed.folder, "federation.db"))
    assert os.path.exists(os.path.join(fed.folder, "federation.json"))  # the configuration stays


def test_routes_export_reset_and_permissions(site, monkeypatch):
    app, exps, tmp = site
    monkeypatch.setattr(lifecycle, "_default_member_zip", fake_zip)
    fed = service.create_federation("W", list(exps.values()), owner="admin")
    with_run(fed)
    client = login(app, "admin")
    res = client.get(f"{BASE}/{fed.id}/export")
    assert res.status_code == 200 and res.mimetype == "application/zip" and "W.zip" in res.headers["Content-Disposition"]
    res.close()
    html = client.get(f"{BASE}/{fed.id}").get_data(as_text=True)
    assert 'id="ws-export"' in html and f"{BASE}/{fed.id}/clone" in html and f"{BASE}/{fed.id}/reset" in html
    assert client.post(f"{BASE}/{fed.id}/reset").status_code == 302
    assert not os.path.exists(os.path.join(fed.folder, "federation.db"))
    assert login(app, "teacher").get(f"{BASE}/{fed.id}/export").status_code == 302  # sent back home
    assert login(app, "researcher").post(f"{BASE}/{fed.id}/reset").status_code == 404  # not the owner
