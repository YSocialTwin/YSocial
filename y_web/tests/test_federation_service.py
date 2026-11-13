"""World Simulation creation and validation (F5.2): one test per validation rule, then creation end to end."""

import json
import os

import pytest

from y_web.src.federation import service
from y_web.src.federation.service import (
    MemberInfo,
    WorldSimulationError,
    validate_members,
)
from y_web.tests._platform_repos import template_file

POP = frozenset({1})


def info(platform, exp_id=1, **kw):
    sim = kw.pop("simulator_type", "Standard" if platform == "forum" else "HPC")
    return MemberInfo(
        exp_id=exp_id,
        exp_name=f"e-{platform}",
        platform_type=platform,
        simulator_type=sim,
        population_ids=kw.pop("population_ids", POP),
        **kw,
    )


def good():
    return [info("microblogging", 1), info("forum", 2)]


def codes(infos):
    return {e["code"] for e in validate_members(infos)}


def test_a_valid_group_has_no_errors():
    assert validate_members(good()) == []
    assert (
        validate_members(
            [
                info(p, i)
                for i, p in enumerate(
                    (
                        "microblogging",
                        "forum",
                        "photo_sharing",
                        "instant_messaging",
                        "dating",
                    )
                )
            ]
        )
        == []
    )


def test_member_count():
    assert "member_count" in codes([info("microblogging")])
    nine = [
        info("microblogging", i) for i in range(9)
    ]  # P15: up to eight, several of the same platform type
    assert "member_count" in codes(nine)
    assert "member_count" not in codes(nine[:8])


def test_experiments_must_be_stopped():
    assert "experiment_running" in codes(
        [info("microblogging", running=True), info("forum")]
    )


def test_remote_experiments_are_refused():
    assert "remote" in codes([info("microblogging", is_remote=True), info("forum")])


def test_populations_may_differ_but_not_all_be_empty():
    """INV-17: disjoint or partly overlapping populations are allowed; a member may start empty (clients can be added later)."""
    assert "population" not in codes(
        [info("microblogging"), info("forum", population_ids=frozenset({2}))]
    )
    assert "population" not in codes(
        [info("microblogging"), info("forum", population_ids=frozenset())]
    )
    assert "population" in codes(
        [
            info("microblogging", population_ids=frozenset()),
            info("forum", population_ids=frozenset()),
        ]
    )


def test_several_members_of_the_same_platform_type_are_allowed():
    """P15: the one-member-per-platform-type rule is gone; an experiment can still belong to one World Simulation only."""
    assert (
        validate_members(
            [info("microblogging", 1), info("microblogging", 2), info("forum", 3)]
        )
        == []
    )
    assert validate_members([info("forum", 1), info("forum", 2)]) == []
    assert "duplicate_platform" not in codes(
        [info("microblogging", 1), info("microblogging", 2)]
    )


def test_simulator_type_is_coherent_with_the_platform():
    assert "simulator_type" in codes(
        [info("forum", simulator_type="HPC"), info("microblogging")]
    )
    assert "simulator_type" in codes(
        [info("dating", simulator_type="Standard"), info("microblogging")]
    )
    # microblogging runs on both backends (D-06)
    assert (
        validate_members(
            [info("microblogging", simulator_type="Standard"), info("forum")]
        )
        == []
    )


def test_platform_must_support_federation():
    assert "platform" in codes([info("unknown_platform"), info("forum")])


def test_clock_must_be_simulated_with_24_slots():
    assert "clock" in codes(
        [info("microblogging", clock_mode="real_time"), info("forum")]
    )
    assert "clock" in codes(
        [info("microblogging", feed_refresh="daily"), info("forum")]
    )


def test_an_experiment_belongs_to_one_world_simulation():
    assert "already_member" in codes(
        [info("microblogging", other_federation="other"), info("forum")]
    )


def test_every_error_is_reported_at_once():
    found = codes(
        [
            info("microblogging", running=True, is_remote=True),
            info("microblogging", 2, clock_mode="real_time"),
        ]
    )
    assert {"experiment_running", "remote", "clock"} <= found


