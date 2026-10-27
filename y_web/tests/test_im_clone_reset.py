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
        "logs/x_server.log.1", "logs/old.log.gz", "scenario_design_im.db", "scenario_design_im.db-journal",
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
    assert removed >= 10 and failed == []
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


def test_download_of_a_running_experiment_has_an_openable_database(app, env, monkeypatch, tmp_path):
    import sqlite3
    import zipfile

    from y_web.routes.admin.sub.experiments import _notifications

    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="1")
        folder = Path(env.im._experiment_folder(exp))
        db_file = folder / "database_server.db"
        writer = sqlite3.connect(str(db_file), isolation_level=None)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE run_info (run_id TEXT)")
        writer.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, text TEXT)")
        writer.executemany("INSERT INTO messages (text) VALUES (?)", [(f"m{i}",) for i in range(200)])
        assert (folder / "database_server.db-wal").exists() and (folder / "database_server.db-wal").stat().st_size > 0
        monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
        out = tmp_path / "out.zip"
        _notifications._build_single_experiment_zip(exp.idexp, str(out))
        writer.close()
        with zipfile.ZipFile(out) as archive:
            names = archive.namelist()
            assert "database_server.db" in names
            assert not any(n.endswith("-wal") or n.endswith("-shm") for n in names)
            archive.extract("database_server.db", tmp_path / "x")
        conn = sqlite3.connect(str(tmp_path / "x" / "database_server.db"))
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 200
        conn.close()


def test_is_im_folder_detects_marker_and_topic_catalog(tmp_path):
    import sqlite3

    from y_web.src.im.clone import is_im_folder

    plain = tmp_path / "hpc"
    plain.mkdir()
    (plain / "server_config.json").write_text("{}")
    assert not is_im_folder(str(plain))
    sqlite3.connect(plain / "database_server.db").executescript("CREATE TABLE post (id INTEGER)")
    assert not is_im_folder(str(plain))
    (plain / "topic_catalog.json").write_text("{}")
    assert is_im_folder(str(plain))

    marked = tmp_path / "marked"
    marked.mkdir()
    (marked / "server_config.json").write_text("{}")
    sqlite3.connect(marked / "database_server.db").executescript("CREATE TABLE run_info (k TEXT)")
    assert is_im_folder(str(marked))
    assert not is_im_folder(str(tmp_path))  # no server_config.json


def test_uploaded_im_folder_is_validated_and_registered_without_the_ysocial_schema(
    app, env, monkeypatch, tmp_path
):
    import shutil
    import sqlite3

    from y_web import db
    from y_web.src.models import Exps

    flashes = []
    with app.app_context():
        exp, pop = _seed(app, env)
        _post(app, env, exp, pop, days="2")
        source = Path(env.im._experiment_folder(exp))
        _dirty(source)
        upload = tmp_path / "up"
        shutil.copytree(source, upload)
        sqlite3.connect(upload / "database_server.db").executescript("CREATE TABLE run_info (k TEXT)")
        from y_web.src.im import validation

        calls = []

        def fake_validate(folder, repo_dir=None, client_config=None):
            calls.append(client_config)
            if client_config and Path(folder, client_config).read_text().strip() == "{}":
                raise validation.ImValidationError(["config: broken client"])

        monkeypatch.setattr(validation, "validate_im_folder", fake_validate)
        monkeypatch.setattr(env.ecrud, "current_user", SimpleNamespace(username="admin", id=1))
        monkeypatch.setattr(env.ecrud, "flash", lambda m, c="message": flashes.append(str(m)))
        monkeypatch.setattr(env.ecrud, "url_for", lambda e, **k: f"/{e}")
        monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
        with app.test_request_context("/admin/upload_experiment", method="POST"):
            env.ecrud._import_im_upload(str(upload), "newuid", "uploaded", "g")
        assert not any("not valid" in m or "could not" in m for m in flashes), flashes
        new = db.session.query(Exps).filter_by(exp_name="uploaded").one()
        assert new.platform_type == "instant_messaging" and new.running == 0 and new.exp_group == "g"
        names = {p.name for p in upload.iterdir()}
        assert "database_server.db" not in names  # a foreign run database is never kept
        cfg = json.loads((upload / "server_config.json").read_text())
        assert cfg["experiment_name"] == "uploaded" and cfg["server"]["port"] == new.port
        assert any("imported" in m for m in flashes), flashes
        assert calls[0] is None and "client_cl-pop.json" in calls, calls

        # an invalid configuration is refused and nothing is registered
        bad = tmp_path / "bad"
        shutil.copytree(source, bad)
        (bad / "client_cl-pop.json").write_text("{}")
        flashes.clear()
        with app.test_request_context("/admin/upload_experiment", method="POST"):
            env.ecrud._import_im_upload(str(bad), "baduid", "bad-one", "")
        assert db.session.query(Exps).filter_by(exp_name="bad-one").first() is None
        assert any("not valid" in m for m in flashes), flashes
        assert not bad.exists()
