"""
Helpers for experiment/client clock configuration.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VALID_CLOCK_MODES = {"simulated", "real_time"}
VALID_FEED_REFRESH = {"hourly"}

DEFAULT_CLOCK_MODE = "simulated"
DEFAULT_CLOCK_TIMEZONE = "Europe/Belgrade"
DEFAULT_CLOCK_FEED_REFRESH = "hourly"


def default_clock_config() -> Dict[str, str]:
    """Return default experiment-wide clock configuration."""
    return {
        "mode": DEFAULT_CLOCK_MODE,
        "timezone": DEFAULT_CLOCK_TIMEZONE,
        "feed_refresh": DEFAULT_CLOCK_FEED_REFRESH,
    }


def validate_clock_mode(value: Any) -> str:
    """Validate and normalize clock mode."""
    mode = str(value or DEFAULT_CLOCK_MODE).strip().lower()
    if mode not in VALID_CLOCK_MODES:
        raise ValueError(
            f"Invalid clock mode '{mode}'. Valid values: {', '.join(sorted(VALID_CLOCK_MODES))}."
        )
    return mode


def validate_feed_refresh(value: Any) -> str:
    """Validate and normalize feed refresh policy."""
    feed_refresh = str(value or DEFAULT_CLOCK_FEED_REFRESH).strip().lower()
    if feed_refresh not in VALID_FEED_REFRESH:
        raise ValueError(
            f"Invalid feed refresh '{feed_refresh}'. Valid values: {', '.join(sorted(VALID_FEED_REFRESH))}."
        )
    return feed_refresh


def validate_timezone(value: Any) -> str:
    """Validate IANA timezone and return normalized value."""
    timezone_name = str(value or DEFAULT_CLOCK_TIMEZONE).strip()
    if not timezone_name:
        timezone_name = DEFAULT_CLOCK_TIMEZONE

    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(
            f"Invalid timezone '{timezone_name}'. Use a valid IANA timezone like '{DEFAULT_CLOCK_TIMEZONE}'."
        ) from None

    return timezone_name


def parse_anchor_date(anchor_value: Any) -> Optional[date]:
    """Parse optional anchor date from ISO format."""
    if anchor_value is None:
        return None

    text = str(anchor_value).strip()
    if not text:
        return None

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def current_local_time(timezone_name: str) -> datetime:
    """Return timezone-aware current datetime for the given timezone."""
    return datetime.now(ZoneInfo(validate_timezone(timezone_name)))


def wall_clock_slot(
    now_local: datetime,
    anchor_date: Optional[date],
) -> tuple[int, int]:
    """Convert current local wall-clock time to (simulation_day, simulation_hour)."""
    base_day = anchor_date or now_local.date()
    day_offset = (now_local.date() - base_day).days
    return max(day_offset, 0), int(now_local.hour)


def seconds_until_next_hour(now_local: datetime) -> float:
    """Return seconds until next top-of-hour boundary."""
    next_hour = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(
        hours=1
    )
    return max((next_hour - now_local).total_seconds(), 1.0)


def ensure_experiment_clock(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure config has a valid `clock` section; mutate and return normalized section.
    """
    raw_clock = config.get("clock")
    if not isinstance(raw_clock, dict):
        raw_clock = {}

    normalized: Dict[str, Any] = {
        "mode": validate_clock_mode(raw_clock.get("mode", DEFAULT_CLOCK_MODE)),
        "timezone": validate_timezone(
            raw_clock.get("timezone", DEFAULT_CLOCK_TIMEZONE)
        ),
        "feed_refresh": validate_feed_refresh(
            raw_clock.get("feed_refresh", DEFAULT_CLOCK_FEED_REFRESH)
        ),
    }

    parsed_anchor = parse_anchor_date(raw_clock.get("anchor_date"))
    if parsed_anchor is not None:
        normalized["anchor_date"] = parsed_anchor.isoformat()

    config["clock"] = normalized
    return normalized


def apply_clock_to_client_simulation(
    simulation: Dict[str, Any], clock: Dict[str, Any]
) -> None:
    """Write experiment clock settings into a client simulation config payload."""
    simulation["clock_mode"] = validate_clock_mode(
        clock.get("mode", DEFAULT_CLOCK_MODE)
    )
    simulation["timezone"] = validate_timezone(
        clock.get("timezone", DEFAULT_CLOCK_TIMEZONE)
    )
    simulation["feed_refresh"] = validate_feed_refresh(
        clock.get("feed_refresh", DEFAULT_CLOCK_FEED_REFRESH)
    )

    parsed_anchor = parse_anchor_date(clock.get("anchor_date"))
    if parsed_anchor is not None:
        simulation["clock_anchor_date"] = parsed_anchor.isoformat()
    else:
        simulation.pop("clock_anchor_date", None)
