from datetime import datetime

import y_web.src.forum.service.formatters as _formatters
from y_web.reddit import service


def test_simulated_mode_uses_day_hour_label(monkeypatch):
    clock = {
        "mode": "simulated",
        "timezone": "Europe/Rome",
        "feed_refresh": "hourly",
    }
    monkeypatch.setattr(service, "_resolve_experiment_clock", lambda: clock)
    monkeypatch.setattr(_formatters, "_resolve_experiment_clock", lambda: clock)

    assert service._format_display_time("3", "7") == "Day 3 · Hour 07"
    assert (
        service._format_display_time_from_created_at(datetime(2026, 3, 19, 12, 45))
        is None
    )


def test_real_time_mode_uses_calendar_time(monkeypatch):
    clock = {
        "mode": "real_time",
        "timezone": "Europe/Rome",
        "feed_refresh": "hourly",
    }
    monkeypatch.setattr(service, "_resolve_experiment_clock", lambda: clock)
    monkeypatch.setattr(_formatters, "_resolve_experiment_clock", lambda: clock)

    rendered = service._format_display_time_from_created_at(
        datetime(2026, 3, 19, 12, 45)
    )
    assert rendered is not None
    assert ":" in rendered
    assert service._format_display_time("3", "7")
