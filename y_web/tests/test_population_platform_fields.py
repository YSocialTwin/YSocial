"""A population is not tied to a platform: dedicated custom fields are optional and added to the same agents."""

import pytest

from y_web.tests.test_dating_population import needs_runtime, routes  # noqa: F401

pytestmark = pytest.mark.integration


def _standard_population(db, n=8):
    from y_web.src.models import Agent, Agent_Population, Population

    row = Population(name="std", descr="", size=n, username_type="microblogging")
    db.session.add(row)
    db.session.commit()
    agents = []
    for i in range(n):
        agents.append(
            Agent(
                name=f"agent_{i}",
                age=22 + 3 * i,
                gender="male" if i % 2 else "female",
                language="en",
                nationality="Italian",
                education_level="bachelor",
                profession="engineer",
                leaning="center",
                daily_activity_level=1,
                oe="high", co="high", ex="low", ag="low", ne="low",
            )
        )  # fmt: skip
    db.session.add_all(agents)
    db.session.flush()
    for a in agents:
        db.session.add(Agent_Population(agent_id=a.id, population_id=row.id))
    db.session.commit()
    return row, agents


@needs_runtime
def test_a_standard_population_gets_dating_fields_and_keeps_its_own_demographics(app):
    from y_web import db
    from y_web.src.agents.platform import (
        population_matches_platform,
        population_platform_fields,
    )
    from y_web.src.dating import population as dp
    from y_web.src.models import Agent_Custom_Feature

    with app.app_context():
        row, agents = _standard_population(db)
        assert not dp.has_dating_fields(row) and population_platform_fields(row) == []
        before = [(a.name, a.age, a.gender, a.profession) for a in agents]

        assert dp.complete_population(row.id, seed=3) == 8
        assert dp.complete_population(row.id, seed=3) == 0  # nothing left to complete
        db.session.expire_all()

        assert [(a.name, a.age, a.gender, a.profession) for a in agents] == before
        assert dp.has_dating_fields(row) and "dating" in population_platform_fields(row)
        for a in agents:
            keys = {
                f.key
                for f in db.session.query(Agent_Custom_Feature).filter_by(agent_id=a.id)
                if f.feature_type == "custom"
            }
            assert any(k.startswith("dating.latent.") for k in keys)
            assert "dating.profile.city" in keys and "dating.id" not in keys
        # the document the runtime reads is valid, and the population is deployable anywhere
        assert dp.validate_population(dp.load_document(row.id)) == []
        for platform in ("microblogging", "forum", "photo_sharing", "instant_messaging", "dating"):
            assert population_matches_platform(row, platform)


@needs_runtime
def test_dating_fields_follow_the_gender_and_age_of_the_agent(app):
    from y_web import db
    from y_web.src.dating import population as dp

    with app.app_context():
        row, agents = _standard_population(db, n=6)
        dp.complete_population(row.id, seed=5)
        doc = {d["username"]: d for d in dp.load_document(row.id)["agents"]}
        assert {doc[a.name]["gender"] for a in agents if a.gender == "male"} == {"male"}
        assert all(doc[a.name]["age"] == a.age for a in agents)


