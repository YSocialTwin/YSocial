"""Appearance (optional, platform-independent) and the profile pictures of the agents of a population."""

import json
import os

import pytest

from y_web.tests.test_dating_population import routes  # noqa: F401
from y_web.tests.test_population_platform_fields import _standard_population

pytestmark = pytest.mark.integration


@pytest.fixture
def media(tmp_path, monkeypatch):
    from y_web.src.agents import profile_pictures as pp

    monkeypatch.setattr(pp, "media_dir", lambda: str(tmp_path / "media"))
    return tmp_path / "media"


def _notification(db):
    from y_web.src.models import DownloadNotification

    row = DownloadNotification(user_id=1, title="t", message="m", status="processing")
    db.session.add(row)
    db.session.commit()
    return row.id


def test_appearance_is_drawn_from_the_weights_and_read_back(app):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import Agent_Custom_Feature

    with app.app_context():
        _, agents = _standard_population(db, n=5)
        ids = [a.id for a in agents]
        cfg = {"hair_color": {"red": 100}, "height_cm": [170, 170], "glasses": 1.0}
        assert pp.assign_appearance(ids, cfg, seed=1) == 5
        assert pp.assign_appearance(ids, cfg, seed=1) == 0  # nothing left to draw
        traits = pp.read_appearance(ids)
        assert traits[ids[0]] == {"hair_color": "red", "height_cm": "170", "glasses": "true"}
        # a Dating population keeps them as dating.appearance.*: read the same way, the generic ones win
        db.session.add(Agent_Custom_Feature(agent_id=ids[0], feature_type="custom", key="dating.appearance.eye_color", value="blue"))
        db.session.add(Agent_Custom_Feature(agent_id=ids[0], feature_type="custom", key="dating.appearance.hair_color", value="black"))
        db.session.commit()
        got = pp.read_appearance([ids[0]])[ids[0]]
        assert got["eye_color"] == "blue" and got["hair_color"] == "red"


def test_the_prompt_uses_visible_traits_only_in_english():
    from y_web.src.agents import profile_pictures as pp

    text = pp.compose_prompt(31, "female", {"hair_color": "red", "eye_color": "green", "glasses": "true", "secret": "x"})
    assert "31 years old" in text and "red" in text and "green eyes" in text and "wearing glasses" in text
    assert "secret" not in text and "x" not in text.split(",")
    assert "cartoon" in pp.compose_prompt(30, "male", {}, "cartoon")
    with pytest.raises(ValueError):
        pp.compose_prompt(30, "male", {}, "oil")


def test_the_pictures_are_written_in_the_media_folder_and_linked_to_the_agents(app, media):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import Agent, DownloadNotification

    with app.app_context():
        _, agents = _standard_population(db, n=3)
        ids = [a.id for a in agents]
        nid = _notification(db)
        made = pp.run_generation(app, nid, ids, {"generator": "stub", "style": "photorealistic"})
        assert made == 3
        db.session.expire_all()
        for agent_id in ids:
            agent = db.session.get(Agent, agent_id)
            assert agent.profile_pic == f"/media/agents/{agent_id}.png"
            assert (media / f"{agent_id}.png").read_bytes().startswith(b"\x89PNG")
        row = db.session.get(DownloadNotification, nid)
        assert row.status == "ready" and "3 profile pictures generated." == row.message


def test_the_progress_is_reported_in_the_notification(app, media, monkeypatch):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import DownloadNotification

    seen = []
    real = pp._set_notification

    def spy(nid, **fields):
        status = real(nid, **fields)
        if "message" in fields and fields.get("status") is None:
            seen.append(fields["message"])
        return status

    monkeypatch.setattr(pp, "_set_notification", spy)
    with app.app_context():
        _, agents = _standard_population(db, n=3)
        nid = _notification(db)
        pp.run_generation(app, nid, [a.id for a in agents], {"generator": "stub"})
        assert seen == [pp.progress_message(i, 3) for i in (1, 2, 3)]
        from y_web.routes.admin.sub.experiments import _helpers

        monkeypatch.setattr(_helpers, "format_datetime", lambda *a, **k: "now")
        _serialize_download_notification = _helpers._serialize_download_notification

        row = db.session.get(DownloadNotification, nid)
        row.status, row.message = "processing", pp.progress_message(1, 4)
        with app.test_request_context("/"):
            data = _serialize_download_notification(row)
        assert data["progress"] == {"done": 1, "total": 4, "percent": 25}
        assert "progress" not in data["message"] and data["message"].startswith("Generating profile pictures: 1 of 4")


def test_a_cancelled_job_stops(app, media):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import DownloadNotification

    with app.app_context():
        _, agents = _standard_population(db, n=4)
        nid = _notification(db)
        db.session.get(DownloadNotification, nid).status = "cancelled"
        db.session.commit()
        assert pp.run_generation(app, nid, [a.id for a in agents], {"generator": "stub"}) == 1  # stops after the first
        assert db.session.get(DownloadNotification, nid).status == "cancelled"


