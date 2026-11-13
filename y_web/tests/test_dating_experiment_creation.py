"""Creation of dating experiments, their configuration file and database isolation (plan S1, IR-D-04)."""

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
DATING_REPO = ROOT / "external" / "YDating"
SCHEMA = DATING_REPO / "schemas" / "config" / "server_config.json"


def _generate(**kw):
    from y_web.src.dating.experiment_config import generate_dating_server_config

    return generate_dating_server_config("exp", "/x/database_server.db", "/x/", **kw)


# -- generator -------------------------------------------------------------------------------------
def test_generated_server_config_has_the_documented_keys():
    cfg = _generate(seed=7)
    assert cfg["server_name"] == "orchestrator_server" and cfg["seed"] == 7
    assert cfg["min_to_start"] == 1 and cfg["simulation"]["num_slots_per_day"] == 24
    assert cfg["database"]["type"] == "sqlite"
    assert cfg["platform_type"] == "dating" and cfg["experiment_name"] == "exp"
    assert cfg["experiment_configuration_confirmed"] is False
    assert cfg["opinion_dynamics_enabled"] is False
    assert cfg["memory"] == {"enabled": False}
    assert cfg["annotations"] == {
        "sentiment": False,
        "toxicity": False,
        "emotions": False,
    }


def test_the_seed_is_drawn_once_and_stored_when_not_given():
    first, second = _generate(), _generate()
    assert isinstance(first["seed"], int) and 0 <= first["seed"] <= 2**31 - 1
    assert first["seed"] != second["seed"]


@pytest.mark.parametrize(
    "kwargs",
    [{"seed": "-1"}, {"seed": "abc"}, {"slots_per_day": "0"}, {"slots_per_day": "97"}],
)
def test_generator_rejects_out_of_range_values(kwargs):
    from y_web.src.dating.experiment_config import DatingConfigError

    with pytest.raises(DatingConfigError):
        _generate(**kwargs)


@pytest.mark.skipif(not SCHEMA.exists(), reason="YDating is not present")
def test_generated_and_switched_config_satisfy_the_strict_runtime_schema():
    jsonschema = pytest.importorskip("jsonschema")
    from y_web.src.dating.experiment_config import apply_experiment_switches

    schema = json.loads(SCHEMA.read_text())
    cfg = _generate(seed=1, toxicity_annotation=True)
    jsonschema.Draft7Validator(schema).validate(cfg)
    apply_experiment_switches(
        cfg, sentiment=True, emotion=True, stress_reward=True, memory=True
    )
    jsonschema.Draft7Validator(schema).validate(cfg)


def test_switches_write_the_runtime_blocks_and_the_page_mirrors():
    from y_web.src.dating import experiment_config as xc

    cfg = xc.apply_experiment_switches(
        _generate(seed=1),
        toxicity=True,
        sentiment=True,
        stress_reward=True,
        memory=True,
    )
    assert cfg["annotations"] == {
        "sentiment": True,
        "toxicity": True,
        "emotions": False,
    }
    assert cfg["toxicity_annotation"] is True and cfg["sentiment_annotation"] is True
    assert (
        cfg["stress_reward"]["enabled"] is True and cfg["stress_reward_enabled"] is True
    )
    assert xc.read_switches(cfg) == {
        "toxicity": True,
        "sentiment": True,
        "emotion": False,
        "opinion": False,
        "stress_reward": True,
        "memory": True,
    }
    cfg["stress_reward"]["base_stress"] = 0.3
    xc.apply_experiment_switches(cfg, toxicity=False)
    assert cfg["annotations"]["sentiment"] is True  # untouched when not named
    assert cfg["stress_reward"]["base_stress"] == 0.3  # researcher detail is kept
    cfg["perspective_api"] = "k"
    xc.apply_experiment_switches(cfg)
    assert "perspective_api" not in cfg


# -- database isolation ------------------------------------------------------------------------------
def _make_dating_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE rounds (id INTEGER PRIMARY KEY, slot INTEGER)")
    conn.execute("CREATE TABLE dating_profile (id INTEGER PRIMARY KEY, bio TEXT)")
    conn.commit()
    conn.close()


def test_sqlite_schema_ensure_leaves_a_dating_database_untouched(tmp_path):
    from y_web.src.experiment.schema import ensure_sqlite_experiment_schema

    db = str(tmp_path / "dating.db")
    _make_dating_db(db)
    conn = sqlite3.connect(db)
    before = conn.execute(
        "SELECT name, sql FROM sqlite_master ORDER BY name"
    ).fetchall()
    conn.close()
    assert ensure_sqlite_experiment_schema(db) is False
    conn = sqlite3.connect(db)
    after = conn.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    conn.close()
    assert after == before


