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
        {"start_date": "tomorrow"},
        {"adv.telegram.reactive.probability": "2"},
        {"adv.telegram.discovery.mode": "psychic"},
        {"memory_enabled": "true", "adv.agents.memory_high_affect_uncertain_low": "0.9",
         "adv.agents.memory_high_affect_uncertain_high": "0.2"},
    ):
        with pytest.raises(ImClientFormError):
            parse_client_form(bad)


def test_config_never_carries_runtime_keys_or_secrets():
    from y_web.src.im.client_config import build_client_config, parse_client_form

    s = parse_client_form(
        {"days": "2", "seed": "5", "llm": "localhost:11434/v1", "llm_model": "m",
         "adv.telegram.reactive.enabled__present": "1", "adv.telegram.reactive.probability": "0.4"}
    )
    cfg = build_client_config(client_name="c", settings=s, topics=["a", " "], activity_profiles={"p": "1,2"},
                              prompt_language="it")
    assert cfg["seed"] == 5 and cfg["simulation"]["num_days"] == 2
    assert cfg["logging"] == {"compress_rotated": False}  # YWeb reads plain rotated logs
    assert cfg["simulation"]["discussion_topics"] == ["a"]
    assert cfg["telegram"]["topics"]["catalog_file"] == "topic_catalog.json"
    assert cfg["prompt_language"] == "it" and cfg["llm"]["model"] == "m"
    assert cfg["llm"]["address"] == "http://localhost:11434"
    assert cfg["telegram"]["reactive"] == {"enabled": False, "probability": 0.4}
    assert "client_id" not in cfg and "namespace" not in cfg and "llm_api_key" not in cfg["llm"]


def test_llm_url_maps_to_the_address_im_expects():
    from y_web.src.im.client_config import split_llm_url

    assert split_llm_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434"
    assert split_llm_url("localhost:8000/") == "http://localhost:8000"
    assert split_llm_url("https://api.example.org/v1/") == "https://api.example.org"
    assert split_llm_url("  ") is None


def test_memory_fields_are_read_only_when_memory_is_on():
    from y_web.src.im.client_config import parse_client_form

    form = {"adv.agents.memory_total_max_chars": "900", "adv.agents.memory_forget_deleted__present": "1",
            "adv.agents.memory_forget_deleted": "true"}
    assert parse_client_form(form)["advanced"] is None
    on = parse_client_form({**form, "memory_enabled": "true"})["advanced"]
    assert on == {"agents": {"memory_total_max_chars": 900, "memory_forget_deleted": True}}


def test_structured_advanced_table_matches_im_schema():
    """Every field of the form exists in IM's schema, with the same default and compatible bounds."""
    from y_web.src.im import advanced_settings as adv

    schema = json.loads((IM_REPO / "schemas" / "config" / "client_config.json").read_text())
    for path, kind, label, default, bounds in adv.all_fields():
        node = schema
        keys = path.split(".")
        for i, key in enumerate(keys):
            if "properties" not in node:
                # a free-form object (a map): the key lives in its default, the bounds in additionalProperties
                assert node.get("default", {}).get(key, default) == default, path
                node = node.get("additionalProperties", {})
                break
            assert key in node["properties"], path
            node = node["properties"][key]
        if "default" in node and i == len(keys) - 1:
            assert node["default"] == default, (path, node["default"], default)
        if kind == "choice":
            assert set(node["enum"]) == set(bounds), path
        if kind in ("int", "float") and "minimum" in node:
            assert bounds[0] >= node["minimum"], path
        if kind in ("int", "float") and "maximum" in node:
            assert bounds[1] <= node["maximum"], path


def test_default_advanced_form_builds_a_schema_valid_config():
    from y_web.src.im import advanced_settings as adv
    from y_web.src.im.client_config import build_client_config, parse_client_form, schema_errors

    form = {"memory_enabled": "true"}
    for path, kind, _label, default, _bounds in adv.all_fields():
        if kind == "bool":
            form[adv.field_name(path) + "__present"] = "1"
            if default:
                form[adv.field_name(path)] = "true"
        else:
            form[adv.field_name(path)] = str(default)
    settings = parse_client_form(form)
    cfg = build_client_config(client_name="c", settings=settings, topics=["a"], activity_profiles={"p": "1"})
    assert schema_errors(cfg, str(IM_REPO / "schemas" / "config" / "client_config.json")) == []
    assert cfg["telegram"]["actions_likelihood"]["post"] == 2.0 and cfg["agents"]["memory_backend"] == "hybrid_semantic"


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


