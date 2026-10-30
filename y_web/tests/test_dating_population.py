"""Dating populations: validation, storage, generation, compatibility and routes (plan S2, IR-D-05)."""

import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "external" / "YDating"
EXAMPLE = REPO / "example" / "population" / "population_10.json"

needs_runtime = pytest.mark.skipif(
    not EXAMPLE.exists(), reason="YDating is not present"
)


@pytest.fixture
def example():
    return json.loads(EXAMPLE.read_text())


@needs_runtime
def test_the_example_population_of_the_runtime_is_valid_unchanged(example):
    from y_web.src.dating import population as dp

    assert dp.validate_population(example, str(REPO)) == []
    summary = dp.summarize(example)
    assert summary["size"] == 10 and summary["with_photos"] == 10


@needs_runtime
def test_problems_carry_the_path_of_the_offending_value(example):
    from y_web.src.dating import population as dp

    bad = copy.deepcopy(example)
    bad["agents"][3]["age"] = 12
    problems = dp.validate_population(bad, str(REPO))
    assert any(p.startswith("agents/3/age") for p in problems)
    bad = copy.deepcopy(example)
    bad["agents"][1]["profile"]["intent"] = "marriage"
    assert any(
        p.startswith("agents/1/profile/intent")
        for p in dp.validate_population(bad, str(REPO))
    )
    assert dp.validate_population({"agents": "x"}, str(REPO))


@needs_runtime
def test_cross_checks_of_the_runtime_are_repeated(example):
    from y_web.src.dating import population as dp

    dup = copy.deepcopy(example)
    dup["agents"][1]["username"] = dup["agents"][0]["username"]
    assert any(
        "duplicate username" in p for p in dp.validate_population(dup, str(REPO))
    )
    window = copy.deepcopy(example)
    window["agents"][0]["profile"].update(age_min=50, age_max=30)
    assert any("age_min" in p for p in dp.validate_population(window, str(REPO)))
    interest = copy.deepcopy(example)
    interest["agents"][0]["interests"] = ["not-in-catalogue"]
    assert any("catalogue" in p for p in dp.validate_population(interest, str(REPO)))
    single = {"agents": example["agents"][:1]}
    assert any("at least two" in p for p in dp.validate_population(single, str(REPO)))


def test_upload_reader_reports_a_file_that_is_not_json():
    from y_web.src.dating import population as dp

    with pytest.raises(dp.DatingPopulationError):
        dp.read_upload(b"{nope")
    assert dp.read_upload(b'\xef\xbb\xbf{"agents": []}') == {"agents": []}


def test_the_public_card_never_carries_the_latent_variables(example):
    from y_web.src.dating import population as dp

    card = dp.profile_card(example["agents"][0])
    assert "latent" not in json.dumps(card) and "attractiveness" not in json.dumps(card)
    assert card["username"] == example["agents"][0]["username"]
    assert "latent" not in json.dumps(dp.summarize(example))


def _normal(doc):
    """A document without the empty lists and objects the schema defaults to, and with the catalogue sorted."""
    out = {"interests": sorted(doc.get("interests") or []), "agents": []}
    for agent in doc["agents"]:
        item = {k: v for k, v in agent.items() if v not in ([], {}, "")}
        out["agents"].append(item)
    return out


def test_agent_fields_roundtrip_every_shape_of_agent():
    from y_web.src.dating import agent_fields as af

    types = {
        "id": "string",
        "profile.age_min": "integer",
        "profile.max_distance_km": "number",
        "profile.seeking_genders": "array",
        "profile.city": "string",
        "profile.prompt_answers": "object",
        "latent.attractiveness": "number",
        "appearance.glasses": "boolean",
        "appearance.height_cm": "integer",
        "photos": "array",
    }
    agent = {
        "id": "abc",
        "username": "u1",
        "age": 31,
        "gender": "non-binary-extended",  # longer than the column of agents
        "language": "it",
        "personality": {"oe": "high", "ne": "low"},
        "match_recsys": "preference_similarity",
        "daily_activity_level": 2,
        "profile": {
            "seeking_genders": ["man", "woman"],
            "age_min": 20,
            "max_distance_km": 12.5,
            "city": "123",
            "bio": "",
            "prompt_answers": {"a": "b"},
        },
        "interests": ["art", "gaming"],
        "photos": [{"caption": "x"}, {"caption": "y", "subject": "s"}],
        "appearance": {"glasses": False, "height_cm": 180},
        "latent": {"attractiveness": 0.5},
    }
    af.set_limits({"gender": 10})
    try:
        columns, interests, custom = af.agent_to_rows(agent)
        assert columns["gender"] == "non-binary" and columns["name"] == "u1"
        assert all(c["key"].startswith("dating.") for c in custom)
        back = af.rows_to_agent(
            columns, interests, {c["key"]: c["value"] for c in custom}, types
        )
    finally:
        af.set_limits({})
    assert back == agent


