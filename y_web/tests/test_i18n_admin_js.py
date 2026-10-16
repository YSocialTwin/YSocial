"""Admin browser code: every YI18n.t() key is in the catalog and translated (F2-8)."""

import json
import pathlib
import re

JS_DIR = pathlib.Path(__file__).resolve().parents[1] / "static" / "assets" / "js"
CAT = pathlib.Path(__file__).resolve().parents[1] / "translations" / "js" / "admin"
CALL = re.compile(r"YI18n\.(?:t|tn)\(\s*'((?:\\.|[^'\\])*)'")
PH = re.compile(r"\{(\w+)\}")


def _unescape(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n"}.get(m.group(1), m.group(1)), s)


def _used_keys():
    keys = set()
    for f in JS_DIR.glob("admin-*.js"):
        keys |= {_unescape(k) for k in CALL.findall(f.read_text(encoding="utf-8"))}
    return keys


def _load(lang):
    return json.loads((CAT / f"{lang}.json").read_text(encoding="utf-8"))


def test_every_used_key_is_in_english_catalog():
    assert _used_keys() - set(_load("en")) == set()


def test_italian_covers_english_with_same_placeholders():
    en, it = _load("en"), _load("it")
    assert [k for k in en if not it.get(k)] == []
    assert [k for k in en if set(PH.findall(k)) != set(PH.findall(it[k]))] == []