def test_experiment_switches_and_time_parameters_come_through_the_server_config(app, env):
    from y_web.src.im.experiment_config import apply_experiment_switches, load_server_config, save_server_config

    with app.app_context():
        exp, pop = _seed(app, env)
        folder = env.im._experiment_folder(exp)
        server = load_server_config(folder)
        apply_experiment_switches(server, opinion=True, stress_reward=True, memory=True, emotion=True)
        save_server_config(folder, server)
        # the form may claim anything: the switches are the experiment's
        _post(app, env, exp, pop, days="3", start_date="2026-03-02", ticks_per_round="6",
              opinion_enabled="", memory_enabled="true",
              **{"adv.agents.memory_total_max_chars": "700"})
        assert not [f for f in env.flashes if f[0] == "error"], env.flashes
        cfg = json.loads(Path(folder, "client_cl-pop.json").read_text())
        assert cfg["opinion_dynamics"]["enabled"] is True and cfg["stress_reward"]["enabled"] is True
        assert cfg["agents"]["memory_enabled"] is True and cfg["agents"]["memory_total_max_chars"] == 700
        assert cfg["simulation"]["emotion_annotation"] is True
        server = load_server_config(folder)
        assert server["simulation"]["num_days"] == 3 and server["simulation"]["start_date"] == "2026-03-02"
        assert server["telegram"]["time"]["ticks_per_round"] == 6
        # a second client must agree on the start date and the round length
        env.flashes.clear()
        _post(app, env, exp, pop, name="cl2", days="5", start_date="2026-04-01", ticks_per_round="6")
        assert any("start date" in m for _, m in env.flashes)
        _post(app, env, exp, pop, name="cl3", days="5", start_date="2026-03-02", ticks_per_round="6")
        assert load_server_config(folder)["simulation"]["num_days"] == 5


def test_memory_stays_off_when_the_experiment_has_it_off(app, env):
    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, memory_enabled="true", **{"adv.agents.memory_total_max_chars": "700"})
        cfg = json.loads(Path(env.im._experiment_folder(exp), "client_cl-pop.json").read_text())
        assert cfg["agents"] == {"memory_enabled": False}


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


# -- real run -------------------------------------------------------------------------------------
def _start_server(hs, exp, folder, monkeypatch, tmp_path):
    import os
    import sys
    import time

    monkeypatch.setattr(hs, "get_writable_path", lambda *a: str(tmp_path))
    monkeypatch.setattr(hs, "get_base_path", lambda: str(ROOT))
    monkeypatch.setattr(hs, "build_subprocess_env", lambda: dict(os.environ))
    monkeypatch.setattr("y_web.src.simulation.server.detect_env_handler", lambda: sys.executable)
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_external_repo_dir", lambda name: str(ROOT / "external" / name)
    )
    hs.start_hpc_server(exp)
    deadline = time.time() + 120
    while time.time() < deadline and not (Path(folder) / "ray_ready.temp").exists():
        time.sleep(0.5)
    assert (Path(folder) / "ray_ready.temp").exists(), "server never became ready"


def _run_client(folder, name, timeout, kill_after=None):
    import os
    import subprocess
    import sys
    import time

    from y_web.src.hpc.client import _normalize_im_client_config
    from y_web.src.im.validation import validate_im_folder

    cfg = Path(folder) / f"client_{name}-pop.json"
    _normalize_im_client_config(str(folder), name, "pop", str(cfg))
    validate_im_folder(str(folder), str(IM_REPO), client_config=cfg.name)
    proc = subprocess.Popen(
        [sys.executable, str(IM_REPO / "run_client.py"), "--config", str(cfg)],
        env=dict(os.environ), stdout=open(Path(folder) / f'client_{name}.out', 'w'), stderr=subprocess.STDOUT,
    )
    if kill_after is not None:
        time.sleep(kill_after)
        proc.kill()
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise


@pytest.mark.external_repo
@pytest.mark.integration
def test_one_day_echo_run_through_the_admin_routes(app, env, monkeypatch, tmp_path):
    import sqlite3

    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.src.hpc import server as hs

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="1")
        folder = env.im._experiment_folder(exp)
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        try:
            assert _run_client(folder, "cl", timeout=150) == 0
            conn = sqlite3.connect(str(Path(folder) / "database_server.db"))
            rounds = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
            conn.close()
            assert rounds >= 1
        finally:
            hs.stop_hpc_server(exp.idexp)