@needs_runtime
def test_a_population_is_stored_as_agents_with_custom_features(app, example):
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import (
        Agent,
        Agent_Custom_Feature,
        Agent_Population,
        Population,
    )

    with app.app_context():
        row = Population(name="rt", descr="", size=10, username_type="dating")
        db.session.add(row)
        db.session.commit()
        assert dp.store_agents(row.id, example) == 10
        agents = (
            db.session.query(Agent)
            .join(Agent_Population)
            .filter(Agent_Population.population_id == row.id)
        )
        assert agents.count() == 10
        first = agents.order_by(Agent.id).first()
        assert first.name == "user_01" and first.age == 30 and first.gender == "woman"
        keys = {
            f.key
            for f in db.session.query(Agent_Custom_Feature).filter_by(agent_id=first.id)
            if f.feature_type == "custom"
        }
        assert "dating.profile.city" in keys and "dating.latent.attractiveness" in keys
        assert "dating.photos" in keys
        back = dp.load_document(row.id, str(REPO))
        assert _normal(back) == _normal(example)
        assert dp.validate_population(back, str(REPO)) == []
        # deleting the population removes its agents and their features
        assert dp.remove_agents(row.id) == 10
        assert db.session.query(Agent).count() == 0
        assert db.session.query(Agent_Custom_Feature).count() == 0
        assert dp.load_document(row.id, str(REPO)) is None


@needs_runtime
def test_generation_is_deterministic_and_valid():
    from y_web.src.dating import population as dp

    a = dp.generate(12, seed=5, repo_dir=str(REPO))
    b = dp.generate(12, seed=5, repo_dir=str(REPO))
    c = dp.generate(12, seed=6, repo_dir=str(REPO))
    assert a == b and a != c and len(a["agents"]) == 12
    assert dp.validate_population(a, str(REPO)) == []


@pytest.mark.parametrize("n", ["1", "abc", "20001"])
def test_generation_refuses_bad_sizes(n):
    from y_web.src.dating import population as dp

    with pytest.raises(dp.DatingPopulationError):
        dp.generate(n)


# -- compatibility ---------------------------------------------------------------------------------
def test_a_dating_population_matches_only_dating_experiments():
    from y_web.src.agents.platform import population_matches_platform

    pop = SimpleNamespace(id=1, username_type="dating")
    assert population_matches_platform(pop, "dating")
    for other in ("microblogging", "forum", "photo_sharing", "instant_messaging"):
        assert not population_matches_platform(pop, other)
        assert not population_matches_platform(
            SimpleNamespace(id=2, username_type=other), "dating"
        )


# -- routes ------------------------------------------------------------------------------------------
@pytest.fixture
def routes(app, monkeypatch, tmp_path):
    from y_web.routes.admin.sub import populations as mod

    monkeypatch.setattr(mod, "check_privileges", lambda *_: None)
    monkeypatch.setattr(mod, "current_user", SimpleNamespace(username="admin", id=1))
    monkeypatch.setattr(mod, "ensure_population_username_type_column", lambda: None)
    flashes = []
    monkeypatch.setattr(
        mod, "flash", lambda msg, cat="message": flashes.append((cat, str(msg)))
    )
    return SimpleNamespace(mod=mod, flashes=flashes, tmp=tmp_path)


def _upload(app, routes, payload: bytes, name="pop.json", **form):
    data = {
        "population_file": (io.BytesIO(payload), name),
        "upload_population_type": "dating",
        **form,
    }
    with app.test_request_context(
        "/admin/upload_population",
        method="POST",
        data=data,
        content_type="multipart/form-data",
    ):
        return routes.mod.upload_population.__wrapped__()


