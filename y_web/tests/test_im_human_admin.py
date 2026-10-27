"""Human participation: configuration, gateway lifecycle and the researcher's view (plan 5.8, Phase 10)."""

import json
import os
import stat
import sys
import textwrap
import time

import pytest

from y_web.tests.test_im_admin_pages import _make_im_experiment, im_app  # noqa: F401


def test_participation_off_leaves_the_configuration_untouched_and_on_is_the_default():
    from y_web.routes.admin.sub.experiments._im import generate_im_server_config

    base = dict(exp_name="e", db_uri="/x/database_server.db", data_path="/x", num_days="3", start_date="2026-01-01")
    plain = generate_im_server_config(**base, human_enabled=False)
    assert "human" not in plain
    assert generate_im_server_config(**base, human_enabled=False, human_min_round_seconds="9") == plain
    assert generate_im_server_config(**base)["human"]["enabled"] is True  # YWeb experiments always have it


def test_participation_on_writes_the_human_section_and_validates():
    from y_web.routes.admin.sub.experiments._im import ImConfigError, generate_im_server_config

    base = dict(exp_name="e", db_uri="/x/database_server.db", data_path="/x")
    cfg = generate_im_server_config(**base, human_enabled=True, human_min_round_seconds="5", human_max_humans="12")
    assert cfg["human"] == {"enabled": True, "max_humans": 12, "pace": {"min_round_seconds": 5.0}}
    assert generate_im_server_config(**base, human_enabled=True)["human"]["pace"]["min_round_seconds"] == 0
    for bad in ({"human_min_round_seconds": "-1"}, {"human_min_round_seconds": "x"}, {"human_max_humans": "0"}):
        with pytest.raises(ImConfigError):
            generate_im_server_config(**base, human_enabled=True, **bad)


def test_the_generated_human_section_is_valid_for_the_runtime(tmp_path):
    from y_web.routes.admin.sub.experiments._im import generate_im_server_config
    from y_web.src.im.engine import ensure_im_importable

    ensure_im_importable()
    from yinstantmessaging.common.config import load_server_config

    cfg = generate_im_server_config("e", str(tmp_path / "database_server.db"), str(tmp_path), human_enabled=True, human_min_round_seconds="3")
    for key in ("database_uri", "data_path", "is_remote", "experiment_name", "platform_type"):
        cfg.pop(key, None)
    (tmp_path / "server_config.json").write_text(json.dumps(cfg))
    loaded = load_server_config(tmp_path)
    assert loaded["human"]["enabled"] is True and loaded["human"]["pace"]["min_round_seconds"] == 3


def _folder(tmp_path, human=True):
    (tmp_path / "server_config.json").write_text(json.dumps({"human": {"enabled": True}} if human else {}))
    return str(tmp_path)


FAKE_GATEWAY = textwrap.dedent(
    """
    import json, os, signal, sys, time
    folder = sys.argv[1]
    assert len(os.environ["YIM_GATEWAY_TOKEN"]) >= 16
    open(os.path.join(folder, "human_gateway.json"), "w").write(json.dumps({"host": "127.0.0.1", "port": 1, "pid": os.getpid()}))
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    time.sleep(60)
    """
)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX signals")
def test_gateway_lifecycle_start_status_stop(tmp_path):
    from y_web.src.im import gateway_process as gp

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "run_gateway.py").write_text(FAKE_GATEWAY)
    (tmp_path / "exp").mkdir()
    folder = _folder(tmp_path / "exp")
    assert gp.gateway_status(folder)["status"] == "stopped"
    pid = gp.start_gateway(folder, str(repo))
    try:
        assert pid and gp.is_running(folder)
        mode = stat.S_IMODE(os.stat(os.path.join(folder, "human_gateway.token")).st_mode)
        assert mode == 0o600  # the per-run token is readable by the owner only
        assert gp.start_gateway(folder, str(repo)) == pid  # idempotent: a running gateway is reused
    finally:
        assert gp.stop_gateway(folder) is True
    assert not gp.is_running(folder)
    assert not os.path.exists(os.path.join(folder, "human_gateway.json"))
    assert not os.path.exists(os.path.join(folder, "human_gateway.token"))


def test_a_gateway_that_cannot_start_is_a_warning_not_an_error(tmp_path):
    from y_web.src.im import gateway_process as gp

    (tmp_path / "exp").mkdir()
    folder = _folder(tmp_path / "exp")
    assert gp.start_gateway(folder, str(tmp_path / "missing-repo")) is None  # no script
    assert not os.path.exists(os.path.join(folder, "human_gateway.token"))
    off = tmp_path / "off"
    off.mkdir()
    assert gp.start_gateway(_folder(off, human=False), str(tmp_path)) is None  # participation off: nothing starts
    assert gp.gateway_status(str(off))["status"] == "off"


def test_the_hpc_start_helper_never_raises(monkeypatch, tmp_path):
    from y_web.src.hpc import client

    monkeypatch.setattr("y_web.src.im.gateway_process.start_gateway", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    client._start_im_human_gateway(str(tmp_path))  # must not raise


def test_gateway_runtime_files_are_run_artifacts():
    from y_web.src.im.clone import is_run_artifact

    assert is_run_artifact("human_gateway.json") and is_run_artifact("human_gateway.token")


def test_the_gateway_client_needs_the_state_and_the_token(tmp_path):
    from y_web.src.im.gateway_client import GatewayClient, GatewayUnavailable

    with pytest.raises(GatewayUnavailable):
        GatewayClient(str(tmp_path)).state()
    (tmp_path / "human_gateway.json").write_text(json.dumps({"host": "127.0.0.1", "port": 1}))
    with pytest.raises(GatewayUnavailable):  # no token
        GatewayClient(str(tmp_path)).state()
    (tmp_path / "human_gateway.token").write_text("t" * 20)
    with pytest.raises(GatewayUnavailable):  # nothing listens on port 1
        GatewayClient(str(tmp_path)).state()


def test_details_page_lists_the_participants_and_the_gateway(im_app, tmp_path, monkeypatch):
    from y_web import db
    from y_web.src.im.human_identity import human_account_id
    from y_web.src.models import Admin_users, Exps, User_Experiment

    monkeypatch.setattr(
        "y_web.routes.admin.sub.clients._im._experiment_configuration_update_required", lambda exp: False
    )
    app, client = im_app
    exp_id = _make_im_experiment(app)
    with app.app_context():
        exp = db.session.get(Exps, exp_id)
        uid = exp.db_name.split("/")[1]
        user = Admin_users(username="pp", email="pp@x.test", password="x", last_seen="2026-01-01", role="user")
        db.session.add(user)
        db.session.commit()
        db.session.add(User_Experiment(user_id=user.id, exp_id=exp_id))
        db.session.commit()
        expected = human_account_id(uid, user.id)
    folder = tmp_path / "y_web" / "experiments" / uid
    folder.mkdir(parents=True)
    page = client.get(f"/admin/experiment_details/{exp_id}")
    assert page.status_code == 200 and b"im-human-section" not in page.data  # off: nothing shown
    (folder / "server_config.json").write_text(json.dumps({"human": {"enabled": True, "pace": {"min_round_seconds": 4}}}))
    page = client.get(f"/admin/experiment_details/{exp_id}")
    html = page.data.decode()
    assert page.status_code == 200 and "im-human-section" in html
    assert "pp" in html and "not entered yet" in html and "cannot be reproduced" in html
    assert "stopped" in html and "Minimum round duration" in html
    assert expected not in html  # the account is listed only once it exists