def _fingerprint(db_file):
    """A digest of what the run produced, without the wall-clock columns."""
    import hashlib
    import sqlite3

    conn = sqlite3.connect(str(db_file))
    digest = hashlib.sha256()
    try:
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('run_info') ORDER BY name"
        ).fetchall():
            wall = ("created_at", "updated_at", "heartbeat", "timestamp", "opened_at", "closed_at", "applied_at")
            columns = [
                c[1]
                for c in conn.execute(f"PRAGMA table_info({table})").fetchall()
                # wall-clock columns and auto-increment keys depend on timing, not on the simulation
                if not any(w in c[1] for w in wall) and not (c[5] and c[2].upper() == "INTEGER")
            ]
            if not columns:
                continue
            rows = sorted(
                conn.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall(), key=repr
            )
            digest.update(repr((table, columns, rows)).encode())
    finally:
        conn.close()
    return digest.hexdigest()


@pytest.mark.external_repo
@pytest.mark.integration
def test_kill_nine_resume_and_server_restart_equal_a_clean_run(app, env, monkeypatch, tmp_path):
    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.src.hpc import server as hs

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="8")
        folder = env.im._experiment_folder(exp)

        # clean run
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        try:
            assert _run_client(folder, "cl", timeout=170) == 0
        finally:
            hs.stop_hpc_server(exp.idexp)
        clean = _fingerprint(Path(folder) / "database_server.db")

        # The same inputs under the same experiment folder name in a second root (the client id, which is
        # part of every derived id and seed, includes the folder name): killed with SIGKILL, the server
        # restarted, then resumed.
        import shutil

        root_b = tmp_path / "root_b"
        other = root_b / "y_web" / "experiments" / Path(folder).name
        other.mkdir(parents=True)
        for name in ("server_config.json", "client_cl-pop.json", "pop.json", "topic_catalog.json", "prompt_language.json"):
            shutil.copy(Path(folder) / name, other / name)
        cfg = json.loads((other / "server_config.json").read_text())
        cfg["database"] = {"type": "sqlite"}
        (other / "server_config.json").write_text(json.dumps(cfg))
        _start_server(hs, exp, other, monkeypatch, root_b)
        try:
            assert _run_client(other, "cl", timeout=170, kill_after=5) == -9, "the client ended before it was killed: raise the days"
        finally:
            hs.stop_hpc_server(exp.idexp)
        _start_server(hs, exp, other, monkeypatch, root_b)  # exit 6 would show here as a server that never gets ready
        try:
            assert _run_client(other, "cl", timeout=170) == 0
        finally:
            hs.stop_hpc_server(exp.idexp)
        assert _fingerprint(other / "database_server.db") == clean


def test_chat_rows_become_catalog_chats_with_catalog_topic_ids():
    from y_web.src.im.client_config import ImClientFormError, build_topic_catalog, parse_chat_rows

    topics = {7: "Climate Change", 8: "health"}
    form = {
        "chat.0.title": "Green News", "chat.0.type": "channel", "chat.0.visibility": "public",
        "chat.0.topic.7": "true", "chat.0.popularity": "2.5", "chat.0.owner": "newsbot", "chat.0.discussion": "true",
        "chat.1.title": "", "chat.1.type": "group",  # an untouched row
        "chat.2.title": "Doctors", "chat.2.type": "group", "chat.2.visibility": "private",
        "chat.2.topic.7": "true", "chat.2.topic.8": "true",
        "chat.3.title": "Green News", "chat.3.type": "supergroup", "chat.3.topic.8": "true",
    }
    chats = parse_chat_rows(form, topics)
    assert [c["id"] for c in chats] == ["chat-green-news", "chat-doctors", "chat-green-news-2"]
    assert chats[0] == {"id": "chat-green-news", "type": "channel", "title": "Green News", "visibility": "public",
                        "topics": ["Climate Change"], "popularity": 2.5, "owner": "page:newsbot", "discussion_group": True}
    assert chats[1]["visibility"] == "private" and "discussion_group" not in chats[1]
    catalog = build_topic_catalog({"Climate Change": 1.0, "health": 1.0}, chats=chats)
    assert catalog["chats"][1]["topics"] == ["climate-change", "health"]
    schema = json.loads((IM_REPO / "schemas" / "config" / "topic_catalog.json").read_text())
    import jsonschema

    jsonschema.validate(catalog, schema)
    for bad in ({"chat.0.title": "x"}, {"chat.0.topic.7": "true"},
                {"chat.0.title": "x", "chat.0.topic.7": "true", "chat.0.type": "dm"},
                {"chat.0.title": "x", "chat.0.topic.7": "true", "chat.0.visibility": "secret"}):
        with pytest.raises(ImClientFormError):
            parse_chat_rows(bad, topics)
    assert parse_chat_rows({}, topics) == []


