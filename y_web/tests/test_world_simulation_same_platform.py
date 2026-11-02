"""P15: a World Simulation may contain several experiments of the same platform type.

Two microblogging experiments ("Alpha", "Beta") and one forum ("Agora") in one World Simulation: member names, identities,
bindings files, the configuration files, the probability matrix and the creation form. A world with one member per platform type
must be written exactly as before (member named after its type, no `name` field)."""

import json
import re
from pathlib import Path

import pytest

from y_web.src.federation import service
from y_web.src.federation.service import MemberInfo, WorldSimulationError, member_names, validate_members
from y_web.tests.test_world_simulation_ui import _post, login, site  # noqa: F401  (fixture)

LAYOUT = (("microblogging", "Alpha"), ("microblogging", "Beta"), ("forum", "Agora"))


@pytest.fixture
def world(app, tmp_path, monkeypatch):  # overrides the two-experiment fixture used by `site`
    from y_web import db
    from y_web.src.experiment import helpers
    from y_web.src.models.admin import Agent, Agent_Population, Exps, Population, Population_Experiment

    monkeypatch.setattr(helpers, "BASE_DIR", tmp_path)
    monkeypatch.setattr(service, "experiment_db_uri", lambda exp: f"sqlite:///{tmp_path}/{exp.exp_name}.db")
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
        for platform, name in LAYOUT:
            exp = Exps(platform_type=platform, exp_name=name, db_name=f"experiments/{name}/db.db", owner="admin", exp_descr="", status=0,
                       running=0, port=5000, simulator_type="Standard", exp_status="stopped")
            db.session.add(exp)
            db.session.flush()
            db.session.add(Population_Experiment(id_population=pop.id, id_exp=exp.idexp))
            folder = tmp_path / "experiments" / name
            folder.mkdir(parents=True)
            (folder / "config_server.json").write_text(json.dumps({"name": name, "clock": {"mode": "simulated", "feed_refresh": "hourly"}}))
            (folder / "client_x.json").write_text(json.dumps({"simulation": {}}))
            exps[name] = exp.idexp
        db.session.commit()
        yield app, exps, tmp_path


def info(platform, exp_id, **kw):
    return MemberInfo(exp_id=exp_id, exp_name=f"e{exp_id}", platform_type=platform, simulator_type="Standard",
                      population_ids=frozenset({1}), **kw)


# ------------------------------------------------------------------------------------------------ naming
def test_member_names_keep_a_unique_type_and_qualify_a_repeated_one():
    from types import SimpleNamespace as NS

    exps = [NS(idexp=3, platform_type="microblogging"), NS(idexp=9, platform_type="forum"), NS(idexp=5, platform_type="microblogging")]
    assert member_names(exps) == {3: "microblogging-3", 9: "forum", 5: "microblogging-5"}
    assert member_names(exps[:2]) == {3: "microblogging", 9: "forum"}  # one member per type: named as before
    assert member_names(list(reversed(exps))) == member_names(exps)  # does not depend on the order of the selection
    assert not service.has_repeated_platform([NS(platform_type="forum"), NS(platform_type="dating")])
    assert service.has_repeated_platform([NS(platform_type="forum"), NS(platform_type="forum")])


def test_member_names_are_filename_safe_unique_and_free_of_separators():
    from types import SimpleNamespace as NS

    exps = [NS(idexp=i, platform_type=t) for i, t in enumerate(
        ("photo_sharing", "photo_sharing", "instant_messaging", "instant_messaging", "dating", "forum", "microblogging", "microblogging"), 1)]
    names = list(member_names(exps).values())
    assert len(set(names)) == len(names)
    for name in names:
        assert re.fullmatch(r"[a-z]+(?:_[a-z]+)*(?:-\d+)?", name) and ":" not in name and "/" not in name and "__" not in name
        assert len(name) <= 50  # FederationMember.member


def test_validation_accepts_repeated_types_up_to_eight():
    assert validate_members([info("microblogging", 1), info("microblogging", 2), info("forum", 3)]) == []
    assert validate_members([info("microblogging", i) for i in range(1, 9)]) == []
    assert {e["code"] for e in validate_members([info("microblogging", i) for i in range(1, 10)])} == {"member_count"}


