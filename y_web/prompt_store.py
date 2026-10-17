"""English prompt strings kept as data, rendered with a closed list of fields.

Step 1 of the multilingual prompts task: prompts that used to be written inside the Python code live in
``prompts_internal.json`` next to this module and are filled in by :func:`render`, which

* replaces only the ``{name}`` fields the caller passes (every other brace, such as the JSON examples some
  prompts contain, stays as it is);
* raises :class:`PromptError` when a field named in the text is not passed, instead of leaving it in the prompt;
* never evaluates anything.

``language`` is accepted so call sites do not change when language packs are added; only English exists today
and any other language falls back to it.

This file is copied unchanged into every repository that builds prompts; keep the copies identical.
"""

import json
import re
from pathlib import Path

PACK_FILE = Path(__file__).with_name("prompts_internal.json")
_FIELD = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_cache = {}


class PromptError(KeyError):
    """A prompt key is unknown or a field named in its text was not provided."""

    def __str__(self):
        return str(self.args[0]) if self.args else ""


def _pack(language="en"):
    path = PACK_FILE
    if path not in _cache:
        with open(path, encoding="utf-8") as handle:
            _cache[path] = json.load(handle)
    return _cache[path]


def get(key, language="en"):
    """The template text for ``key`` (English until other languages exist)."""
    try:
        return _pack(language)[key]
    except KeyError:
        raise PromptError(f"unknown prompt key: {key}") from None


def render(template, **fields):
    """Fill the ``{name}`` fields of ``template`` from ``fields``; nothing else is touched."""

    def fill(match):
        name = match.group(1)
        if name not in fields:
            raise PromptError(f"prompt field not provided: {name}")
        return str(fields[name])

    return _FIELD.sub(fill, template)


def prompt(key, language="en", **fields):
    """``render(get(key), **fields)``."""
    return render(get(key, language), **fields)
