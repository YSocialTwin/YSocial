"""The experiment-level switches of an IM experiment (annotations, opinion, stress/reward, memory)."""

import json
import uuid
from pathlib import Path

import pytest

from y_web.src.im import experiment_config as xc


def _server_config():
    from y_web.routes.admin.sub.experiments._im import generate_im_server_config

    return generate_im_server_config("e", "/x/database_server.db", "/x/")


# -- pure functions --------------------------------------------------------------------------------
def test_switches_are_mirrored_into_the_keys_im_reads():
    cfg = xc.apply_experiment_switches(_server_config(), toxicity=True, sentiment=True, memory=True, stress_reward=True)
    assert cfg["simulation"]["enable_toxicity"] is True and cfg["toxicity_annotation"] is True
    assert cfg["simulation"]["enable_sentiment"] is True and cfg["sentiment_annotation"] is True
    assert cfg["simulation"]["memory_enabled"] is True and cfg["memory"]["enabled"] is True
    assert cfg["telegram"]["stress_reward"]["enabled"] is True and cfg["stress_reward_enabled"] is True
    assert xc.read_switches(cfg) == {
        "toxicity": True, "sentiment": True, "emotion": False, "opinion": False, "stress_reward": True, "memory": True,
    }
    xc.apply_experiment_switches(cfg, toxicity=False, memory=False)
    assert cfg["simulation"]["enable_toxicity"] is False and cfg["simulation"]["memory_enabled"] is False
    assert cfg["simulation"]["enable_sentiment"] is True  # untouched when not named


def test_the_stress_reward_detail_follows_im_schema_and_drops_the_events_it_does_not_have():
    from y_web.routes.admin.sub.experiments._helpers import normalize_stress_reward_config

    detail = normalize_stress_reward_config({"enabled": True, "system": {"coupling": {"reward_buffers_stress_alpha": 0.5}}})
    block = xc.stress_reward_to_im(detail)
    assert block["enabled"] is True and block["coupling"]["reward_buffers_stress_alpha"] == 0.5
    assert set(block["events"]) == {"reaction", "comment"}
    assert "traits" not in block  # IM's own default applies
    back = normalize_stress_reward_config(xc.stress_reward_from_im(block))
    assert back["system"]["coupling"]["reward_buffers_stress_alpha"] == 0.5


def test_the_switches_written_are_valid_for_the_im_schema():
    jsonschema = pytest.importorskip("jsonschema")
    from y_web.src.system.path_utils import get_external_repo_dir

    schema_file = Path(get_external_repo_dir("YInstantMessaging")) / "schemas" / "config" / "server_config.json"
    if not schema_file.is_file():
        pytest.skip("YInstantMessaging is not installed")
    cfg = xc.apply_experiment_switches(_server_config(), toxicity=True, sentiment=True, memory=True, stress_reward=True)
    jsonschema.validate(cfg, json.loads(schema_file.read_text()))


def test_client_switches_keep_the_parameters_the_researcher_chose():
    client = {"opinion_dynamics": {"enabled": False, "model_name": "llm_evaluation"}, "agents": {"memory_total_max_chars": 900}}
    xc.apply_switches_to_client(client, emotion=True, opinion=True, stress_reward=True, memory=True)
    assert client["opinion_dynamics"] == {"enabled": True, "model_name": "llm_evaluation"}
    assert client["simulation"]["emotion_annotation"] is True
    assert client["stress_reward"]["enabled"] is True
    assert client["agents"] == {"memory_total_max_chars": 900, "memory_enabled": True}


def test_time_parameters_come_from_the_client_form():
    cfg = _server_config()
    xc.apply_time_parameters(cfg, days=3, start_date="2026-05-01", ticks_per_round=6)
    assert cfg["simulation"]["num_days"] == 3 and cfg["simulation"]["start_date"] == "2026-05-01"
    assert cfg["telegram"]["time"]["ticks_per_round"] == 6
    # a second client may lengthen the run but must agree on the experiment's clock
    xc.apply_time_parameters(cfg, days=10, start_date="2026-05-01", ticks_per_round=6, other_clients=1)
    assert cfg["simulation"]["num_days"] == 10
    xc.apply_time_parameters(cfg, days=2, other_clients=1)
    assert cfg["simulation"]["num_days"] == 10
    with pytest.raises(xc.TimeParameterError):
        xc.apply_time_parameters(cfg, start_date="2026-06-01", other_clients=1)
    with pytest.raises(xc.TimeParameterError):
        xc.apply_time_parameters(cfg, ticks_per_round=12, other_clients=1)
    # once the run has started nothing may change the clock
    with pytest.raises(xc.TimeParameterError):
        xc.apply_time_parameters(cfg, days=11, run_started=True)
    xc.apply_time_parameters(cfg, days=5, run_started=True)
    assert cfg["simulation"]["num_days"] == 10


