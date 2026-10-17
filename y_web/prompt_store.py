"""English prompt strings kept as data, rendered with a closed list of fields.

Step 1 of the multilingual prompts task: prompts that used to be written inside the Python code live in
``prompts_internal.json`` next to this module and are filled in by :func:`render`, which

* replaces only the fields the caller passes (every other brace, such as the JSON examples some prompts
  contain, stays as it is). A field is a name (``{topic}``), optionally followed by attribute or item steps
  (``{self.age}``, ``{article['title']}``), a literal join (``{', '.join(interests)}``) and a numeric format
  (``{trust:.2f}``); nothing else is understood and there are no calls or expressions;
* raises :class:`PromptError` when a field named in the text is not passed, instead of leaving it in the prompt;
* never evaluates anything.

Languages: English lives in ``prompts_internal.json``; another language ``xx`` lives in
``prompts_internal.xx.json`` next to it and only needs the keys it translates. A key missing from a language
(or a language without a file) falls back to English and logs a warning once. ``set_language`` sets the
language used when a call passes none; nothing is ever translated at run time.

This file is copied unchanged into every repository that builds prompts; keep the copies identical.
"""

import json
import logging
import re
from pathlib import Path

PACK_FILE = Path(__file__).with_name("prompts_internal.json")
DEFAULT_LANGUAGE = "en"
_language = DEFAULT_LANGUAGE
_warned = set()
_LANG = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
log = logging.getLogger(__name__)
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


def _clean(language):
    language = (language or "").strip().lower()
    return language if _LANG.match(language) else DEFAULT_LANGUAGE


def set_language(language):
    """Language used by calls that do not pass one (empty or unknown values mean English)."""
    global _language
    _language = _clean(language)


def current_language():
    return _language


def _pack_path(language):
    if language == DEFAULT_LANGUAGE:
        return PACK_FILE
    return PACK_FILE.with_name(f"{PACK_FILE.stem}.{language}{PACK_FILE.suffix}")


def _pack(language):
    path = _pack_path(language)
    if path not in _cache:
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                _cache[path] = json.load(handle)
        else:
            _cache[path] = {}
    return _cache[path]


def _warn_once(language, key):
    if (language, key) not in _warned:
        _warned.add((language, key))
        log.warning("prompt %r has no %r text; using English", key, language)


def get(key, language=None):
    """The template text for ``key`` in ``language`` (default: the current language), else in English."""
    language = _clean(language) if language else _language
    if language != DEFAULT_LANGUAGE:
        text = _pack(language).get(key)
        if text is not None:
            return text
        if key in _pack(DEFAULT_LANGUAGE):
            _warn_once(language, key)
    try:
        return _pack(DEFAULT_LANGUAGE)[key]
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


def prompt(key, language=None, **fields):
    """``render(get(key), **fields)``."""
    return render(get(key, language), **fields)
