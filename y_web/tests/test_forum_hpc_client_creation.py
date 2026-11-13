"""Creating a client of a forum experiment on YForum (HPC) through the dedicated page and route (plan F12)."""

import importlib
import json
import sys
from pathlib import Path

import pytest

from y_web.tests._platform_repos import forum_file
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


def _needs_flask_forum_pair():
    """The standard forum is served by the YServerReddit / YClientReddit pair: without them (a clean checkout)
    its experiment database cannot be created."""
    root = Path(__file__).resolve().parents[2] / "external"
    if not (root / "YServerReddit").is_dir() or not (root / "YClientReddit").is_dir():
        pytest.skip("YServerReddit / YClientReddit are not installed")


def _pin_paths(monkeypatch, tmp_path):
    module = importlib.import_module("y_web.routes.admin.sub.clients._forum_hpc")
    monkeypatch.setattr(module, "get_writable_path", lambda *a: str(tmp_path))


def _seed(app, http, **form):
    from y_web import db
    from y_web.src.models import (
        Agent,
        Agent_Custom_Feature,
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
            if i == 1:  # structured interests, opinions and free features of an agent
                for kind, key, value in (
                    ("interest", "politics", None),
                    ("custom", "hobby", "chess"),
                ):
                    db.session.add(
                        Agent_Custom_Feature(
                            agent_id=ag.id, feature_type=kind, key=key, value=value
                        )
                    )
        db.session.commit()
        return exp.idexp, pop.id, exp.db_name.split("/")[1]


def _confirm(tmp_path, folder):
    path = tmp_path / "y_web" / "experiments" / folder / "server_config.json"
    config = json.loads(path.read_text())
    config["experiment_configuration_confirmed"] = True
    path.write_text(json.dumps(config))


@pytest.mark.integration
def test_the_standard_forum_page_has_no_archetypes_either():
    html = Path(forum_file("y_web/templates/admin/clients_forum.html")).read_text()
    assert "archetype" not in html.lower()  # YClientReddit does not implement them


def test_the_page_offers_every_field_of_the_standard_forum_page():
    """Every field of clients_forum.html is on the forum-HPC page, except the three YForum does not implement."""
    import re

    templates = Path(forum_file("y_web/templates/admin/clients_forum.html")).parent
    names = lambda f: set(
        re.findall(r'name="([a-z_0-9]+)"', (templates / f).read_text())
    )
    standard, hpc = names("clients_forum.html"), names("clients_forum_hpc.html")
    not_implemented = {
        "clock_mode",
        "clock_timezone",
        "clock_feed_refresh",
    }
    assert standard - hpc - not_implemented == set()
    assert hpc - standard == set()


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
    assert "create_forum_hpc_client" in html and 'name="post"' in html
    assert 'name="user_type"' not in html  # rule-based agents: no model field
    assert 'name="hourly_8"' in html and 'name="memory_pair_limit"' not in html
    assert 'name="clock_mode"' not in html and 'name="infinite_duration"' in html
    assert "archetype" not in html.lower()

    response = http.post(
        "/admin/create_forum_hpc_client",
        data={
            "id_exp": idexp,
            "name": "c1",
            "descr": "d",
            "population_id": pop_id,
            "days": "2",
            "post": "4",
            # the first option of each list of the form
            "recsys_type": "ContentRecSys",
            "frecsys_type": "FollowRecSys",
        },
    )
    assert response.status_code == 302
    with http.session_transaction() as sess:
        flashed = sess.get("_flashes")
    # the experiment has opinion dynamics on: the opinions are set on the dedicated page, as on every platform
    assert response.headers["Location"].startswith(
        f"/admin/opinion_configuration_hpc/{idexp}?client_id="
    ), flashed

    exp_dir = tmp_path / "y_web" / "experiments" / folder
    config = validate(
        json.loads((exp_dir / "client_c1-pop.json").read_text()), "config/client_config"
    )
    assert config["mode"] == "rule_based" and config["num_days"] == 2
    assert config["simulation"]["actions_likelihood"]["post"] == 0.4
    profiles, _generation = load_population(exp_dir / "pop.json", "auto", "admin")
    assert sorted(p.name for p in profiles) == ["u1", "u2", "u3"]
    agents = json.loads((exp_dir / "pop.json").read_text())["agents"]
    first = next(a for a in agents if a["username"] == "u1")
    assert first["custom_features"] == {
        "hobby": "chess"
    }  # plain values, not database rows

    assert [
        a["recsys_type"]
        for a in json.loads((exp_dir / "pop.json").read_text())["agents"]
    ] == ["random"] * 3
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
def test_llm_agents_choose_the_model_in_the_form_and_get_it_in_the_configuration(
    monkeypatch, tmp_path
):
    validate, _load = _yforum()
    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    idexp, pop_id, folder = _seed(
        app, http
    )  # the experiment uses language-model agents
    _confirm(tmp_path, folder)
    html = http.get(f"/admin/clients_forum_hpc/{idexp}").get_data(as_text=True)
    assert 'name="user_type"' in html and 'name="llm_v_agent"' in html
    base = {"id_exp": idexp, "name": "l1", "population_id": pop_id}
    http.post("/admin/create_forum_hpc_client", data=base)  # no model: refused
    exp_dir = tmp_path / "y_web" / "experiments" / folder
    assert not list(exp_dir.glob("client_*.json"))
    # the form posts the standard defaults: -1 tokens (no limit) must not be refused
    http.post(
        "/admin/create_forum_hpc_client",
        data={
            **base,
            "user_type": "llama3.2",
            "llm": "http://127.0.0.1:11434/v1",
            "llm_api_key": "NULL",
            "llm_max_tokens": "-1",
            "llm_temperature": "1.5",
            "llm_v_max_tokens": "300",
        },
    )
    config = validate(
        json.loads((exp_dir / "client_l1-pop.json").read_text()), "config/client_config"
    )
    assert config["mode"] == "llm" and config["agents"]["llm_agents"] == ["llama3.2"]
    assert config["servers"]["llm_max_tokens"] == 800  # no limit keeps YForum's default


@pytest.mark.integration
def test_a_client_can_run_until_stopped(monkeypatch, tmp_path):
    validate, _load = _yforum()
    from y_web import db
    from y_web.src.models import Client, Client_Execution

    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    idexp, pop_id, folder = _seed(app, http, llm_agents_enabled="")
    _confirm(tmp_path, folder)
    response = http.post(
        "/admin/create_forum_hpc_client",
        data={
            "id_exp": idexp,
            "name": "endless",
            "population_id": pop_id,
            "days": "-1",
            "infinite_duration": "on",
        },
    )
    assert response.status_code == 302
    exp_dir = tmp_path / "y_web" / "experiments" / folder
    config = validate(
        json.loads((exp_dir / "client_endless-pop.json").read_text()),
        "config/client_config",
    )
    assert config["num_days"] == 0  # YForum: until stopped
    with app.app_context():
        client = db.session.query(Client).filter_by(id_exp=idexp).one()
        assert client.days == -1
        execution = (
            db.session.query(Client_Execution).filter_by(client_id=client.id).one()
        )
        assert execution.expected_duration_rounds == -1


@pytest.mark.integration
def test_a_network_model_writes_the_initial_follow_network(monkeypatch, tmp_path):
    validate, _load = _yforum()
    from y_web import db
    from y_web.src.models import Client

    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    idexp, pop_id, folder = _seed(app, http, llm_agents_enabled="")
    _confirm(tmp_path, folder)
    http.post(
        "/admin/create_forum_hpc_client",
        data={
            "id_exp": idexp,
            "name": "net",
            "population_id": pop_id,
            "network_model": "ER",
            "network_p": "1",
        },
    )
    exp_dir = tmp_path / "y_web" / "experiments" / folder
    config = validate(
        json.loads((exp_dir / "client_net-pop.json").read_text()),
        "config/client_config",
    )
    assert config["population"]["network_file"] == "net_network.csv"
    pairs = {
        tuple(l.split(",")) for l in (exp_dir / "net_network.csv").read_text().split()
    }
    assert ("u1", "u2") in pairs and ("u2", "u1") in pairs
    with app.app_context():
        assert (
            db.session.query(Client).filter_by(id_exp=idexp).one().network_type == "ER"
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
    _needs_flask_forum_pair()
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


@pytest.mark.integration
def test_the_opinions_are_set_on_the_dedicated_page_and_reach_yforum(
    monkeypatch, tmp_path
):
    """Opinion dynamics on: creation leads to the opinion page; saving it writes the population and YForum's own keys."""
    validate, load_population = _yforum()
    from y_web import db
    from y_web.src.models import Topic_List

    _availability(monkeypatch, forum_hpc=True)
    app, http = _app_and_client(monkeypatch, tmp_path)
    _pin_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path)
    )
    idexp, pop_id, folder = _seed(
        app, http, llm_agents_enabled="", opinion_dynamics_enabled="on"
    )
    _confirm(tmp_path, folder)

    response = http.post(
        "/admin/create_forum_hpc_client",
        data={
            "id_exp": idexp,
            "name": "c1",
            "descr": "d",
            "population_id": pop_id,
            "days": "1",
            "recsys_type": "ContentRecSys",
            "frecsys_type": "FollowRecSys",
        },
    )
    assert response.status_code == 302
    location = response.headers["Location"]
    assert f"/admin/opinion_configuration_hpc/{idexp}" in location, location
    page = http.get(location)
    assert page.status_code == 200 and b"Traceback" not in page.data

    client_id = location.split("client_id=")[1]
    with app.app_context():
        politics = db.session.query(Topic_List).filter_by(name="politics").one().id
    saved = http.post(
        "/admin/set_hpc_opinion_distributions",
        data={
            "idexp": idexp,
            "client_id": client_id,
            "segmentation": "",
            "update_rule": "bounded_confidence",
            "bc_epsilon": "0.3",
            "bc_mu": "0.4",
            "bc_theta": "0",
            "bc_cold_start": "neutral",
            f"dist_topic_{politics}_segment_0": "none-such",
        },
    )
    assert saved.status_code == 302

    exp_dir = tmp_path / "y_web" / "experiments" / folder
    raw = json.loads((exp_dir / "client_c1-pop.json").read_text())
    assert "opinion_dynamics" not in raw  # not YForum's shape
    config = validate(raw, "config/client_config")  # the strict schema accepts it
    assert config["simulation"]["opinion_dynamics"] == {
        "enabled": True,
        "model_name": "bounded_confidence",
        "parameters": {
            "epsilon": 0.3,
            "mu": 0.4,
            "theta": 0.0,
            "cold_start": "neutral",
        },
    }
    profiles, _generation = load_population(exp_dir / "pop.json", "auto", "admin")
    first = next(p for p in profiles if p.name == "u1")
    assert set(first.opinions) == {"politics"} and 0 <= first.opinions["politics"] <= 1