# ------------------------------------------------------------------------------------- creation with a database
@pytest.fixture
def world(app, tmp_path, monkeypatch):
    from y_web import db
    from y_web.src.experiment import helpers
    from y_web.src.models.admin import (
        Agent,
        Agent_Population,
        Exps,
        Population,
        Population_Experiment,
    )

    monkeypatch.setattr(helpers, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        service,
        "experiment_db_uri",
        lambda exp: f"sqlite:///{tmp_path}/{exp.platform_type}.db",
    )
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
        for platform, sim, cfg in (
            ("microblogging", "Standard", "config_server.json"),
            ("forum", "Standard", "config_server.json"),
        ):
            exp = Exps(
                platform_type=platform,
                exp_name=platform,
                db_name=f"experiments/{platform}/db.db",
                owner="admin",
                exp_descr="",
                status=0,
                running=0,
                port=5000,
                simulator_type=sim,
                exp_status="stopped",
            )
            db.session.add(exp)
            db.session.flush()
            db.session.add(
                Population_Experiment(id_population=pop.id, id_exp=exp.idexp)
            )
            folder = tmp_path / "experiments" / platform
            folder.mkdir(parents=True)
            (folder / cfg).write_text(
                json.dumps(
                    {
                        "name": platform,
                        "clock": {"mode": "simulated", "feed_refresh": "hourly"},
                    }
                )
            )
            (folder / f"client_x-{platform}.json").write_text(
                json.dumps({"simulation": {}})
            )
            exps[platform] = exp.idexp
        db.session.commit()
        yield app, exps, tmp_path


def test_create_writes_folder_token_configuration_and_rows(world):
    from y_web.src.models.admin import FederationIdentityLink, FederationMember

    app, exps, tmp = world
    fed = service.create_federation(
        "my world",
        list(exps.values()),
        owner="admin",
        seed=7,
        options={"attention": {"enabled": True}},
    )
    folder = tmp / "experiments" / "federations"
    assert (
        fed.folder.startswith(str(folder))
        and fed.seed == 7
        and fed.federation_id == str(fed.id)
    )
    config = json.loads(
        (
            os.path.join(fed.folder, "federation.json")
            and open(os.path.join(fed.folder, "federation.json"))
        ).read()
    )
    assert (
        config["seed"] == 7
        and config["federation_id"] == fed.id
        and config["attention"] == {"enabled": True}
    )
    assert {m["member"] for m in config["members"]} == {"microblogging", "forum"}
    assert len(config["identity"]) == 6  # 3 agents x 2 members
    token = os.path.join(fed.folder, "federation.token")
    assert oct(os.stat(token).st_mode & 0o777) == "0o600" and fed.token
    assert (
        FederationMember.query.count() == 2
        and FederationIdentityLink.query.count() == 6
    )
    for (
        platform
    ) in exps:  # member configurations are untouched until the World Simulation starts
        for name in ("config_server.json", f"client_x-{platform}.json"):
            assert "federation" not in json.loads(
                (tmp / "experiments" / platform / name).read_text()
            )
    written = service.write_member_configs(fed)
    assert len(written) == 4
    service.write_member_configs(fed)  # idempotent
    for platform in exps:
        for name in ("config_server.json", f"client_x-{platform}.json"):
            section = json.loads((tmp / "experiments" / platform / name).read_text())[
                "federation"
            ]
            assert (
                section["enabled"]
                and section["member"] == platform
                and section["federation_id"] == fed.id
            )
            assert section["coordinator_file"].endswith("federation_coordinator.json")
    assert len(service.remove_member_configs(fed)) == 4
    for platform in exps:
        assert "federation" not in json.loads(
            (tmp / "experiments" / platform / "config_server.json").read_text()
        )


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
        assert "federation" not in json.loads(
            (tmp / "experiments" / platform / "config_server.json").read_text()
        )


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


