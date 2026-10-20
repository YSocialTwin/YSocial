"""Pseudo-localisation (``en-XA``) used to spot unmarked strings and broken layouts.

Every letter of a marked string becomes an accented one, the text is wrapped in
``[`` ``]`` and padded by about 30% (translations are usually longer than English).
Placeholders (``%(name)s``, ``%d``, ``{name}``), HTML tags and entities are kept
intact so the pseudo catalog still formats and renders correctly.
"""

import re

PSEUDO_LANGUAGE = "en-XA"
# Babel has no ``en_XA`` locale: this existing, unused locale carries the catalog.
PSEUDO_CARRIER = "en_US_POSIX"

_PROTECTED = re.compile(
    r"%\([^)]+\)[#0\- +]*\d*(?:\.\d+)?[a-zA-Z]"  # %(name)s
    r"|%[#0\- +]*\d*(?:\.\d+)?[a-zA-Z]"  # %s %d
    r"|\{[^{}]*\}"  # {name}
    r"|<[^>]+>"  # <b>, </a href=...>
    r"|&[a-zA-Z#0-9]+;"  # &amp;
)

_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "àƀçðéƒĝĥíĵķļmñóþqŕšţûvŵxýžÀƁÇÐÉFĜĤÍĴĶĻMÑÓÞQŔŠŢÛVŴXÝŽ",
)


def pseudolocalize(text):
    """Return the pseudo-localised form of *text* (empty text is unchanged)."""
    if not text:
        return text
    out = []
    last = 0
    for match in _PROTECTED.finditer(text):
        out.append(text[last : match.start()].translate(_MAP))
        out.append(match.group(0))
        last = match.end()
    out.append(text[last:].translate(_MAP))
    body = "".join(out)
    padding = "~" * max(1, len(text) // 3)
    return f"[{body}{padding}]"


def pseudolocalize_catalog(data):
    """Pseudo-localise a JS catalog (strings and plural objects)."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = {cat: pseudolocalize(txt) for cat, txt in value.items()}
        else:
            result[key] = pseudolocalize(value)
    return result
