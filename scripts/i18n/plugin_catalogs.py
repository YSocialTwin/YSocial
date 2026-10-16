#!/usr/bin/env python3
"""Catalog tooling for one plugin (a repository under ``external/``).

    plugin_catalogs.py extract <plugin_dir> --domain D          # translations/D.pot
    plugin_catalogs.py update  <plugin_dir> --domain D --langs it
    plugin_catalogs.py compile <plugin_dir> --domain D
    plugin_catalogs.py js-sync <plugin_dir> --domain D          # translations/js/D/en.json
    plugin_catalogs.py js-check <plugin_dir> --domain D --lang it
    plugin_catalogs.py check   <plugin_dir> --domain D --langs it

The ``.pot`` holds manifest strings (``meta/*.json``), Python ``_()`` calls and
Jinja ``_()`` calls. Browser strings live in ``translations/js/D/<lang>.json`` with
the English text as key; ``translations/js/D/_static.json`` lists extra keys that
cannot be found by scanning (data-driven labels such as ``emotion.joy``).
"""

import argparse
import json
import re
import sys
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import extract_from_dir
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest_extractor import extract_plugin_manifests  # noqa: E402

SKIP_DIRS = ["tests", "test", "node_modules", "_to_delete", "__pycache__", "docs", "venv", ".venv"]
JS_CALL = re.compile(r"YI18n\.(?:t|tn)\(\s*'((?:\\.|[^'\\])*)'")
PH = re.compile(r"\{(\w+)\}")
METHODS = [("**.py", "python"), ("**/templates/**.html", "jinja2")]
OPTIONS = {"**/templates/**.html": {"extensions": "jinja2.ext.i18n"}}


def _extract(plugin_dir):
    yield from extract_from_dir(
        str(plugin_dir),
        method_map=METHODS,
        options_map=OPTIONS,
        keywords={"_": None, "gettext": None, "ngettext": (1, 2)},
        comment_tags=(),
        directory_filter=lambda d: Path(d).name not in SKIP_DIRS,
    )


def build_pot(plugin_dir, domain):
    catalog = Catalog(project=domain, charset="utf-8")
    for text, where in extract_plugin_manifests(plugin_dir):
        catalog.add(text, locations=[(where, 0)], auto_comments=["manifest string"])
    for filename, lineno, message, comments, _ctx in _extract(plugin_dir):
        catalog.add(message, locations=[(filename, lineno)], auto_comments=list(comments))
    return catalog


def translations_dir(plugin_dir):
    return Path(plugin_dir) / "translations"


def cmd_extract(plugin_dir, domain):
    catalog = build_pot(plugin_dir, domain)
    out = translations_dir(plugin_dir)
    out.mkdir(exist_ok=True)
    target = out / f"{domain}.pot"
    with target.open("wb") as fh:
        write_po(fh, catalog, width=100, sort_output=True)
    print(f"{len(catalog)} strings -> {target}")


def cmd_update(plugin_dir, domain, langs):
    pot_path = translations_dir(plugin_dir) / f"{domain}.pot"
    template = read_po(pot_path.open("rb"))
    for lang in langs:
        po_path = translations_dir(plugin_dir) / lang / "LC_MESSAGES" / f"{domain}.po"
        po_path.parent.mkdir(parents=True, exist_ok=True)
        if po_path.is_file():
            catalog = read_po(po_path.open("rb"), locale=lang)
        else:
            catalog = Catalog(locale=lang, project=domain, charset="utf-8")
        catalog.update(template, no_fuzzy_matching=True)
        with po_path.open("wb") as fh:
            write_po(fh, catalog, width=100, sort_output=True)
        missing = sum(1 for m in catalog if m.id and not m.string)
        print(f"{lang}: {len(catalog)} strings, {missing} untranslated")


def cmd_compile(plugin_dir, domain):
    for po_path in sorted(translations_dir(plugin_dir).glob(f"*/LC_MESSAGES/{domain}.po")):
        catalog = read_po(po_path.open("rb"), locale=po_path.parent.parent.name)
        with po_path.with_suffix(".mo").open("wb") as fh:
            write_mo(fh, catalog)
        print(f"compiled {po_path.with_suffix('.mo')}")


def js_files(plugin_dir):
    for path in Path(plugin_dir).rglob("*.js"):
        parts = set(path.relative_to(plugin_dir).parts)
        if parts & set(SKIP_DIRS) or path.name.endswith(".min.js"):
            continue
        yield path


def unescape(text):
    return re.sub(r"\\(.)", lambda m: {"n": "\n"}.get(m.group(1), m.group(1)), text)


def js_dir(plugin_dir, domain):
    return translations_dir(plugin_dir) / "js" / domain


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def cmd_js_sync(plugin_dir, domain):
    keys = {}
    for path in js_files(plugin_dir):
        for match in JS_CALL.finditer(path.read_text(encoding="utf-8")):
            text = unescape(match.group(1))
            keys[text] = text
    base = js_dir(plugin_dir, domain)
    keys.update(read_json(base / "_static.json"))
    write_json(base / "en.json", keys)
    print(f"{len(keys)} keys -> {base / 'en.json'}")


def cmd_js_check(plugin_dir, domain, lang):
    base = js_dir(plugin_dir, domain)
    en, tr = read_json(base / "en.json"), read_json(base / f"{lang}.json")
    problems = 0
    for key, value in en.items():
        if key not in tr:
            print(f"missing: {key}")
            problems += 1
        elif set(PH.findall(str(value))) != set(PH.findall(str(tr[key]))):
            print(f"placeholder mismatch: {key}")
            problems += 1
    for key in tr:
        if key not in en:
            print(f"stale: {key}")
            problems += 1
    print(f"{lang}: {len(en)} keys, {problems} problems")
    return problems


def cmd_check(plugin_dir, domain, langs):
    problems = 0
    current = build_pot(plugin_dir, domain)
    pot_path = translations_dir(plugin_dir) / f"{domain}.pot"
    committed = {m.id for m in read_po(pot_path.open("rb")) if m.id} if pot_path.is_file() else set()
    if {m.id for m in current if m.id} != committed:
        print("the .pot is stale: run extract")
        problems += 1
    for lang in langs:
        mo = translations_dir(plugin_dir) / lang / "LC_MESSAGES" / f"{domain}.mo"
        po = mo.with_suffix(".po")
        if not mo.is_file() or not po.is_file() or mo.stat().st_mtime + 2 < po.stat().st_mtime:
            print(f"{lang}: .mo missing or older than .po: run compile")
            problems += 1
        if js_dir(plugin_dir, domain).is_dir():
            problems += cmd_js_check(plugin_dir, domain, lang)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("cmd", choices=["extract", "update", "compile", "js-sync", "js-check", "check"])
    parser.add_argument("plugin_dir")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--langs", default="it")
    parser.add_argument("--lang", default="it")
    args = parser.parse_args(argv)
    plugin_dir = Path(args.plugin_dir).resolve()
    langs = [lang for lang in args.langs.split(",") if lang]
    if args.cmd == "extract":
        cmd_extract(plugin_dir, args.domain)
    elif args.cmd == "update":
        cmd_update(plugin_dir, args.domain, langs)
    elif args.cmd == "compile":
        cmd_compile(plugin_dir, args.domain)
    elif args.cmd == "js-sync":
        cmd_js_sync(plugin_dir, args.domain)
    elif args.cmd == "js-check":
        return 1 if cmd_js_check(plugin_dir, args.domain, args.lang) else 0
    elif args.cmd == "check":
        return 1 if cmd_check(plugin_dir, args.domain, langs) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
