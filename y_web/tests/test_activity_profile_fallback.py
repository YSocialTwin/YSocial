"""The sampler finds the activity profile of an agent even when its population lists none (merged populations)."""


def test_a_population_without_activity_profiles_still_samples_its_agents(app):
    """A merged population has no activity-profile rows: the agents' own profile (by name or by id) must be used,
    otherwise no agent is sampled in any hour and the simulation stays silent."""
    from types import SimpleNamespace

    from y_web import db
    from y_web.src.models import ActivityProfile, Population
    from y_web.src.simulation.agent_sampler import get_users_per_hour

    with app.app_context():
        profile = ActivityProfile(name="Always On Test", hours=",".join(str(h) for h in range(24)))
        pop = Population(name="merged", descr="")
        db.session.add_all([profile, pop])
        db.session.commit()
        by_name = SimpleNamespace(name="a", activity_profile="Always On Test", is_page=0)
        by_id = SimpleNamespace(name="b", activity_profile=profile.id, is_page=0)
        unknown = SimpleNamespace(name="c", activity_profile="No such profile", is_page=0)
        hours = get_users_per_hour(pop, [by_name, by_id, unknown], db.session)
        assert all(by_name in hours[h] and by_id in hours[h] for h in range(24))
        assert all(unknown not in hours[h] for h in range(24))
