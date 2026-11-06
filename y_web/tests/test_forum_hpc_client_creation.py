"""Creating a client of a forum experiment on YForum (HPC) through the dedicated page and route (plan F12)."""

import importlib
import json
import sys

import pytest

from y_web.tests.test_forum_hpc_experiment_creation import (
    FORM,
    YFORUM,
    _app_and_client,
    _availability,
)


def _yforum():
    if not (YFORUM / "YForum" / "config_validation.py").exists():
        pytest.skip("external/YForum is not checked out")
    pytest.importorskip("jsonschema")
    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.config_validation import validate
        from YForum.YClient.population import load_population
    finally:
        sys.path.remove(str(YFORUM))
    return validate, load_population


def _pin_paths(monkeypatch, tmp_path):
    module = importlib.import_module("y_web.routes.admin.sub.clients._forum_hpc")
    monkeypatch.setattr(module, "get_writable_path", lambda *a: str(tmp_path))


def _seed(app, http, **form):
    from y_web import db
    from y_web.src.models import (
        Agent,
        Agent_Population,
        Exp_Topic,
        Exps,
        Population,
        Topic_List,
    )

    assert (
        http.post("/admin/create_experiment", data={**FORM, **form}).status_code == 302
    )
    with app.app_context():
        exp = db.session.query(Exps).filter_by(exp_name=FORM["exp_name"]).one()
        for name in ("politics", "sport"):
            topic = db.session.query(Topic_List).filter_by(name=name).first()
            if topic is None:
                topic = Topic_List(name=name)
                db.session.add(topic)
                db.session.flush()
            if (
                not db.session.query(Exp_Topic)
                .filter_by(exp_id=exp.idexp, topic_id=topic.id)
                .count()
            ):
                db.session.add(Exp_Topic(exp_id=exp.idexp, topic_id=topic.id))
        pop = Population(name="pop", descr="p", username_type="forum")
        db.session.add(pop)
        db.session.flush()
        for i in (1, 2, 3):
            ag = Agent(
                name=f"u{i}",
                age=30 + i,
                leaning="center",
                language="en",
                gender="f",
                education_level="x",
                toxicity="none",
                round_actions="3",
                nationality="it",
            )
            db.session.add(ag)
            db.session.flush()
            db.session.add(Agent_Population(agent_id=ag.id, population_id=pop.id))
        db.session.commit()
        return exp.idexp, pop.id, exp.db_name.split("/")[1]


def _confirm(tmp_path, folder):
    path = tmp_path / "y_web" / "experiments" / folder / "server_config.json"
    config = json.loads(path.read_text())
    config["experiment_configuration_confirmed"] = True
    path.write_text(json.dumps(config))


@pytest.mark.integration
def test_the_dispatcher_and_the_generic_route_send_forum_hpc_to_the_dedicated_page(
    monkeypatch, tmp_path
):
    _yforum()
    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    idexp, pop_id, _folder = _seed(app, http)
    assert (
        http.get(f"/admin/clients/{idexp}")
        .headers["Location"]
        .endswith(f"/admin/clients_forum_hpc/{idexp}")
    )
    generic = http.get(f"/admin/clients_hpc/{idexp}")
    assert generic.headers["Location"].endswith(f"/admin/clients_forum_hpc/{idexp}")
    refused = http.post(
        "/admin/create_hpc_client",
        data={"id_exp": idexp, "name": "x", "population_id": pop_id},
    )
    assert refused.headers["Location"].endswith(f"/admin/clients_forum_hpc/{idexp}")


@pytest.mark.integration
def test_a_forum_client_is_created_with_a_valid_configuration(monkeypatch, tmp_path):
    validate, load_population = _yforum()
    from y_web import db
    from y_web.src.models import Client, Client_Execution, Population_Experiment

    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    idexp, pop_id, folder = _seed(app, http, llm_agents_enabled="")
    _confirm(tmp_path, folder)

    page = http.get(f"/admin/clients_forum_hpc/{idexp}")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "create_forum_hpc_client" in html and 'name="likelihood_post"' in html
    assert 'name="llm_model"' not in html  # rule-based agents: no model fields

    response = http.post(
        "/admin/create_forum_hpc_client",
        data={
            "id_exp": idexp,
            "name": "c1",
            "descr": "d",
            "population_id": pop_id,
            "days": "2",
            "likelihood_post": "0.3",
        },
    )
    assert response.status_code == 302
    with http.session_transaction() as sess:
        flashed = sess.get("_flashes")
    assert response.headers["Location"].endswith(
        f"/admin/experiment_details/{idexp}"
    ), flashed

    exp_dir = tmp_path / "y_web" / "experiments" / folder
    config = validate(
        json.loads((exp_dir / "client_c1-pop.json").read_text()), "config/client_config"
    )
    assert config["mode"] == "rule_based" and config["num_days"] == 2
    assert config["simulation"]["actions_likelihood"]["post"] == 0.3
    profiles, _generation = load_population(exp_dir / "pop.json", "auto", "admin")
    assert sorted(p.name for p in profiles) == ["u1", "u2", "u3"]

    with app.app_context():
        client = db.session.query(Client).filter_by(id_exp=idexp).one()
        assert client.name == "c1" and client.days == 2 and client.status == 0
        execution = (
            db.session.query(Client_Execution).filter_by(client_id=client.id).one()
        )
        assert execution.expected_duration_rounds == 2 * config["num_slots_per_day"]
        assert (
            db.session.query(Population_Experiment).filter_by(id_exp=idexp).count() == 1
        )


@pytest.mark.integration
def test_bad_settings_and_duplicates_leave_nothing_behind(monkeypatch, tmp_path):
    _yforum()
    from y_web import db
    from y_web.src.models import Client

    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    idexp, pop_id, folder = _seed(app, http, llm_agents_enabled="")
    _confirm(tmp_path, folder)
    base = {"id_exp": idexp, "name": "c", "population_id": pop_id}

    for bad in ({"days": "0"}, {"probability_of_daily_follow": "2"}):
        http.post("/admin/create_forum_hpc_client", data={**base, **bad})
    http.post("/admin/create_forum_hpc_client", data={**base, "population_id": "999"})
    exp_dir = tmp_path / "y_web" / "experiments" / folder
    assert not list(exp_dir.glob("client_*.json"))
    with app.app_context():
        assert db.session.query(Client).filter_by(id_exp=idexp).count() == 0

    http.post("/admin/create_forum_hpc_client", data=base)
    http.post("/admin/create_forum_hpc_client", data=base)  # same name and population
    with app.app_context():
        assert db.session.query(Client).filter_by(id_exp=idexp).count() == 1


@pytest.mark.integration
def test_a_non_forum_hpc_experiment_is_refused(monkeypatch, tmp_path):
    _availability(monkeypatch, forum_hpc=True, forum=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    idexp, pop_id, _folder = _seed(app, http, simulator_type="Standard")
    response = http.post(
        "/admin/create_forum_hpc_client",
        data={"id_exp": idexp, "name": "c", "population_id": pop_id},
    )
    assert response.status_code == 302
    assert "clients_forum_hpc" not in response.headers["Location"]
