"""World Simulation creation and validation (F5.2): one test per validation rule, then creation end to end."""

import json
import os

import pytest

from y_web.src.federation import service
from y_web.src.federation.service import MemberInfo, WorldSimulationError, validate_members

POP = frozenset({1})


def info(platform, exp_id=1, **kw):
    sim = kw.pop("simulator_type", "Standard" if platform == "forum" else "HPC")
    return MemberInfo(exp_id=exp_id, exp_name=f"e-{platform}", platform_type=platform, simulator_type=sim,
                      population_ids=kw.pop("population_ids", POP), **kw)


def good():
    return [info("microblogging", 1), info("forum", 2)]


def codes(infos):
    return {e["code"] for e in validate_members(infos)}


def test_a_valid_group_has_no_errors():
    assert validate_members(good()) == []
    assert validate_members([info(p, i) for i, p in enumerate(
        ("microblogging", "forum", "photo_sharing", "instant_messaging", "dating"))]) == []


def test_member_count():
    assert "member_count" in codes([info("microblogging")])
    six = [info(p, i) for i, p in enumerate(("microblogging", "forum", "photo_sharing", "instant_messaging", "dating", "x"))]
    assert "member_count" in codes(six)


def test_experiments_must_be_stopped():
    assert "experiment_running" in codes([info("microblogging", running=True), info("forum")])


def test_remote_experiments_are_refused():
    assert "remote" in codes([info("microblogging", is_remote=True), info("forum")])


def test_same_population():
    assert "population" in codes([info("microblogging"), info("forum", population_ids=frozenset({2}))])
    assert "population" in codes([info("microblogging", population_ids=frozenset()), info("forum", population_ids=frozenset())])


def test_one_member_per_platform_type():
    assert "duplicate_platform" in codes([info("microblogging", 1), info("microblogging", 2)])


def test_simulator_type_is_coherent_with_the_platform():
    assert "simulator_type" in codes([info("forum", simulator_type="HPC"), info("microblogging")])
    assert "simulator_type" in codes([info("dating", simulator_type="Standard"), info("microblogging")])
    # microblogging runs on both backends (D-06)
    assert validate_members([info("microblogging", simulator_type="Standard"), info("forum")]) == []


def test_platform_must_support_federation():
    assert "platform" in codes([info("unknown_platform"), info("forum")])


def test_clock_must_be_simulated_with_24_slots():
    assert "clock" in codes([info("microblogging", clock_mode="real_time"), info("forum")])
    assert "clock" in codes([info("microblogging", feed_refresh="daily"), info("forum")])


def test_an_experiment_belongs_to_one_world_simulation():
    assert "already_member" in codes([info("microblogging", other_federation="other"), info("forum")])


def test_every_error_is_reported_at_once():
    found = codes([info("microblogging", running=True, is_remote=True), info("microblogging", 2)])
    assert {"experiment_running", "remote", "duplicate_platform"} <= found


# ------------------------------------------------------------------------------------- creation with a database
@pytest.fixture
def world(app, tmp_path, monkeypatch):
    from y_web import db
    from y_web.src.experiment import helpers
    from y_web.src.models.admin import Agent, Agent_Population, Exps, Population, Population_Experiment

    monkeypatch.setattr(helpers, "BASE_DIR", tmp_path)
    monkeypatch.setattr(service, "experiment_db_uri", lambda exp: f"sqlite:///{tmp_path}/{exp.platform_type}.db")
    with app.app_context():
        pop = Population(name="p", descr="d", size=3)
        db.session.add(pop)
        db.session.flush()
        for n in range(3):
            agent = Agent(name=f"a{n}")
            db.session.add(agent)
            db.session.flush()
            db.session.add(Agent_Population(agent_id=agent.id, population_id=pop.id))
        exps = {}
        for platform, sim, cfg in (("microblogging", "Standard", "config_server.json"), ("forum", "Standard", "config_server.json")):
            exp = Exps(platform_type=platform, exp_name=platform, db_name=f"experiments/{platform}/db.db", owner="admin",
                       exp_descr="", status=0, running=0, port=5000, simulator_type=sim, exp_status="stopped")
            db.session.add(exp)
            db.session.flush()
            db.session.add(Population_Experiment(id_population=pop.id, id_exp=exp.idexp))
            folder = tmp_path / "experiments" / platform
            folder.mkdir(parents=True)
            (folder / cfg).write_text(json.dumps({"name": platform, "clock": {"mode": "simulated", "feed_refresh": "hourly"}}))
            (folder / f"client_x-{platform}.json").write_text(json.dumps({"simulation": {}}))
            exps[platform] = exp.idexp
        db.session.commit()
        yield app, exps, tmp_path


