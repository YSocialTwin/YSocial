"""F7.3: import of a World Simulation bundle and the round trip export -> import -> run."""

import io
import json
import os
import re
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.coordinator.db import SCHEMA  # noqa: E402

from y_web.src.federation import lifecycle, service  # noqa: E402
from y_web.src.federation.service import WorldSimulationError  # noqa: E402
from y_web.tests.test_federation_service import world  # noqa: E402,F401  (fixture)
from y_web.tests.test_world_simulation_lifecycle import copy_of, fake_zip  # noqa: E402
from y_web.tests.test_world_simulation_ui import login, site  # noqa: E402,F401  (fixtures and helper)

BASE = "/admin/world_simulation"


def stub_import(archive_path, name):
    """Stands in for "Upload experiment": the archive must be a readable zip, the experiment a copy of a member."""
    from y_web.src.models.admin import Exps

    with zipfile.ZipFile(archive_path) as z:
        exp_id = int(z.read("experiment.txt").decode().split()[1])
    return copy_of(Exps.query.get(exp_id), name)


def run_data(fed):
    """A coordinator database as a finished run leaves it: members, identity map and a few events and messages."""
    db = sqlite3.connect(os.path.join(fed.folder, "federation.db"), isolation_level=None)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO federation_meta VALUES (?,?,?,?,?,0)", (int(fed.federation_id), "1.0", fed.seed, fed.granularity, "completed"))
    for row, exp in service.members_of(fed):
        db.execute("INSERT INTO federation_member VALUES (?,?,?,?,5)", (row.member, str(exp.idexp), row.platform_type, "finished"))
    for l in __import__("y_web").db.session.query(__import__("y_web.src.models.admin", fromlist=["x"]).FederationIdentityLink).filter_by(federation_pk=fed.id):
        db.execute("INSERT INTO federation_identity VALUES (?,?,?,'active',0,NULL)", (l.global_agent_id, l.member, l.local_account_id or f"{l.member}-{l.global_agent_id}"))  # the runtime's binding
    db.execute("INSERT INTO federation_event (tick, kind, detail_json, at) VALUES (3,'ready','{}',1.5)")
    db.execute("INSERT INTO federation_message VALUES ('x:0','coordinator','forum',3,4,'crosspost.v1','{}')")
    db.close()


