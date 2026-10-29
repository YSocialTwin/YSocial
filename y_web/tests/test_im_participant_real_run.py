"""A person takes part in a real IM run (Ray server, gateway process, simulated agents): Phase 10 gate.

Scenarios E11 (a participant writes during a live run), E12 (the gateway dies: the run goes on) and the
barrier property: no human, absent or slow, ever holds a round.
"""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from y_web.tests.test_im_client_creation import (  # noqa: F401
    IM_REPO,
    _post,
    _seed,
    _start_server,
    env,
)


def _start_client(folder, name):
    from y_web.src.hpc.client import _normalize_im_client_config
    from y_web.src.im.validation import validate_im_folder

    cfg = Path(folder) / f"client_{name}-pop.json"
    _normalize_im_client_config(str(folder), name, "pop", str(cfg))
    validate_im_folder(str(folder), str(IM_REPO), client_config=cfg.name)
    return subprocess.Popen(
        [sys.executable, str(IM_REPO / "run_client.py"), "--config", str(cfg)],
        env=dict(os.environ),
        stdout=open(Path(folder) / f"client_{name}.out", "w"),
        stderr=subprocess.STDOUT,
    )


def _prepare(app, env):
    from y_web import db
    from y_web.src.models import Admin_users, User_Experiment

    exp, pop = _seed(app, env)
    _post(app, env, exp, pop, days="1")
    folder = Path(env.im._experiment_folder(exp))
    cfg_path = folder / "server_config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["human"] = {"enabled": True, "max_humans": 3}
    cfg_path.write_text(json.dumps(cfg))
    user = Admin_users(
        username="pp",
        email="pp@x.test",
        password="x",
        last_seen="2026-01-01",
        role="user",
    )
    db.session.add(user)
    db.session.commit()
    db.session.add(User_Experiment(user_id=user.id, exp_id=exp.idexp))
    db.session.commit()
    return exp, folder, user


def _rounds(folder):
    conn = sqlite3.connect(str(Path(folder) / "database_server.db"))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM rounds WHERE status='closed'"
        ).fetchone()[0]
    finally:
        conn.close()


@pytest.mark.external_repo
@pytest.mark.integration
def test_a_participant_writes_during_a_live_run_and_the_run_completes(
    app, env, monkeypatch, tmp_path
):
    """The gateway process, the Ray server and the simulated agents, with a person writing in between.

    The routes are exercised against an in-process server in ``test_im_participant.py``; here the pieces
    that only exist in a real run are checked: the gateway as a separate process with its per-run token,
    registration as a non-blocking client, and a run that completes with a human in it.
    """
    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.src.hpc import server as hs
    from y_web.src.im import gateway_process as gp
    from y_web.src.im.gateway_client import GatewayClient
    from y_web.src.im.human_identity import human_account_id, human_key

    with app.app_context():
        exp, folder, user = _prepare(app, env)
        uid = Path(folder).name
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        gateway_pid = gp.start_gateway(str(folder), str(IM_REPO), sys.executable)
        client = None
        try:
            assert gateway_pid, "the gateway process did not start"
            gw = GatewayClient(str(folder))
            assert gp.gateway_status(str(folder))["status"] == "running"
            client = _start_client(folder, "cl")
            code, body = gw.ensure(human_key(uid, user.id), "participant-%d" % user.id)
            assert code == 200 and body["data"]["account_id"] == human_account_id(
                uid, user.id
            )
            account = body["data"]["account_id"]
            sent, deadline, last, refused = None, time.time() + 150, None, None
            while client.poll() is None and time.time() < deadline and sent is None:
                target = _first_public_message(folder)
                if target:
                    chat_id, message_id = target
                    gw.actions(
                        account,
                        [
                            {
                                "type": "join",
                                "chat_id": chat_id,
                                "client_action_id": "j1",
                            }
                        ],
                    )
                    if (
                        refused is None
                    ):  # a channel does not let members post: IM's permission service says no
                        code, body = gw.actions(
                            account,
                            [
                                {
                                    "type": "post",
                                    "chat_id": chat_id,
                                    "text": "not allowed here",
                                    "client_action_id": "p0",
                                }
                            ],
                        )
                        refused = (
                            code == 200 and body["data"]["outcomes"][0]["ok"] is False
                        )
                    code, body = gw.actions(
                        account,
                        [
                            {
                                "type": "react",
                                "message_id": message_id,
                                "emoji": "👍",
                                "client_action_id": "r1",
                            }
                        ],
                    )
                    last = (code, body)
                    if code == 200 and body["data"]["outcomes"][0]["ok"]:
                        sent = message_id
                time.sleep(0.3)
            assert (
                client.wait(timeout=150) == 0
            ), "the simulation did not complete with a human in the run"
            assert (
                sent
            ), f"the participant could not act during the live run: {last} {_chat_kinds(folder)}"
            assert refused is True
            conn = sqlite3.connect(str(Path(folder) / "database_server.db"))
            reaction = conn.execute(
                "SELECT emoji FROM reactions WHERE account_id=? AND message_id=?",
                (account, sent),
            ).fetchone()
            kind = conn.execute(
                "SELECT kind FROM accounts WHERE id=?", (account,)
            ).fetchone()
            posted = conn.execute(
                "SELECT count(*) FROM messages WHERE text=?", ("not allowed here",)
            ).fetchone()[0]
            conn.close()
            assert reaction == ("👍",) and kind == ("human",) and posted == 0
            assert _rounds(folder) >= 24
        finally:
            if client is not None and client.poll() is None:
                client.kill()
            gp.stop_gateway(str(folder))
            hs.stop_hpc_server(exp.idexp)
        assert not (Path(folder) / "human_gateway.token").exists()


