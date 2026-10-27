"""The dedicated opinion page of an IM client: shown only with the toggle on, writes IM's own keys."""

import json
import uuid

import pytest

from y_web.tests.test_im_admin_pages import im_app  # noqa: F401  (fixture)

pytestmark = pytest.mark.integration


def _setup(app, tmp_path, *, opinion):
    """An IM experiment with a population file and one client, as the client form leaves them."""
    from y_web import db
    from y_web.src.im.client_config import build_agent, build_client_config, parse_client_form
    from y_web.src.im.experiment_config import apply_experiment_switches
    from y_web.src.im.client_config import build_page
    from y_web.src.models import Client, Exps, Population
    from types import SimpleNamespace

    with app.app_context():
        folder_name = uuid.uuid4().hex
        exp = Exps(
            exp_name="im opinion", platform_type="instant_messaging", simulator_type="HPC",
            db_name=f"experiments/{folder_name}/database_server.db", owner="adm", exp_descr="d", status=0,
            port=5097, server="127.0.0.1", prompt_language="en", llm_agents_enabled=1,
        )
        pop = Population(name="two words", descr="p", username_type="instant_messaging")
        db.session.add_all([exp, pop])
        db.session.commit()
        folder = tmp_path / "y_web" / "experiments" / folder_name
        folder.mkdir(parents=True)
        server = apply_experiment_switches({"simulation": {}}, opinion=opinion)
        (folder / "server_config.json").write_text(json.dumps(server))
        agent = SimpleNamespace(id=1, name="ann", leaning="left", age=30, language="en", education_level="bachelor",
                                gender="f", nationality="it", profession="x", toxicity="none",
                                daily_activity_level=2, round_actions="3", oe=None, co=None, ex=None, ag=None, ne=None)
        accounts = [build_agent(agent, interests=["politics"], activity_profile="Always On", opinions_enabled=True)]
        # IM keeps the population name as it is, spaces included
        (folder / "two words.json").write_text(json.dumps({"agents": accounts}))
        settings = parse_client_form({"opinion_enabled": "true"})
        cfg = build_client_config(client_name="cl", settings=settings, topics=["politics"], activity_profiles={"p": "1"})
        (folder / "client_cl-two words.json").write_text(json.dumps(cfg))
        client = Client(name="cl", descr="", id_exp=exp.idexp, population_id=pop.id, days=1, status=0)
        db.session.add(client)
        db.session.commit()
        return exp.idexp, client.id, folder


def test_page_is_refused_without_the_toggle_and_rendered_with_it(im_app, monkeypatch, tmp_path):
    app, http = im_app
    monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
    exp_id, client_id, _folder = _setup(app, tmp_path, opinion=False)
    response = http.get(f"/admin/opinion_configuration_im/{exp_id}?client_id={client_id}")
    assert response.status_code == 302 and "experiment_details" in response.headers["Location"]

    exp_id, client_id, _folder = _setup(app, tmp_path, opinion=True)
    page = http.get(f"/admin/opinion_configuration_im/{exp_id}?client_id={client_id}")
    assert page.status_code == 200 and b"Traceback" not in page.data
    html = page.data.decode()
    assert "/admin/set_im_opinion_distributions" in html and "interlocutor_and_friends" not in html
    # the other families send an IM experiment here
    other = http.get(f"/admin/opinion_configuration_hpc/{exp_id}?client_id={client_id}")
    assert other.status_code == 302 and "opinion_configuration_im" in other.headers["Location"]
    # the details page links to it, per client, only with the toggle on
    details = http.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert f"/admin/opinion_configuration_im/{exp_id}?client_id={client_id}" in details


def test_saving_writes_distributions_and_im_opinion_keys(im_app, monkeypatch, tmp_path):
    app, http = im_app
    monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
    exp_id, client_id, folder = _setup(app, tmp_path, opinion=True)
    from y_web import db
    from y_web.src.models import OpinionDistribution, Topic_List, Exp_Topic

    with app.app_context():
        topic = Topic_List(name="politics")
        db.session.add(topic)
        db.session.flush()
        db.session.add(Exp_Topic(exp_id=exp_id, topic_id=topic.id))
        dist = db.session.query(OpinionDistribution).first()
        if dist is None:
            dist = OpinionDistribution(name="flat", distribution_type="uniform", parameters="{}")
            db.session.add(dist)
        db.session.commit()
        topic_id, dist_name = topic.id, dist.name
    response = http.post(
        "/admin/set_im_opinion_distributions",
        data={"idexp": exp_id, "client_id": client_id, "segmentation": "", "update_rule": "bounded_confidence",
              "bc_epsilon": "0.3", "bc_mu": "0.4", "bc_theta": "0.1", "bc_cold_start": "inherited",
              f"dist_topic_{topic_id}_segment_0": dist_name},
    )
    assert response.status_code == 302
    cfg = json.loads((folder / "client_cl-two words.json").read_text())
    block = cfg["opinion_dynamics"]
    assert block["enabled"] is True and block["model_name"] == "bounded_confidence"
    assert block["parameters"] == {"epsilon": 0.3, "mu": 0.4, "theta": 0.1, "cold_start": "inherited"}
    assert block["opinion_groups"]
    agent = json.loads((folder / "two words.json").read_text())["agents"][0]
    assert 0.0 <= agent["opinions"]["politics"] <= 1.0
    # and what is written is valid for IM
    from pathlib import Path

    from y_web.src.im.client_config import schema_errors

    schema = Path(__file__).resolve().parents[2] / "external" / "YInstantMessaging" / "schemas" / "config" / "client_config.json"
    assert schema_errors(cfg, str(schema)) == []
