"""
Tests for experiment progress computation in the admin experiments data API.
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def test_client_execution_progress_percentage_ignores_infinite_clients():
    from y_web.routes.admin.sub.experiments._data import (
        _client_execution_progress_percentage,
    )

    infinite_exec = SimpleNamespace(elapsed_time=40, expected_duration_rounds=-1)
    assert _client_execution_progress_percentage(infinite_exec) is None


def test_average_experiment_progress_returns_none_without_client_executions():
    from y_web.routes.admin.sub.experiments._data import _average_experiment_progress

    clients = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    assert _average_experiment_progress(clients, {}) is None


def test_average_experiment_progress_averages_available_client_executions():
    from y_web.routes.admin.sub.experiments._data import _average_experiment_progress

    clients = [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]
    client_exec_by_client_id = {
        1: SimpleNamespace(elapsed_time=25, expected_duration_rounds=100),
        2: SimpleNamespace(elapsed_time=50, expected_duration_rounds=100),
        3: SimpleNamespace(elapsed_time=150, expected_duration_rounds=100),
    }

    assert _average_experiment_progress(clients, client_exec_by_client_id) == 58
