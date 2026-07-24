"""
Regression tests for client execution duration synchronization.

These tests ensure that changing a client's simulation length keeps the
database and the on-disk client config aligned with the new total length.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_duration_sync_updates_all_duration_fields():
    from y_web.routes.admin.sub.clients._execution import (
        _sync_duration_fields_in_client_config,
    )

    config = {
        "simulation": {
            "days": 7,
            "num_days": 7,
            "run_until_stopped": False,
        },
        "client": {"max_ticks": 168},
        "max_ticks": 168,
    }

    updated = _sync_duration_fields_in_client_config(config, 2)

    assert updated["simulation"]["days"] == 2
    assert updated["simulation"]["num_days"] == 2
    assert updated["client"]["max_ticks"] == 48
    assert updated["max_ticks"] == 48


def test_process_runner_reuses_client_days_as_expected_rounds():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/src/simulation/process_runner.py"
    ).read_text(encoding="utf-8")

    assert "expected_rounds = -1 if cli.days == -1 else cli.days * 24" in source
    assert "ce.expected_duration_rounds = expected_rounds" in source


def test_hpc_client_reuses_client_days_as_expected_rounds():
    source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/src/hpc/client.py"
    ).read_text(encoding="utf-8")

    assert "_sync_hpc_client_duration_from_config" in source
    assert "_resolve_hpc_client_days_from_config" in source
    assert "client_exec.expected_duration_rounds = expected_rounds" in source
