"""Statistics of the custom fields on admin/population_details and the forum "force placeholders" switch."""

import json

import pytest

from y_web.tests.test_dating_population import routes  # noqa: F401
from y_web.tests.test_population_platform_fields import _standard_population

pytestmark = pytest.mark.integration


def test_fields_are_grouped_and_described():
    from y_web.src.agents import custom_field_stats as cf

    custom = {
        "appearance.hair_color": {1: "red", 2: "red", 3: "black"},
        "dating.appearance.eye_color": {1: "blue"},
        "dating.latent.attractiveness": {1: "0.2", 2: "0.8", 3: "0.5"},
        "dating.profile.smokes": {1: "true", 2: "false"},
        "dating.photos": {1: json.dumps(["a", "b"]), 2: json.dumps(["a"])},
        "x.other": {1: "v"},
    }
    ext = {"creator_tier": {1: "gold", 2: "gold"}, "bio": {1: "hi", 2: ""}}
    groups = {g["id"]: g for g in cf.build(custom, ext, total=4)}
    assert list(groups) == ["appearance", "dating_profile", "dating_latent", "dating_other", "photo_sharing", "other"]
    hair = next(b for b in groups["appearance"]["blocks"] if b["key"] == "hair_color")
    assert hair["labels"] == ["red", "black"] and hair["data"] == [2, 1] and hair["coverage"] == 75
    latent = groups["dating_latent"]["blocks"][0]
    assert latent["kind"] == "numeric" and latent["summary"]["mean"] == 0.5 and sum(latent["data"]) == 3
    assert groups["dating_profile"]["blocks"][0]["kind"] == "flag"
    assert groups["dating_other"]["blocks"][0]["summary"]["max"] == 2.0
    assert groups["photo_sharing"]["badge"] == "photo"


def test_nothing_without_custom_fields(app):
    from y_web import db
    from y_web.src.agents import custom_field_stats as cf

    with app.app_context():
        _, agents = _standard_population(db, n=3)
        assert cf.collect([a.id for a in agents]) == []
        assert cf.collect([]) == []


def test_collect_reads_any_population(app):
    from y_web import db
    from y_web.src.agents import custom_field_stats as cf
    from y_web.src.agents import profile_pictures as pp

    with app.app_context():
        _, agents = _standard_population(db, n=4)
        ids = [a.id for a in agents]
        pp.assign_appearance(ids, {"hair_color": {"red": 100}}, seed=1)
        groups = cf.collect(ids)
        assert [g["id"] for g in groups] == ["appearance"]
        assert groups[0]["blocks"][0]["coverage"] == 100


def test_page_ships_the_scripts_and_the_data_hook():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    page = (root / "templates" / "admin" / "population_details.html").read_text()
    assert "YS_CUSTOM_FIELDS" in page and "admin-population-fields.js" in page
    assert (root / "static" / "assets" / "js" / "admin-population-fields.js").exists()


def test_a_generated_picture_wins_unless_placeholders_are_forced(app, monkeypatch):
    from y_web import db
    from y_web.src.content import avatars
    from y_web.src.models import Agent

    class U:
        username = "zed"
        is_page = False
        id = 1

    with app.app_context():
        monkeypatch.setattr("y_web.src.agents.profile_pictures.picture_of_username", lambda name: "/media/agents/9.png")
        monkeypatch.setattr(avatars, "_forum_settings", lambda exp_id=None: {"mode": "placeholder", "force_placeholder": False})
        assert avatars.resolve_forum_profile_pic(U()) == "/media/agents/9.png"
        monkeypatch.setattr(avatars, "_forum_settings", lambda exp_id=None: {"mode": "placeholder", "force_placeholder": True})
        assert avatars.resolve_forum_profile_pic(U()) == avatars.deterministic_forum_avatar_url("zed")
    assert avatars.normalize_force_placeholder("on") and not avatars.normalize_force_placeholder(None)
    assert Agent  # model import keeps the metadata loaded


def _details_context(app, routes, monkeypatch, with_fields):  # noqa: F811
    from y_web import db
    from y_web.src.agents import profile_pictures as pp

    seen = {}
    monkeypatch.setattr(routes.mod, "render_template", lambda name, **kw: seen.update(name=name, **kw) or "ok")
    with app.app_context():
        pop, agents = _standard_population(db, n=4)
        if with_fields:
            pp.assign_appearance([a.id for a in agents], {"hair_color": {"red": 60, "black": 40}, "height_cm": [160, 190], "glasses": 0.5}, seed=3)
        with app.test_request_context(f"/admin/population_details/{pop.id}"):
            routes.mod.population_details.__wrapped__(pop.id)
    return seen


def test_details_route_passes_the_custom_fields_when_present(app, routes, monkeypatch):  # noqa: F811
    seen = _details_context(app, routes, monkeypatch, True)
    assert seen["name"] == "admin/population_details.html"
    assert [g["id"] for g in seen["custom_fields"]] == ["appearance"]
    assert seen["kpis"]["agents"] == 4 and seen["kpis"]["fields"] == len(seen["custom_fields"][0]["blocks"])


def test_details_route_without_custom_fields(app, routes, monkeypatch):  # noqa: F811
    seen = _details_context(app, routes, monkeypatch, False)
    assert seen["custom_fields"] == [] and seen["kpis"]["fields"] == 0
