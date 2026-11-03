"""Admin agent form: optional Appearance (with the profile picture) and platform-specific sections (as in populations)."""

import json
from pathlib import Path

import pytest

from y_web.tests.test_dating_agent_form import STANDARD, _post, agents_mod  # noqa: F401

pytestmark = pytest.mark.integration

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "admin"


def _features(db, agent_id):
    from y_web.src.models import Agent_Custom_Feature

    return {
        r.key: r.value
        for r in db.session.query(Agent_Custom_Feature).filter_by(agent_id=agent_id)
    }


def test_appearance_is_stored_only_when_the_section_is_on(
    app, agents_mod
):  # noqa: F811
    from y_web import db
    from y_web.src.models import Agent

    with app.app_context():
        _post(
            app, agents_mod, {**STANDARD, "appearance_hair_color": "black"}
        )  # section off: ignored
        agent = db.session.query(Agent).one()
        assert _features(db, agent.id) == {}
        _post(
            app, agents_mod,
            {**STANDARD, "name": "b", "include_appearance": "1", "appearance_hair_color": "black",
             "appearance_height_cm": "172", "appearance_glasses": "yes"},
        )  # fmt: skip
        agent = db.session.query(Agent).filter_by(name="b").one()
        assert _features(db, agent.id) == {
            "appearance.hair_color": "black", "appearance.height_cm": "172", "appearance.glasses": "true",
        }  # fmt: skip


@pytest.mark.parametrize(
    "bad",
    [
        {"appearance_height_cm": "20"},
        {"appearance_glasses": "maybe"},
        {"appearance_hair_color": "rainbow"},
    ],
)
def test_wrong_appearance_is_refused(app, agents_mod, bad):  # noqa: F811
    from y_web import db
    from y_web.src.models import Agent

    with app.app_context():
        _post(app, agents_mod, {**STANDARD, "include_appearance": "1", **bad})
        assert (
            db.session.query(Agent).count() == 0
            and agents_mod.flashes[-1][0] == "error"
        )


def test_the_picture_toggle_starts_one_background_job(
    app, agents_mod, monkeypatch
):  # noqa: F811
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import Agent

    started = []
    monkeypatch.setattr(
        pp, "start_generation", lambda *a: started.append(a) or (1, None)
    )
    with app.app_context():
        _post(
            app,
            agents_mod,
            {
                **STANDARD,
                "include_appearance": "1",
                "generate_profile_pictures": "1",
                "pictures_generator": "stub",
                "pictures_style": "cartoon",
            },
        )
        agent = db.session.query(Agent).one()
        assert (
            len(started) == 1
            and started[0][2] == [agent.id]
            and started[0][3]["style"] == "cartoon"
        )
        started.clear()
        _post(
            app, agents_mod, {**STANDARD, "name": "c", "generate_profile_pictures": "1"}
        )  # section off: no job
        assert started == []


def test_photo_sharing_fields_are_stored_as_extensions(
    app, agents_mod, monkeypatch
):  # noqa: F811
    from y_web import db
    from y_web.src.models import Agent, Agent_Ext

    monkeypatch.setattr(agents_mod.mod, "_photo_sharing_available", lambda: True)
    with app.app_context():
        _post(
            app, agents_mod,
            {**STANDARD, "include_photo_sharing": "1", "photo_bio": "hi", "photo_is_private": "yes",
             "photo_attention_budget": "80", "photo_favorite_filters": "warm, mono, warm", "photo_creator_tier": "pro"},
        )  # fmt: skip
        agent = db.session.query(Agent).one()
        ext = {
            e.feature_name: e.feature_value
            for e in db.session.query(Agent_Ext).filter_by(agent_id=agent.id)
        }
        assert ext == {
            "bio": "hi", "is_private": "true", "attention_budget": "80",
            "favorite_filters": json.dumps(["warm", "mono"]), "creator_tier": "pro",
        }  # fmt: skip


def test_photo_sharing_needs_the_simulator_and_valid_values(
    app, agents_mod, monkeypatch
):  # noqa: F811
    from y_web import db
    from y_web.src.models import Agent

    monkeypatch.setattr(agents_mod.mod, "_photo_sharing_available", lambda: False)
    with app.app_context():
        _post(
            app,
            agents_mod,
            {**STANDARD, "include_photo_sharing": "1", "photo_bio": "x"},
        )
        assert db.session.query(Agent).count() == 0
        monkeypatch.setattr(agents_mod.mod, "_photo_sharing_available", lambda: True)
        _post(
            app,
            agents_mod,
            {**STANDARD, "include_photo_sharing": "1", "photo_creator_tier": "god"},
        )
        _post(
            app,
            agents_mod,
            {**STANDARD, "include_photo_sharing": "1", "photo_attention_budget": "0"},
        )
        assert db.session.query(Agent).count() == 0


def test_the_appearance_feeds_the_dating_fields(
    app, agents_mod, monkeypatch
):  # noqa: F811
    from y_web import db
    from y_web.src.dating import population as dp
    from y_web.src.models import Agent

    monkeypatch.setattr(dp, "runtime_available", lambda user=None: True)
    with app.app_context():
        _post(
            app, agents_mod,
            {**STANDARD, "include_appearance": "1", "appearance_eye_color": "green", "appearance_glasses": "yes",
             "dating_city": "Pisa"},
        )  # fmt: skip
        agent = db.session.query(Agent).one()
        rows = _features(db, agent.id)
        if "dating.profile.city" in rows:  # the YDating schema is present
            assert (
                rows["dating.appearance.eye_color"] == "green"
                and rows["dating.appearance.glasses"] == "true"
            )
        assert rows["appearance.eye_color"] == "green"


def test_the_template_offers_the_sections_as_the_population_form_does():
    page = (TEMPLATES / "agents.html").read_text()
    assert (
        'name="include_appearance"' in page
        and "{% if photo_available or dating_available %}" in page
    )
    assert "{% if photo_available %}" in page and "{% if dating_available %}" in page
    assert "checked" not in page.split('name="include_appearance"')[1].split(">")[0]
    assert 'id="appearance-config-wrapper" class="ys-opt-body d-none"' in page
    for part in ("_agent_appearance", "_agent_photo_sharing", "_dating_agent_fields"):
        assert (
            "disabled>"
            in (TEMPLATES / f"{part}.html")
            .read_text()
            .split("<fieldset")[1]
            .split(">")[0]
            + ">"
        )
    assert (
        "checked"
        not in (TEMPLATES / "_agent_appearance.html")
        .read_text()
        .split('name="generate_profile_pictures"')[1]
        .split(">")[0]
    )