def test_a_failure_is_reported_in_the_notification(app, media):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import DownloadNotification

    with app.app_context():
        _, agents = _standard_population(db, n=2)
        nid = _notification(db)
        pp.run_generation(app, nid, [a.id for a in agents], {"generator": "nonsense"})
        row = db.session.get(DownloadNotification, nid)
        assert row.status == "failed" and "unknown image generator" in row.error_message


def test_the_picture_is_deleted_with_the_agent(app, media):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import Agent

    with app.app_context():
        _, agents = _standard_population(db, n=3)
        ids = [a.id for a in agents]
        pp.run_generation(app, _notification(db), ids, {"generator": "stub"})
        assert sorted(os.listdir(media)) == sorted(f"{i}.png" for i in ids)
        db.session.delete(db.session.get(Agent, ids[0]))  # ORM delete (the admin pages)
        db.session.commit()
        assert not (media / f"{ids[0]}.png").exists() and (media / f"{ids[1]}.png").exists()
        assert pp.delete_pictures_of(ids[1:]) == 2  # bulk deletes (population removal)
        assert os.listdir(media) == []


def test_only_files_of_the_media_folder_can_be_deleted(app, media, tmp_path):
    from y_web.src.agents import profile_pictures as pp

    victim = tmp_path / "keep.png"
    victim.write_bytes(b"x")
    assert not pp.delete_picture_file("/media/agents/../keep.png")
    assert not pp.delete_picture_file(str(victim))
    assert not pp.delete_picture_file("/static/assets/img/users/a.png")
    assert not pp.delete_picture_file(None) and victim.exists()


def test_the_picture_is_served(app, media, routes):  # noqa: F811
    from y_web.src.agents import profile_pictures as pp

    if not any(r.rule.startswith("/media/agents") for r in app.url_map.iter_rules()):
        app.register_blueprint(routes.mod.population)

    media.mkdir(parents=True)
    (media / "7.png").write_bytes(b"\x89PNG")
    client = app.test_client()
    assert client.get(pp.picture_url(7)).status_code == 200
    assert client.get("/media/agents/missing.png").status_code == 404
    assert client.get("/media/agents/.hidden").status_code == 404


def _form(**extra):
    one = json.dumps({"1": 100})
    return {
        "pop_name": "Look", "pop_descr": "", "n_agents": "4", "nationalities": "Italian", "languages": "Italian", "tags": "art", "male_percentage": "50", "female_percentage": "50",
        "age_classes": "1", "age_classes_percentages": one,
        "education_levels": "1", "education_levels_percentages": one,
        "political_leanings": "1", "political_leanings_percentages": one,
        "toxicity_levels": "1", "toxicity_levels_percentages": one,
        **extra,
    }  # fmt: skip


def _create(app, routes, monkeypatch, **extra):  # noqa: F811
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import Agent, Agent_Population, Population

    started = []

    def fake_generate(name, percentages, actions, backgrounds, photo_config):
        pop = db.session.query(Population).filter_by(name=name).one()
        for i in range(4):
            a = Agent(name=f"q_{i}", age=25 + i, gender="male" if i % 2 else "female", language="en", nationality="Italian",
                      education_level="bachelor", profession="engineer", leaning="center", daily_activity_level=1)  # fmt: skip
            db.session.add(a)
            db.session.flush()
            db.session.add(Agent_Population(agent_id=a.id, population_id=pop.id))
        db.session.commit()

    monkeypatch.setattr(routes.mod, "generate_population", fake_generate)
    monkeypatch.setattr(routes.mod, "populations", lambda: "listed")
    monkeypatch.setattr(pp, "start_generation", lambda *a: started.append(a) or (1, None))
    with app.app_context():
        with app.test_request_context("/admin/create_population", method="POST", data=_form(**extra), headers={"Referer": "/admin/populations"}):
            routes.mod.create_population.__wrapped__()
        pop = db.session.query(Population).filter_by(name="Look").first()
        traits = pp.read_appearance([r[0] for r in db.session.query(Agent_Population.agent_id).filter_by(population_id=pop.id)]) if pop else {}
    return started, traits, pop


def test_appearance_is_off_by_default(app, routes, monkeypatch):  # noqa: F811
    started, traits, pop = _create(app, routes, monkeypatch)
    assert pop is not None and not started and traits == {}


def test_appearance_without_pictures_assigns_traits_and_starts_no_job(app, routes, monkeypatch):  # noqa: F811
    started, traits, pop = _create(app, routes, monkeypatch, include_appearance="1", appearance_height_cm_min="160", appearance_height_cm_max="170")
    assert pop is not None and not started
    assert len(traits) == 4 and all(160 <= int(t["height_cm"]) <= 170 for t in traits.values())


