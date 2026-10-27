"""Round arithmetic of IM experiments (plan, 5.5): one place for every conversion.

IM numbers rounds from 1 and gives a day 24 slots (``slot`` 1-24): ``ordinal = (day - 1) * 24 + slot``.
Request logs of the server use ``hour`` 0-23, client summaries use ``slot`` 1-24.
"""

from typing import Tuple

from y_web.src.im.client_config import IM_SLOTS_PER_DAY


def ordinal(day: int, slot: int, slots_per_day: int = IM_SLOTS_PER_DAY) -> int:
    """1-based global round of ``day`` (from 1) and ``slot`` (1..``slots_per_day``)."""
    if day < 1 or not 1 <= slot <= slots_per_day:
        raise ValueError(f"invalid round day={day} slot={slot}")
    return (day - 1) * slots_per_day + slot


def day_slot(round_id: int, slots_per_day: int = IM_SLOTS_PER_DAY) -> Tuple[int, int]:
    """Inverse of :func:`ordinal`."""
    if round_id < 1:
        raise ValueError("round ordinal starts at 1")
    return (round_id - 1) // slots_per_day + 1, (round_id - 1) % slots_per_day + 1


def hour_of_slot(slot: int) -> int:
    """Server log hour (0-23) of a client slot (1-24)."""
    return slot - 1


def slot_of_hour(hour: int) -> int:
    return hour + 1


def clamp_round(requested, latest: int) -> int:
    """The round a page shows: ``requested`` limited to ``1..latest``; ``None``/invalid means ``latest``."""
    if latest < 1:
        return 0
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return latest
    return min(max(value, 1), latest)
