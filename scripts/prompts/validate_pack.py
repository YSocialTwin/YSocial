#!/usr/bin/env python3
"""Check that every prompt language pack is a faithful, complete counterpart of the English one.

For each language (every folder of ``data_schema/prompts`` except ``en``, plus every
``prompts_internal.<language>.json`` next to an English ``prompts_internal.json`` in the seven repositories):

* the manifest exists and lists the files that are present;
* the same files, the same keys, at any depth (``--allow-partial`` accepts missing keys);
* the same ``{fields}`` in each text, the same number of times (a field may move, never change or disappear);
* every protocol token (YES, COMMENT, NEUTRAL, ...) written in the English text is still written, untranslated;
* nothing else that looks like a field is introduced.

English itself is checked for a valid manifest and for fields the renderer understands.

Usage: python scripts/prompts/validate_pack.py [--language it] [--allow-partial] [--root PATH]
Exit status 1 when anything is wrong.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKENS_FILE = ROOT / "external" / "YClient" / "y_client" / "protocol_tokens.py"
STORE_FILE = ROOT / "y_web" / "prompt_store.py"
INTERNAL_PACKS = [
    "y_web/prompts_internal.json",
    "external/YClient/y_client/prompts_internal.json",
    "external/YClientReddit/y_client/prompts_internal.json",
    "external/YSimulator/YSimulator/prompts_internal.json",
    "external/YPhotoSharing/YPhotoSharing/prompts_internal.json",
    "external/y_agents_plugins/src/y_agents_plugins/prompts_internal.json",
    "external/reactive_agents/src/reactive_agents/prompts_internal.json",
]
LANG = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
BRACES = re.compile(r"\{[^{}\n]*\}")


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tokens(root):
    path = root / "external" / "YClient" / "y_client" / "protocol_tokens.py"
    module = _load_module(path if path.exists() else TOKENS_FILE, "protocol_tokens_for_validation")
    return {
        value
        for name, value in vars(module).items()
        if name.isupper() and isinstance(value, str) and re.fullmatch(r"[A-Z_]+", value)
    }


def _field_regex(root):
    path = root / "y_web" / "prompt_store.py"
    return _load_module(path if path.exists() else STORE_FILE, "prompt_store_for_validation")._FIELD


def _texts(node, where=""):
    if isinstance(node, str):
        yield where, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _texts(value, f"{where}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _texts(value, f"{where}[{index}]")


def compare(english, other, field_re, tokens, label, allow_partial=False):
    """Problems found when ``other`` is held against ``english`` (both parsed JSON)."""
    problems = []
    en = dict(_texts(english))
    tr = dict(_texts(other))
    for path in sorted(set(tr) - set(en)):
        problems.append(f"{label}{path}: key does not exist in English")
    for path, source in en.items():
        if path not in tr:
            if not allow_partial:
                problems.append(f"{label}{path}: missing")
            continue
        text = tr[path]
        want = Counter(m.group(0) for m in field_re.finditer(source))
        have = Counter(m.group(0) for m in field_re.finditer(text))
        if want != have:
            problems.append(
                f"{label}{path}: fields differ (English {sorted(want.elements())}, here {sorted(have.elements())})"
            )
        others = Counter(m for m in BRACES.findall(text))
        others_en = Counter(m for m in BRACES.findall(source))
        if others != others_en:
            problems.append(f"{label}{path}: braces differ from English")
        words = set(re.findall(r"[A-Za-z_]+", source))
        for token in sorted(tokens & words):
            if token not in set(re.findall(r"[A-Za-z_]+", text)):
                problems.append(f"{label}{path}: protocol token {token} is missing or translated")
    return problems


def check_english(root, field_re):
    problems = []
    manifest = root / "data_schema" / "prompts" / "en" / "manifest.json"
    if not manifest.exists():
        return ["data_schema/prompts/en/manifest.json: missing"]
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for name in data.get("files", []):
        path = manifest.parent / name
        if not path.exists():
            problems.append(f"en/{name}: listed in the manifest but not found")
            continue
        for where, text in _texts(json.loads(path.read_text(encoding="utf-8"))):
            for braces in BRACES.findall(text):
                if not field_re.fullmatch(braces) and re.fullmatch(r"\{[A-Za-z_][^{}\"]*\}", braces):
                    problems.append(f"en/{name}{where}: {braces} is not a field the renderer understands")
    return problems


def check_language(root, language, field_re, tokens, allow_partial=False):
    problems = []
    folder = root / "data_schema" / "prompts" / language
    en_folder = root / "data_schema" / "prompts" / "en"
    manifest = folder / "manifest.json"
    if not manifest.exists():
        return [f"{language}/manifest.json: missing"]
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("language") != language:
        problems.append(f"{language}/manifest.json: language is {data.get('language')!r}")
    english_files = json.loads((en_folder / "manifest.json").read_text(encoding="utf-8"))["files"]
    if not allow_partial and sorted(data.get("files", [])) != sorted(english_files):
        problems.append(f"{language}/manifest.json: files differ from English")
    for name in english_files:
        path = folder / name
        if not path.exists():
            if not allow_partial:
                problems.append(f"{language}/{name}: missing")
            continue
        problems += compare(
            json.loads((en_folder / name).read_text(encoding="utf-8")),
            json.loads(path.read_text(encoding="utf-8")),
            field_re,
            tokens,
            f"{language}/{name}",
            allow_partial,
        )
    return problems


def check_internal(root, language, field_re, tokens, allow_partial=False):
    problems = []
    for relative in INTERNAL_PACKS:
        english = root / relative
        if not english.exists():
            continue
        other = english.with_name(f"{english.stem}.{language}{english.suffix}")
        if not other.exists():
            if not allow_partial:
                problems.append(f"{other.relative_to(root)}: missing")
            continue
        problems += compare(
            json.loads(english.read_text(encoding="utf-8")),
            json.loads(other.read_text(encoding="utf-8")),
            field_re,
            tokens,
            str(other.relative_to(root)),
            allow_partial,
        )
    return problems


def languages(root):
    base = root / "data_schema" / "prompts"
    found = {p.name for p in base.iterdir() if p.is_dir() and LANG.match(p.name)} if base.exists() else set()
    for relative in INTERNAL_PACKS:
        english = root / relative
        for path in english.parent.glob(f"{english.stem}.*{english.suffix}"):
            code = path.name[len(english.stem) + 1 : -len(english.suffix)]
            if LANG.match(code):
                found.add(code)
    found.discard("en")
    return sorted(found)


def run(root, only=None, allow_partial=False):
    root = Path(root)
    field_re, tokens = _field_regex(root), _tokens(root)
    problems = check_english(root, field_re)
    for language in [only] if only else languages(root):
        problems += check_language(root, language, field_re, tokens, allow_partial)
        problems += check_internal(root, language, field_re, tokens, allow_partial)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--language")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    problems = run(args.root, args.language, args.allow_partial)
    for line in problems:
        print(line)
    checked = [args.language] if args.language else languages(Path(args.root))
    print(f"prompt packs: {'OK' if not problems else str(len(problems)) + ' problem(s)'} (en + {', '.join(checked) or 'no other language'})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
