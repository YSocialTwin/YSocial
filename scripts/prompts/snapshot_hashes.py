#!/usr/bin/env python3
"""Fingerprint of today's English prompts (gate G0), and the check that keeps them unchanged (gate G1).

Two kinds of fingerprints are stored in ``docs/prompt-hashes.json``:

* ``json``: sha256 of every prompt template in every prompt file (nested groups use ``group/key``);
* ``code``: sha256 of every prompt-like string literal written in the Python code of the seven
  repositories (same criteria as ``inventory_scan.py``, full text, whitespace kept).

``--check`` fails when a template or a literal that existed at snapshot time can no longer be found
byte for byte, either where it was or in any current English pack (``data_schema/prompts/en``, added
by step 3). Moving a prompt from code to JSON is therefore allowed; changing a character is not.

Usage (from the YWeb root)::

    python scripts/prompts/snapshot_hashes.py --write     # record the current state
    python scripts/prompts/snapshot_hashes.py --check     # exit 1 when an English prompt changed
"""

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory_scan as scan  # noqa: E402

ROOT = scan.ROOT
OUT = ROOT / "docs" / "prompt-hashes.json"
EN_PACK_DIRS = [ROOT / "data_schema" / "prompts" / "en"]
# YWeb is mostly interface text; only these paths build prompts for a model.
YWEB_PROMPT_PATHS = (
    "y_web/src/llm/",
    "y_web/routes/api/interview/",
    "y_web/routes/admin/sub/experiments/_opinion.py",
)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def walk_json(obj, prefix=""):
    if isinstance(obj, str):
        yield prefix, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_json(v, f"{prefix}/{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_json(v, f"{prefix}[{i}]")


def json_hashes(files):
    out = {}
    for rel in files:
        path = ROOT / rel
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out[rel] = {key: digest(text) for key, text in walk_json(data)}
    return out


def code_literals():
    """Prompt-like literals, keyed by file, as a sorted list of hashes (line numbers drift)."""
    out = {}
    for repo, base in scan.REPOS.items():
        if not base.exists():
            continue
        for path in scan.py_files(base):
            rel_path = str(path.relative_to(ROOT)).replace("\\", "/")
            if repo == "YWeb" and not rel_path.startswith(YWEB_PROMPT_PATHS):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            doc_ids = set()
            for n in ast.walk(tree):
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    if n.body and isinstance(n.body[0], ast.Expr):
                        doc_ids.add(id(n.body[0].value))
            hashes = set()
            for n in ast.walk(tree):
                t = scan.text_of(n)
                if (
                    t
                    and id(n) not in doc_ids
                    and len(t.split()) >= 8
                    and scan.CUES.search(t)
                    and not t.lstrip().startswith(("http", "SELECT", "INSERT"))
                ):
                    hashes.add(digest(t))
            if hashes:
                out[str(path.relative_to(ROOT))] = sorted(hashes)
    return out


def current_state():
    return {"json": json_hashes(scan.PROMPT_FILES), "code": code_literals()}


def en_pack_hashes():
    found = set()
    for base in EN_PACK_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            found.update(digest(t) for _, t in walk_json(data))
    return found


def check(saved, now):
    problems = []
    packs = en_pack_hashes()
    now_json_all = {h for f in now["json"].values() for h in f.values()}
    now_code_all = {h for f in now["code"].values() for h in f}
    everywhere = packs | now_json_all | now_code_all
    for rel, keys in saved["json"].items():
        for key, h in keys.items():
            if now["json"].get(rel, {}).get(key) == h:
                continue
            if h not in everywhere:
                problems.append(f"changed or removed template: {rel} :: {key}")
    for rel, hashes in saved["code"].items():
        for h in hashes:
            if h not in everywhere:
                problems.append(f"changed or removed code literal in {rel} (sha256 {h[:12]})")
    return problems


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args()
    now = current_state()
    if args.write:
        OUT.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        n_json = sum(len(v) for v in now["json"].values())
        n_code = sum(len(v) for v in now["code"].values())
        print(f"wrote {OUT.relative_to(ROOT)}: {n_json} template hashes, {n_code} code literal hashes")
        return 0
    saved = json.loads(OUT.read_text(encoding="utf-8"))
    problems = check(saved, now)
    for p in problems:
        print(p)
    print("prompt hashes: OK" if not problems else f"prompt hashes: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
