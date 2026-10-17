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
language used when a call passes none (it also sets ``YSOCIAL_PROMPT_LANGUAGE`` so every copy of this module in
the process, e.g. the plugins', follows it); nothing is ever translated at run time.

A run folder may hold ``prompt_language.json`` (written by YWeb: the language of the experiment and of each
client) and ``profile_values.<language>.json`` (how profile values such as a nationality or a profession read in
that language). :func:`use_language_from_folder` activates them; :func:`localize` then shows an object's profile
attributes in that language to a prompt, without touching the object, the database or the logic.

This file is copied unchanged into every repository that builds prompts; keep the copies identical.
"""

import json
import logging
import os
import re
from pathlib import Path

PACK_FILE = Path(__file__).with_name("prompts_internal.json")
DEFAULT_LANGUAGE = "en"
ENV_VAR = "YSOCIAL_PROMPT_LANGUAGE"
FOLDER_VAR = "YSOCIAL_PROMPT_FOLDER"
RECORD_FILE = "prompt_language.json"
_language = None
_values = {}
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
    os.environ[ENV_VAR] = _language


def current_language():
    return _language or _clean(os.environ.get(ENV_VAR))


def language_from_folder(folder, client=None):
    """The language recorded in ``folder`` for ``client`` (else for the experiment, else English)."""
    try:
        with open(Path(folder) / RECORD_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return DEFAULT_LANGUAGE
    if not isinstance(data, dict):
        return DEFAULT_LANGUAGE
    clients = data.get("clients") if isinstance(data.get("clients"), dict) else {}
    return _clean(clients.get(str(client)) or data.get("experiment"))


def use_language_from_folder(folder, client=None):
    """Make the language of ``folder`` (``YSOCIAL_PROMPT_LANGUAGE`` if set, else its record) the current one.

    The folder is also remembered (``YSOCIAL_PROMPT_FOLDER``) so that worker processes started afterwards, which
    inherit the environment, find the profile values too. Returns the language.
    """
    language = _clean(os.environ[ENV_VAR]) if os.environ.get(ENV_VAR) else language_from_folder(folder, client)
    set_language(language)
    os.environ[FOLDER_VAR] = str(folder)
    _values.pop(language, None)
    return language


def env_for_workers():
    """Environment variables worker processes (e.g. Ray) need to speak the current language."""
    if current_language() == DEFAULT_LANGUAGE:
        return {}
    env = {ENV_VAR: current_language()}
    if os.environ.get(FOLDER_VAR):
        env[FOLDER_VAR] = os.environ[FOLDER_VAR]
    return env


def _values_for(language):
    if language not in _values:
        table = {}
        folder = os.environ.get(FOLDER_VAR)
        if language != DEFAULT_LANGUAGE and folder:
            try:
                with open(Path(folder) / f"profile_values.{language}.json", encoding="utf-8") as handle:
                    table = json.load(handle)
            except (OSError, ValueError):
                log.warning("no profile values for %r in %s; profile values stay in English", language, folder)
        _values[language] = table
    return _values[language]


# attribute of an agent / website -> category of profile_values.json
_CATEGORY = {
    "gender": "gender",
    "leaning": "leaning",
    "education_level": "education_level",
    "toxicity": "toxicity",
    "nationality": "nationality",
    "language": "language",
    "profession": "profession",
    "oe": "big_five",
    "co": "big_five",
    "ex": "big_five",
    "ag": "big_five",
    "ne": "big_five",
    "political_leaning": "leaning",
}


class _Localized:
    """Read-only view of an object whose profile attributes read in the current language."""

    def __init__(self, target, values):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_values", values)

    def __getattr__(self, name):
        value = getattr(self._target, name)
        table = self._values.get(_CATEGORY.get(name))
        if table and isinstance(value, str):
            return table.get(value, value)
        return value


def localize(obj):
    """``obj`` as a prompt should see it: profile values in the current language (English: ``obj`` itself)."""
    values = _values_for(current_language())
    return _Localized(obj, values) if values else obj


def localize_value(category, value):
    """One profile value (``category`` is a key of profile_values.json, e.g. ``"action"``) in the current language."""
    table = _values_for(current_language()).get(category)
    if table and isinstance(value, str):
        return table.get(value, value)
    return value


def localize_attrs(attrs):
    """A copy of a dict of agent attributes with its profile values in the current language."""
    values = _values_for(current_language())
    if not values or not isinstance(attrs, dict):
        return attrs
    out = dict(attrs)
    for key, value in attrs.items():
        table = values.get(_CATEGORY.get(key))
        if table and isinstance(value, str):
            out[key] = table.get(value, value)
    return out


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
    language = _clean(language) if language else current_language()
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
