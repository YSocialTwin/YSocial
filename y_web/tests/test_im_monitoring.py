"""Monitoring and failure classification with real IM processes and logs (plan, Phase 6)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from y_web.tests.test_im_client_creation import (  # noqa: F401  (fixtures and helpers)
    IM_REPO,
    ROOT,
    _post,
    _seed,
    _start_server,
    env,
)


def _spawn(folder, name="cl", edit=None):
    """Start the real client and return the process (the config is normalized and validated first)."""
    from y_web.src.hpc.client import _normalize_im_client_config

    cfg = Path(folder) / f"client_{name}-pop.json"
    if edit:
        data = json.loads(cfg.read_text())
        edit(data)
        cfg.write_text(json.dumps(data))
    _normalize_im_client_config(str(folder), name, "pop", str(cfg))
    return subprocess.Popen(
        [sys.executable, str(IM_REPO / "run_client.py"), "--config", str(cfg)],
        env=dict(os.environ),
        stdout=open(Path(folder) / f"{name}.out", "w"),
        stderr=subprocess.STDOUT,
    )


def _setup(app, env, monkeypatch, tmp_path, days="1"):
    from y_web import db
    from y_web.src.hpc import server as hs

    exp, pop = _seed(app, env)
    _post(app, env, exp, pop, days=days)
    folder = env.im._experiment_folder(exp)
    exp.running = 1
    db.session.commit()
    return hs, exp, folder


def _register(exp, proc, expected_rounds=24):
    from y_web import db
    from y_web.src.models import Client, Client_Execution

    client = db.session.query(Client).one()
    client.status = 1
    client.pid = proc.pid
    execution = db.session.query(Client_Execution).filter_by(client_id=client.id).one()
    execution.expected_duration_rounds = expected_rounds
    db.session.commit()
    return client, execution


def _monitor():
    from y_web.src.hpc.log_metrics import monitor_hpc_client_execution_logs

    monitor_hpc_client_execution_logs()


def test_execution_log_is_found_under_the_client_id_prefix(
    app, env, monkeypatch, tmp_path
):
    from y_web.src.hpc.client import resolve_hpc_client_execution_log_path

    with app.app_context():
        hs, exp, folder = _setup(app, env, monkeypatch, tmp_path)
        logs = Path(folder) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "uid:cl_execution.log").write_text("")
        (logs / "other:cl2_execution.log").write_text("")
        assert resolve_hpc_client_execution_log_path(
            exp, "cl", log_folder=str(logs)
        ).endswith("uid:cl_execution.log")
        assert (
            resolve_hpc_client_execution_log_path(exp, "missing", log_folder=str(logs))
            is None
        )
        (logs / "cl_execution.log").write_text("")
        assert resolve_hpc_client_execution_log_path(
            exp, "cl", log_folder=str(logs)
        ).endswith("/cl_execution.log")


def test_clean_completion_completes_client_experiment_and_stops_the_server(
    app, env, monkeypatch, tmp_path
):
    from y_web import db
    from y_web.src.models import Exps

    with app.app_context():
        hs, exp, folder = _setup(app, env, monkeypatch, tmp_path)
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        proc = _spawn(folder)
        try:
            assert proc.wait(timeout=150) == 0
            client, execution = _register(exp, proc)
            _monitor()
            db.session.expire_all()
            assert execution.terminal_state == "completed" and client.status == 0
            assert db.session.get(Exps, exp.idexp).exp_status == "completed"
            assert db.session.get(Exps, exp.idexp).running == 0
        finally:
            hs.stop_hpc_server(exp.idexp)


@pytest.mark.parametrize(
    "case, edit, code",
    [
        ("invalid_config", lambda d: d["simulation"].update(num_days=0), 2),
        (
            "llm_down",
            lambda d: d.update(
                llm={
                    "backend": "ollama",
                    "address": "127.0.0.1",
                    "port": 9,
                    "model": "x",
                    "timeout_seconds": 2,
                    "max_concurrency": 4,
                }
            ),
            5,
        ),
    ],
)
def test_client_failures_are_classified_with_a_readable_reason(
    app, env, monkeypatch, tmp_path, case, edit, code
):
    from y_web import db
    from y_web.src.hpc.client import resolve_hpc_client_execution_log_path
    from y_web.src.im.failures import describe_client_failure

    with app.app_context():
        hs, exp, folder = _setup(app, env, monkeypatch, tmp_path)
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        proc = _spawn(folder, edit=edit)
        try:
            assert proc.wait(timeout=160) == code
            client, execution = _register(exp, proc)
            _monitor()
            db.session.expire_all()
            assert execution.terminal_state == "failed" and client.status == 0
            log = resolve_hpc_client_execution_log_path(
                exp, "cl", log_folder=str(Path(folder) / "logs")
            )
            info = describe_client_failure(log)
            if code == 2:
                # a configuration error is raised before the logs exist: YWeb stops it earlier, at launch
                from y_web.src.im.validation import (
                    ImValidationError,
                    validate_im_folder,
                )

                assert info is None
                with pytest.raises(ImValidationError):
                    validate_im_folder(
                        str(folder), str(IM_REPO), client_config="client_cl-pop.json"
                    )
            else:
                assert (
                    info["exit_code"] == code and info["message"] and info["error_type"]
                )
        finally:
            hs.stop_hpc_server(exp.idexp)


def test_kill_nine_is_failed_and_manual_stop_is_not(app, env, monkeypatch, tmp_path):
    from y_web import db

    with app.app_context():
        hs, exp, folder = _setup(app, env, monkeypatch, tmp_path, days="8")
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        try:
            proc = _spawn(folder)
            time.sleep(5)
            proc.kill()
            proc.wait(timeout=20)
            client, execution = _register(exp, proc, expected_rounds=192)
            execution.terminal_state = "manual_stop"
            db.session.commit()
            _monitor()
            db.session.expire_all()
            assert (
                execution.terminal_state == "manual_stop"
            )  # an operator stop is not a failure

            execution.terminal_state = "running"
            client.status = 1
            db.session.commit()
            _monitor()
            db.session.expire_all()
            assert execution.terminal_state == "failed"
        finally:
            hs.stop_hpc_server(exp.idexp)


def test_exit_messages_cover_the_documented_codes(app):
    from y_web.src.im.failures import (
        describe_client_failure,
        exit_messages,
        failure_reason,
    )

    with app.app_context():
        assert {1, 2, 3, 4, 5, 6, 130} <= set(exit_messages())
    assert (
        describe_client_failure(None) is None
        and failure_reason("/does/not/exist") is None
    )


def test_describe_failure_reads_the_last_error_record(tmp_path):
    from y_web.src.im.failures import describe_client_failure, failure_reason

    log = tmp_path / "x_execution.log"
    log.write_text(
        "\n".join(
            [
                json.dumps({"level": "INFO", "message": "Client starting"}),
                json.dumps(
                    {
                        "level": "ERROR",
                        "message": "a",
                        "error_type": "ConfigMismatchError",
                        "error_message": "config_mismatch",
                        "exit_code": 6,
                    }
                ),
                "not json",
            ]
        )
    )
    info = describe_client_failure(str(log))
    assert info["exit_code"] == 6 and info["error_type"] == "ConfigMismatchError"
    assert "differs" in failure_reason(str(log))


def test_metrics_tables_fill_from_the_logs_of_a_real_run(
    app, env, monkeypatch, tmp_path
):
    from y_web import db
    from y_web.src.hpc.client import resolve_hpc_client_log_path
    from y_web.src.hpc.log_metrics import (
        update_client_execution_from_log,
        update_client_log_metrics,
        update_server_log_metrics,
    )
    from y_web.src.models import ClientLogMetrics, ServerLogMetrics

    with app.app_context():
        hs, exp, folder = _setup(app, env, monkeypatch, tmp_path, days="2")
        _start_server(hs, exp, folder, monkeypatch, tmp_path)
        proc = _spawn(folder)
        try:
            assert proc.wait(timeout=150) == 0
        finally:
            hs.stop_hpc_server(exp.idexp)
        client, execution = _register(exp, proc, expected_rounds=48)
        logs = Path(folder) / "logs"
        assert (
            update_server_log_metrics(exp.idexp, str(logs / "_server.log"), is_hpc=True)
            is not False
        )
        client_log = resolve_hpc_client_log_path(exp, "cl", log_folder=str(logs))
        assert (
            update_client_log_metrics(exp.idexp, client.id, client_log, is_hpc=True)
            is not False
        )
        update_client_execution_from_log(client.id, client_log)
        db.session.expire_all()
        assert (
            db.session.query(ServerLogMetrics).filter_by(exp_id=exp.idexp).count() > 0
        )
        assert (
            db.session.query(ClientLogMetrics).filter_by(exp_id=exp.idexp).count() > 0
        )
        assert execution.elapsed_time > 0 and execution.last_active_day >= 1