def test_the_picture_toggle_starts_the_background_job(app, routes, monkeypatch):  # noqa: F811
    started, traits, pop = _create(
        app, routes, monkeypatch, include_appearance="1", generate_profile_pictures="1",
        pictures_style="cartoon", pictures_generator="stub", pictures_model="x/y", pictures_steps="8",
    )  # fmt: skip
    assert len(started) == 1
    _app, user_id, ids, cfg = started[0]
    assert user_id == 1 and len(ids) == 4
    assert cfg == {"style": "cartoon", "generator": "stub", "model": "x/y", "inference_steps": 8}
    assert any("notifications menu" in msg for _c, msg in routes.flashes)


def test_wrong_picture_settings_discard_the_population(app, routes, monkeypatch):  # noqa: F811
    started, _traits, pop = _create(app, routes, monkeypatch, include_appearance="1", generate_profile_pictures="1", pictures_style="oil")
    assert pop is None and not started
    assert any("unknown image style" in msg for _c, msg in routes.flashes)


def test_the_page_offers_the_appearance_section_collapsed_and_the_toggle_off():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "templates" / "admin"
    page = (root / "populations.html").read_text()
    assert 'id="include_appearance"' in page and "checked" not in page.split('id="include_appearance"')[1].split(">")[0]
    assert 'id="appearance-config-wrapper" class="ys-opt-body d-none"' in page
    part = (root / "_population_appearance.html").read_text()
    assert 'name="generate_profile_pictures"' in part and "checked" not in part.split('name="generate_profile_pictures"')[1].split(">")[0]
    assert "disabled>" in part.split("<fieldset")[1]
    assert "dating-section-appearance" not in (root / "_dating_population_form.html").read_text()


def test_a_generation_interrupted_by_a_restart_resumes_with_the_missing_pictures(app, media):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import Agent, DownloadNotification

    with app.app_context():
        _, agents = _standard_population(db, n=5)
        ids = [a.id for a in agents]
        nid = _notification(db)
        cfg = {"generator": "stub"}
        pp._write_job(nid, ids, cfg)
        pp.run_generation(app, nid, ids[:2], cfg)  # two pictures made, then the server stops
        db.session.get(DownloadNotification, nid).status = "processing"
        db.session.get(DownloadNotification, nid).message = pp.progress_message(2, 5)
        db.session.commit()
        pp._write_job(nid, ids, cfg)  # (the stopped run left its file)
        db.session.delete(db.session.get(Agent, ids[4]))  # an agent removed meanwhile is skipped
        db.session.commit()
        assert pp.resume_interrupted(app) == [nid]
        import time

        for _ in range(100):
            db.session.expire_all()
            if db.session.get(DownloadNotification, nid).status == "ready":
                break
            time.sleep(0.1)
        row = db.session.get(DownloadNotification, nid)
        assert row.status == "ready" and row.message == "4 profile pictures generated."
        assert sorted(os.listdir(media)) == sorted(f"{i}.png" for i in ids[:4])
        assert not os.path.exists(pp._job_file(nid))  # nothing left to resume


def test_finished_or_unknown_jobs_are_only_cleaned_up(app, media):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp
    from y_web.src.models import DownloadNotification

    with app.app_context():
        _, agents = _standard_population(db, n=2)
        done = _notification(db)
        db.session.get(DownloadNotification, done).status = "cancelled"
        db.session.commit()
        pp._write_job(done, [a.id for a in agents], {"generator": "stub"})
        pp._write_job(9999, [a.id for a in agents], {"generator": "stub"})  # no such notification
        os.makedirs(pp.jobs_dir(), exist_ok=True)
        open(os.path.join(pp.jobs_dir(), "7.json"), "w").write("not json")
        assert pp.resume_interrupted(app) == []
        assert os.listdir(pp.jobs_dir()) == []
        assert not media.exists() or os.listdir(media) == []


def test_a_started_job_leaves_its_file_until_it_ends(app, media):
    from y_web import db
    from y_web.src.agents import profile_pictures as pp

    with app.app_context():
        _, agents = _standard_population(db, n=2)
        nid, thread = pp.start_generation(app, 1, [a.id for a in agents], {"generator": "stub"})
        thread.join(10)
        assert not os.path.exists(pp._job_file(nid))


def test_client_creation_pages_do_not_filter_populations_by_platform():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    crud = (root / "routes/admin/sub/clients/_crud.py").read_text()
    assert "population_matches_platform" not in crud and "incompatible_population_count" not in crud
    for page in (root / "templates/admin").glob("clients*.html"):
        text = page.read_text()
        assert "incompatible_population" not in text and "username type" not in text, page.name
        assert "populations for other platforms" not in text, page.name