@needs_runtime
def test_upload_valid_population_stores_file_and_row(app, routes):
    from y_web import db
    from y_web.src.models import Agent, Population

    with app.app_context():
        response = _upload(app, routes, EXAMPLE.read_bytes(), pop_name="Pisa 10")
        row = db.session.query(Population).one()
        assert (
            row.username_type == "dating" and row.size == 10 and row.name == "Pisa 10"
        )
        assert response.location == f"/admin/population_details/{row.id}"
        assert db.session.query(Agent).count() == 10
        # a second import with the same name gets a suffix
        _upload(app, routes, EXAMPLE.read_bytes(), pop_name="Pisa 10")
        assert sorted(p.name for p in db.session.query(Population)) == [
            "Pisa 10",
            "Pisa 10_1",
        ]


@needs_runtime
def test_upload_invalid_population_is_refused_with_the_path(app, routes, example):
    from y_web import db
    from y_web.src.models import Population

    example["agents"][2]["age"] = 5
    with app.app_context():
        _upload(app, routes, json.dumps(example).encode())
        assert db.session.query(Population).count() == 0
        assert any("agents/2/age" in m for _, m in routes.flashes)
        _upload(app, routes, b"not json")
        assert db.session.query(Population).count() == 0


@needs_runtime
def test_details_download_and_delete(app, routes, monkeypatch):
    from y_web import db
    from y_web.src.models import Agent, Population

    with app.app_context():
        _upload(app, routes, EXAMPLE.read_bytes(), pop_name="P")
        row = db.session.query(Population).one()
        with app.test_request_context(f"/admin/dating_population/{row.id}/download"):
            resp = routes.mod.download_dating_population.__wrapped__(row.id)
            assert json.loads(resp.get_data())["agents"][0]["username"] == "user_01"
        # the generic download and details routes hand dating populations over
        with app.test_request_context(f"/admin/download_population/{row.id}"):
            resp = routes.mod.download_population.__wrapped__(row.id)
            assert resp.location.endswith(f"/admin/dating_population/{row.id}/download")
        captured = {}
        monkeypatch.setattr(
            routes.mod,
            "render_template",
            lambda tpl, **kw: captured.update(tpl=tpl, **kw) or "ok",
        )
        # the standard details page carries the dating block (no page of its own)
        with app.test_request_context(f"/admin/population_details/{row.id}?agent=2"):
            routes.mod.population_details.__wrapped__(row.id)
        assert captured["tpl"] == "admin/population_details.html"
        dating = captured["dating"]
        assert dating["index"] == 2 and dating["card"]["username"] == "user_03"
        assert "latent" not in json.dumps(dating["card"])
        assert dating["summary"]["size"] == 10
        monkeypatch.setattr(routes.mod, "populations", lambda: "listed")
        assert db.session.query(Agent).count() == 10
        with app.test_request_context(f"/admin/delete_population/{row.id}"):
            routes.mod.delete_population.__wrapped__(row.id)
        assert db.session.query(Population).count() == 0
        assert db.session.query(Agent).count() == 0  # the agents go with it


@needs_runtime
def test_generate_route_creates_a_population(app, routes):
    from y_web import db
    from y_web.src.models import Population

    with app.app_context():
        with app.test_request_context(
            "/admin/create_population",
            method="POST",
            data={
                "username_type": "dating",
                "pop_name": "Gen",
                "n_agents": "8",
                "seed": "3",
                "languages": "Italian",
            },
        ):
            routes.mod.create_population.__wrapped__()
        row = db.session.query(Population).one()
        assert row.size == 8 and row.languages == "it" and row.username_type == "dating"
        # the list and the details page read the same columns as the other platforms
        from y_web.src.models import Agent

        for agent in db.session.query(Agent):
            agent.education_level, agent.leaning = "Bachelor", "Centrist"
        db.session.commit()
        routes.mod._sync_dating_population(row)
        assert row.education == "Bachelor" and row.leanings == "Centrist"


