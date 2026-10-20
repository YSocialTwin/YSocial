"""The portable bundle with the real core: its own experiment export, its own experiment upload, real experiment databases."""

import io
import json
import os
import shutil
import sqlite3
import zipfile

import pytest

from y_web.tests.test_training_modules_advance_integration import _release
from y_web.tests.test_training_modules_baseline_auth import core_app  # noqa: F401
from y_web.tests.test_training_modules_phase3_integration import (
    API,
    _client_as,
    _post,
    requires_plugin,
)
from y_web.tests.test_training_modules_phase6_integration import (
    _exp_session,
    _experiment,
    _preexisting_platform_user,
)
from y_web.tests.test_training_modules_registration_integration import _account

AGENT = "agent_integration_one"


@pytest.fixture
def real_layout(core_app, monkeypatch, tmp_path):  # noqa: F811
    """``core_app`` flattens every path; the export and the upload of the core need the real folder layout under tmp_path."""

    def _under_tmp(relative_path=""):
        return os.path.join(str(tmp_path), str(relative_path))

    monkeypatch.setattr("y_web.src.experiment.helpers.get_writable_path", _under_tmp)
    monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", _under_tmp)
    return core_app


def _folder(app, exp_id):
    from y_web import db
    from y_web.src.models import Exps
    from y_web.src.system.path_utils import get_writable_path

    with app.app_context():
        row = db.session.get(Exps, exp_id)
        return (
            os.path.join(get_writable_path(), "y_web", os.path.dirname(row.db_name)),
            row.exp_name,
        )


def _experiment_files(folder, name, population="popint"):
    """What the core's own export finds next to the database: server configuration, population and client files."""
    config = {
        "name": name,
        "host": "127.0.0.1",
        "port": 5999,
        "platform_type": "microblogging",
        "topics": ["Topic 1"],
        "database_uri": "/somewhere/else/database_server.db",
        "data_path": "/somewhere/else/",
    }
    agent = {
        "name": AGENT,
        "is_page": 0,
        "age": 30,
        "type": "llm",
        "leaning": "neutral",
        "oe": "a",
        "co": "a",
        "ne": "a",
        "ag": "a",
        "ex": "a",
        "language": "en",
        "education_level": "hs",
        "round_actions": 1,
        "nationality": "it",
        "toxicity": "no",
        "gender": "none",
        "rec_sys": "default",
        "frec_sys": "default",
        "daily_activity_level": 1,
        "profession": "x",
    }
    client = {
        "simulation": {
            "name": "main",
            "days": 1,
            "percentage_new_agents_iteration": 0,
            "percentage_removed_agents_iteration": 0,
            "slots": 24,
            "actions_likelihood": {
                "post": 0.1,
                "share": 0.1,
                "image": 0.1,
                "comment": 0.1,
                "read": 0.1,
                "news": 0.1,
                "search": 0.1,
                "cast": 0.1,
            },
        },
        "agents": {
            "max_length_thread_reading": 5,
            "reading_from_follower_ratio": 0.5,
            "probability_of_daily_follow": 0.1,
            "attention_window": 10,
            "llm_v_agent": 0,
        },
        "posts": {"visibility_rounds": 10},
        "servers": {
            "api": "http://127.0.0.1:5999/",
            "llm": "http://localhost:11434",
            "llm_api_key": "sk-integration-secret",
            "llm_max_tokens": 50,
            "llm_temperature": 0.5,
            "llm_v": "",
            "llm_v_api_key": "",
            "llm_v_max_tokens": 50,
            "llm_v_temperature": 0.5,
        },
    }
    for filename, payload in (
        ("config_server.json", config),
        (f"{population}.json", {"agents": [agent]}),
        (f"client_main-{population}.json", client),
    ):
        with open(os.path.join(folder, filename), "w") as handle:
            json.dump(payload, handle)
    with open(os.path.join(folder, "_server.log"), "w") as handle:
        handle.write("a student logged in\n")


def _published_module(admin, slot="s1"):
    module = _post(admin, f"{API}/modules", {"title": "Portable module"}).get_json()[
        "module"
    ]["module_uid"]
    r = _post(
        admin,
        f"{API}/modules/{module}/versions/1/steps",
        {
            "type": "scenario",
            "title": "Simulation",
            "revision": 1,
            "completion_policy": {"signal_mode": "declared", "criteria": []},
            "config": {
                "slot_key": slot,
                "hint_name": "Sim",
                "platform_type": "microblogging",
                "simulator_type": "Standard",
            },
        },
    )
    assert (
        _post(
            admin,
            f"{API}/modules/{module}/versions/1/publish",
            {"revision": r.get_json()["revision"]},
        ).status_code
        == 200
    )
    return module


