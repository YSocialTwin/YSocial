"""The sampler finds the activity profile of an agent even when its population lists none (merged populations)."""


def test_a_population_without_activity_profiles_still_samples_its_agents(app):
    """A merged population has no activity-profile rows: the agents' own profile (by name or by id) must be used,
    otherwise no agent is sampled in any hour and the simulation stays silent."""
    from types import SimpleNamespace

    from y_web import db
    from y_web.src.models import ActivityProfile, Population
    from y_web.src.simulation.agent_sampler import get_users_per_hour

    with app.app_context():
        profile = ActivityProfile(
            name="Always On Test", hours=",".join(str(h) for h in range(24))
        )
        pop = Population(name="merged", descr="")
        db.session.add_all([profile, pop])
        db.session.commit()
        by_name = SimpleNamespace(
            name="a", activity_profile="Always On Test", is_page=0
        )
        by_id = SimpleNamespace(name="b", activity_profile=profile.id, is_page=0)
        unknown = SimpleNamespace(
            name="c", activity_profile="No such profile", is_page=0
        )
        hours = get_users_per_hour(pop, [by_name, by_id, unknown], db.session)
        assert all(by_name in hours[h] and by_id in hours[h] for h in range(24))
        assert all(unknown not in hours[h] for h in range(24))


def test_merging_populations_keeps_every_field_of_the_agents_and_the_profiles_of_the_population(
    app, monkeypatch
):
    """The merge links the very same agents (so their custom features, prompts and profiles stay), keeps the kind of
    the sources, and gives the new population the activity profiles its agents follow.
    """
    from types import SimpleNamespace

    from y_web import db
    from y_web.routes.admin.sub import populations as mod
    from y_web.src.models import (
        ActivityProfile,
        Agent,
        Agent_Custom_Feature,
        Agent_Population,
        Population,
        PopulationActivityProfile,
    )

    monkeypatch.setattr(mod, "check_privileges", lambda *_: None)
    monkeypatch.setattr(mod, "current_user", SimpleNamespace(username="admin", id=1))
    monkeypatch.setattr(mod, "ensure_population_username_type_column", lambda: None)
    monkeypatch.setattr(mod, "flash", lambda *a, **k: None)
    monkeypatch.setattr(mod, "populations", lambda: "ok")
    with app.app_context():
        always = ActivityProfile(
            name="AlwaysM", hours=",".join(str(h) for h in range(24))
        )
        night = ActivityProfile(name="NightM", hours="22,23,0,1")
        db.session.add_all([always, night])
        pops = [
            Population(name=f"src{i}", descr="", pop_type="custom", size=2)
            for i in range(2)
        ]
        db.session.add_all(pops)
        db.session.commit()
        agents = []
        for i, (pop, prof) in enumerate(
            [(pops[0], always), (pops[0], always), (pops[1], night), (pops[1], always)]
        ):
            a = Agent(
                name=f"m{i}",
                ag_type="llama",
                age=30,
                gender="female",
                activity_profile=prof.name,
            )
            db.session.add(a)
            db.session.commit()
            db.session.add(Agent_Population(agent_id=a.id, population_id=pop.id))
            db.session.add(
                Agent_Custom_Feature(
                    agent_id=a.id,
                    feature_type="custom",
                    key="appearance.hair_color",
                    value=f"c{i}",
                )
            )
            agents.append(a)
        db.session.commit()
        ids = ",".join(str(p.id) for p in pops)
        with app.test_request_context(
            "/admin/merge_populations",
            method="POST",
            data={"merged_population_name": "merged", "selected_population_ids": ids},
        ):
            assert mod.merge_populations.__wrapped__() == "ok"
        merged = db.session.query(Population).filter_by(name="merged").one()
        linked = {
            r.agent_id
            for r in db.session.query(Agent_Population).filter_by(
                population_id=merged.id
            )
        }
        assert linked == {a.id for a in agents} and merged.size == 4
        assert merged.pop_type == "custom"
        # custom features live on the shared agents: nothing is lost
        kept = {
            r.value
            for r in db.session.query(Agent_Custom_Feature).filter(
                Agent_Custom_Feature.agent_id.in_(linked)
            )
        }
        assert kept == {"c0", "c1", "c2", "c3"}
        shares = {
            r.activity_profile: r.percentage
            for r in db.session.query(PopulationActivityProfile).filter_by(
                population=merged.id
            )
        }
        assert shares == {always.id: 75.0, night.id: 25.0}