def test_create_writes_folder_token_configuration_and_rows(world):
    from y_web.src.models.admin import FederationIdentityLink, FederationMember

    app, exps, tmp = world
    fed = service.create_federation("my world", list(exps.values()), owner="admin", seed=7, options={"attention": {"enabled": True}})
    folder = tmp / "experiments" / "federations"
    assert fed.folder.startswith(str(folder)) and fed.seed == 7 and fed.federation_id == str(fed.id)
    config = json.loads((os.path.join(fed.folder, "federation.json") and open(os.path.join(fed.folder, "federation.json"))).read())
    assert config["seed"] == 7 and config["federation_id"] == fed.id and config["attention"] == {"enabled": True}
    assert {m["member"] for m in config["members"]} == {"microblogging", "forum"}
    assert len(config["identity"]) == 6  # 3 agents x 2 members
    token = os.path.join(fed.folder, "federation.token")
    assert oct(os.stat(token).st_mode & 0o777) == "0o600" and fed.token
    assert FederationMember.query.count() == 2 and FederationIdentityLink.query.count() == 6
    for platform in exps:  # member configurations are untouched until the World Simulation starts
        for name in ("config_server.json", f"client_x-{platform}.json"):
            assert "federation" not in json.loads((tmp / "experiments" / platform / name).read_text())
    written = service.write_member_configs(fed)
    assert len(written) == 4
    service.write_member_configs(fed)  # idempotent
    for platform in exps:
        for name in ("config_server.json", f"client_x-{platform}.json"):
            section = json.loads((tmp / "experiments" / platform / name).read_text())["federation"]
            assert section["enabled"] and section["member"] == platform and section["federation_id"] == fed.id
            assert section["coordinator_file"].endswith("federation_coordinator.json")
    assert len(service.remove_member_configs(fed)) == 4
    for platform in exps:
        assert "federation" not in json.loads((tmp / "experiments" / platform / "config_server.json").read_text())


def test_invalid_group_creates_nothing(world):
    from y_web.src.models.admin import Federation

    app, exps, tmp = world
    with pytest.raises(WorldSimulationError) as caught:
        service.create_federation("w", [exps["forum"]])
    assert caught.value.codes == ["member_count"]
    assert Federation.query.count() == 0
    assert not (tmp / "experiments" / "federations").exists()


def test_an_experiment_cannot_join_two_world_simulations(world):
    app, exps, tmp = world
    service.create_federation("one", list(exps.values()))
    with pytest.raises(WorldSimulationError) as caught:
        service.create_federation("two", list(exps.values()))
    assert "already_member" in caught.value.codes


def test_delete_restores_the_member_configuration(world):
    from y_web.src.models.admin import Federation

    app, exps, tmp = world
    fed = service.create_federation("one", list(exps.values()))
    service.write_member_configs(fed)
    service.delete_federation(fed)
    assert Federation.query.count() == 0
    for platform in exps:
        assert "federation" not in json.loads((tmp / "experiments" / platform / "config_server.json").read_text())


def test_running_world_simulation_cannot_be_deleted(world):
    app, exps, tmp = world
    fed = service.create_federation("one", list(exps.values()))
    fed.status = "running"
    with pytest.raises(WorldSimulationError):
        service.delete_federation(fed)


def test_unknown_parameter_block_and_bad_granularity_are_refused(world):
    app, exps, tmp = world
    with pytest.raises(WorldSimulationError):
        service.create_federation("w", list(exps.values()), options={"bogus": {}})
    with pytest.raises(WorldSimulationError):
        service.create_federation("w", list(exps.values()), granularity="hour")
    with pytest.raises(WorldSimulationError):
        service.create_federation("  ", list(exps.values()))
