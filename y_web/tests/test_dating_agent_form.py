"""Dating fields of the admin agent form: custom features ``dating.*``, validation, availability (IR-D-05)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "external" / "YDating"
needs_runtime = pytest.mark.skipif(
    not (REPO / "schemas" / "population" / "population.json").exists(),
    reason="YDating is not present",
)

FULL = {
    "dating_seeking_genders": "woman, man",
    "dating_age_min": "25",
    "dating_age_max": "40",
    "dating_max_distance_km": "30",
    "dating_city": "Pisa",
    "dating_lat": "43.7",
    "dating_lon": "10.4",
    "dating_intent": "serious",
    "dating_bio": "Hiker.",
    "dating_prompt_answers": "Sunday: long walks",
    "dating_photo_captions": "on a trail\nat the sea",
    "dating_appearance_hair_color": "black",
    "dating_appearance_height_cm": "178",
    "dating_appearance_glasses": "yes",
    "dating_latent_attractiveness": "0.7",
    "dating_latent_selectivity": "0.4",
    "dating_affective_resilience": "1.2",
    "dating_match_recsys": "random",
}
BASE = {"username": "adhoc_1", "age": 31, "gender": "woman", "language": "en"}


@needs_runtime
def test_the_form_builds_a_valid_agent_document_stored_as_dating_features():
    from y_web.src.dating import agent_fields, agent_form
    from y_web.src.dating import population as dp

    entries, problems = agent_form.entries_from_form(FULL, BASE)
    assert problems == []
    keys = {e["key"]: e["value"] for e in entries}
    assert all(
        k.startswith("dating.") and e["feature_type"] == "custom"
        for k, e in zip(keys, entries)
    )
    assert keys["dating.profile.city"] == "Pisa"
    assert json.loads(keys["dating.profile.seeking_genders"]) == ["woman", "man"]
    assert keys["dating.appearance.glasses"] == "true"
    assert json.loads(keys["dating.photos"]) == [
        {"caption": "on a trail"},
        {"caption": "at the sea"},
    ]
    # the rows rebuild a document the runtime accepts
    doc = agent_fields.rows_to_agent(
        {"name": "adhoc_1", "age": 31, "gender": "woman", "language": "en"},
        [],
        {k: v for k, v in keys.items()},
        agent_fields.field_types(None),
    )
    assert doc["profile"]["age_min"] == 25 and doc["latent"]["attractiveness"] == 0.7
    assert doc["appearance"]["height_cm"] == 178 and doc["match_recsys"] == "random"
    assert (
        dp.validate_agent_document(
            {**BASE, **{k: v for k, v in doc.items() if k != "username"}}
        )
        == []
    )


def test_no_dating_field_means_no_feature():
    from y_web.src.dating import agent_form

    assert agent_form.entries_from_form({"name": "x", "dating_intent": ""}, BASE) == (
        [],
        [],
    )


@needs_runtime
@pytest.mark.parametrize(
    "bad",
    [
        {"dating_intent": "marriage"},
        {"dating_age_min": "50", "dating_age_max": "30"},
        {"dating_age_min": "10"},
        {"dating_lat": "120"},
        {"dating_latent_attractiveness": "3"},
        {"dating_appearance_height_cm": "20"},
        {"dating_appearance_glasses": "maybe"},
        {"dating_prompt_answers": "no colon here"},
        {"dating_max_distance_km": "far"},
    ],
)
def test_invalid_dating_fields_are_reported(bad):
    from y_web.src.dating import agent_form

    entries, problems = agent_form.entries_from_form(bad, BASE)
    assert entries == [] and problems


@needs_runtime
def test_the_standard_fields_are_validated_with_the_dating_schema():
    from y_web.src.dating import agent_form

    _entries, problems = agent_form.entries_from_form(
        {"dating_city": "Pisa"}, {**BASE, "age": 16}
    )
    assert any(p.startswith("age") for p in problems)


@pytest.fixture
def agents_mod(app, monkeypatch):
    import importlib

    mod = importlib.import_module("y_web.routes.admin.sub.agents")

    monkeypatch.setattr(mod, "check_privileges", lambda *_: None)
    monkeypatch.setattr(mod, "current_user", SimpleNamespace(username="admin", id=1))
    flashes = []
    monkeypatch.setattr(
        mod, "flash", lambda msg, cat="message": flashes.append((cat, str(msg)))
    )
    monkeypatch.setattr(mod, "_agent_builder_for_type", lambda t: "built")
    return SimpleNamespace(mod=mod, flashes=flashes)


def _post(app, agents_mod, data):
    with app.test_request_context("/admin/create_agent", method="POST", data=data):
        return agents_mod.mod.create_agent.__wrapped__()


STANDARD = {
    "population": "none",
    "name": "adhoc_1",
    "age": "31",
    "gender": "woman",
    "language": "en",
    "daily_user_activity": "1",
    "alt_profile": "",
}


@needs_runtime
def test_create_agent_stores_the_dating_features_when_the_runtime_is_installed(
    app, agents_mod, monkeypatch
):
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import Agent, Agent_Custom_Feature

    monkeypatch.setattr(dp, "runtime_available", lambda user=None: True)
    with app.app_context():
        _post(
            app,
            agents_mod,
            {
                **STANDARD,
                **FULL,
                "custom_feature_key[]": ["Class", "dating.profile.city"],
                "custom_feature_value[]": ["Mage", "Rome"],
            },
        )
        agent = db.session.query(Agent).one()
        rows = {
            r.key: r.value
            for r in db.session.query(Agent_Custom_Feature).filter_by(agent_id=agent.id)
        }
        assert (
            rows["dating.profile.city"] == "Pisa"
        )  # the generated value wins over a typed key
        assert rows["Class"] == "Mage" and rows["dating.profile.intent"] == "serious"
        assert agents_mod.flashes == []


@needs_runtime
def test_create_agent_refuses_invalid_dating_fields_without_creating_the_agent(
    app, agents_mod, monkeypatch
):
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import Agent

    monkeypatch.setattr(dp, "runtime_available", lambda user=None: True)
    with app.app_context():
        _post(app, agents_mod, {**STANDARD, "dating_intent": "marriage"})
        assert db.session.query(Agent).count() == 0
        assert agents_mod.flashes[-1][0] == "error"


def test_without_the_runtime_the_dating_fields_are_ignored_and_the_agent_is_unchanged(
    app, agents_mod, monkeypatch
):
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import Agent, Agent_Custom_Feature

    monkeypatch.setattr(dp, "runtime_available", lambda user=None: False)
    with app.app_context():
        _post(app, agents_mod, {**STANDARD, **FULL})
        assert db.session.query(Agent).count() == 1
        assert db.session.query(Agent_Custom_Feature).count() == 0


def test_the_agent_template_includes_the_dating_section_only_when_available(app):
    templates = ROOT / "y_web" / "templates" / "admin"
    page = (templates / "agents.html").read_text(encoding="utf-8")
    assert "{% if dating_available and" in page
    part = (templates / "_dating_agent_fields.html").read_text(encoding="utf-8")
    assert app.jinja_env.parse(part) is not None
    with app.test_request_context("/"):
        html = app.jinja_env.from_string(part).render(_=lambda t, **k: t % k)
    for name in (
        "dating_seeking_genders",
        "dating_latent_attractiveness",
        "dating_appearance_glasses",
        "dating_photo_captions",
    ):
        assert f'name="{name}"' in html
    # the recommender is a choice of the client, not of each individual
    assert "dating_match_recsys" not in html
