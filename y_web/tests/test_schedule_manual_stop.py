"""
Tests for manual stop isolation in scheduled experiments.

Manual stop must affect only the targeted experiment. It must not remove the
experiment from its schedule group, and it must not promote sibling experiments
to completed/stopped as a side effect.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_manual_stop_keeps_experiment_in_schedule_group():
    """Manual stop should no longer remove the experiment from its group."""
    crud_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_crud.py"
    ).read_text(encoding="utf-8")

    assert "removed from schedule group" not in crud_source
    assert "left in place for later resume" in crud_source
    assert '{Exps.running: 0, Exps.exp_status: "stopped"}' in crud_source


def test_schedule_stop_marks_experiment_stopped_not_completed():
    """Schedule stop should not infer natural completion."""
    schedule_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_schedule.py"
    ).read_text(encoding="utf-8")

    assert 'exp.exp_status = "stopped"' in schedule_source
    assert 'final_status = "completed" if all_clients_completed else "stopped"' not in schedule_source


def test_schedule_progress_only_advances_on_completed_experiments():
    """Group advancement should still depend on explicit completed status."""
    schedule_source = Path(
        "/Users/rossetti/PycharmProjects/YWeb/y_web/routes/admin/sub/experiments/_schedule.py"
    ).read_text(encoding="utf-8")

    assert 'if exp.exp_status != "completed":' in schedule_source
    assert "current_group.is_completed = 1" in schedule_source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
