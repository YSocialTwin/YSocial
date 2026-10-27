"""IM client form, config builders and creation route (plan, Phase 5)."""

import functools
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
IM_REPO = ROOT / "external" / "YInstantMessaging"


def _agent(i=1, **kw):
    base = dict(
        id=i, name=f"ann{i}", leaning="center", age=30, language="en",
        education_level="bachelor", gender="f", nationality="it", profession="nurse",
        toxicity="none", daily_activity_level=2, round_actions="3",
        oe="high", co=None, ex="", ag="low", ne=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_form_defaults_and_validation():
    from y_web.src.im.client_config import ImClientFormError, parse_client_form

    s = parse_client_form({})
    assert s["backend"] == "echo" and s["days"] == 1 and s["seed"] > 0
    assert s["opinion_enabled"] is False and s["advanced"] is None
    for bad in (
        {"llm_backend": "gpt"},
        {"days": "0"},
        {"llm_api_key_env": "sk-abc def"},
        {"advanced_json": "[1]"},
        {"advanced_json": "{oops"},
    ):
        with pytest.raises(ImClientFormError):
            parse_client_form(bad)


def test_config_never_carries_runtime_keys_or_secrets():
    from y_web.src.im.client_config import build_client_config, parse_client_form

    s = parse_client_form(
        {"days": "2", "seed": "5", "advanced_json": json.dumps(
            {"client_id": "x", "namespace": "n", "llm": {"llm_api_key": "SECRET", "model": "m"}})}
    )
    cfg = build_client_config(client_name="c", settings=s, topics=["a", " "], activity_profiles={"p": "1,2"},
                              prompt_language="it")
    assert cfg["seed"] == 5 and cfg["simulation"]["num_days"] == 2
    assert cfg["simulation"]["discussion_topics"] == ["a"]
    assert cfg["telegram"]["topics"]["catalog_file"] == "topic_catalog.json"
    assert cfg["prompt_language"] == "it" and cfg["llm"]["model"] == "m"
    assert "client_id" not in cfg and "namespace" not in cfg
    assert "SECRET" not in json.dumps(cfg)


def test_agent_mapper_writes_only_read_fields_and_dict_interests():
    from y_web.src.im.client_config import build_agent

    a = build_agent(_agent(), interests=["t1", "t2"], activity_profile="Always On",
                    structured={"custom_features": {"k": 1}}, opinions_enabled=True)
    assert a["id"] == "agent-1" and a["interests"] == {"t1": 1.0, "t2": 1.0}
    assert a["round_actions"] == 3 and a["oe"] == "high" and "co" not in a and "ex" not in a
    assert a["custom_features"] == {"k": 1} and set(a["opinions"]) == {"t1", "t2"}
    assert "opinions" not in build_agent(_agent(), interests=["t1"], activity_profile="x")


def test_page_mapper_and_uniqueness():
    from y_web.src.im.client_config import ImClientFormError, build_agent, build_page, check_unique

    page = SimpleNamespace(id=4, name="News", leaning="left", feed="http://f")
    p = build_page(page, topics=["t"], activity_profile="Always On")
    assert p["id"] == "page-4" and p["is_page"] == 1 and p["feed_url"] == "http://f"
    check_unique([p, build_agent(_agent(), interests=["t"], activity_profile="x")])
    with pytest.raises(ImClientFormError):
        check_unique([build_agent(_agent(1), interests=["t"], activity_profile="x"),
                      build_agent(_agent(2, name="ANN1"), interests=["t"], activity_profile="x")])


def test_topic_catalog_is_deterministic_and_requires_topics():
    from y_web.src.im.client_config import ImClientFormError, build_topic_catalog

    assert build_topic_catalog({"a b": 1.0, "c": 0.5}) == build_topic_catalog({"a b": 1.0, "c": 0.5})
    with pytest.raises(ImClientFormError):
        build_topic_catalog({})


def test_im_is_a_valid_population_type():
    from y_web.src.agents.platform import VALID_POPULATION_TYPES

    assert "instant_messaging" in VALID_POPULATION_TYPES


# -- route ---------------------------------------------------------------------------------------
@pytest.fixture
def env(app, monkeypatch, tmp_path):
    from y_web.routes.admin.sub.clients import _im
    from y_web.routes.admin.sub.experiments import _crud as ecrud

    monkeypatch.setattr(ecrud, "check_privileges", lambda *_: None)
    monkeypatch.setattr(ecrud, "current_user", SimpleNamespace(username="admin", id=1))
    monkeypatch.setattr(ecrud, "get_suggested_port", lambda: 5099)
    monkeypatch.setattr(ecrud, "url_for", lambda endpoint, **kw: f"/{endpoint}")
    monkeypatch.setattr(ecrud, "flash", lambda *a, **k: None)
    monkeypatch.setattr(ecrud, "_external_repo_availability",
                        lambda: {"instant_messaging": True, "microblogging": True, "hpc": True,
                                 "forum": True, "photo_sharing": True})
    monkeypatch.setattr(ecrud, "Jupyter_instances", functools.partial(ecrud.Jupyter_instances, process=0))
    monkeypatch.setattr("y_web.src.telemetry.Telemetry", lambda **kw: MagicMock())
    monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
    monkeypatch.setattr(_im, "get_writable_path", lambda *a: str(tmp_path))
    monkeypatch.setattr(_im, "check_privileges", lambda *_: None)
    monkeypatch.setattr(_im, "current_user", SimpleNamespace(username="admin", id=1))
    monkeypatch.setattr(_im, "url_for", lambda endpoint, **kw: f"/{endpoint}")
    flashes = []
    monkeypatch.setattr(_im, "flash", lambda msg, cat="message": flashes.append((cat, str(msg))))
    monkeypatch.setattr(_im, "get_external_repo_dir", lambda name: str(IM_REPO))
    return SimpleNamespace(im=_im, ecrud=ecrud, flashes=flashes, tmp=tmp_path)


def _seed(app, env):
    from y_web import db
    from y_web.src.models import (Agent, Agent_Population, Exp_Topic, Exps, Page, Page_Population,
                                  Population, Topic_List)

    form = {"exp_name": "im", "exp_descr": "d", "platform_type": "instant_messaging",
            "simulator_type": "Standard", "tags": "politics,health", "llm_agents_enabled": "true"}
    with app.test_request_context("/admin/create_experiment", method="POST", data=form):
        env.ecrud.create_experiment.__wrapped__()
    exp = db.session.query(Exps).one()
    for name in ("politics", "health"):
        topic = Topic_List(name=name)
        db.session.add(topic)
        db.session.flush()
        db.session.add(Exp_Topic(exp_id=exp.idexp, topic_id=topic.id))
    pop = Population(name="pop", descr="p", username_type="instant_messaging")
    db.session.add(pop)
    db.session.flush()
    for i in (1, 2):
        ag = Agent(name=f"u{i}", age=30 + i, leaning="center", language="en", gender="f",
                   education_level="x", toxicity="none", round_actions="3", nationality="it")
        db.session.add(ag)
        db.session.flush()
        db.session.add(Agent_Population(agent_id=ag.id, population_id=pop.id))
    pg = Page(name="news", page_type="news", feed="http://f", leaning="")
    db.session.add(pg)
    db.session.flush()
    db.session.add(Page_Population(page_id=pg.id, population_id=pop.id))
    db.session.commit()
    return exp, pop


def _post(app, env, exp, pop, **form):
    data = {"id_exp": str(exp.idexp), "name": "cl", "descr": "", "population_id": str(pop.id),
            "days": "2", "seed": "11", "llm_backend": "echo"}
    data.update(form)
    with app.test_request_context("/admin/create_im_client", method="POST", data=data):
        return env.im.create_im_client_route.__wrapped__()


def test_create_im_client_writes_files_and_rows(app, env):
    from y_web import db
    from y_web.src.models import Client, Client_Execution

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop)
        assert not [f for f in env.flashes if f[0] == 'error'], env.flashes
        folder = env.im._experiment_folder(exp)
        cfg = json.loads(Path(folder, "client_cl-pop.json").read_text())
        assert cfg["seed"] == 11 and cfg["simulation"]["num_days"] == 2
        agents = json.loads(Path(folder, "pop.json").read_text())["agents"]
        assert [a["id"] for a in agents] == ["agent-1", "agent-2", "page-1"]
        assert all(isinstance(a["interests"], dict) for a in agents)
        catalog = json.loads(Path(folder, "topic_catalog.json").read_text())
        assert catalog["topics"]
        client = db.session.query(Client).one()
        assert client.days == 2 and client.id_exp == exp.idexp
        assert db.session.query(Client_Execution).one().expected_duration_rounds == 48
        assert Path(folder, "prompt_language.json").is_file()
        # a second client with the same name and population is refused, nothing is overwritten
        _post(app, env, exp, pop)
        assert db.session.query(Client).count() == 1
        assert any("already exists" in m for _, m in env.flashes)


def test_bad_settings_leave_nothing_behind(app, env):
    from y_web import db
    from y_web.src.models import Client

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="0")
        _post(app, env, exp, pop, llm_api_key_env="not a name")
        assert db.session.query(Client).count() == 0
        assert not list(Path(env.im._experiment_folder(exp)).glob("client_*"))
        assert any("Invalid client settings" in m for _, m in env.flashes)


def test_non_im_experiment_is_refused(app, env):
    from y_web import db
    from y_web.src.models import Client

    with app.app_context():
        exp, pop = _seed(app, env)
        exp.platform_type = "microblogging"
        db.session.commit()
        _post(app, env, exp, pop)
        assert db.session.query(Client).count() == 0
        assert any("not an instant messaging" in m for _, m in env.flashes)


def test_population_of_another_platform_is_refused(app, env):
    from y_web import db
    from y_web.src.models import Client

    with app.app_context():
        exp, pop = _seed(app, env)
        pop.username_type = "microblogging"
        db.session.commit()
        _post(app, env, exp, pop)
        assert db.session.query(Client).count() == 0
        assert any("incompatible" in m for _, m in env.flashes)