def test_chats_typed_in_the_editor_get_their_own_catalog_and_the_shared_one_stays_topics_only(app, env):
    with app.app_context():
        exp, pop = _seed(app, env)
        from y_web import db
        from y_web.src.models import Topic_List

        topic_ids = {t.name: t.id for t in db.session.query(Topic_List).all()}
        _post(app, env, exp, pop, **{
            "chat.0.title": "Politics Daily", "chat.0.type": "channel", "chat.0.discussion": "true",
            f"chat.0.topic.{topic_ids['politics']}": "true",
        })
        assert not [f for f in env.flashes if f[0] == "error"], env.flashes
        folder = Path(env.im._experiment_folder(exp))
        cfg = json.loads((folder / "client_cl-pop.json").read_text())
        assert cfg["telegram"]["topics"]["catalog_file"] == "topic_catalog_cl.json"
        own = json.loads((folder / "topic_catalog_cl.json").read_text())
        assert own["chats"][0]["title"] == "Politics Daily" and own["chats"][0]["topics"] == ["politics"]
        assert "chats" not in json.loads((folder / "topic_catalog.json").read_text())
        # without chats the shared catalog is the one the client uses
        _post(app, env, exp, pop, name="plain")
        assert json.loads((folder / "client_plain-pop.json").read_text())["telegram"]["topics"]["catalog_file"] == "topic_catalog.json"


@pytest.mark.external_repo
def test_a_client_with_typed_chats_passes_yim_validate(app, env):
    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web import db
    from y_web.src.hpc.client import _normalize_im_client_config
    from y_web.src.im.validation import validate_im_folder
    from y_web.src.models import Topic_List

    with app.app_context():
        exp, pop = _seed(app, env)
        topic_ids = {t.name: t.id for t in db.session.query(Topic_List).all()}
        _post(app, env, exp, pop, **{
            "chat.0.title": "Politics Daily", "chat.0.type": "channel", "chat.0.discussion": "true",
            f"chat.0.topic.{topic_ids['politics']}": "true",
            "chat.1.title": "Health Talk", "chat.1.type": "supergroup",
            f"chat.1.topic.{topic_ids['health']}": "true", f"chat.1.topic.{topic_ids['politics']}": "true",
        })
        folder = Path(env.im._experiment_folder(exp))
        cfg = folder / "client_cl-pop.json"
        _normalize_im_client_config(str(folder), "cl", "pop", str(cfg))
        validate_im_folder(str(folder), str(IM_REPO), client_config=cfg.name)


def test_with_opinion_dynamics_on_the_new_client_goes_to_its_opinion_page(app, env):
    from y_web import db
    from y_web.src.im.experiment_config import apply_experiment_switches, load_server_config, save_server_config
    from y_web.src.models import Client

    with app.app_context():
        exp, pop = _seed(app, env)
        response = _post(app, env, exp, pop)  # switch off: back to the experiment
        assert response.status_code == 302 and response.location.endswith(f"/admin/experiment_details/{exp.idexp}")
        folder = env.im._experiment_folder(exp)
        server = load_server_config(folder)
        apply_experiment_switches(server, opinion=True)
        save_server_config(folder, server)
        response = _post(app, env, exp, pop, name="cl2")
        client = db.session.query(Client).filter_by(name="cl2").one()
        assert response.status_code == 302
        assert "opinion_configuration_im" in response.location and client.id