def test_the_dating_templates_compile(app):
    templates = ROOT / "y_web" / "templates" / "admin"
    for name in (
        "population_details.html",
        "experiment_details_dating.html",
    ):
        source = (templates / name).read_text(encoding="utf-8")
        assert app.jinja_env.parse(source) is not None


# ------------------------------------------------------------------ creation form (full parameter set)


def test_config_from_form_reads_every_parameter_and_leaves_empty_ones_out():
    from y_web.src.dating import population as dp

    assert dp.config_from_form({}) == {}
    assert dp.config_from_form({"age_mean": " ", "genders": "", "cities": ""}) == {}
    cfg = dp.config_from_form(
        {
            "age_mean": "30",
            "age_min": "20",
            "genders": "woman=2, man=1, non-binary",
            "seeking": "woman: man=0.9, man+woman=0.1",
            "intents": "serious=1, casual=1",
            "cities": "Pisa, 43.7, 10.4, 2\nRoma, 41.9, 12.5",
            "city_radius_km": "12",
            "max_distance_km_min": "5",
            "max_distance_km_max": "30",
            "interests": "hiking, cooking\nhiking",
            "nationalities": "Italian=3, French=1",
            "personality_oe": "inventive/curious=1, consistent/cautious=1",
            "appearance_hair_color": "black=1, blond=1",
            "appearance_height_cm_min": "150",
            "appearance_height_cm_max": "190",
            "appearance_glasses": "25",
            "latent_attractiveness_a": "2",
            "latent_attractiveness_b": "5",
            "affective_resilience_min": "0.5",
            "affective_resilience_max": "1.5",
            "daily_activity_level_min": "1",
            "daily_activity_level_max": "3",
            "match_recsys": "random=1",
        }
    )
    assert cfg["age"] == {"mean": 30.0, "min": 20}
    assert cfg["genders"] == {"woman": 2.0, "man": 1.0, "non-binary": 1.0}
    assert cfg["seeking"] == {"woman": {"man": 0.9, "man,woman": 0.1}}
    assert cfg["cities"][0] == {"name": "Pisa", "lat": 43.7, "lon": 10.4, "weight": 2.0}
    assert cfg["cities"][1]["name"] == "Roma" and "weight" not in cfg["cities"][1]
    assert cfg["interests"] == ["hiking", "cooking"]
    assert cfg["max_distance_km"] == [5.0, 30.0]
    assert cfg["appearance"] == {
        "hair_color": {"black": 1.0, "blond": 1.0},
        "height_cm": [150, 190],
        "glasses": 0.25,
    }
    assert cfg["latent"] == {"attractiveness": [2.0, 5.0]}
    assert cfg["affective_traits"] == {"resilience": [0.5, 1.5]}
    assert cfg["daily_activity_level"] == [1, 3]
    assert cfg["personality"]["oe"]["inventive/curious"] == 1.0


@pytest.mark.parametrize(
    "form",
    [
        {"genders": "woman=abc"},
        {"genders": "woman=-1"},
        {"genders": "woman=0, man=0"},
        {"seeking": "no colon"},
        {"cities": "Pisa, 1"},
        {"cities": "Pisa, x, y"},
        {"age_mean": "old"},
        {"age_min": "10"},
        {"max_distance_km_min": "5"},
        {"max_distance_km_min": "9", "max_distance_km_max": "3"},
        {"latent_selectivity_a": "2"},
        {"appearance_glasses": "300"},
        {"appearance_height_cm_min": "50", "appearance_height_cm_max": "190"},
    ],
)
def test_config_from_form_refuses_malformed_values(form):
    from y_web.src.dating import population as dp

    with pytest.raises(dp.DatingPopulationError):
        dp.config_from_form(form)


