"""Dating run management (S4): validator, launch wiring, clone, reset and download helpers."""

import json
import os
import sqlite3

import pytest

from y_web.src.dating import clone, validation
from y_web.src.hpc.client import _normalize_dating_client_config
from y_web.src.hpc.platforms import get_hpc_platform

pytestmark = pytest.mark.unit


def _make_folder(tmp_path):
    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / "server_config.json").write_text(
        json.dumps({"platform_type": "dating", "simulation": {"num_slots_per_day": 6}})
    )
    pop = {"agents": []}
    (folder / "pop.json").write_text(json.dumps(pop))
    (folder / "client_c1-pop.json").write_text(
        json.dumps({"client_name": "c1", "population_file": "pop.json", "num_days": 2})
    )
    return folder


def test_platform_spec_launches_with_separate_client_file():
    spec = get_hpc_platform("dating")
    assert spec.validates_config and spec.client_config_file_arg
    assert spec.client_config_only and spec.orchestrator_actor == "Orchestrator"


def test_normalizer_checks_name_and_population(tmp_path):
    folder = _make_folder(tmp_path)
    cfg = str(folder / "client_c1-pop.json")
    before = open(cfg).read()
    _normalize_dating_client_config(str(folder), "c1", "pop", cfg)
    assert open(cfg).read() == before  # nothing rewritten: the run hash must not move
    with pytest.raises(ValueError):
        _normalize_dating_client_config(str(folder), "other", "pop", cfg)
    (folder / "pop.json").unlink()
    with pytest.raises(FileNotFoundError):
        _normalize_dating_client_config(str(folder), "c1", "pop", cfg)


def test_validator_runs_the_runtime_module(tmp_path, monkeypatch):
    seen = {}

    class Done:
        returncode = 2
        stdout = json.dumps(
            {"valid": False, "errors": [{"check": "population", "message": "bad"}]}
        )
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Done()

    monkeypatch.setattr(validation.subprocess, "run", fake_run)
    monkeypatch.setattr(validation, "_python_command", lambda: ["python"])
    with pytest.raises(validation.DatingValidationError) as exc:
        validation.validate_dating_folder(
            str(tmp_path), "/repo", client_config="c.json"
        )
    assert exc.value.messages == ["population: bad"]
    assert "YDating.cli.validate" in seen["cmd"] and "--client-config" in seen["cmd"]


def test_validator_failure_to_run_counts_as_invalid(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("no python")

    monkeypatch.setattr(validation.subprocess, "run", boom)
    monkeypatch.setattr(validation, "_python_command", lambda: ["python"])
    valid, messages = validation.run_dating_validate(str(tmp_path), "/repo")
    assert not valid and "could not be run" in messages[0]


def test_clone_copies_inputs_only_and_reset_removes_artifacts(tmp_path):
    folder = _make_folder(tmp_path)
    for name in (
        "database_server.db",
        "database_server.db-wal",
        "run_lock.json",
        "ray_ready.temp",
        "client_summary_exp:c1.json",
        "analytics_dating.db",
        "c1_execution.log",
    ):
        (folder / name).write_text("x")
    (folder / "logs").mkdir()
    (folder / "logs" / "a.log").write_text("x")
    new = tmp_path / "copy"
    clone.copy_dating_folder(str(folder), str(new))
    assert sorted(os.listdir(new)) == [
        "client_c1-pop.json",
        "logs",
        "pop.json",
        "server_config.json",
    ]
    assert os.listdir(new / "logs") == []

    removed, failed = clone.clear_dating_run_artifacts(str(folder))
    assert removed >= 7 and not failed
    assert sorted(os.listdir(folder)) == [
        "client_c1-pop.json",
        "logs",
        "pop.json",
        "server_config.json",
    ]
    assert os.listdir(folder / "logs") == []


def test_slots_per_day_and_folder_detection(tmp_path):
    folder = _make_folder(tmp_path)
    assert clone.slots_per_day(str(folder)) == 6
    assert clone.slots_per_day(str(tmp_path / "none")) == 24
    assert clone.is_dating_folder(str(folder))
    (folder / "server_config.json").write_text("{}")
    assert not clone.is_dating_folder(str(folder))
    conn = sqlite3.connect(folder / "database_server.db")
    conn.execute(f"CREATE TABLE {clone.DATING_MARKER_TABLE} (id integer)")
    conn.commit()
    conn.close()
    assert clone.is_dating_folder(str(folder))


def test_snapshot_is_consistent_and_leaves_derived_files_out(tmp_path):
    folder = _make_folder(tmp_path)
    conn = sqlite3.connect(folder / "database_server.db")
    conn.execute("CREATE TABLE t (v integer)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()
    (folder / "analytics_dating.db").write_text("derived")
    out = clone.snapshot_for_download(str(folder), str(tmp_path / "snap"))
    assert not os.path.exists(os.path.join(out, "analytics_dating.db"))
    got = (
        sqlite3.connect(os.path.join(out, "database_server.db"))
        .execute("SELECT v FROM t")
        .fetchall()
    )
    assert got == [(1,)]


def test_monitor_reads_dating_progress_and_completion(tmp_path):
    from y_web.src.hpc import log_metrics as lm

    log = tmp_path / "c1_execution.log"
    rows = [
        {"message": "registered"},
        {
            "message": "[x:c1] hourly summary",
            "summary_type": "hourly",
            "day": 1,
            "slot": 1,
        },
        {
            "message": "[x:c1] hourly summary",
            "summary_type": "hourly",
            "day": 2,
            "slot": 3,
        },
        {"message": "Client natural completion reached"},
        {"message": "Client shutdown complete"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    summary = lm.get_latest_hourly_summary_from_client_log(str(log))
    assert summary == {"day": 2, "slot": 3, "elapsed_time": 27}
    lines, _ = lm._read_execution_log_tail(str(log))
    assert lm._tail_contains_completion_marker(lines)


def test_progress_uses_the_slots_of_the_experiment(tmp_path):
    from y_web.src.hpc import log_metrics as lm

    log = tmp_path / "c1_execution.log"
    log.write_text(
        json.dumps({"summary_type": "hourly", "day": 3, "slot": 2, "slots_per_day": 6})
        + "\n"
    )
    assert lm.get_latest_hourly_summary_from_client_log(str(log))["elapsed_time"] == 14