def test_registering_a_dating_experiment_binds_nothing(app):
    from y_web import db
    from y_web.src.experiment.context import register_experiment_database
    from y_web.src.models import Exps

    with app.app_context():
        exp = Exps(
            exp_name="d",
            platform_type="dating",
            db_name="experiments/u/database_server.db",
            owner="admin",
            exp_descr="",
            status=0,
            port=5001,
            server="127.0.0.1",
            annotations="",
            llm_agents_enabled=1,
            simulator_type="HPC",
            is_remote=0,
        )
        db.session.add(exp)
        db.session.commit()
        binds = dict(app.config["SQLALCHEMY_BINDS"])
        register_experiment_database(app, exp.idexp, exp.db_name)
        assert app.config["SQLALCHEMY_BINDS"] == binds


# -- create_experiment route -------------------------------------------------------------------------
@pytest.fixture
def create_env(app, monkeypatch, tmp_path):
    from y_web.routes.admin.sub.experiments import _crud

    monkeypatch.setattr(_crud, "check_privileges", lambda *_: None)
    monkeypatch.setattr(_crud, "current_user", SimpleNamespace(username="admin", id=1))
    monkeypatch.setattr(_crud, "get_suggested_port", lambda: 5099)
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path)
    )
    monkeypatch.setattr(_crud, "url_for", lambda endpoint, **kw: f"/{endpoint}")
    flashes = []
    monkeypatch.setattr(
        _crud, "flash", lambda msg, cat="message": flashes.append((cat, str(msg)))
    )
    monkeypatch.setattr("y_web.src.telemetry.Telemetry", lambda **kw: MagicMock())
    import functools

    monkeypatch.setattr(
        _crud,
        "Jupyter_instances",
        functools.partial(_crud.Jupyter_instances, process=0),
    )
    return SimpleNamespace(crud=_crud, flashes=flashes, tmp=tmp_path)


AVAILABLE = {
    "microblogging": True,
    "hpc": True,
    "forum": True,
    "photo_sharing": True,
    "instant_messaging": True,
    "dating": True,
}


def _post_create(app, env, availability, **form):
    env.crud._external_repo_availability = lambda: availability
    base = {
        "exp_name": "dating exp",
        "exp_descr": "d",
        "platform_type": "dating",
        "simulator_type": "Standard",
        "tags": "love,music",
        "llm_agents_enabled": "true",
    }
    base.update(form)
    with app.test_request_context("/admin/create_experiment", method="POST", data=base):
        return env.crud.create_experiment.__wrapped__()


def test_create_dating_experiment_writes_config_and_no_database(app, create_env):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        _post_create(app, create_env, AVAILABLE, seed="42", sentiment_annotation="true")
        exp = db.session.query(Exps).one()
        assert exp.platform_type == "dating" and exp.simulator_type == "HPC"
        assert exp.db_name.endswith("database_server.db")
        assert exp.annotations == "sentiment"
        folder = create_env.tmp / "y_web" / Path(exp.db_name).parent
        cfg = json.loads((folder / "server_config.json").read_text())
        assert cfg["seed"] == 42 and cfg["platform_type"] == "dating"
        assert cfg["annotations"]["sentiment"] is True
        assert cfg["experiment_configuration_confirmed"] is False
        assert not (folder / "database_server.db").exists()
        assert not (folder / "config_server.json").exists()


def test_create_dating_experiment_ignores_opinion_dynamics_and_remote(app, create_env):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        _post_create(app, create_env, AVAILABLE, opinion_dynamics_enabled="true")
        exp = db.session.query(Exps).one()
        assert "opinions" not in exp.annotations
        _post_create(
            app,
            create_env,
            AVAILABLE,
            is_remote="true",
            remote_host="h",
            remote_port="1",
        )
        assert db.session.query(Exps).count() == 1
        assert any("Remote dating" in m for _, m in create_env.flashes)


def test_create_dating_experiment_without_the_runtime_is_refused(app, create_env):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        _post_create(app, create_env, {**AVAILABLE, "dating": False})
        assert db.session.query(Exps).count() == 0
        assert any("YDating" in m for _, m in create_env.flashes)


def test_dating_invalid_seed_is_refused_and_leaves_no_folder(app, create_env):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        _post_create(app, create_env, AVAILABLE, seed="-5")
        assert db.session.query(Exps).count() == 0
        assert any("Invalid dating settings" in m for _, m in create_env.flashes)


def test_create_dating_experiment_without_topics(app, create_env):
    """The topics field is hidden for dating: the form sends no value and no topic is stored."""
    from y_web import db
    from y_web.src.models import Exp_Topic, Exps

    with app.app_context():
        env = create_env
        env.crud._external_repo_availability = lambda: AVAILABLE
        data = {
            "exp_name": "no topics",
            "exp_descr": "d",
            "platform_type": "dating",
            "simulator_type": "Standard",
            "llm_agents_enabled": "true",
        }
        with app.test_request_context(
            "/admin/create_experiment", method="POST", data=data
        ):
            env.crud.create_experiment.__wrapped__()
        assert db.session.query(Exps).count() == 1
        assert db.session.query(Exp_Topic).count() == 0