# ------------------------------------------------------------------------------------------------ creation
def test_two_microblogging_members_and_a_forum_are_created(world):
    from y_web.src.models.admin import FederationIdentityLink, FederationMember

    app, exps, tmp = world
    fed = service.create_federation("three", list(exps.values()), seed=4, options={"provisioning": {"members": ["microblogging"]}})
    a, b, f = exps["Alpha"], exps["Beta"], exps["Agora"]
    rows = {(m.member, m.platform_type, m.exp_id) for m in FederationMember.query.filter_by(federation_pk=fed.id)}
    assert rows == {(f"microblogging-{a}", "microblogging", a), (f"microblogging-{b}", "microblogging", b), ("forum", "forum", f)}
    config = json.loads(Path(fed.folder, "federation.json").read_text())
    assert [(m["member"], m["platform"], m["name"]) for m in config["members"]] == [  # by platform type, then experiment id
        ("forum", "forum", "Agora"), (f"microblogging-{a}", "microblogging", "Alpha"), (f"microblogging-{b}", "microblogging", "Beta")]
    assert [m.get("provision") for m in config["members"]] == [None, True, True]  # a platform type provisions all its members
    # the same agents have one identity on each member, even on the two of one type
    links = FederationIdentityLink.query.filter_by(federation_pk=fed.id).all()
    assert len(links) == 9 and {l.member for l in links} == {f"microblogging-{a}", f"microblogging-{b}", "forum"}
    assert {(l.global_agent_id, l.member): l.username for l in links}[(links[0].global_agent_id, f"microblogging-{a}")] == \
        {(l.global_agent_id, l.member): l.username for l in links}[(links[0].global_agent_id, f"microblogging-{b}")]
    assert len([i for i in config["identity"] if i["member"] == f"microblogging-{b}"]) == 3
    # YWeb defaults: every ordered pair of members, including the two of one type, at 0.3 (keys are member names)
    probability = config["crosspost"]["probability"]
    assert len(probability) == 6 and set(probability.values()) == {0.3}
    assert f"microblogging-{a}->microblogging-{b}" in probability and f"microblogging-{b}->microblogging-{a}" in probability
    assert f"forum->microblogging-{a}" in probability and f"microblogging-{b}->forum" in probability


def test_member_sections_name_the_member_and_use_one_bindings_file_each(world):
    app, exps, tmp = world
    fed = service.create_federation("three", list(exps.values()), options={"provisioning": {"members": ["microblogging"]}})
    sections = {row.member: service.member_section(fed, row, exp) for row, exp in service.members_of(fed)}
    assert set(sections) == {f"microblogging-{exps['Alpha']}", f"microblogging-{exps['Beta']}", "forum"}
    files = [s["bindings_file"] for s in sections.values()]
    assert len(set(files)) == 3 and all(Path(f).name == f"bindings_{m}.db" for m, f in zip(sections, files))
    assert sorted(s["name"] for s in sections.values()) == ["Agora", "Alpha", "Beta"]
    assert all(s["member"] == m and s["exp_id"] == str(exps[s["name"]]) for m, s in sections.items())
    assert sections[f"microblogging-{exps['Alpha']}"]["provision"] is True and "provision" not in sections["forum"]
    service.write_member_configs(fed)
    for name in ("Alpha", "Beta", "Agora"):
        written = json.loads((tmp / "experiments" / name / "config_server.json").read_text())["federation"]
        assert written["name"] == name


def test_a_world_with_one_member_per_type_is_written_exactly_as_before(world):
    """Regression: member named after the platform type, no `name`, no change in the keys of the member entries."""
    app, exps, tmp = world
    fed = service.create_federation("two", [exps["Alpha"], exps["Agora"]], seed=9)
    text = Path(fed.folder, "federation.json").read_text()
    config = json.loads(text)
    assert [list(m) for m in config["members"]] == [["member", "exp_id", "platform", "db_uri"]] * 2
    assert [(m["member"], m["platform"]) for m in config["members"]] == [("forum", "forum"), ("microblogging", "microblogging")]
    assert set(config["crosspost"]["probability"]) == {"microblogging->forum", "forum->microblogging"}
    assert '"name"' not in text.split('"identity"')[0]
    for row, exp in service.members_of(fed):
        assert "name" not in service.member_section(fed, row, exp)
    # the order of the keys of the file is the one of the code before P15
    assert list(config) == ["federation_id", "seed", "granularity", "protocol", "members", "identity", "crosspost"]


def test_the_same_experiment_twice_creates_nothing(world):
    from y_web.src.models.admin import Federation

    app, exps, tmp = world
    # the ids are de-duplicated before the check: two microblogging members need two different experiments
    with pytest.raises(WorldSimulationError) as caught:
        service.create_federation("x", [exps["Alpha"], exps["Alpha"]])
    assert caught.value.codes == ["member_count"] and Federation.query.count() == 0