@needs_runtime
def test_optional_sections_create_a_standard_population_with_the_fields_asked_for(
    app, routes, monkeypatch  # noqa: F811
):
    import json

    from y_web import db
    from y_web.src.agents.platform import population_platform_fields
    from y_web.src.models import Agent, Agent_Population, Population

    seen = {}

    def fake_generate(name, percentages, actions, backgrounds, photo_config):
        seen["photo"] = photo_config
        pop = db.session.query(Population).filter_by(name=name).one()
        for i in range(6):
            a = Agent(
                name=f"p_{i}", age=25 + i, gender="male" if i % 2 else "female",
                language="en", nationality="Italian", education_level="bachelor",
                profession="engineer", leaning="center", daily_activity_level=1,
            )  # fmt: skip
            db.session.add(a)
            db.session.flush()
            db.session.add(Agent_Population(agent_id=a.id, population_id=pop.id))
        db.session.commit()

    monkeypatch.setattr(routes.mod, "generate_population", fake_generate)
    monkeypatch.setattr(routes.mod, "_photo_sharing_available", lambda: True)
    monkeypatch.setattr("y_web.src.dating.population.runtime_available", lambda user=None: True)
    monkeypatch.setattr(routes.mod, "_dating_generator_config", lambda: {})
    monkeypatch.setattr(routes.mod, "populations", lambda: "listed")
    one = json.dumps({"1": 100})
    form = {
        "pop_name": "Both", "pop_descr": "", "n_agents": "6", "nationalities": "Italian", "languages": "Italian", "tags": "art", "male_percentage": "50", "female_percentage": "50",
        "age_classes": "1", "age_classes_percentages": one,
        "education_levels": "1", "education_levels_percentages": one,
        "political_leanings": "1", "political_leanings_percentages": one,
        "toxicity_levels": "1", "toxicity_levels_percentages": one,
        "include_photo_sharing": "1", "include_dating": "1", "seed": "4",
    }  # fmt: skip
    with app.app_context():
        with app.test_request_context("/admin/create_population", method="POST", data=form):
            routes.mod.create_population.__wrapped__()
        assert db.session.query(Population).filter_by(name="Both").count() == 1, routes.flashes
        pop = db.session.query(Population).filter_by(name="Both").one()
        assert pop.username_type == "microblogging"  # not tied to a platform
        assert seen["photo"] is not None  # the Photo Sharing section was on
        assert set(population_platform_fields(pop)) == {"dating"}  # the stub wrote no photo fields
        assert routes.mod._flag is not None


@needs_runtime
def test_a_section_of_a_platform_that_is_not_installed_is_refused(app, routes, monkeypatch):  # noqa: F811
    from y_web import db
    from y_web.src.models import Population

    monkeypatch.setattr(routes.mod, "_photo_sharing_available", lambda: False)
    monkeypatch.setattr(routes.mod, "populations", lambda: "listed")
    with app.app_context():
        with app.test_request_context(
            "/admin/create_population", method="POST", data={"pop_name": "X", "n_agents": "5", "include_photo_sharing": "1"},
            headers={"Referer": "/admin/populations"},
        ):  # fmt: skip
            routes.mod.create_population.__wrapped__()
        assert db.session.query(Population).count() == 0
        assert any("not installed" in msg for _cat, msg in routes.flashes)


@needs_runtime
def test_agents_under_18_are_skipped_not_refused_on_dating(app):
    from y_web import db
    from y_web.src.dating import population as dp

    with app.app_context():
        row, agents = _standard_population(db, n=6)
        agents[0].age = 16
        agents[1].age = 17
        db.session.commit()
        dp.complete_population(row.id, seed=2)
        doc = dp.load_document(row.id)
        assert dp.validate_population(doc)  # as stored, the minors make it invalid for the runtime
        adults, skipped = dp.adults_only(doc)
        assert skipped == 2 and len(adults["agents"]) == 4
        assert dp.validate_population(adults) == []
        assert dp.adults_only(adults) == (adults, 0)


@needs_runtime
def test_an_uploaded_dating_document_is_recognised_without_choosing_a_platform(app, routes):  # noqa: F811
    import io

    from y_web import db
    from y_web.src.models import Population
    from y_web.tests.test_dating_population import EXAMPLE

    with app.app_context():
        with app.test_request_context(
            "/admin/upload_population",
            method="POST",
            data={"population_file": (io.BytesIO(EXAMPLE.read_bytes()), "p.json"), "pop_name": "Up"},
            content_type="multipart/form-data",
        ):
            routes.mod.upload_population.__wrapped__()
        row = db.session.query(Population).one()
        assert row.name == "Up" and row.size == 10


def test_every_name_the_populations_page_exports_to_window_is_defined():
    """A name exported but no longer defined throws at load time and none of the page's handlers is registered."""
    import re
    from pathlib import Path

    js = (
        Path(__file__).resolve().parents[1] / "static" / "assets" / "js" / "admin-populations.js"
    ).read_text(encoding="utf-8")
    block = re.search(r"Object\.assign\(window, \{(.*?)\}\);", js, re.S).group(1)
    names = [n.strip().split(":")[0] for n in block.split(",") if n.strip()]
    assert names
    for name in names:
        assert re.search(rf"(function\s+{name}\b|(?:const|let|var)\s+{name}\b)", js), name
