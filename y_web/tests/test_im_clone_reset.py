"""Clone and reset of IM experiments (plan, 5.6)."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.tests.test_im_client_creation import _post, _seed, env  # noqa: F401

pytestmark = pytest.mark.unit


def _dirty(folder):
    folder = Path(folder)
    (folder / "logs").mkdir(exist_ok=True)
    for name in (
        "database_server.db", "database_server.db-wal", "database_server.db-shm",
        "client_cl-pop.json.state.json", "ray_ready.temp", "ray_config.temp", "logs/x_server.log",
        "logs/x_server.log.1", "logs/old.log.gz",
    ):
        (folder / name).write_text("x")
    for d in ("reports", "exports"):
        (folder / d).mkdir()
        (folder / d / "f.json").write_text("{}")
    (folder / "news_snapshot.jsonl").write_text('{"a": 1}\n')
    (folder / "events.jsonl").write_text('{"b": 2}\n')


def test_clear_artifacts_keeps_inputs(tmp_path):
    from y_web.src.im.clone import clear_im_run_artifacts

    for name in ("server_config.json", "client_cl-pop.json", "pop.json", "topic_catalog.json", "prompt_language.json"):
        (tmp_path / name).write_text("{}")
    _dirty(tmp_path)
    removed, failed = clear_im_run_artifacts(str(tmp_path))
    assert removed >= 8 and failed == []
    left = {p.name for p in tmp_path.iterdir()}
    assert left == {"server_config.json", "client_cl-pop.json", "pop.json", "topic_catalog.json",
                    "prompt_language.json", "news_snapshot.jsonl", "events.jsonl", "logs"}
    assert list((tmp_path / "logs").iterdir()) == []


def test_copy_folder_takes_inputs_only(tmp_path):
    from y_web.src.im.clone import copy_im_folder, rewrite_server_config

    src = tmp_path / "src"
    src.mkdir()
    (src / "server_config.json").write_text(json.dumps({"experiment_name": "a", "database_uri": "x", "data_path": "y"}))
    (src / "pop.json").write_text("{}")
    (src / "client_cl-pop.json").write_text("{}")
    _dirty(src)
    dst = tmp_path / "dst"
    copy_im_folder(str(src), str(dst))
    names = {p.name for p in dst.iterdir()}
    assert names == {"server_config.json", "pop.json", "client_cl-pop.json", "news_snapshot.jsonl", "events.jsonl", "logs"}
    assert list((dst / "logs").iterdir()) == []
    rewrite_server_config(str(dst), "b", "u", "d/")
    cfg = json.loads((dst / "server_config.json").read_text())
    assert (cfg["experiment_name"], cfg["database_uri"], cfg["data_path"]) == ("b", "u", "d/")


def test_copy_experiment_creates_a_fresh_experiment(app, env, monkeypatch):
    from y_web import db
    from y_web.src.models import Client, Client_Execution, Exps

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="3")
        folder = env.im._experiment_folder(exp)
        _dirty(folder)
        monkeypatch.setattr(env.ecrud, "current_user", SimpleNamespace(username="admin", id=1))
        assert env.ecrud._create_single_experiment_copy(exp, "copy", "grp") is True
        new = db.session.query(Exps).filter_by(exp_name="copy").one()
        assert new.platform_type == "instant_messaging" and new.exp_group == "grp" and new.running == 0
        new_folder = Path(folder).parent / new.db_name.split(os.sep)[1]
        names = {p.name for p in new_folder.iterdir()}
        assert "server_config.json" in names and "client_cl-pop.json" in names
        assert "database_server.db" not in names and "database_server.db-wal" not in names
        assert not any(n.endswith(".state.json") or n.startswith("ray_") for n in names)
        cfg = json.loads((new_folder / "server_config.json").read_text())
        assert cfg["experiment_name"] == "copy" and str(new_folder) in cfg["data_path"]
        client = db.session.query(Client).filter_by(id_exp=new.idexp).one()
        assert client.days == 3
        assert db.session.query(Client_Execution).filter_by(client_id=client.id).one().expected_duration_rounds == 72
        # the source is untouched
        assert (Path(folder) / "database_server.db").exists()


def test_reset_deletes_sidecars_and_keeps_news_snapshot(app, env, monkeypatch, tmp_path):
    from y_web import db
    from y_web.routes.admin.sub.experiments import _data
    from y_web.src.models import Client_Execution

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="2")
        folder = Path(env.im._experiment_folder(exp))
        _dirty(folder)
        flashes = []
        monkeypatch.setattr(_data, "check_privileges", lambda *_: None)
        monkeypatch.setattr(_data, "current_user", SimpleNamespace(username="admin", id=1))
        monkeypatch.setattr(_data, "_current_admin_user_or_none", lambda: SimpleNamespace(id=1))
        monkeypatch.setattr(_data, "user_can_manage_experiment", lambda *a: True)
        monkeypatch.setattr(_data, "_experiment_has_started_once", lambda *a, **k: True)
        monkeypatch.setattr(_data, "url_for", lambda e, **k: f"/{e}")
        monkeypatch.setattr(_data, "flash", lambda m, c="message": flashes.append((c, str(m))))
        monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
        exp.running = 0
        db.session.commit()
        _data.reset_hpc_experiment.__wrapped__(exp.idexp)
        assert not any(c == "error" for c, _ in flashes), flashes
        left = {p.name for p in folder.iterdir()}
        assert {"news_snapshot.jsonl", "events.jsonl", "topic_catalog.json", "server_config.json"} <= left
        assert not {"database_server.db", "database_server.db-wal", "database_server.db-shm",
                    "client_cl-pop.json.state.json", "reports", "exports", "ray_ready.temp"} & left
        assert db.session.query(Client_Execution).one().expected_duration_rounds == 48
