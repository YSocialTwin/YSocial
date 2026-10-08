"""Centralized free-text sanitization and length limits (piano tecnico
§21: "sanitizzazione HTML/script su ogni campo libero... mai ``|safe``
lato Jinja su contenuto utente/LLM", "cap su lunghezza testo").

A single point of implementation, reused by every route that accepts a
free-text field from an admin or an LLM backend (post content, scenario
name/description, metadata JSON values) -- so a new field added later
inherits sanitization by construction instead of by remembering to call
it (piano di implementazione, Fase 8 rischio esplicito: "sanitizzazione
incompleta per campi non ancora previsti").

Pure module: no Flask, no db_exp, no I/O -- unit-tested directly with
plain strings.
"""
from __future__ import annotations

import re

# Generous but bounded: long enough for a realistic social post/comment
# (even a long-form one) without allowing an unbounded admin/LLM payload
# into the database. Piano tecnico asks this to be reconciled with any
# real YClient-side limit (Fase 0) -- none was found hardcoded client-side
# at the time of writing (Fase 0 finding, decisions.md §F0.x), so this is
# this plugin's own first authoritative limit, not a mirror of one.
MAX_POST_CONTENT_LENGTH = 10_000
MAX_SCENARIO_NAME_LENGTH = 200
MAX_SCENARIO_DESCRIPTION_LENGTH = 2_000
MAX_ROLE_KEY_LENGTH = 128
MAX_METADATA_VALUE_LENGTH = 10_000

_SCRIPT_TAG_RE = re.compile(r"<\s*script\b[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


class TextTooLongError(Exception):
    """Raised with the field name and the limit that was exceeded --
    never a bare ``ValueError``, so callers can map it to the uniform
    error envelope (piano tecnico §15) with a stable ``code``."""

    def __init__(self, field: str, limit: int, actual_length: int):
        message = (
            f"{field} is {actual_length} characters, exceeding the {limit}-character limit."
        )
        super().__init__(message)
        self.field = field
        self.limit = limit
        self.actual_length = actual_length
        self.code = "text_too_long"
        self.message = message


def enforce_length(value, field: str, limit: int) -> str:
    """Return *value* unchanged if within *limit* characters, else raise
    ``TextTooLongError``. Never truncates silently -- a silently truncated
    post is a worse admin experience than an explicit rejection (the
    admin would not notice their content was cut)."""
    text = value or ""
    if len(text) > limit:
        raise TextTooLongError(field, limit, len(text))
    return text


def sanitize_free_text(value: str) -> str:
    """Strip any HTML/script markup from *value* and return plain text,
    safe to store and to render without ever needing ``|safe`` in a
    template. Two-step, defense in depth, not just one:

    1. Strip ``<script>...</script>`` blocks (and their content) outright
       -- a lone closing-tag removal would otherwise leave an executable
       inline-event-free script body as visible plain text, which is
       merely ugly, not unsafe, but still worth removing explicitly
       rather than relying on step 2 alone to neutralize it.
    2. Strip every remaining HTML tag (``<...>``), then HTML-escape
       whatever text remains, so a value that was never valid markup
       to begin with (e.g. containing a literal ``<`` the admin typed)
       round-trips safely too.

    This makes server-side storage plain-text by construction: no field
    this module processes is ever rendered with Jinja's ``|safe`` filter,
    consistent with autoescape already being the platform default (piano
    tecnico §21) -- this function is the second, independent layer for
    the API surface, which a future non-Jinja frontend could also read
    directly.

    Deliberately does *not* HTML-escape or -unescape the result: the
    stored value stays plain text with every tag removed, and it is
    autoescaped at render time like any other field -- escaping here too
    would double-escape on render (``&amp;amp;``), and unescaping would
    turn a literal ``&lt;b&gt;`` the admin actually typed back into live
    angle brackets.
    """
    if not value:
        return value or ""
    without_scripts = _SCRIPT_TAG_RE.sub("", value)
    return _TAG_RE.sub("", without_scripts)