def test_member_sections_carry_the_crosspost_mode_and_the_agent_propensity(world):
    app, exps, tmp = world
    plain = service.create_federation("plain", list(exps.values()))
    assert (
        service.member_section(
            plain,
            plain.members[0] if hasattr(plain, "members") else _first_member(plain),
            _exp_of(plain),
        )["crosspost_mode"]
        == "coordinator_rule"
    )
    service.delete_federation(plain)
    fed = service.create_federation(
        "agents",
        list(exps.values()),
        seed=11,
        options={"crosspost": {"mode": "agent_action", "propensity": 0.25}},
    )
    service.write_member_configs(fed)
    for platform in exps:
        for name in ("config_server.json", f"client_x-{platform}.json"):
            section = json.loads((tmp / "experiments" / platform / name).read_text())[
                "federation"
            ]
            assert (
                section["crosspost_mode"] == "agent_action"
                and section["crosspost_propensity"] == 0.25
                and section["seed"] == 11
            )


def _first_member(fed):
    return service.members_of(fed)[0][0]


def _exp_of(fed):
    return service.members_of(fed)[0][1]


def test_world_simulation_of_an_experiment_and_its_lock(world):
    app, exps, tmp = world
    assert (
        service.world_simulation_of(exps["forum"]) is None
        and service.world_simulation_map() == {}
    )
    fed = service.create_federation("badge", list(exps.values()))
    found = service.world_simulation_of(exps["forum"])
    assert found == {
        "id": fed.id,
        "name": "badge",
        "status": "stopped",
        "locked": False,
    }
    assert set(service.world_simulation_map([exps["forum"]])) == {exps["forum"]}
    for status, locked in (
        ("starting", True),
        ("running", True),
        ("paused", True),
        ("stopping", True),
        ("stopped", False),
        ("completed", False),
        ("failed", False),
    ):
        fed.status = status
        assert service.world_simulation_of(exps["forum"])["locked"] is locked


def test_the_experiment_pages_show_the_badge_and_disable_the_member_commands():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("experiment_details.html", "experiment_details_forum.html"):
        text = template_file(root / "templates" / "admin", name).read_text()
        assert (
            "world_simulation_of(experiment.idexp)" in text
            and text.count("ws and ws.locked") == 2
        )
    assert (
        "world_simulation_locked"
        in (root / "static" / "assets" / "js" / "admin-settings.js").read_text()
    )
    assert "world_simulation_of" in (root / "__init__.py").read_text()


def test_member_sections_carry_the_topic_migration_switch_only_where_a_runtime_reads_it(
    world,
):
    """Topic migration is on by default; the forum reads `topic_migration`, an HPC microblogging `create_topics`."""
    app, exps, tmp = world
    on = service.create_federation("topics-on", list(exps.values()))
    by_platform = {
        row.platform_type: service.member_section(on, row, exp)
        for row, exp in service.members_of(on)
    }
    assert (
        by_platform["forum"]["topic_migration"] is True
        and "create_topics" not in by_platform["forum"]
    )
    assert (
        "topic_migration" not in by_platform["microblogging"]
        and "create_topics" not in by_platform["microblogging"]
    )  # Standard
    service.delete_federation(on)
    off = service.create_federation(
        "topics-off", list(exps.values()), options={"topics": {"migration": False}}
    )
    by_platform = {
        row.platform_type: service.member_section(off, row, exp)
        for row, exp in service.members_of(off)
    }
    assert by_platform["forum"]["topic_migration"] is False


