"""Identifiers of forum entities treated as opaque values.

Standard experiments use integer ids, HPC (YForum) ones use UUID strings: ids are
never cast blindly with ``int()``, a clean integer-like value stays an ``int`` and
anything else is kept as a string (same convention as the microblogging frontend).
"""

import re
from typing import Any

_INT_LIKE = re.compile(r"-?\d+")


def opaque_id(value: Any) -> Any:
    """Return ``value`` as ``int`` when integer-like, else as a stripped ``str`` (``None`` stays ``None``)."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if _INT_LIKE.fullmatch(text):
        return int(text)
    return text
