"""
Phase C — experiment/clock.py validation and computation logic tests.

Covers the clock helpers that determine experiment timing. Bugs here silently
corrupt scheduled simulations, so every computation path is exercised.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
pytestmark = pytest.mark.unit



# ---------------------------------------------------------------------------
# validate_feed_refresh
# ---------------------------------------------------------------------------


def test_validate_feed_refresh_accepts_valid_value():
    from y_web.src.experiment.clock import validate_feed_refresh

    assert validate_feed_refresh("hourly") == "hourly"


def test_validate_feed_refresh_normalises_case():
    from y_web.src.experiment.clock import validate_feed_refresh

    assert validate_feed_refresh("HOURLY") == "hourly"


def test_validate_feed_refresh_rejects_invalid():
    from y_web.src.experiment.clock import validate_feed_refresh

    with pytest.raises(ValueError, match="feed refresh"):
        validate_feed_refresh("daily")


def test_validate_feed_refresh_uses_default_for_none():
    from y_web.src.experiment.clock import validate_feed_refresh, DEFAULT_CLOCK_FEED_REFRESH

    assert validate_feed_refresh(None) == DEFAULT_CLOCK_FEED_REFRESH


# ---------------------------------------------------------------------------
# parse_anchor_date
# ---------------------------------------------------------------------------


def test_parse_anchor_date_returns_date_object():
    from y_web.src.experiment.clock import parse_anchor_date

    result = parse_anchor_date("2024-03-15")
    assert isinstance(result, date)
    assert result == date(2024, 3, 15)


def test_parse_anchor_date_invalid_returns_none():
    from y_web.src.experiment.clock import parse_anchor_date

    assert parse_anchor_date("not-a-date") is None


def test_parse_anchor_date_none_returns_none():
    from y_web.src.experiment.clock import parse_anchor_date

    assert parse_anchor_date(None) is None


def test_parse_anchor_date_empty_string_returns_none():
    from y_web.src.experiment.clock import parse_anchor_date

    assert parse_anchor_date("") is None


# ---------------------------------------------------------------------------
# wall_clock_slot
# ---------------------------------------------------------------------------


def test_wall_clock_slot_returns_day_and_hour():
    from y_web.src.experiment.clock import wall_clock_slot

    tz = ZoneInfo("Europe/Belgrade")
    now = datetime(2024, 6, 10, 14, 30, tzinfo=tz)
    anchor = date(2024, 6, 10)
    day, hour = wall_clock_slot(now, anchor)
    assert day == 0
    assert hour == 14


def test_wall_clock_slot_advances_day_on_next_calendar_date():
    from y_web.src.experiment.clock import wall_clock_slot

    tz = ZoneInfo("Europe/Belgrade")
    anchor = date(2024, 6, 10)
    now = datetime(2024, 6, 11, 8, 0, tzinfo=tz)
    day, hour = wall_clock_slot(now, anchor)
    assert day == 1
    assert hour == 8


def test_wall_clock_slot_no_anchor_uses_today():
    from y_web.src.experiment.clock import wall_clock_slot

    tz = ZoneInfo("UTC")
    now = datetime(2024, 6, 10, 9, 0, tzinfo=tz)
    day, hour = wall_clock_slot(now, None)
    # With no anchor, today is the base → day must be 0
    assert day == 0
    assert hour == 9


# ---------------------------------------------------------------------------
# seconds_until_next_hour
# ---------------------------------------------------------------------------


def test_seconds_until_next_hour_at_half_past():
    from y_web.src.experiment.clock import seconds_until_next_hour

    tz = ZoneInfo("UTC")
    now = datetime(2024, 1, 1, 12, 30, 0, tzinfo=tz)
    secs = seconds_until_next_hour(now)
    assert abs(secs - 1800.0) < 2, f"Expected ~1800 s, got {secs}"


def test_seconds_until_next_hour_at_top_of_hour():
    from y_web.src.experiment.clock import seconds_until_next_hour

    tz = ZoneInfo("UTC")
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=tz)
    secs = seconds_until_next_hour(now)
    assert abs(secs - 3600.0) < 2, f"Expected ~3600 s, got {secs}"


def test_seconds_until_next_hour_always_positive():
    from y_web.src.experiment.clock import seconds_until_next_hour

    tz = ZoneInfo("UTC")
    now = datetime(2024, 1, 1, 23, 59, 59, tzinfo=tz)
    secs = seconds_until_next_hour(now)
    assert secs >= 1.0


# ---------------------------------------------------------------------------
# ensure_experiment_clock
# ---------------------------------------------------------------------------


def test_ensure_experiment_clock_fills_defaults():
    from y_web.src.experiment.clock import ensure_experiment_clock

    config = {}
    clock = ensure_experiment_clock(config)
    assert "mode" in clock
    assert "timezone" in clock
    assert "feed_refresh" in clock


def test_ensure_experiment_clock_preserves_valid_values():
    from y_web.src.experiment.clock import ensure_experiment_clock

    config = {"clock": {"mode": "simulated", "timezone": "UTC", "feed_refresh": "hourly"}}
    clock = ensure_experiment_clock(config)
    assert clock["mode"] == "simulated"
    assert clock["timezone"] == "UTC"


def test_ensure_experiment_clock_stores_result_in_config():
    from y_web.src.experiment.clock import ensure_experiment_clock

    config = {}
    clock = ensure_experiment_clock(config)
    assert config.get("clock") is clock


def test_ensure_experiment_clock_parses_anchor_date():
    from y_web.src.experiment.clock import ensure_experiment_clock

    config = {"clock": {"anchor_date": "2025-01-01"}}
    clock = ensure_experiment_clock(config)
    assert clock.get("anchor_date") == "2025-01-01"


# ---------------------------------------------------------------------------
# apply_clock_to_client_simulation
# ---------------------------------------------------------------------------


def test_apply_clock_to_client_simulation_sets_fields():
    from y_web.src.experiment.clock import apply_clock_to_client_simulation

    simulation = {}
    clock = {"mode": "simulated", "timezone": "UTC", "feed_refresh": "hourly"}
    apply_clock_to_client_simulation(simulation, clock)
    assert simulation["clock_mode"] == "simulated"
    assert simulation["timezone"] == "UTC"
    assert simulation["feed_refresh"] == "hourly"


def test_apply_clock_to_client_simulation_sets_anchor_date():
    from y_web.src.experiment.clock import apply_clock_to_client_simulation

    simulation = {}
    clock = {
        "mode": "simulated",
        "timezone": "UTC",
        "feed_refresh": "hourly",
        "anchor_date": "2025-06-01",
    }
    apply_clock_to_client_simulation(simulation, clock)
    assert simulation.get("clock_anchor_date") == "2025-06-01"


def test_apply_clock_to_client_simulation_removes_stale_anchor():
    from y_web.src.experiment.clock import apply_clock_to_client_simulation

    simulation = {"clock_anchor_date": "2024-01-01"}
    clock = {"mode": "simulated", "timezone": "UTC", "feed_refresh": "hourly"}
    apply_clock_to_client_simulation(simulation, clock)
    assert "clock_anchor_date" not in simulation
