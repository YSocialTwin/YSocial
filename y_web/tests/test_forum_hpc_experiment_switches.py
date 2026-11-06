"""The switches of /admin/experiment_details work on a forum HPC experiment (plan F12).

Saving the page writes the keys YForum reads, in the server and in the client files, and the result still satisfies the
strict schemas of YForum. Skipped when YForum is not checked out.
"""

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from y_web.src.forum.experiment_config import generate_forum_server_config

YFORUM = Path(__file__).resolve().parents[2] / "external" / "YForum"


@pytest.mark.integration
def test_saving_the_page_activates_the_modules_of_a_forum_hpc_experiment(
    monkeypatch, tmp_path
):
    if not (YFORUM / "YForum" / "config_validation.py").exists():
        pytest.skip("external/YForum is not checked out")
    pytest.importorskip("jsonschema")

    from y_web import create_app, db
    from y_web.src.models import Admin_users, Client, Exps, Population

    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.config_validation import validate
    finally:
        sys.path.remove(str(YFORUM))

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
            username="admf",
            email=f"{uuid.uuid4().hex}@x.test",
            password="x",
            last_seen="2026-01-01",
            role="admin",
        )
        db.session.add(admin)
        exp = Exps(
            exp_name="forum hpc",
            platform_type="forum",
            simulator_type="HPC",
            db_name=f"experiments/{uid}/database_server.db",
            owner="admf",
            exp_descr="d",
            status=0,
            port=5102,
            server="127.0.0.1",
            prompt_language="en",
            llm_agents_enabled=1,
        )
        pop = Population(name="pop one", descr="d")
        db.session.add_all([exp, pop])
        db.session.commit()
        client = Client(
            name="c1",
            descr="d",
            id_exp=exp.idexp,
            population_id=pop.id,
            days=1,
            status=0,
        )
        db.session.add(client)
        db.session.commit()
        exp_id, admin_id, admin_name, admin_email = (
            exp.idexp,
            admin.id,
            admin.username,
            admin.email,
        )

    server_file = folder / "server_config.json"
    server_file.write_text(
        json.dumps(
            generate_forum_server_config(
                "forum hpc",
                f"experiments/{uid}/database_server.db",
                str(folder),
                seed=3,
            )
        )
    )
    example = json.loads(
        (YFORUM / "example" / "rule_based" / "client_config.json").read_text()
    )
    # the page switches annotations and memory off for rule-based agents (llm_agents null): use an LLM client
    example.setdefault("agents", {})["llm_agents"] = ["llama3.2"]
    client_file = folder / "client_c1-pop one.json"
    client_file.write_text(json.dumps(example))

    user = SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        is_anonymous=False,
        id=admin_id,
        username=admin_name,
        role="admin",
        telemetry_enabled=0,
        get_id=lambda: str(admin_id),
        email=admin_email,
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: user)
    monkeypatch.setattr(
        "y_web.src.system.miscellanea.check_privileges", lambda *a, **k: None
    )
    http = app.test_client()

    response = http.post(
        f"/admin/update_experiment_config/{exp_id}",
        data={
            "opinion_dynamics_enabled": "on",
            "stress_reward_enabled": "on",
            "memory_enabled": "on",
            "sentiment_annotation": "on",
            "emotion_annotation": "on",
        },
    )
    assert response.status_code == 302

    server = validate(json.loads(server_file.read_text()), "config/server_config")
    assert server["experiment_configuration_confirmed"] is True
    assert (
        server["sentiment_annotation"] is True and server["emotion_annotation"] is True
    )
    assert server["toxicity_annotation"] is False
    assert server["stress_reward"] == {"enabled": True}
    assert server["opinion_dynamics_enabled"] is True
    assert server["memory"] == {"enabled": True}

    client_cfg = validate(json.loads(client_file.read_text()), "config/client_config")
    assert client_cfg["simulation"]["opinion_dynamics"]["enabled"] is True
    assert client_cfg["simulation"]["emotion_annotation"] is True
    assert client_cfg["stress_reward"]["enabled"] is True
    assert client_cfg["agents"]["memory_enabled"] is True
    # nothing the Flask clients understand is written into the YForum client file
    assert "opinion_dynamics" not in json.loads(client_file.read_text())
    assert "enable_sentiment" not in client_cfg["simulation"]

    page = http.get(f"/admin/experiment_details/{exp_id}")
    assert page.status_code == 200
    assert "memory_enabled" in page.data.decode(), "the memory selector is offered"

    # switching everything off turns the runtime keys off as well
    http.post(f"/admin/update_experiment_config/{exp_id}", data={})
    server = validate(json.loads(server_file.read_text()), "config/server_config")
    client_cfg = validate(json.loads(client_file.read_text()), "config/client_config")
    assert server["stress_reward"] == {"enabled": False}
    assert server["emotion_annotation"] is False and server["memory"] == {
        "enabled": False
    }
    assert client_cfg["simulation"]["opinion_dynamics"]["enabled"] is False
    assert client_cfg["agents"]["memory_enabled"] is False
    assert client_cfg["stress_reward"]["enabled"] is False
