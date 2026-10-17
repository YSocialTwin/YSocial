"""English prompt strings kept as data, rendered with a closed list of fields.

Step 1 of the multilingual prompts task: prompts that used to be written inside the Python code live in
``prompts_internal.json`` next to this module and are filled in by :func:`render`, which

* replaces only the fields the caller passes (every other brace, such as the JSON examples some prompts
  contain, stays as it is). A field is a name (``{topic}``), optionally followed by attribute or item steps
  (``{self.age}``, ``{article['title']}``), a literal join (``{', '.join(interests)}``) and a numeric format
  (``{trust:.2f}``); nothing else is understood and there are no calls or expressions;
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
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_PATH = rf"(?P<root>{_NAME})(?P<steps>(?:\.{_NAME}|\[(?:'[^'\n]*'|\"[^\"\n]*\"|\d+)\])*)"
_JOIN = rf"(?:'(?P<sq>[^'\n]*)'|\"(?P<dq>[^\"\n]*)\")\.join\((?P<jroot>{_NAME})\)"
_SPEC = r"(?::(?P<spec>[<>^]?\d*(?:\.\d+)?[sdf]?))?"
_FIELD = re.compile(rf"\{{(?:{_PATH}|{_JOIN}){_SPEC}\}}")
_STEP = re.compile(rf"\.({_NAME})|\[(?:'([^'\n]*)'|\"([^\"\n]*)\"|(\d+))\]")
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


def fields_of(template):
    """The names a caller has to pass for ``template`` (the root of every field)."""
    return {m.group("root") or m.group("jroot") for m in _FIELD.finditer(template)}


def _resolve(match, fields):
    root = match.group("root") or match.group("jroot")
    if root not in fields:
        raise PromptError(f"prompt field not provided: {root}")
    value = fields[root]
    if match.group("jroot"):
        sep = match.group("sq") if match.group("sq") is not None else match.group("dq")
        return sep.join(str(item) for item in value)
    for step in _STEP.finditer(match.group("steps") or ""):
        attr, sq, dq, index = step.groups()
        if attr is not None:
            if attr.startswith("_"):
                raise PromptError(f"prompt field not allowed: {match.group(0)}")
            value = getattr(value, attr)
        elif index is not None:
            value = value[int(index)]
        else:
            value = value[sq if sq is not None else dq]
    spec = match.group("spec")
    return format(value, spec) if spec else str(value)


def render(template, **fields):
    """Fill the fields of ``template`` from ``fields``; nothing else is touched or evaluated."""
    return _FIELD.sub(lambda match: _resolve(match, fields), template)


def prompt(key, language="en", **fields):
    """``render(get(key), **fields)``."""
    return render(get(key, language), **fields)
