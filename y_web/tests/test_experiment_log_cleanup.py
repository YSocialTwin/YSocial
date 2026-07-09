"""
Tests for experiment log cleanup helpers.
"""

import pytest

pytestmark = pytest.mark.unit


def test_clear_experiment_log_files_removes_root_and_nested_logs(tmp_path):
    from y_web.routes.admin.sub.experiments._helpers import clear_experiment_log_files

    exp_folder = tmp_path / "experiment"
    nested_logs = exp_folder / "logs"
    nested_custom = exp_folder / "subdir" / "runtime"
    nested_logs.mkdir(parents=True)
    nested_custom.mkdir(parents=True)

    keep_file = exp_folder / "config_server.json"
    keep_file.write_text("{}", encoding="utf-8")

    removable_files = [
        exp_folder / "_server.log",
        exp_folder / "server_stdout.log",
        nested_logs / "client_a_client.log",
        nested_logs / "client_a_client.log.1",
        nested_logs / "vllm_actor.log.1.gz",
        nested_custom / "agent_execution.log",
        nested_custom / "events.jsonl",
    ]
    for file_path in removable_files:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("log", encoding="utf-8")

    deleted_count, failed_paths = clear_experiment_log_files(str(exp_folder))

    assert deleted_count == len(removable_files)
    assert failed_paths == []
    assert keep_file.exists()
    for file_path in removable_files:
        assert not file_path.exists()


def test_is_experiment_log_filename_handles_rotated_and_compressed_names():
    from y_web.routes.admin.sub.experiments._helpers import _is_experiment_log_filename

    assert _is_experiment_log_filename("_server.log")
    assert _is_experiment_log_filename("client.log.1")
    assert _is_experiment_log_filename("vllm_actor.log.2.gz")
    assert _is_experiment_log_filename("history.jsonl")
    assert not _is_experiment_log_filename("config_server.json")
    assert not _is_experiment_log_filename("population_name.json")