@requires_plugin
def test_a_bundle_made_by_the_real_core_export_imports_through_the_real_core_upload(
    real_layout,
):
    real_layout.config.pop(
        "TM_EXPERIMENT_SCENARIO"
    )  # read the real experiment databases
    app, admin = real_layout, _client_as(real_layout, "admin")
    master, release = _experiment(app, "microblogging", "Standard"), _experiment(
        app, "microblogging", "Standard"
    )
    _release(app, release, master, '{"mode": "after_time", "minutes": 7}')
    account, username, email = _account(app)
    _preexisting_platform_user(
        app, release, username, email, 4242
    )  # a student who used the release
    folder, name = _folder(app, release)
    _experiment_files(folder, name)
    module = _published_module(admin)

    # ---- export: the core's archive, cleaned
    exported = _post(
        admin,
        f"{API}/modules/{module}/versions/1/bundle",
        {"assignments": {"s1": release}},
    )
    assert exported.status_code == 200, exported.get_data(as_text=True)
    raw = exported.get_data()
    parts = {
        n: zipfile.ZipFile(io.BytesIO(raw)).read(n)
        for n in zipfile.ZipFile(io.BytesIO(raw)).namelist()
    }
    manifest = json.loads(parts["manifest.json"])
    assert manifest["scenarios"][0]["scenario_name"] == "Drill" and manifest[
        "scenarios"
    ][0]["advance"] == {"mode": "after_time", "minutes": 7}
    inner = zipfile.ZipFile(io.BytesIO(parts["scenarios/01.zip"]))
    names = set(inner.namelist())
    assert {
        "config_server.json",
        "database_server.db",
        "popint.json",
        "client_main-popint.json",
    } <= names and "_server.log" not in names
    blob = b"".join(inner.read(n) for n in names)
    for forbidden in (
        username.encode(),
        email.encode(),
        b"sk-integration-secret",
        b"/somewhere/else",
    ):
        assert forbidden not in blob, forbidden
    assert AGENT.encode() in blob
    assert (
        json.loads(inner.read("client_main-popint.json"))["servers"]["llm_max_tokens"]
        == 50
    )  # numbers stay numbers

    # ---- import (as a copy: this installation already has the module): the core's own upload builds the experiment
    imported = admin.post(
        f"{API}/bundle/import?as_copy=1",
        data={"file": (io.BytesIO(raw), "bundle.zip")},
        headers={"X-CSRF-Token": "tok"},
    )
    assert imported.status_code == 201, imported.get_json()
    report = imported.get_json()
    new_exp = report["experiments"][0]["exp_id"]
    assert (
        new_exp not in (master, release)
        and report["experiments"][0]["name"] == "Portable module - Drill"
    )
    from y_web import db
    from y_web.src.models import Exps, Population_Experiment

    with app.app_context():
        row = db.session.get(Exps, new_exp)
        assert (
            row.exp_name == "Portable module - Drill"
            and row.platform_type == "microblogging"
            and row.simulator_type == "Standard"
        )
        assert (
            db.session.query(Population_Experiment).filter_by(id_exp=new_exp).count()
            == 1
        )  # the population came with it
    new_folder, _ = _folder(app, new_exp)
    config = json.load(open(os.path.join(new_folder, "config_server.json")))
    assert config[
        "name"
    ] == "Portable module - Drill" and "/somewhere/else" not in json.dumps(config)
    database = sqlite3.connect(os.path.join(new_folder, "database_server.db"))
    try:
        assert database.execute(
            "SELECT COUNT(*) FROM user_mgmt WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone() == (0,)
        assert database.execute("SELECT exp_id, name FROM sd_scenario").fetchone() == (
            0,
            "Drill",
        )
    finally:
        database.close()

    # ---- the guide: a run of the copy binds the imported release in one step, and the real scenario check accepts it
    copy = report["module_uid"]
    assert copy != module
    rev = admin.get(f"{API}/modules/{copy}/versions/1").get_json()["version"][
        "revision"
    ]
    assert (
        _post(
            admin, f"{API}/modules/{copy}/versions/1/publish", {"revision": rev}
        ).status_code
        == 200
    )
    rid = _post(
        admin,
        f"{API}/runs",
        {"module_uid": copy, "version_no": 1, "name": "Copied run"},
    ).get_json()["run"]["id"]
    links = admin.get(f"{API}/runs/{rid}/bundle-links").get_json()["links"]
    assert [(l["slot_key"], l["exp_id"], l["problems"]) for l in links] == [
        ("s1", new_exp, [])
    ]
    bound = _post(admin, f"{API}/runs/{rid}/bundle-bind").get_json()["results"]
    assert [b["bound"] for b in bound] == [True]
    state = admin.get(f"{API}/runs/{rid}/bindings").get_json()["bindings"][0]
    assert (
        state["exp_id"] == new_exp
        and state["scenario"]["name"] == "Drill"
        and state["scenario"]["advance"] == {"mode": "after_time", "minutes": 7}
    )

    for exp in (
        release,
        new_exp,
    ):  # the files of the experiments of this test are not kept
        shutil.rmtree(_folder(app, exp)[0], ignore_errors=True)


@requires_plugin
def test_the_bundle_pages_and_routes_need_a_staff_session(core_app):  # noqa: F811
    student = _client_as(core_app, "user")
    admin = _client_as(core_app, "admin")
    module = _published_module(admin)
    assert (
        _post(
            student, f"{API}/modules/{module}/versions/1/bundle", {"assignments": {}}
        ).status_code
        == 403
    )
    assert (
        student.post(
            f"{API}/bundle/import", data={}, headers={"X-CSRF-Token": "tok"}
        ).status_code
        == 403
    )