# ------------------------------------------------------------------------------------------------ interface
def test_the_creation_form_offers_every_experiment_and_creates_the_world(site):
    from y_web.src.models.admin import Federation

    app, exps, tmp = site
    a, b, f = exps["Alpha"], exps["Beta"], exps["Agora"]
    client = login(app, "admin")
    page = client.get("/admin/world_simulation/new").get_data(as_text=True)
    for key in (f"microblogging-{a}", f"microblogging-{b}", f"forum-{f}"):  # one row and one column per candidate experiment
        assert f'data-platform="{key}"' in page
    assert f'name="prob__microblogging-{a}__microblogging-{b}"' in page and f'name="membership_p__microblogging-{b}"' in page
    assert ">Alpha<" in page and ">Beta<" in page  # the matrix is labelled with the experiment names
    response = _post(client, "/admin/world_simulation/new", name="W3", experiments=[str(a), str(b), str(f)], seed="3", granularity="slot",
                     **{f"prob__microblogging-{a}__microblogging-{b}": "0.9", f"prob__forum-{f}__microblogging-{a}": "0.1",
                        f"prob__microblogging-{b}__forum-{f}": "0", "membership_initial": "custom",
                        f"membership_p__microblogging-{a}": "1", f"membership_p__forum-{f}": "0.5"})
    assert response.status_code == 302
    fed = Federation.query.one()
    options = json.loads(fed.config_json)
    # the fields of the candidates became the member names of the world (the forum is the only one of its type: named `forum`)
    assert options["crosspost"]["probability"] == {f"microblogging-{a}->microblogging-{b}": 0.9, f"forum->microblogging-{a}": 0.1,
                                                   f"microblogging-{b}->forum": 0.0}
    assert options["membership"]["initial"] == {f"microblogging-{a}": 1.0, "forum": 0.5}
    detail = client.get(response.headers["Location"]).get_data(as_text=True)
    assert f'name="prob__microblogging-{a}__microblogging-{b}" value="0.9"' in detail and "Alpha" in detail and "Beta" in detail


def test_a_second_microblogging_experiment_can_be_ticked_next_to_the_first(site):
    app, exps, tmp = site
    js = (Path(__file__).resolve().parents[1] / "static" / "assets" / "js" / "admin-world-simulation.js").read_text()
    assert "o.dataset.platform === b.dataset.platform" not in js  # the script no longer unticks the other experiments of a type
    page = login(app, "admin").get("/admin/world_simulation/new").get_data(as_text=True)
    assert page.count('type="checkbox" name="experiments"') == 3 and page.count("disabled") >= 0
    assert "2 to 8 experiments chosen" in page


def test_the_detail_page_and_the_parameters_use_member_names(site):
    from y_web.src.models.admin import Federation

    app, exps, tmp = site
    a, b = exps["Alpha"], exps["Beta"]
    fed = service.create_federation("D", list(exps.values()), seed=1)
    from y_web import db

    db.session.commit()
    client = login(app, "admin")
    page = client.get(f"/admin/world_simulation/{fed.id}").get_data(as_text=True)
    assert f'name="prob__microblogging-{a}__microblogging-{b}"' in page and 'name="prob__forum__microblogging-' in page
    assert "<th>Alpha</th>" in page and "<th>Beta</th>" in page and "<th>Agora</th>" in page
    saved = _post(client, f"/admin/world_simulation/{fed.id}/configuration", seed="1", granularity="slot",
                  **{f"prob__microblogging-{b}__microblogging-{a}": "0.7", "prob__forum__microblogging-99": "0.5"})
    assert saved.status_code == 302
    stored = json.loads(Federation.query.one().config_json)
    assert stored["crosspost"]["probability"] == {f"microblogging-{b}->microblogging-{a}": 0.7}  # the field of a non-member is ignored
    config = json.loads(Path(Federation.query.one().folder, "federation.json").read_text())
    assert config["crosspost"]["probability"][f"microblogging-{b}->microblogging-{a}"] == 0.7
    assert config["crosspost"]["probability"][f"microblogging-{a}->microblogging-{b}"] == 0.3  # the default of the other direction


def test_labels_are_experiment_names_only_when_a_type_is_repeated(site):
    import importlib

    route = importlib.import_module("y_web.routes.admin.sub.world_simulation")

    app, exps, tmp = site
    repeated = service.create_federation("R", list(exps.values()))
    assert set(route._member_labels(repeated).values()) == {"Alpha", "Beta", "Agora"}
    service.delete_federation(repeated)
    single = service.create_federation("S", [exps["Alpha"], exps["Agora"]])
    assert set(route._member_labels(single).values()) == {"Microblogging", "Forum"}