@needs_runtime
def test_generate_with_the_standard_selectors_stores_every_field(app, routes):
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import AgeClass, Agent, Education, Leanings, Population

    with app.app_context():
        edu = Education(education_level="master")
        lean = Leanings(leaning="centrist")
        young = AgeClass(name="Young", age_start=20, age_end=25)
        db.session.add_all([edu, lean, young])
        db.session.commit()
        with app.test_request_context(
            "/admin/create_population",
            method="POST",
            data={
                "username_type": "dating",
                "pop_name": "Full",
                "n_agents": "20",
                "seed": "9",
                "languages": "Italian",
                "nationalities": "Italian",
                "male_percentage": "50",
                "female_percentage": "50",
                "age_classes": [str(young.id)],
                "age_classes_percentages": json.dumps({str(young.id): 100}),
                "education_levels": [str(edu.id)],
                "education_levels_percentages": json.dumps({str(edu.id): 100}),
                "political_leanings": [str(lean.id)],
                "political_leanings_percentages": json.dumps({str(lean.id): 100}),
                "d_intents": ["serious"],
                "d_intents_percentages": json.dumps({"serious": 100}),
                "d_appearance_hair_color": ["black"],
                "d_appearance_hair_color_percentages": json.dumps({"black": 100}),
                "appearance_glasses": "100",
                "daily_activity_level_min": "2",
                "daily_activity_level_max": "2",
                "latent_selectivity_a": "2",
                "latent_selectivity_b": "3",
            },
        ):
            routes.mod.create_population.__wrapped__()
        row = db.session.query(Population).one()
        agent = db.session.query(Agent).first()
        assert row.size == 20 and not routes.flashes[-1][0] == "error"
        assert agent.nationality == "Italian" and agent.language == "it"
        assert agent.education_level == "master" and agent.leaning == "centrist"
        assert agent.daily_activity_level == 2 and 20 <= agent.age <= 25
        doc = dp.load_document(row.id)
        a0 = doc["agents"][0]
        assert a0["appearance"]["hair_color"] == "black"
        assert a0["appearance"]["glasses"] is True
        assert a0["profile"]["intent"] == "serious"


@needs_runtime
def test_generate_route_reports_percentages_that_do_not_total_100(app, routes):
    from y_web import db
    from y_web.src.models import Population

    with app.app_context():
        with app.test_request_context(
            "/admin/create_population",
            method="POST",
            data={
                "username_type": "dating",
                "pop_name": "Bad",
                "n_agents": "8",
                "d_intents": ["serious", "casual"],
                "d_intents_percentages": json.dumps({"serious": 30, "casual": 30}),
            },
        ):
            routes.mod.create_population.__wrapped__()
        assert db.session.query(Population).count() == 0
        assert routes.flashes[-1][0] == "error"


def test_the_form_composer_uses_percentages_and_proposed_defaults():
    from werkzeug.datastructures import MultiDict

    from y_web.src.dating import population as dp

    form = MultiDict(
        {
            "male_percentage": "40",
            "female_percentage": "60",
            "nationalities": "French",
            "age_classes": "1",
            "age_classes_percentages": json.dumps({"1": 100}),
            "d_seek_woman": ["man", "woman"],
            "d_seek_woman_percentages": json.dumps({"man": 90, "woman": 10}),
        }
    )
    cfg = dp.config_from_population_form(form, {"1": (10, 30)}, {}, {})
    assert cfg["genders"] == {"man": 40.0, "woman": 60.0}
    assert cfg["nationalities"] == {"French": 1.0}
    assert cfg["age_classes"] == [{"min": 18, "max": 30, "weight": 100.0}]
    assert cfg["seeking"] == {"woman": {"man": 90.0, "woman": 10.0}}
    for table in dp.APPEARANCE_DEFAULTS.values():
        assert not table or sum(table.values()) == 100
    assert sum(dp.INTENT_DEFAULTS.values()) == 100
    for table in dp.SEEKING_DEFAULTS.values():
        assert sum(table.values()) == 100
    assert dp.language_code("Italian") == "it" and dp.language_code("English") == "en"