def _first_public_message(folder):
    try:
        conn = sqlite3.connect(str(Path(folder) / "database_server.db"))
        row = conn.execute(
            "SELECT m.chat_id, m.id FROM messages m JOIN chats c ON c.id = m.chat_id "
            "WHERE c.visibility='public' AND m.deleted_round IS NULL ORDER BY m.sim_ts LIMIT 1"
        ).fetchone()
        conn.close()
        return row
    except sqlite3.Error:
        return None


@pytest.mark.external_repo
@pytest.mark.integration
def test_a_dead_gateway_does_not_stop_the_simulation(app, env, monkeypatch, tmp_path):
    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.src.hpc import server as hs
    from y_web.src.im import gateway_process as gp
    from y_web.src.im.gateway_client import read_gateway_state

    with app.app_context():
        exp, folder, user = _prepare(app, env)
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        pid = gp.start_gateway(str(folder), str(IM_REPO), sys.executable)
        client = None
        try:
            assert pid
            client = _start_client(folder, "cl")
            time.sleep(2)
            os.kill(
                read_gateway_state(str(folder))["pid"], signal.SIGKILL
            )  # the gateway crashes mid-run
            assert client.wait(timeout=150) == 0
            assert _rounds(folder) >= 24
            assert gp.gateway_status(str(folder))["status"] in (
                "stopped",
                "unreachable",
            )
        finally:
            if client is not None and client.poll() is None:
                client.kill()
            gp.stop_gateway(str(folder))
            hs.stop_hpc_server(exp.idexp)


def _chat_kinds(folder):
    conn = sqlite3.connect(str(Path(folder) / "database_server.db"))
    try:
        return conn.execute(
            "SELECT type, visibility, count(*) FROM chats GROUP BY 1,2"
        ).fetchall()
    finally:
        conn.close()


@pytest.mark.external_repo
@pytest.mark.integration
def test_round_pacing_is_a_lower_bound_and_the_run_still_completes(
    app, env, monkeypatch, tmp_path
):
    """Pilot of ``human.pace.min_round_seconds`` (O-15): 24 rounds of at least 1.5 s each, nobody waited for."""
    if not (IM_REPO / "run_server.py").is_file():
        pytest.skip("YInstantMessaging is not installed")
    from y_web.src.hpc import server as hs

    with app.app_context():
        exp, folder, user = _prepare(app, env)
        cfg_path = Path(folder) / "server_config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["human"]["pace"] = {"min_round_seconds": 1.5}
        cfg_path.write_text(json.dumps(cfg))
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        try:
            started = time.time()
            client = _start_client(folder, "cl")
            assert client.wait(timeout=170) == 0
            elapsed = time.time() - started
            assert _rounds(folder) >= 24
            assert elapsed >= 24 * 1.5 * 0.9, f"paced run took only {elapsed:.1f}s"
        finally:
            hs.stop_hpc_server(exp.idexp)