def logical(path, skip_exp_id=True):
    """The content of a coordinator database without wall-clock values and the experiment ids of the members."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = {}
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
        keep = [c for c in cols if c not in ("at", "created_at", "id") and not (skip_exp_id and (table, c) == ("federation_member", "exp_id"))]
        out[table] = sorted(map(repr, conn.execute(f"SELECT {', '.join(keep)} FROM {table}").fetchall()))
    conn.close()
    return out


def export(fed, tmp_path, name="b.zip"):
    out = str(tmp_path / name)
    lifecycle.export_bundle(fed, out, member_zip=fake_zip)
    return out


def test_round_trip_restores_the_run_and_a_second_export_has_the_same_content(world, tmp_path):
    from y_web import db

    app, exps, tmp = world
    fed = service.create_federation("my world", list(exps.values()), owner="admin", seed=9, granularity="day",
                                    options={"crosspost": {"mode": "agent_action", "propensity": 0.25}}, exposures=True)
    run_data(fed)
    bundle, original_id, original_db = export(fed, tmp_path), fed.federation_id, logical(os.path.join(fed.folder, "federation.db"))
    service.delete_federation(fed)
    new, report = lifecycle.import_bundle(bundle, owner="admin", member_import=stub_import)
    assert report == {"restored_database": True, "federation_id_kept": True, "notes": []}
    assert new.federation_id == original_id and new.name == "my world" and new.status == "stopped"
    assert new.seed == 9 and new.granularity == "day" and json.loads(new.config_json)["exposures"] is True
    assert logical(os.path.join(new.folder, "federation.db")) == original_db
    exp_ids = {row.member: str(exp.idexp) for row, exp in service.members_of(new)}
    conn = sqlite3.connect(os.path.join(new.folder, "federation.db"))
    assert dict(conn.execute("SELECT member, exp_id FROM federation_member")) == exp_ids
    conn.close()
    again = json.loads(zipfile.ZipFile(export(new, tmp_path, "c.zip")).read("world_simulation.json"))
    first = json.loads(zipfile.ZipFile(bundle).read("world_simulation.json"))
    for data in (again, first):
        for member in data["members"]:
            member.pop("exp_name")
        data.pop("files")
    assert again == first
    config = json.loads(open(os.path.join(new.folder, "federation.json")).read())
    assert config["federation_id"] == int(original_id) and config["seed"] == 9
    assert oct(os.stat(os.path.join(new.folder, "federation.token")).st_mode & 0o777) == "0o600"


def test_the_id_in_use_means_a_fresh_start_with_a_note(world, tmp_path):
    app, exps, tmp = world
    fed = service.create_federation("w", list(exps.values()), owner="admin")
    run_data(fed)
    bundle = export(fed, tmp_path)
    # the original is still there, so its experiments belong to it: import copies of them under the same population
    service.delete_federation(fed)
    other = service.create_federation("squatter", list(exps.values()), owner="admin")
    other.federation_id = fed.federation_id
    from y_web import db

    db.session.commit()
    new, report = lifecycle.import_bundle(bundle, owner="admin", name="again", member_import=stub_import)
    assert report["federation_id_kept"] is False and report["restored_database"] is False and report["notes"]
    assert not os.path.exists(os.path.join(new.folder, "federation.db")) and new.name == "again"


def test_a_different_set_of_agents_means_a_fresh_start(world, tmp_path):
    from y_web import db
    from y_web.src.models.admin import FederationIdentityLink

    app, exps, tmp = world
    fed = service.create_federation("w", list(exps.values()), owner="admin")
    run_data(fed)
    bundle = export(fed, tmp_path)
    service.delete_federation(fed)
    conn = sqlite3.connect(os.path.join(tmp_path, "tweak.db"))
    conn.close()
    with zipfile.ZipFile(bundle) as z:
        files = {n: z.read(n) for n in z.namelist()}
    stored = tmp_path / "x.db"
    stored.write_bytes(files["federation.db"])
    c = sqlite3.connect(stored)
    c.execute("UPDATE federation_identity SET global_agent_id='9999' WHERE rowid=1")  # an agent the experiments do not have
    c.commit()
    c.close()
    import hashlib

    files["federation.db"] = stored.read_bytes()
    manifest = json.loads(files["world_simulation.json"])
    manifest["files"]["federation.db"] = hashlib.sha256(files["federation.db"]).hexdigest()
    files["world_simulation.json"] = json.dumps(manifest).encode()
    changed = tmp_path / "changed.zip"
    with zipfile.ZipFile(changed, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    new, report = lifecycle.import_bundle(str(changed), owner="admin", member_import=stub_import)
    assert report["federation_id_kept"] is True and report["restored_database"] is False and report["notes"]


def test_damaged_or_foreign_bundles_are_refused_before_anything_is_created(world, tmp_path):
    from y_web.src.models.admin import Exps, Federation

    app, exps, tmp = world
    fed = service.create_federation("w", list(exps.values()), owner="admin")
    run_data(fed)
    bundle = export(fed, tmp_path)
    service.delete_federation(fed)
    before = Exps.query.count()
    damaged = tmp_path / "damaged.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(damaged, "w") as dst:
        for n in src.namelist():
            dst.writestr(n, src.read(n) + (b"x" if n == "federation.db" else b""))
    for bad in (str(damaged), str(tmp_path / "missing.zip")):
        with pytest.raises(WorldSimulationError) as caught:
            lifecycle.import_bundle(bad, member_import=stub_import)
        assert caught.value.codes == ["bundle"]
    notzip = tmp_path / "x.zip"
    notzip.write_text("hello")
    with pytest.raises(WorldSimulationError):
        lifecycle.import_bundle(str(notzip), member_import=stub_import)
    wrong = tmp_path / "version.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(wrong, "w") as dst:
        for n in src.namelist():
            body = src.read(n)
            if n == "world_simulation.json":
                body = json.dumps({**json.loads(body), "bundle_version": 99}).encode()
            dst.writestr(n, body)
    with pytest.raises(WorldSimulationError):
        lifecycle.import_bundle(str(wrong), member_import=stub_import)
    assert Exps.query.count() == before and Federation.query.count() == 0


def test_a_member_of_another_platform_is_refused(world, tmp_path):
    app, exps, tmp = world
    fed = service.create_federation("w", list(exps.values()), owner="admin")
    bundle = export(fed, tmp_path)
    service.delete_federation(fed)

    def wrong(archive, name):
        exp = stub_import(archive, name)
        exp.platform_type = "dating"
        return exp

    with pytest.raises(WorldSimulationError) as caught:
        lifecycle.import_bundle(bundle, member_import=wrong)
    assert caught.value.codes == ["platform"]


def test_the_default_import_posts_the_archive_to_the_upload_route_as_the_same_user(site):
    from flask import Blueprint, request, session

    from y_web import db
    from y_web.src.models.admin import Exps

    app, exps, tmp = site
    seen = {}
    bp = Blueprint("fake_upload", __name__)

    @bp.route("/admin/upload_experiment", methods=["POST"])
    def upload():
        seen["user"] = session.get("_user_id")
        seen["name"] = request.form["exp_name"]
        seen["entries"] = zipfile.ZipFile(io.BytesIO(request.files["experiment"].read())).namelist()
        db.session.add(Exps(platform_type="forum", exp_name=request.form["exp_name"], db_name="x", owner="admin", exp_descr="",
                            status=0, running=0, port=5000, simulator_type="Standard", exp_status="stopped"))
        db.session.commit()
        return "ok"

    app.register_blueprint(bp)
    archive = tmp / "member.zip"
    fake_zip(1, str(archive))

    @app.route("/probe")
    def probe():
        return str(lifecycle._default_member_import(str(archive), "imported one").idexp)

    client = login(app, "admin")
    assert client.get("/probe").status_code == 200
    assert seen["name"] == "imported one" and seen["entries"] == ["experiment.txt"] and seen["user"]


def test_the_import_route_and_its_form(site, monkeypatch):
    from y_web.src.models.admin import Federation

    app, exps, tmp = site
    monkeypatch.setattr(lifecycle, "_default_member_import", stub_import)
    fed = service.create_federation("W", list(exps.values()), owner="admin", seed=3)
    run_data(fed)
    bundle = export(fed, tmp)
    service.delete_federation(fed)
    client = login(app, "admin")
    assert f"{BASE}/import" in client.get(BASE).get_data(as_text=True)
    res = client.post(f"{BASE}/import", data={"bundle": (open(bundle, "rb"), "b.zip"), "name": "Back"}, content_type="multipart/form-data")
    assert res.status_code == 302
    new = Federation.query.filter_by(name="Back").one()
    assert res.headers["Location"].endswith(f"{BASE}/{new.id}") and new.seed == 3
    assert client.post(f"{BASE}/import", data={}).status_code == 302  # no file: back to the list
    junk = client.post(f"{BASE}/import", data={"bundle": (io.BytesIO(b"junk"), "j.zip")}, content_type="multipart/form-data")
    assert junk.status_code == 302 and Federation.query.count() == 1
    assert login(app, "teacher").post(f"{BASE}/import").status_code == 302


def arrival_independent(content):
    """Which member finishes last is the arrival order of two processes, not an outcome of the simulation: the 'finished'
    events keep their ticks (one before the end, one at the end) and lose the member."""
    out = dict(content)
    out["federation_event"] = sorted(re.sub(r'\{"member": "[^"]*"\}', "{}", row) if "'finished'" in row else row
                                     for row in content["federation_event"])
    return out


def run_coordinator(fed, workdir, ticks=30):
    """Run the coordinator of this World Simulation with two stand-in members (no runtime, no model) and return its database."""
    sdk = Path(__file__).resolve().parents[2] / "external" / "YFederation"
    if str(sdk) not in sys.path:
        sys.path.insert(0, str(sdk))
    pytest.importorskip("flask")
    from tools.launch_local import launch

    workdir.mkdir()
    config = json.loads(open(os.path.join(fed.folder, "federation.json")).read())
    for member in config["members"]:
        member["launch"] = {"client": [sys.executable, str(sdk / "tests" / "fake_member.py"), "--ticks", str(ticks)]}
    (workdir / "federation.json").write_text(json.dumps(config))
    shutil.copyfile(os.path.join(fed.folder, "federation.token"), workdir / "federation.token")
    assert launch(workdir / "federation.json", workdir / "logs", timeout=120) == 0
    return str(workdir / "federation.db")


def test_the_imported_world_simulation_runs_to_the_same_coordinator_database(world, tmp_path):
    """Export -> import -> run: the original and the imported World Simulation, run with the same stand-in members, end with the
    same coordinator database (events, messages, identity, attention, ... without clock values and experiment ids)."""
    app, exps, tmp = world
    options = {"attention": {"enabled": True}, "crosspost": {"mode": "coordinator_rule", "probability": {"microblogging->forum": 1.0}}}
    fed = service.create_federation("rt", list(exps.values()), owner="admin", seed=21, options=options)
    bundle = export(fed, tmp_path)
    first = arrival_independent(logical(run_coordinator(fed, tmp_path / "run_a")))
    service.delete_federation(fed)
    new, report = lifecycle.import_bundle(bundle, owner="admin", member_import=stub_import)
    assert report["federation_id_kept"] is True
    second = arrival_independent(logical(run_coordinator(new, tmp_path / "run_b")))
    assert first == second
    assert first["federation_event"] and first["federation_identity"] and len(first["federation_member"]) == 2


def test_the_comparison_of_runs_can_tell_two_configurations_apart(world, tmp_path):
    """Control of the test above: another seed or other options do give another coordinator database."""
    app, exps, tmp = world
    a = service.create_federation("a", list(exps.values()), owner="admin", seed=21, options={"attention": {"enabled": True}})
    base = logical(run_coordinator(a, tmp_path / "a"))
    service.delete_federation(a)
    b = service.create_federation("b", list(exps.values()), owner="admin", seed=22, options={"attention": {"enabled": True}})
    other_seed = logical(run_coordinator(b, tmp_path / "b"))
    service.delete_federation(b)
    c = service.create_federation("c", list(exps.values()), owner="admin", seed=21, granularity="day")
    other_granularity = logical(run_coordinator(c, tmp_path / "c"))
    assert base != other_seed or base != other_granularity