# -- the update action ---------------------------------------------------------------------------
@pytest.mark.integration
def test_the_update_action_writes_server_and_client_files(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from y_web import create_app, db
    from y_web.src.models import Admin_users, Client, Exps, Population

    monkeypatch.setattr("y_web.src.system.path_utils.get_writable_path", lambda *a: str(tmp_path))
    app = create_app(db_type="sqlite")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    uid = uuid.uuid4().hex
    folder = tmp_path / "y_web" / "experiments" / uid
    folder.mkdir(parents=True)
    with app.app_context():
        admin = Admin_users(username="adm2", email=f"{uuid.uuid4().hex}@x.test", password="x", last_seen="2026-01-01", role="admin")
        db.session.add(admin)
        exp = Exps(
            exp_name="sw", platform_type="instant_messaging", simulator_type="HPC",
            db_name=f"experiments/{uid}/database_server.db", owner="adm2", exp_descr="d", status=0, port=5101,
            server="127.0.0.1", prompt_language="en", llm_agents_enabled=1,
        )
        pop = Population(name="pop one", descr="d")
        db.session.add_all([exp, pop])
        db.session.commit()
        client = Client(name="c1", descr="d", id_exp=exp.idexp, population_id=pop.id, days=1, status=0)
        db.session.add(client)
        db.session.commit()
        exp_id, admin_id, admin_name, admin_email = exp.idexp, admin.id, admin.username, admin.email
    (folder / "server_config.json").write_text(json.dumps(_server_config()))
    (folder / "client_c1-pop one.json").write_text(json.dumps({"client_name": "c1", "opinion_dynamics": {"enabled": False, "model_name": "bounded_confidence"}}))
    user = SimpleNamespace(
        is_authenticated=True, is_active=True, is_anonymous=False, id=admin_id, username=admin_name,
        role="admin", telemetry_enabled=0, get_id=lambda: str(admin_id), email=admin_email,
    )
    monkeypatch.setattr("flask_login.utils._get_user", lambda: user)
    monkeypatch.setattr("y_web.src.system.miscellanea.check_privileges", lambda *a, **k: None)
    client_http = app.test_client()

    response = client_http.post(
        f"/admin/update_experiment_config/{exp_id}",
        data={"opinion_dynamics_enabled": "on", "stress_reward_enabled": "on", "memory_enabled": "on", "sentiment_annotation": "on"},
    )
    assert response.status_code == 302
    server = json.loads((folder / "server_config.json").read_text())
    assert server["experiment_configuration_confirmed"] is True
    assert server["simulation"]["enable_sentiment"] is True and server["simulation"]["memory_enabled"] is True
    assert server["telegram"]["stress_reward"]["enabled"] is True
    assert server["opinion_dynamics_enabled"] is True and "perspective_api" not in server
    cfg = json.loads((folder / "client_c1-pop one.json").read_text())
    assert cfg["opinion_dynamics"] == {"enabled": True, "model_name": "bounded_confidence"}
    assert cfg["stress_reward"]["enabled"] is True and cfg["agents"]["memory_enabled"] is True
    assert "enable_sentiment" not in cfg.get("simulation", {})  # server-side keys stay out of the client file
    page = client_http.get(f"/admin/experiment_details/{exp_id}").data.decode()
    assert "memory_enabled" in page, "memory toggle"
    assert "Stress / Reward Settings" in page, "stress link"
    assert "Memory Embeddings" not in page and "Edit LLM Prompts" not in page
    assert 'id="im-advanced-settings"' in page and 'name="min_round_seconds"' in page
    save = client_http.post(f"/admin/update_im_advanced_settings/{exp_id}", data={"min_round_seconds": "2", "max_humans": "9"})
    assert save.status_code == 302
    assert json.loads((folder / "server_config.json").read_text())["human"] == {"enabled": True, "max_humans": 9, "pace": {"min_round_seconds": 2.0}}


def test_advanced_settings_are_validated_written_and_locked_after_the_first_start(tmp_path):
    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / "server_config.json").write_text(json.dumps(_server_config()))
    assert xc.read_advanced_settings(str(folder)) == {"min_round_seconds": 0.0, "max_humans": 50, "locked": False}
    xc.write_advanced_settings(str(folder), min_round_seconds="3", max_humans="20")
    assert xc.read_advanced_settings(str(folder)) == {"min_round_seconds": 3.0, "max_humans": 20, "locked": False}
    for bad in ({"min_round_seconds": "-1"}, {"min_round_seconds": "x"}, {"max_humans": "0"}):
        with pytest.raises(xc.AdvancedSettingsError):
            xc.write_advanced_settings(str(folder), **bad)
    (folder / "database_server.db").write_text("")
    with pytest.raises(xc.AdvancedSettingsError):
        xc.write_advanced_settings(str(folder), min_round_seconds="1")
    assert xc.read_advanced_settings(str(folder))["locked"] is True
