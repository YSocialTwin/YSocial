"""Creation, activation and validation of instant messaging experiments (plan, Phase 4)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
IM_REPO = ROOT / "external" / "YInstantMessaging"


# -- generator ------------------------------------------------------------------------------------
def test_generated_server_config_has_the_documented_keys():
    from y_web.routes.admin.sub.experiments._im import generate_im_server_config

    cfg = generate_im_server_config(
        "exp", "/x/database_server.db", "/x/", False, 3, "2026-02-01", 6
    )
    assert cfg["server_name"] == "orchestrator_server"
    assert cfg["namespace"] == "yinstantmessaging"
    assert cfg["min_to_start"] == 1
    assert cfg["timeout_seconds"] == cfg["ready_timeout_seconds"] == 180
    assert cfg["database"] == {"type": "sqlite"}
    assert (
        cfg["simulation"]["num_days"] == 3
        and cfg["simulation"]["start_date"] == "2026-02-01"
    )
    assert (
        cfg["simulation"]["enable_toxicity"] is False
        and cfg["simulation"]["memory_enabled"] is False
    )
    assert cfg["telegram"]["time"] == {"ticks_per_round": 6}
    assert cfg["telegram"]["stress_reward"]["enabled"] is False
    # the switches the experiment page reads, and the lock until the researcher confirms them
    assert (
        cfg["toxicity_annotation"] is False and cfg["opinion_dynamics_enabled"] is False
    )
    assert (
        cfg["memory"] == {"enabled": False}
        and cfg["experiment_configuration_confirmed"] is False
    )
    # humans can register at any time: the gateway is always part of the experiment
    assert cfg["human"] == {
        "enabled": True,
        "max_humans": 50,
        "pace": {"min_round_seconds": 0.0},
    }
    assert cfg["logging"]["enable_server_log"] is True
    assert cfg["platform_type"] == "instant_messaging"
    assert cfg["experiment_name"] == "exp" and cfg["is_remote"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_days": "0"},
        {"num_days": "abc"},
        {"ticks_per_round": "61"},
        {"start_date": "01/02/2026"},
    ],
)
def test_generator_rejects_out_of_range_values(kwargs):
    from y_web.routes.admin.sub.experiments._im import (
        ImConfigError,
        generate_im_server_config,
    )

    with pytest.raises(ImConfigError):
        generate_im_server_config("e", "/x/db", "/x/", **kwargs)


def test_generated_config_is_valid_for_the_im_schema():
    jsonschema = pytest.importorskip("jsonschema")
    from y_web.routes.admin.sub.experiments._im import generate_im_server_config

    schema_file = IM_REPO / "schemas" / "config" / "server_config.json"
    if not schema_file.is_file():
        pytest.skip("YInstantMessaging is not installed")
    schema = json.loads(schema_file.read_text())
    jsonschema.validate(generate_im_server_config("e", "/x/db", "/x/"), schema)


@pytest.mark.external_repo
def test_generated_folder_passes_yim_validate(tmp_path):
    if not (IM_REPO / "yinstantmessaging").is_dir():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.routes.admin.sub.experiments._im import generate_im_server_config
    from y_web.src.im.validation import (
        ImValidationError,
        run_yim_validate,
        validate_im_folder,
    )

    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / "server_config.json").write_text(
        json.dumps(generate_im_server_config("e", str(folder / "d.db"), str(folder)))
    )
    assert run_yim_validate(str(folder), str(IM_REPO)) == (True, [])

    cfg = json.loads((folder / "server_config.json").read_text())
    cfg["simulation"]["num_days"] = 0
    (folder / "server_config.json").write_text(json.dumps(cfg))
    valid, messages = run_yim_validate(str(folder), str(IM_REPO))
    assert valid is False and messages
    with pytest.raises(ImValidationError):
        validate_im_folder(str(folder), str(IM_REPO))


def test_run_yim_validate_reports_unreadable_output(monkeypatch, tmp_path):
    from y_web.src.im import validation

    monkeypatch.setattr(validation, "_python_command", lambda: ["python"])
    monkeypatch.setattr(validation, "build_subprocess_env", lambda: {})
    monkeypatch.setattr(
        validation.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="", stderr="Traceback\nboom"
        ),
    )
    valid, messages = validation.run_yim_validate(str(tmp_path), str(tmp_path))
    assert valid is False and "boom" in messages[0]


# -- spec table --------------------------------------------------------------------------------------
def test_im_platform_spec():
    from y_web.src.hpc.platforms import get_hpc_platform

    spec = get_hpc_platform("instant_messaging")
    assert spec.runtime_repo == "YInstantMessaging"
    assert spec.supports_gunicorn is False
    assert spec.orchestrator_actor == "orchestrator_server"
    assert spec.prompts_filename == "prompts_im.json"
    assert spec.validates_config is True


def test_im_server_command_and_validation_gate(monkeypatch, tmp_path):
    from y_web.src.hpc import server as hs

    base = tmp_path / "base"
    writable = tmp_path / "writable"
    folder = writable / "y_web" / "experiments" / "uid1"
    folder.mkdir(parents=True)
    repo = base / "external" / "YInstantMessaging"
    repo.mkdir(parents=True)
    (repo / "run_server.py").write_text("")

    monkeypatch.setattr(hs, "get_base_path", lambda: str(base))
    monkeypatch.setattr(hs, "get_writable_path", lambda: str(writable))
    monkeypatch.setattr(hs, "build_subprocess_env", lambda: {})
    monkeypatch.setattr(
        "y_web.src.simulation.server.detect_env_handler", lambda: "python"
    )
    monkeypatch.setattr(hs.db.session, "commit", lambda: None)
    monkeypatch.setattr(
        hs,
        "current_app",
        SimpleNamespace(config={"SQLALCHEMY_DATABASE_URI": "sqlite://"}),
    )
    popen_calls = []
    proc = MagicMock()
    proc.pid = 4242
    monkeypatch.setattr(
        hs.subprocess, "Popen", lambda cmd, **kw: popen_calls.append(list(cmd)) or proc
    )
    exp = SimpleNamespace(
        idexp=9,
        db_name="experiments/uid1/database_server.db",
        platform_type="instant_messaging",
        server="127.0.0.1",
        port=5004,
        server_pid=None,
        prompt_language="en",
    )

    from y_web.src.im import validation

    monkeypatch.setattr(
        validation, "run_yim_validate", lambda *a, **k: (False, ["bad"])
    )
    with pytest.raises(validation.ImValidationError):
        hs.start_hpc_server(exp)
    assert popen_calls == []

    monkeypatch.setattr(validation, "run_yim_validate", lambda *a, **k: (True, []))
    hs.start_hpc_server(exp)
    assert popen_calls == [
        ["python", str(repo / "run_server.py"), "--config", str(folder)]
    ]
    assert exp.server_pid == 4242


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
    # the test schema is built from the models, where ``process`` is NOT NULL (the shipped database is not)
    import functools

    monkeypatch.setattr(
        _crud,
        "Jupyter_instances",
        functools.partial(_crud.Jupyter_instances, process=0),
    )
    return SimpleNamespace(crud=_crud, flashes=flashes, tmp=tmp_path)


def _post_create(app, env, availability, **form):
    env.crud._external_repo_availability = lambda: availability
    base = {
        "exp_name": "im exp",
        "exp_descr": "d",
        "platform_type": "instant_messaging",
        "simulator_type": "Standard",
        "tags": "politics,health",
        "llm_agents_enabled": "true",
    }
    base.update(form)
    with app.test_request_context("/admin/create_experiment", method="POST", data=base):
        return env.crud.create_experiment.__wrapped__()


AVAILABLE = {
    "microblogging": True,
    "hpc": True,
    "forum": True,
    "photo_sharing": True,
    "instant_messaging": True,
}


def test_create_im_experiment_writes_config_and_no_database(app, create_env):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        # the form has no IM-specific fields: run length and start date come from the client form
        _post_create(
            app, create_env, AVAILABLE, im_num_days="5", im_start_date="2026-03-01"
        )
        exp = db.session.query(Exps).one()
        assert exp.platform_type == "instant_messaging" and exp.simulator_type == "HPC"
        assert exp.db_name.endswith("database_server.db") and exp.annotations == ""
        folder = create_env.tmp / "y_web" / Path(exp.db_name).parent
        cfg = json.loads((folder / "server_config.json").read_text())
        assert (
            cfg["simulation"]["num_days"] == 7
            and cfg["simulation"]["start_date"] != "2026-03-01"
        )
        assert (
            cfg["human"]["enabled"] is True
            and cfg["experiment_configuration_confirmed"] is False
        )
        assert not (folder / "database_server.db").exists()
        assert not (folder / "config_server.json").exists()


def test_create_im_experiment_without_the_runtime_is_refused(app, create_env):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        _post_create(app, create_env, {**AVAILABLE, "instant_messaging": False})
        assert db.session.query(Exps).count() == 0
        assert any("YInstantMessaging" in m for _, m in create_env.flashes)


# -- real server start/stop cycles --------------------------------------------------------------------
def _table_names(db_file):
    import sqlite3

    conn = sqlite3.connect(db_file)
    try:
        return {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()


@pytest.mark.external_repo
def test_real_im_server_start_stop_cycles(app, monkeypatch, tmp_path):
    """The real ``run_server.py`` is started and stopped through YWeb's HPC functions (plan, Phase 4 gate)."""
    import hashlib
    import sqlite3
    import time

    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web import db
    from y_web.routes.admin.sub.experiments._im import generate_im_server_config
    from y_web.src.hpc import server as hs
    from y_web.src.models import Exps

    uid = "uid_cycle"
    folder = tmp_path / "y_web" / "experiments" / uid
    folder.mkdir(parents=True)
    (folder / "server_config.json").write_text(
        json.dumps(
            generate_im_server_config(
                "cycle",
                str(folder / "database_server.db"),
                str(folder) + os.sep,
                num_days=1,
            )
        )
    )
    monkeypatch.setattr(hs, "get_writable_path", lambda *a: str(tmp_path))
    monkeypatch.setattr(hs, "get_base_path", lambda: str(ROOT))
    monkeypatch.setattr(hs, "build_subprocess_env", lambda: dict(os.environ))
    monkeypatch.setattr(
        "y_web.src.simulation.server.detect_env_handler", lambda: sys.executable
    )
    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_external_repo_dir",
        lambda name: str(ROOT / "external" / name),
    )
    cycles = int(os.environ.get("YSOCIAL_IM_CYCLES", "5"))

    with app.app_context():
        exp = Exps(
            exp_name="cycle",
            platform_type="instant_messaging",
            db_name=f"experiments/{uid}/database_server.db",
            owner="admin",
            exp_descr="cycle",
            status=1,
            port=5090,
            server="127.0.0.1",
            simulator_type="HPC",
            prompt_language="en",
        )
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.idexp
        fingerprints = set()
        for _ in range(cycles):
            exp = db.session.get(Exps, exp_id)
            hs.start_hpc_server(exp)
            pid = exp.server_pid
            assert pid
            deadline = time.time() + 120
            while time.time() < deadline and not (folder / "ray_ready.temp").exists():
                time.sleep(0.5)
            assert (folder / "ray_ready.temp").exists(), "server never became ready"
            db_file = folder / "database_server.db"
            assert db_file.is_file()
            tables = _table_names(str(db_file))
            assert "run_info" in tables and not {"user_mgmt", "post"} & tables

            # the YWeb guards must leave the running IM database alone
            from y_web.src.experiment.schema import (
                ensure_experiment_schema_for_uri,
                ensure_sqlite_experiment_schema,
            )

            assert ensure_sqlite_experiment_schema(str(db_file)) is False
            conn = sqlite3.connect(str(db_file))
            fingerprints.add(
                hashlib.sha256(
                    repr(
                        conn.execute(
                            "SELECT name, sql FROM sqlite_master ORDER BY name"
                        ).fetchall()
                    ).encode()
                ).hexdigest()
            )
            conn.close()

            started = time.time()
            assert hs.stop_hpc_server(exp_id) is True
            assert time.time() - started < 60
            db.session.expire_all()
            exp = db.session.get(Exps, exp_id)
            assert exp.server_pid is None and exp.running == 0
            assert not any(
                (folder / m).exists()
                for m in ("ray_ready.temp", "ray_config.temp", "ray_namespace.temp")
            )
            import psutil

            try:  # a zombie is a finished child that nobody waited for: not alive
                alive = psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                alive = False
            assert not alive, "server process survived the stop"
        assert len(fingerprints) == 1  # the schema is the same in every cycle