def test_the_creation_form_is_offered_only_when_the_runtime_is_installed(app):
    templates = ROOT / "y_web" / "templates" / "admin"
    form = (templates / "_dating_population_form.html").read_text(encoding="utf-8")
    assert app.jinja_env.parse(form) is not None
    populations = (templates / "populations.html").read_text(encoding="utf-8")
    assert "{% if dating_available %}" in populations
    assert '{% include "admin/_dating_population_form.html" %}' in populations
    # one form for every platform: Dating is an option of the platform select, its sections live inside the
    # standard form, which keeps posting to its own route; there is no separate box or page any more
    assert 'action="/admin/create_population"' in populations
    assert '<option value="dating">' in populations
    assert 'id="dating-population-sections"' in form
    assert "<form" not in form
    assert "dating_popcreate_form" not in populations
    assert "box-create-dating-population" not in populations
    assert "/admin/dating_populations" not in populations
    from y_web.src.dating import population as dp

    defaults = {
        "intents": dp.INTENT_DEFAULTS,
        "seeking": dp.SEEKING_DEFAULTS,
        "seeking_sets": dp.SEEKING_SETS,
        "appearance": dp.APPEARANCE_DEFAULTS,
        "appearance_options": dp.APPEARANCE_OPTIONS,
        "latent": dp.LATENT_DEFAULTS,
        "affective": dp.AFFECTIVE_DEFAULT_RANGE,
        "activity": dp.ACTIVITY_DEFAULT_RANGE,
        "height": dp.HEIGHT_DEFAULT_RANGE,
        "glasses": dp.GLASSES_DEFAULT_PERCENT,
        "photos": dp.PHOTOS_DEFAULT_RANGE,
        "age_window": dp.AGE_WINDOW_DEFAULT_RANGE,
    }
    with app.test_request_context("/"):
        html = app.jinja_env.from_string(form).render(
            _=lambda text, **kw: text % kw if kw else text,
            dating_defaults=defaults,
        )
    # the selectors are the multi-selects with percentages of the other platforms, with proposed defaults
    assert (
        'id="d_intents_dropdown"' in html
        and 'id="d_appearance_hair_color_dropdown"' in html
    )
    assert 'name="appearance_glasses"' in html and 'name="latent_selectivity_a"' in html
    assert 'name="daily_activity_level_min"' in html and 'value="1"' in html
    assert 'data-platform-only="dating"' in html
    # what the standard form already asks, or the runtime samples, is not repeated
    for name in (
        "personality_",
        "cities",
        "city_radius_km",
        "max_distance_km",
        "interests",
        "match_recsys",
    ):
        assert f'name="{name}' not in html


def test_dating_runtime_availability_follows_the_registry(monkeypatch):
    from y_web.src import external_runtime as er
    from y_web.src.dating import population as dp

    monkeypatch.setattr(
        er, "runtime_installed_and_visible", lambda key, user: key == "dating"
    )
    assert dp.runtime_available(object()) is True
    monkeypatch.setattr(er, "runtime_installed_and_visible", lambda key, user: False)
    assert dp.runtime_available(object()) is False

    def boom(*_):
        raise RuntimeError

    monkeypatch.setattr(er, "runtime_installed_and_visible", boom)
    assert dp.runtime_available(object()) is False


def test_cities_of_the_form_can_name_the_nationality_that_lives_there():
    from y_web.src.dating import population as dp

    cfg = dp.config_from_form(
        {
            "cities": "Lyon, 45.7, 4.8, 2, French\nRoma, 41.9, 12.5, , Italian\nOslo, 59.9, 10.7"
        }
    )
    assert cfg["cities"] == [
        {
            "name": "Lyon",
            "lat": 45.7,
            "lon": 4.8,
            "weight": 2.0,
            "nationality": "French",
        },
        {"name": "Roma", "lat": 41.9, "lon": 12.5, "nationality": "Italian"},
        {"name": "Oslo", "lat": 59.9, "lon": 10.7},
    ]


@needs_runtime
def test_generated_agents_live_in_a_city_of_their_nationality(app, routes):
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import Population

    with app.app_context():
        with app.test_request_context(
            "/admin/create_population",
            method="POST",
            data={
                "username_type": "dating",
                "pop_name": "Nat",
                "n_agents": "30",
                "seed": "4",
                "nationalities": "French",
            },
        ):
            routes.mod.create_population.__wrapped__()
        row = db.session.query(Population).one()
        doc = dp.load_document(row.id)
        french = {"Paris", "Lyon", "Marseille", "Toulouse", "Lille", "Bordeaux"}
        japanese = {"Tokyo", "Osaka", "Nagoya", "Fukuoka", "Sapporo"}
        for a in doc["agents"]:
            assert a["profile"]["city"] in (
                french if a["nationality"] == "French" else japanese
            )
