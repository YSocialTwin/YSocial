"""Start-time checks of a forum client on YForum: the offline validator and the client-file normalizer (plan F12)."""

import json
import sys

import pytest

from y_web.src.forum import validation
from y_web.src.forum.client_config import build_client_config, parse_client_form
from y_web.src.forum.experiment_config import generate_forum_server_config
from y_web.src.hpc.client import _normalize_forum_client_config
from y_web.tests.test_forum_hpc_experiment_creation import YFORUM


def _folder(tmp_path, slots=24, client_slots=None):
    server = generate_forum_server_config("e", "u", "d", seed=3, slots_per_day=slots)
    values = parse_client_form({}, content_recsys=[], follow_recsys=[])
    client = build_client_config(
        values,
        client_name="c1",
        population_file="pop.json",
        owner="admin",
        llm_agents_enabled=False,
        language="en",
        server_config=server,
    )
    if client_slots:
        client["num_slots_per_day"] = client_slots
    (tmp_path / "server_config.json").write_text(json.dumps(server))
    (tmp_path / "client_c1-pop.json").write_text(json.dumps(client))
    (tmp_path / "pop.json").write_text(json.dumps({"agents": []}))
    return tmp_path


@pytest.fixture
def yforum(monkeypatch):
    if not (YFORUM / "YForum" / "cli" / "validate.py").exists():
        pytest.skip("external/YForum is not checked out")
    pytest.importorskip("jsonschema")
    monkeypatch.setattr(validation, "python_command", lambda: [sys.executable])
    return str(YFORUM)


def test_a_valid_folder_passes_the_offline_validator(tmp_path, yforum):
    folder = _folder(tmp_path)
    validation.validate_forum_folder(str(folder), yforum, "client_c1-pop.json")
    validation.validate_forum_folder(str(folder), yforum)  # server start: no client yet


def test_a_broken_client_is_refused_with_the_reasons(tmp_path, yforum):
    folder = _folder(tmp_path, slots=24, client_slots=12)
    with pytest.raises(validation.ForumValidationError) as info:
        validation.validate_forum_folder(str(folder), yforum, "client_c1-pop.json")
    assert info.value.messages
    path = folder / "client_c1-pop.json"
    config = json.loads(path.read_text())
    config["unknown_key"] = 1
    path.write_text(json.dumps(config))
    with pytest.raises(validation.ForumValidationError):
        validation.validate_forum_folder(str(folder), yforum, "client_c1-pop.json")


def test_an_unrunnable_validator_counts_as_invalid(tmp_path):
    ok, messages = validation.run_forum_validate(str(tmp_path), str(tmp_path / "nope"))
    assert not ok and messages


def test_the_normalizer_checks_name_and_population_without_rewriting(tmp_path):
    folder = _folder(tmp_path)
    path = str(folder / "client_c1-pop.json")
    before = (folder / "client_c1-pop.json").read_text()
    _normalize_forum_client_config(str(folder), "c1", "pop", path)
    assert (folder / "client_c1-pop.json").read_text() == before
    with pytest.raises(ValueError):
        _normalize_forum_client_config(str(folder), "other", "pop", path)
    (folder / "pop.json").unlink()
    with pytest.raises(FileNotFoundError):
        _normalize_forum_client_config(str(folder), "c1", "pop", path)


def _yforum_log(path, slots=4, days=2, complete=True):
    """Write an execution log with YForum's own formatter, as the client does."""
    if not (YFORUM / "YForum" / "YServer" / "logging_utils.py").exists():
        pytest.skip("external/YForum is not checked out")
    import logging

    sys.path.insert(0, str(YFORUM))
    try:
        from YForum.YServer.logging_utils import JsonFormatter
    finally:
        sys.path.remove(str(YFORUM))
    logger = logging.getLogger(f"forum-test-{path.name}")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(path)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    for day in range(1, days + 1):
        for slot in range(1, slots + 1):
            logger.info(
                "hourly summary",
                extra={
                    "extra_data": {
                        "summary_type": "hourly",
                        "day": day,
                        "slot": slot,
                        "slots_per_day": slots,
                    }
                },
            )
    if complete:
        logger.info("Client natural completion reached")
    handler.close()


def test_the_monitor_reads_the_progress_and_completion_of_a_yforum_client(tmp_path):
    from y_web.src.hpc import log_metrics

    log = tmp_path / "c1_execution.log"
    _yforum_log(log, slots=4, days=2)
    latest = log_metrics.get_latest_hourly_summary_from_client_log(str(log))
    # 1-based elapsed rounds with the slots per day of the log, not a fixed 24
    assert latest == {"day": 2, "slot": 4, "elapsed_time": 8}
    lines, _last = log_metrics._read_execution_log_tail(str(log))
    assert log_metrics._tail_contains_completion_marker(lines)

    running = tmp_path / "c2_execution.log"
    _yforum_log(running, complete=False)
    lines, _last = log_metrics._read_execution_log_tail(str(running))
    assert not log_metrics._tail_contains_completion_marker(lines)
