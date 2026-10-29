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


def test_store_load_remove_roundtrip(tmp_path, example):
    from y_web.src.dating import population as dp

    dp.store(str(tmp_path), 7, example)
    assert dp.load(str(tmp_path), 7) == example
    dp.remove(str(tmp_path), 7)
    assert dp.load(str(tmp_path), 7) is None
    dp.remove(str(tmp_path), 7)  # idempotent


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
    monkeypatch.setattr(mod, "_dating_base_dir", lambda: str(tmp_path))
    flashes = []
    monkeypatch.setattr(
        mod, "flash", lambda msg, cat="message": flashes.append((cat, str(msg)))
    )
    return SimpleNamespace(mod=mod, flashes=flashes, tmp=tmp_path)


def _upload(app, routes, payload: bytes, name="pop.json", **form):
    data = {"population_file": (io.BytesIO(payload), name), **form}
    with app.test_request_context(
        "/admin/dating_populations/upload",
        method="POST",
        data=data,
        content_type="multipart/form-data",
    ):
        return routes.mod.upload_dating_population.__wrapped__()


@needs_runtime
def test_upload_valid_population_stores_file_and_row(app, routes):
    from y_web import db
    from y_web.src.models import Population

    with app.app_context():
        response = _upload(app, routes, EXAMPLE.read_bytes(), pop_name="Pisa 10")
        row = db.session.query(Population).one()
        assert (
            row.username_type == "dating" and row.size == 10 and row.name == "Pisa 10"
        )
        assert response.location == f"/admin/dating_population/{row.id}"
        assert (routes.tmp / "y_web" / "dating_populations" / f"{row.id}.json").exists()
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
    from y_web.src.models import Population

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
        with app.test_request_context(f"/admin/dating_population/{row.id}?agent=2"):
            routes.mod.dating_population_details.__wrapped__(row.id)
        assert captured["tpl"] == "admin/dating_population_details.html"
        assert captured["index"] == 2 and captured["card"]["username"] == "user_03"
        assert "latent" not in json.dumps(captured["card"])
        with app.test_request_context(f"/admin/population_details/{row.id}"):
            resp = routes.mod.population_details.__wrapped__(row.id)
            assert resp.location == f"/admin/dating_population/{row.id}"
        monkeypatch.setattr(routes.mod, "populations", lambda: "listed")
        path = routes.tmp / "y_web" / "dating_populations" / f"{row.id}.json"
        assert path.exists()
        with app.test_request_context(f"/admin/delete_population/{row.id}"):
            routes.mod.delete_population.__wrapped__(row.id)
        assert not path.exists() and db.session.query(Population).count() == 0


@needs_runtime
def test_generate_route_creates_a_population(app, routes):
    from y_web import db
    from y_web.src.models import Population

    with app.app_context():
        with app.test_request_context(
            "/admin/dating_populations/generate",
            method="POST",
            data={"pop_name": "Gen", "n_agents": "8", "seed": "3", "language": "it"},
        ):
            routes.mod.generate_dating_population.__wrapped__()
        row = db.session.query(Population).one()
        assert row.size == 8 and row.languages == "it" and row.username_type == "dating"


def test_the_dating_templates_compile(app):
    templates = ROOT / "y_web" / "templates" / "admin"
    for name in (
        "dating_populations.html",
        "dating_population_details.html",
        "experiment_details_dating.html",
    ):
        source = (templates / name).read_text(encoding="utf-8")
        assert app.jinja_env.parse(source) is not None
