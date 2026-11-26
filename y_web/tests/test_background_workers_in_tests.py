"""The HPC log-sync thread is not started for test applications, and still is for a real one."""

import pytest

pytestmark = pytest.mark.unit


class _App:
    def __init__(self, testing):
        self.config = {"TESTING": testing}


def test_testing_apps_do_not_start_background_workers():
    from y_web import background_workers_allowed

    assert background_workers_allowed(_App(True)) is False


def test_running_under_pytest_is_enough_to_hold_them_back():
    from y_web import background_workers_allowed

    assert background_workers_allowed(_App(False)) is False


def test_a_real_app_outside_pytest_starts_them(monkeypatch):
    from y_web import background_workers_allowed

    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert background_workers_allowed(_App(False)) is True
    assert background_workers_allowed(_App(None)) is True


def test_create_app_leaves_the_log_sync_scheduler_stopped():
    from y_web import create_app
    from y_web.src.hpc.log_sync_scheduler import get_scheduler, stop_log_sync_scheduler

    stop_log_sync_scheduler()
    create_app(db_type="sqlite")
    assert get_scheduler() is None