def _use_population(exp_id, agent_names, new_agents=()):
    """Give the experiment a population made of existing agents (by name) and new ones; the old populations are detached."""
    from y_web import db
    from y_web.src.models.admin import (
        Agent,
        Agent_Population,
        Population,
        Population_Experiment,
    )

    Population_Experiment.query.filter_by(id_exp=exp_id).delete()
    pop = Population(
        name=f"p{exp_id}", descr="d", size=len(agent_names) + len(new_agents)
    )
    db.session.add(pop)
    db.session.flush()
    agents = [Agent.query.filter_by(name=n).first() for n in agent_names]
    for name in new_agents:
        agent = Agent(name=name)
        db.session.add(agent)
        db.session.flush()
        agents.append(agent)
    for agent in agents:
        db.session.add(Agent_Population(agent_id=agent.id, population_id=pop.id))
    db.session.add(Population_Experiment(id_population=pop.id, id_exp=exp_id))
    db.session.commit()
    return {a.name: a.id for a in agents}


def test_members_with_disjoint_and_overlapping_populations(world):
    """INV-17: each member declares the agents of its own populations by username; nothing carries a local id."""
    from y_web.src.models.admin import FederationIdentityLink

    app, exps, tmp = world
    ids = _use_population(exps["microblogging"], ["a0", "a1"])
    ids.update(
        _use_population(exps["forum"], ["a1"], new_agents=["z9"])
    )  # a1 on both, a0 only micro, z9 only forum
    fed = service.create_federation("flex", list(exps.values()), owner="admin")
    links = {
        (l.global_agent_id, l.member, l.username, l.local_account_id)
        for l in FederationIdentityLink.query.filter_by(federation_pk=fed.id)
    }
    assert links == {
        (str(ids["a0"]), "microblogging", "a0", ""),
        (str(ids["a1"]), "microblogging", "a1", ""),
        (str(ids["a1"]), "forum", "a1", ""),
        (str(ids["z9"]), "forum", "z9", ""),
    }
    config = service.build_federation_config(fed)
    assert {
        (r["global_agent_id"], r["member"], r["username"]) for r in config["identity"]
    } == {(g, m, u) for g, m, u, _ in links}
    assert all("local_account_id" not in r for r in config["identity"])


def test_a_member_may_start_without_agents_but_not_all_of_them(world):
    from y_web.src.models.admin import FederationIdentityLink, Population_Experiment

    app, exps, tmp = world
    Population_Experiment.query.filter_by(id_exp=exps["forum"]).delete()
    fed = service.create_federation(
        "late", list(exps.values()), owner="admin"
    )  # the forum gets its clients later
    assert {
        l.member for l in FederationIdentityLink.query.filter_by(federation_pk=fed.id)
    } == {"microblogging"}
    Population_Experiment.query.filter_by(id_exp=exps["microblogging"]).delete()
    with pytest.raises(service.WorldSimulationError) as e:
        service.create_federation("none", list(exps.values()), owner="admin")
    assert "population" in e.value.codes


def test_two_agents_with_the_same_name_on_one_member_are_refused(world):
    from y_web import db
    from y_web.src.models.admin import Agent, Agent_Population, Population_Experiment

    app, exps, tmp = world
    pop = (
        Population_Experiment.query.filter_by(id_exp=exps["forum"])
        .first()
        .id_population
    )
    twin = Agent(name="a0")  # same name as an agent of the population
    db.session.add(twin)
    db.session.flush()
    db.session.add(Agent_Population(agent_id=twin.id, population_id=pop))
    db.session.commit()
    with pytest.raises(service.WorldSimulationError) as e:
        service.create_federation("twins", list(exps.values()), owner="admin")
    assert "username" in e.value.codes


def test_links_of_older_releases_are_declared_by_name_not_by_local_id(world):
    """Before INV-17 a link carried local id = agent id, which no runtime guaranteed: the configuration now ignores it."""
    from y_web import db
    from y_web.src.models.admin import FederationIdentityLink

    app, exps, tmp = world
    fed = service.create_federation("old", list(exps.values()), owner="admin")
    for link in FederationIdentityLink.query.filter_by(federation_pk=fed.id):
        link.username, link.local_account_id = (
            None,
            link.global_agent_id,
        )  # as an old release wrote them
    db.session.commit()
    rows = service.build_federation_config(fed)["identity"]
    assert len(rows) == 6 and all(
        r["username"].startswith("a") and "local_account_id" not in r for r in rows
    )


