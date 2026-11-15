"""Display time of a post as the experiment's clock shows it (shared by the platforms whose pages show the time)."""

from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select

from y_web import db
from y_web.src.experiment.clock import (
    DEFAULT_CLOCK_MODE,
    DEFAULT_CLOCK_TIMEZONE,
    default_clock_config,
    ensure_experiment_clock,
    parse_anchor_date,
)
from y_web.src.experiment.context import get_current_experiment_id
from y_web.src.models import Exps, Rounds

_Y_WEB_DIR = Path(__file__).resolve().parents[2]

_clock_config_cache: Dict[int, Tuple[float, Dict[str, Any]]] = {}


def _get_experiment_dir(experiment: Exps) -> Path:
    """Locate the on-disk directory that stores experiment artifacts."""
    db_name = str(getattr(experiment, "db_name", "") or "").replace("\\", os.sep)
    if os.sep in db_name:
        return _Y_WEB_DIR / Path(db_name).parent
    folder = db_name.removeprefix("experiments_")
    return _Y_WEB_DIR / "experiments" / folder


def _format_round(round_id: Optional[int]) -> Tuple[str, str]:
    if round_id is None:
        return "None", "00"
    round_obj = db.session.scalars(select(Rounds).filter_by(id=round_id)).first()
    if not round_obj:
        return "None", "00"
    return str(round_obj.day), f"{round_obj.hour:02d}"


def _resolve_experiment_clock() -> Dict[str, Any]:
    """
    Load experiment clock settings from config_server.json, with fallback to the
    client JSON generated at creation time when the experiment-level clock config
    is stale or missing.
    """
    try:
        exp_id_raw = get_current_experiment_id()
    except Exception:
        return default_clock_config()

    if exp_id_raw is None:
        return default_clock_config()

    try:
        exp_id = int(exp_id_raw)
    except (TypeError, ValueError):
        return default_clock_config()

    try:
        experiment = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
        if not experiment:
            return default_clock_config()

        experiment_dir = _get_experiment_dir(experiment)
        config_path = experiment_dir / "config_server.json"
        client_paths = sorted(experiment_dir.glob("client_*.json"))
        newest_client_mtime = (
            max(path.stat().st_mtime for path in client_paths) if client_paths else -1.0
        )
        mtime = max(
            config_path.stat().st_mtime if config_path.exists() else -1.0,
            newest_client_mtime,
        )
        cached = _clock_config_cache.get(exp_id)
        if cached and cached[0] == mtime:
            return cached[1]

        resolved_clock = default_clock_config()
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            resolved_clock = ensure_experiment_clock(payload)

        if client_paths:
            latest_client_path = max(
                client_paths, key=lambda path: path.stat().st_mtime
            )
            try:
                with latest_client_path.open("r", encoding="utf-8") as fh:
                    client_payload = json.load(fh)
                simulation = client_payload.get("simulation", {})
                raw_mode = simulation.get("clock_mode")
                raw_timezone = simulation.get("clock_timezone") or simulation.get(
                    "timezone"
                )
                raw_feed_refresh = simulation.get("feed_refresh")
                raw_anchor_date = simulation.get("clock_anchor_date")
                if raw_mode or raw_timezone or raw_feed_refresh or raw_anchor_date:
                    candidate_payload = {
                        "clock": {
                            "mode": raw_mode or resolved_clock.get("mode"),
                            "timezone": raw_timezone or resolved_clock.get("timezone"),
                            "feed_refresh": raw_feed_refresh
                            or resolved_clock.get("feed_refresh"),
                            "anchor_date": raw_anchor_date
                            or resolved_clock.get("anchor_date"),
                        }
                    }
                    resolved_clock = ensure_experiment_clock(candidate_payload)
            except Exception:
                pass

        _clock_config_cache[exp_id] = (mtime, resolved_clock)
        return resolved_clock
    except Exception:
        return default_clock_config()


def _format_display_time(day: str, hour: str) -> str:
    """
    Return the user-facing timestamp label for feed items.
    """
    clock = _resolve_experiment_clock()
    clock_mode = str(clock.get("mode", DEFAULT_CLOCK_MODE) or DEFAULT_CLOCK_MODE)

    if clock_mode != "real_time":
        if day == "None":
            return ""
        try:
            day_num = int(day)
            hour_num = int(hour)
            return f"Day {max(day_num, 0)} · Hour {min(max(hour_num, 0), 23):02d}"
        except (TypeError, ValueError):
            return str(day or "").strip()

    timezone_name = str(
        clock.get("timezone", DEFAULT_CLOCK_TIMEZONE) or DEFAULT_CLOCK_TIMEZONE
    )

    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        try:
            tz = ZoneInfo(DEFAULT_CLOCK_TIMEZONE)
        except Exception:
            return datetime.now().strftime("%d-%m-%y %H:%M")

    fallback = datetime.now(tz).strftime("%d-%m-%y %H:%M")
    if day == "None":
        return fallback

    try:
        day_num = int(day)
        hour_num = int(hour)
    except (TypeError, ValueError):
        return fallback

    anchor_date = parse_anchor_date(clock.get("anchor_date"))
    if anchor_date is None:
        anchor_date = datetime.now(tz).date()

    try:
        day_offset = max(day_num, 0)
        normalized_hour = min(max(hour_num, 0), 23)
        dt = datetime.combine(
            anchor_date + timedelta(days=day_offset),
            time(hour=normalized_hour, minute=0),
            tzinfo=tz,
        )
    except Exception:
        return fallback

    return dt.strftime("%d-%m-%y %H:%M")


def _format_display_time_from_created_at(
    created_at: Optional[datetime],
) -> Optional[str]:
    """
    Format a persisted post/comment timestamp as calendar datetime.
    """
    if created_at is None:
        return None

    clock = _resolve_experiment_clock()
    clock_mode = str(clock.get("mode", DEFAULT_CLOCK_MODE) or DEFAULT_CLOCK_MODE)
    if clock_mode != "real_time":
        return None

    timezone_name = str(
        clock.get("timezone", DEFAULT_CLOCK_TIMEZONE) or DEFAULT_CLOCK_TIMEZONE
    )

    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = None

    dt = created_at
    if tz is not None:
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            else:
                dt = dt.astimezone(tz)
        except Exception:
            pass

    return dt.strftime("%d-%m-%y %H:%M")
