"""Every combination of the "Experiment Configuration" switches is written to the files of a forum HPC experiment.

The page posts to /admin/update_experiment_config; for each combination the server file, every client file and the
page itself (re-read) must show exactly what was submitted, and the strict YForum schemas must still accept the files.
"""

import itertools
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.src.forum.experiment_config import (
    generate_forum_server_config,
    read_switches,
)

YFORUM = Path(__file__).resolve().parents[2] / "external" / "YForum"
SWITCHES = (
    "opinion_dynamics_enabled",
    "stress_reward_enabled",
    "memory_enabled",
    "sentiment_annotation",
    "emotion_annotation",
)


def _env(monkeypatch, tmp_path, llm):
    from y_web import create_app, db
    from y_web.src.models import Admin_users, Client, Exps, Population

    monkeypatch.setattr(
        "y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path)
    )
    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    uid = uuid.uuid4().hex
    folder = tmp_path / "y_web" / "experiments" / uid
    folder.mkdir(parents=True)
    with app.app_context():
        admin = Admin_users(
            username="admm",
            email=f"{uuid.uuid4().hex}@x.test",
            password="x",
            last_seen="2026-01-01",
            role="admin",
        )
        db.session.add(admin)
        exp = Exps(
            exp_name="matrix",
            platform_type="forum",
            simulator_type="HPC",
            db_name=f"experiments/{uid}/database_server.db",
            owner="admm",
            exp_descr="d",
            status=0,
            port=5103,
            server="127.0.0.1",
            prompt_language="en",
            llm_agents_enabled=llm,
        )
        pop = Population(name="pop one", descr="d")
        db.session.add_all([exp, pop])
        db.session.commit()
        for name in ("a", "b"):  # two clients, as the experiment of the report has
            db.session.add(
                Client(
                    name=name,
                    descr="d",
                    id_exp=exp.idexp,
                    population_id=pop.id,
                    days=1,
                    status=0,
                )
            )
        db.session.commit()
        ids = (exp.idexp, admin.id, admin.username, admin.email, uid)
    return app, folder, ids


@pytest.mark.integration
@pytest.mark.parametrize("llm", [1, 0])
def test_every_combination_of_switches_is_written_and_read_back(
    monkeypatch, tmp_path, llm
):
    if not (YFORUM / "YForum" / "config_validation.py").exists():
        pytest.skip("external/YForum is not checked out")
    pytest.importorskip("jsonschema")
    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.config_validation import validate
    finally:
        sys.path.remove(str(YFORUM))

    app, folder, (exp_id, admin_id, name, email, uid) = _env(monkeypatch, tmp_path, llm)
    server_file = folder / "server_config.json"
    server_file.write_text(
        json.dumps(
            generate_forum_server_config(
                "matrix", f"experiments/{uid}/database_server.db", str(folder), seed=3
            )
        )
    )
    example = json.loads(
        (YFORUM / "example" / "rule_based" / "client_config.json").read_text()
    )
    example.setdefault("agents", {})["llm_agents"] = ["llama3.2"] if llm else [None]
    client_files = [folder / f"client_{c}-pop one.json" for c in ("a", "b")]
    for path in client_files:
        path.write_text(json.dumps(example))

    user = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        is_anonymous=False,
        id=admin_id,
        username=name,
        role="admin",
        telemetry_enabled=0,
        get_id=lambda: str(admin_id),
        email=email,
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: user)
    monkeypatch.setattr(
        "y_web.src.system.miscellanea.check_privileges", lambda *a, **k: None
    )
    http = app.test_client()

    for mask in itertools.product([False, True], repeat=len(SWITCHES)):
        form = {key: "on" for key, on in zip(SWITCHES, mask) if on}
        assert (
            http.post(
                f"/admin/update_experiment_config/{exp_id}", data=form
            ).status_code
            == 302
        )
        sent = dict(zip(SWITCHES, mask))
        # annotations and memory only exist for LLM agents; the rest is stored as sent
        expect = {
            "opinion": sent["opinion_dynamics_enabled"],
            "stress_reward": sent["stress_reward_enabled"],
            "memory": sent["memory_enabled"] and bool(llm),
            "sentiment": sent["sentiment_annotation"] and bool(llm),
            "emotion": sent["emotion_annotation"] and bool(llm),
        }
        raw = json.loads(server_file.read_text())
        server = validate(raw, "config/server_config")
        got = read_switches(server)
        assert {k: got[k] for k in expect} == expect, (mask, got)
        assert server["experiment_configuration_confirmed"] is True
        for path in client_files:
            cfg = validate(json.loads(path.read_text()), "config/client_config")
            assert cfg["simulation"]["opinion_dynamics"]["enabled"] is expect["opinion"]
            assert cfg["stress_reward"]["enabled"] is expect["stress_reward"]
            assert cfg["agents"]["memory_enabled"] is expect["memory"]
            assert cfg["simulation"]["emotion_annotation"] is expect["emotion"]
        # the page shows what was stored
        html = http.get(f"/admin/experiment_details/{exp_id}").data.decode()
        for key in ("opinion_dynamics_enabled", "stress_reward_enabled"):
            tag = html.split(f'name="{key}"', 1)[1].split(">", 1)[0]
            assert ("checked" in tag) is sent[key], (key, mask)