# ------------------------------------------------------------------ INV-17/18/19: bindings, late populations, provisioning
def _sections(fed):
    return {
        row.member: service.member_section(fed, row, exp)
        for row, exp in service.members_of(fed)
    }


def test_member_sections_carry_a_bindings_file_and_provision_only_where_asked_and_supported(
    world,
):
    app, exps, tmp = world
    plain = service.create_federation("plain", list(exps.values()))
    for member, section in _sections(plain).items():
        assert (
            section["bindings_file"].endswith(f"bindings_{member}.db")
            and "provision" not in section
        )
    assert not any(
        "provision" in m
        for m in json.load(open(os.path.join(plain.folder, "federation.json")))[
            "members"
        ]
    )


def test_provisioning_is_local_to_yweb_and_honoured_by_every_platform_asked(
    world,
):
    app, exps, tmp = world
    fed = service.create_federation(
        "p",
        list(exps.values()),
        options={
            "discovery": {"enabled": True},
            "provisioning": {"members": ["microblogging", "forum"]},
        },
    )
    sections = _sections(fed)
    assert sections["microblogging"]["provision"] and sections["microblogging"]["adopt"]
    assert sections["forum"]["provision"] and sections["forum"]["adopt"]
    assert all(
        "provision" not in sections[m]
        for m in sections
        if m not in ("microblogging", "forum")
    )
    config = json.load(open(os.path.join(fed.folder, "federation.json")))
    assert "provisioning" not in config and config["discovery"] == {"enabled": True}
    assert sorted(m["member"] for m in config["members"] if m.get("provision")) == [
        "forum",
        "microblogging",
    ]


def test_a_population_added_to_a_running_world_simulation_is_declared_by_username(
    world, monkeypatch
):
    from y_web import db
    from y_web.src.federation import dynamic
    from y_web.src.models.admin import (
        Agent,
        Agent_Population,
        FederationIdentityLink,
        Population,
    )

    app, exps, tmp = world
    fed = service.create_federation("late", list(exps.values()))
    pop = Population(name="late pop", descr="", size=2)
    db.session.add(pop)
    db.session.flush()
    new = []
    for n in ("zed", "zoe"):
        a = Agent(name=n)
        db.session.add(a)
        db.session.flush()
        db.session.add(Agent_Population(agent_id=a.id, population_id=pop.id))
        new.append(a)
    db.session.commit()
    sent = []

    class Fake:
        def declare_expected(self, identities):
            sent.append(identities)

    monkeypatch.setattr(dynamic, "_coordinator_client", lambda fed, member: Fake())
    assert dynamic.population_added(exps["forum"], pop.id)[0][1] == [
        "zed",
        "zoe",
    ]  # stopped: recorded, nothing sent
    assert sent == []
    assert (
        FederationIdentityLink.query.filter_by(
            federation_pk=fed.id, member="forum"
        ).count()
        == 5
    )
    config = json.load(open(os.path.join(fed.folder, "federation.json")))
    assert {i["username"] for i in config["identity"] if i["member"] == "forum"} >= {
        "zed",
        "zoe",
    }
    assert dynamic.population_added(exps["forum"], pop.id) == []  # idempotent
    other = Population(name="other", descr="", size=1)
    db.session.add(other)
    db.session.flush()
    b = Agent(name="yan")
    db.session.add(b)
    db.session.flush()
    db.session.add(Agent_Population(agent_id=b.id, population_id=other.id))
    fed.status = "running"
    db.session.commit()
    dynamic.population_added(exps["microblogging"], other.id)
    assert sent == [[{"global_agent_id": str(b.id), "username": "yan", "name": "yan"}]]


