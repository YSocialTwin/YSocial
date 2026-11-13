"""How many days a runtime must run when a client (re)starts."""

from typing import Any, Dict


def remaining_days(
    total_days: int, last_day: int, last_slot: int, slots_per_day: int
) -> int:
    """Days the runtime must run when the client (re)starts so that the client ends after ``total_days`` in all.

    The runtime counts ``num_days`` from the day it registers (days and slots start at 1). A client that never ran
    (``last_day`` < 1) runs the whole total; one stopped inside a day runs that day again; ``-1`` means until
    stopped. A result of 0 means that nothing is left (the runtime would read 0 as "unlimited": the caller refuses).
    """
    if int(total_days) <= 0:
        return -1
    if int(last_day) < 1:
        start = 1
    else:
        start = int(last_day) + (1 if int(last_slot) >= int(slots_per_day) else 0)
    return max(0, 1 + int(total_days) - start)


def set_duration(config: Dict[str, Any], days: int) -> Dict[str, Any]:
    """The client configuration with the number of days the runtime runs from now."""
    updated = dict(config)
    updated["num_days"] = int(days)
    return updated
