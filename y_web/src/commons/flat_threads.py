"""What a feed shows of a post when its platform has no threads of its own (``provider.threads`` is ``None``).

The time of a post as the experiment clock shows it, and a post written as a title and a body split into the two.
A platform with threads (a ``provider.threads`` object with the same two functions) replaces this one.
"""

from __future__ import annotations

from y_web.src.commons.display_time import (
    _format_display_time,
    _format_display_time_from_created_at,
)
from y_web.src.content.text_utils import split_title_and_body


def display_time(created_at, day, hour):
    """The time of a post as the experiment's clock shows it."""
    return _format_display_time_from_created_at(created_at) or _format_display_time(
        str(day), f"{int(hour):02d}" if str(hour).isdigit() else str(hour)
    )


def split_title(text):
    """``(title, body)`` of a post written as a title and a body."""
    return split_title_and_body(text)