def test_a_failing_coordinator_never_breaks_the_creation_of_a_client(
    world, monkeypatch
):
    from y_web import db
    from y_web.src.federation import dynamic
    from y_web.src.models.admin import Agent, Agent_Population, Population

    app, exps, tmp = world
    fed = service.create_federation("late", list(exps.values()))
    pop = Population(name="p2", descr="", size=1)
    db.session.add(pop)
    db.session.flush()
    a = Agent(name="kim")
    db.session.add(a)
    db.session.flush()
    db.session.add(Agent_Population(agent_id=a.id, population_id=pop.id))
    fed.status = "running"
    db.session.commit()

    def boom(fed, member):
        raise OSError("down")

    monkeypatch.setattr(dynamic, "_coordinator_client", boom)
    assert (
        dynamic.population_added(exps["forum"], pop.id) == []
    )  # swallowed, and nothing recorded ...
    from y_web.src.models.admin import FederationIdentityLink

    assert (
        FederationIdentityLink.query.filter_by(
            federation_pk=fed.id, member="forum"
        ).count()
        == 3
    )
    sent = []
    monkeypatch.setattr(
        dynamic,
        "_coordinator_client",
        lambda fed, member: type(
            "F", (), {"declare_expected": lambda self, i: sent.append(i)}
        )(),
    )
    assert (
        dynamic.population_added(exps["forum"], pop.id)[0][1] == ["kim"]
        and len(sent) == 1
    )  # ... so the next call declares it
    assert dynamic.population_added(99999, pop.id) == []  # not a member of anything


def test_member_sections_carry_the_decision_only_when_the_agent_decides(world):
    app, exps, tmp = world
    plain = service.create_federation(
        "rand",
        list(exps.values()),
        seed=5,
        options={"crosspost": {"mode": "agent_action", "decision": "random"}},
    )
    service.write_member_configs(plain)
    for platform in exps:
        section = json.loads(
            (tmp / "experiments" / platform / "config_server.json").read_text()
        )["federation"]
        assert not any(
            k.startswith("crosspost_decision") for k in section
        ), section  # the default is never written
    service.delete_federation(plain)
    fed = service.create_federation(
        "llm",
        list(exps.values()),
        seed=5,
        options={
            "crosspost": {
                "mode": "agent_action",
                "decision": "llm",
                "decision_triggers": ["interaction"],
                "decision_max_per_day": 3,
            }
        },
    )
    service.write_member_configs(fed)
    for platform in exps:
        for name in ("config_server.json", f"client_x-{platform}.json"):
            section = json.loads((tmp / "experiments" / platform / name).read_text())[
                "federation"
            ]
            assert section["crosspost_decision"] == "llm" and section[
                "crosspost_decision_triggers"
            ] == ["interaction"]
            assert (
                section["crosspost_decision_max_per_day"] == 3
                and section["crosspost_mode"] == "agent_action"
            )
    service.delete_federation(fed)
    minimal = service.create_federation(
        "llm2", list(exps.values()), seed=5, options={"crosspost": {"decision": "llm"}}
    )
    service.write_member_configs(minimal)
    section = json.loads(
        (tmp / "experiments" / next(iter(exps)) / "config_server.json").read_text()
    )["federation"]
    assert (
        section["crosspost_decision"] == "llm"
        and "crosspost_decision_triggers" not in section
        and "crosspost_decision_max_per_day" not in section
    )
    # the coordinator receives the keys in its crosspost block and accepts them
    config = service.build_federation_config(minimal)
    assert config["crosspost"]["decision"] == "llm"
    policy = pytest.importorskip("ysocial_federation.decision_policy")
    assert policy.normalize(config["crosspost"])["decision"] == "llm"


def test_a_platform_without_support_does_not_get_the_decision(world, monkeypatch):
    from y_web.src.federation import options_schema as schema

    app, exps, tmp = world
    monkeypatch.setattr(schema, "LLM_DECISION_SUPPORT", {})
    fed = service.create_federation(
        "nosupport",
        list(exps.values()),
        seed=5,
        options={"crosspost": {"decision": "llm"}},
    )
    service.write_member_configs(fed)
    for platform in exps:
        section = json.loads(
            (tmp / "experiments" / platform / "config_server.json").read_text()
        )["federation"]
        assert "crosspost_decision" not in section
