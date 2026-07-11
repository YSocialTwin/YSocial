"""
Regression checks for dynamic schedule filling.

These tests guard the new optional queue-like execution mode while preserving
the default fixed-batch workflow.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")


def test_dynamic_fill_ui_and_start_payload_are_wired():
    settings_template = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "settings.html"
    ).read_text(encoding="utf-8")
    admin_settings_js = (
        REPO_ROOT / "y_web" / "static" / "assets" / "js" / "admin-settings.js"
    ).read_text(encoding="utf-8")

    assert 'id="dynamic-fill-toggle"' in settings_template
    assert "Optional dynamic filling can reuse open slots" in settings_template
    assert settings_template.index('id="dynamic-fill-toggle"') < settings_template.index(
        'id="schedule-log-container"'
    )
    assert "dynamic_filling_enabled: dynamicFillingEnabled" in admin_settings_js
    assert "dynamicFillToggle.disabled = true;" in admin_settings_js
    assert "dynamicFillToggle.checked = !!data.dynamic_filling_enabled;" in admin_settings_js


def test_dynamic_fill_schema_columns_are_present():
    model_source = (
        REPO_ROOT / "y_web" / "src" / "models" / "admin.py"
    ).read_text(encoding="utf-8")
    migration_source = (
        REPO_ROOT / "y_web" / "migrations" / "add_experiment_schedule_tables.py"
    ).read_text(encoding="utf-8")

    assert "current_group_capacity" in model_source
    assert "dynamic_filling_enabled" in model_source
    assert "launch_in_progress" in model_source
    assert "current_group_capacity INTEGER" in migration_source
    assert "dynamic_filling_enabled INTEGER NOT NULL DEFAULT 0" in migration_source
    assert "launch_in_progress INTEGER NOT NULL DEFAULT 0" in migration_source


def test_dynamic_fill_helper_uses_no_autoflush_for_read_queries():
    schedule_source = (
        REPO_ROOT / "y_web" / "routes" / "admin" / "sub" / "experiments" / "_schedule.py"
    ).read_text(encoding="utf-8")

    assert "with db.session.no_autoflush:" in schedule_source
    assert "Population.query.filter_by(id=client.population_id).first()" in schedule_source
    assert "Client.query.filter_by(id_exp=exp.idexp).all()" in schedule_source
    assert "with _schedule_check_lock:" in schedule_source


def test_check_progress_dispatches_to_dynamic_fill_mode():
    from y_web.routes.admin.sub.experiments._schedule import _do_check_schedule_progress

    status = SimpleNamespace(
        is_running=1,
        current_group_id=11,
        dynamic_filling_enabled=1,
    )

    with patch(
        "y_web.routes.admin.sub.experiments._schedule._get_or_create_schedule_status",
        return_value=status,
    ), patch(
        "y_web.routes.admin.sub.experiments._schedule._advance_dynamic_schedule",
        return_value={"success": True, "is_running": True},
    ) as mock_advance:
        result = _do_check_schedule_progress()

    mock_advance.assert_called_once_with(status, [])
    assert result["success"] is True
    assert result["is_running"] is True


def test_dynamic_fill_is_blocked_while_initial_launch_is_in_progress(app):
    from y_web.routes.admin.sub.experiments._schedule import _advance_dynamic_schedule

    status = SimpleNamespace(
        is_running=1,
        current_group_id=11,
        dynamic_filling_enabled=1,
        launch_in_progress=1,
    )

    with app.app_context():
        with patch(
            "y_web.routes.admin.sub.experiments._schedule.ExperimentScheduleGroup.query.get"
        ) as mock_group_get, patch(
            "y_web.routes.admin.sub.experiments._schedule._get_ordered_schedule_items"
        ) as mock_ordered:
            result = _advance_dynamic_schedule(status, [])

        assert result["success"] is True
        assert result["is_running"] is True
        assert result["all_completed"] is False
        assert result["current_group_id"] == 11
        mock_group_get.assert_not_called()
        mock_ordered.assert_not_called()


def test_stop_schedule_disables_advancement_before_teardown():
    schedule_source = (
        REPO_ROOT / "y_web" / "routes" / "admin" / "sub" / "experiments" / "_schedule.py"
    ).read_text(encoding="utf-8")

    stop_section = schedule_source.split("def stop_schedule():", 1)[1].split(
        "@experiments.route(\"/admin/schedule/check_progress\"", 1
    )[0]

    assert "with _schedule_check_lock:" in stop_section
    assert "status.is_running = 0" in stop_section
    assert "status.dynamic_filling_enabled = 0" in stop_section
    assert "status.launch_in_progress = 1" in stop_section


def test_check_progress_preserves_default_batch_progression():
    from y_web.routes.admin.sub.experiments._schedule import _do_check_schedule_progress

    status = SimpleNamespace(
        is_running=1,
        current_group_id=22,
        dynamic_filling_enabled=0,
    )
    current_item = SimpleNamespace(experiment_id=7)
    current_exp = SimpleNamespace(exp_status="active")

    with patch(
        "y_web.routes.admin.sub.experiments._schedule._get_or_create_schedule_status",
        return_value=status,
    ), patch(
        "y_web.routes.admin.sub.experiments._schedule._advance_dynamic_schedule"
    ) as mock_advance, patch(
        "y_web.routes.admin.sub.experiments._schedule.ExperimentScheduleItem"
    ) as mock_item_cls, patch(
        "y_web.routes.admin.sub.experiments._schedule.Exps"
    ) as mock_exps_cls:
        mock_item_cls.query.filter_by.return_value.order_by.return_value.all.return_value = [
            current_item
        ]
        mock_exps_cls.query.get.return_value = current_exp

        result = _do_check_schedule_progress()

    mock_advance.assert_not_called()
    assert result["success"] is True
    assert result["is_running"] is True
    assert result["all_completed"] is False
    assert result["current_group_id"] == 22


def test_failed_experiment_does_not_free_dynamic_fill_slot(app):
    from y_web.routes.admin.sub.experiments._schedule import _advance_dynamic_schedule
    from y_web.routes.admin.sub.experiments import _schedule as schedule_module

    current_group = SimpleNamespace(id=11, order_index=0, name="group-1")
    current_items = [
        SimpleNamespace(experiment_id=1),
        SimpleNamespace(experiment_id=2),
        SimpleNamespace(experiment_id=3),
    ]
    exp_active_1 = SimpleNamespace(idexp=1, exp_status="active", running=1)
    exp_failed = SimpleNamespace(idexp=2, exp_status="stopped", running=0)
    exp_active_2 = SimpleNamespace(idexp=3, exp_status="active", running=1)

    status = SimpleNamespace(
        is_running=1,
        current_group_id=11,
        current_group_capacity=3,
        dynamic_filling_enabled=1,
        launch_in_progress=0,
    )

    with app.app_context():
        fake_group_query = SimpleNamespace(
            get=lambda group_id: current_group,
            filter=SimpleNamespace(
                order_by=SimpleNamespace(
                    all=lambda: []
                )
            ),
        )
        fake_exp_query = SimpleNamespace(
            get=lambda exp_id: {
                1: exp_active_1,
                2: exp_failed,
                3: exp_active_2,
            }.get(exp_id)
        )

        with patch.object(schedule_module.ExperimentScheduleGroup, "query", fake_group_query), patch.object(
            schedule_module.Exps, "query", fake_exp_query
        ), patch(
            "y_web.routes.admin.sub.experiments._schedule._get_ordered_schedule_items",
            return_value=current_items,
        ):
            result = _advance_dynamic_schedule(status, [])

        assert result["success"] is True
        assert result["is_running"] is True
        assert result["all_completed"] is False