def test_news_feeds_become_pages_and_the_mode_and_snapshot_follow_the_form(app, env, monkeypatch):
    from y_web.src.im import news

    calls = []
    monkeypatch.setattr(news, "write_snapshot", lambda folder, urls, **k: calls.append(sorted(urls)) or {"articles": 3, "feeds": {}, "written": True})
    with app.app_context():
        exp, pop = _seed(app, env)
        folder = env.im._experiment_folder(exp)
        Path(folder, "rss_feeds.json").write_text(json.dumps([{"name": "BBC", "feed_url": "http://bbc/rss"}]))
        _post(app, env, exp, pop, news_mode="snapshot", news_pages_from_feeds="1")
        assert not [f for f in env.flashes if f[0] == "error"], env.flashes
        cfg = json.loads(Path(folder, "client_cl-pop.json").read_text())
        assert cfg["telegram"]["news"]["mode"] == "snapshot"
        pages = [a for a in json.loads(Path(folder, "pop.json").read_text())["agents"] if a.get("is_page")]
        assert sorted(p["feed_url"] for p in pages) == ["http://bbc/rss", "http://f"]
        assert calls == [["http://bbc/rss", "http://f"]]
        # live mode reads the feeds at start: no snapshot is written, and no feed page without the box ticked
        _post(app, env, exp, pop, name="cl2", news_mode="live")
        cfg2 = json.loads(Path(folder, "client_cl2-pop.json").read_text())
        assert cfg2["telegram"]["news"]["mode"] == "live" and len(calls) == 1
        # the topic of each news post: the article's own by default, every channel topic on request
        assert cfg["telegram"]["news"]["topic_mode"] == "classify"
        _post(app, env, exp, pop, name="cl3", news_mode="live", news_topic_mode="channel")
        cfg3 = json.loads(Path(folder, "client_cl3-pop.json").read_text())
        assert cfg3["telegram"]["news"]["topic_mode"] == "channel"


def _topic_ids(exp):
    from y_web import db
    from y_web.src.models import Exp_Topic, Topic_List

    rows = (db.session.query(Topic_List).join(Exp_Topic, Exp_Topic.topic_id == Topic_List.id)
            .filter(Exp_Topic.exp_id == exp.idexp).all())
    return {t.name: t.id for t in rows}


def _stale_catalog(env, exp):
    folder = Path(env.im._experiment_folder(exp))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic_catalog.json").write_text(json.dumps({"topics": [{"id": "old", "label": "old", "weight": 1.0}]}))
    return folder


def test_a_leftover_catalog_is_replaced_when_nothing_depends_on_it(app, env):
    """The previous client was deleted and nothing ran: its catalog must not block (or warn about) the new one."""
    with app.app_context():
        exp, pop = _seed(app, env)
        folder = _stale_catalog(env, exp)
        _post(app, env, exp, pop)
        assert not [f for f in env.flashes if f[0] in ("error", "warning")], env.flashes
        labels = [t["label"] for t in json.loads((folder / "topic_catalog.json").read_text())["topics"]]
        assert labels == ["politics", "health"]


def test_a_client_with_its_own_catalog_is_not_warned_about_the_shared_one(app, env):
    with app.app_context():
        exp, pop = _seed(app, env)
        _stale_catalog(env, exp)
        politics = _topic_ids(exp)["politics"]
        _post(app, env, exp, pop, **{"chat.0.title": "Debate", "chat.0.type": "supergroup",
                                     f"chat.0.topic.{politics}": "true"})
        assert not [f for f in env.flashes if f[0] in ("error", "warning")], env.flashes


def test_the_shared_catalog_is_kept_with_a_warning_once_other_clients_use_it(app, env):
    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop)  # the first client writes the shared catalog
        folder = Path(env.im._experiment_folder(exp))
        before = (folder / "topic_catalog.json").read_text()
        env.flashes.clear()
        _post(app, env, exp, pop, name="cl2", **{f"topic_interest_{_topic_ids(exp)['politics']}": "40"})
        assert any("topic catalog" in m for _, m in env.flashes), env.flashes
        assert (folder / "topic_catalog.json").read_text() == before


def test_filled_hourly_rates_are_used_without_a_switch_and_the_others_stay_default(app, env):
    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, hourly_8="0.2", hourly_9="")
        assert not [f for f in env.flashes if f[0] == "error"], env.flashes
        cfg = json.loads(Path(env.im._experiment_folder(exp), "client_cl-pop.json").read_text())
        assert cfg["simulation"]["hourly_activity"] == {"8": 0.2}


def test_no_hourly_rate_leaves_the_runtime_default(app, env):
    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop)
        cfg = json.loads(Path(env.im._experiment_folder(exp), "client_cl-pop.json").read_text())
        assert "hourly_activity" not in cfg["simulation"]


def test_a_rate_out_of_range_is_refused(app, env):
    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, hourly_3="1.5")
        assert any(f[0] == "error" for f in env.flashes), env.flashes
