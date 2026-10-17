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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory_scan as scan  # noqa: E402

ROOT = scan.ROOT
OUT = Path(__file__).resolve().parents[2] / "docs" / "prompt-hashes.json"
# English packs: the packs of step 3 and the ``prompts_internal.json`` files that hold prompts moved out of the code.
EN_PACK_DIRS = [ROOT / "data_schema" / "prompts" / "en"]
INTERNAL_PACK_NAME = "prompts_internal.json"
FIELD = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}|\{\}")


def norm(text):
    """Text with every ``{field}`` or ``{}`` replaced by ``{}``: a moved prompt keeps its words, not its field names."""
    return FIELD.sub("{}", text)
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
            hashes = {}
            # parts of an f-string are covered by the f-string itself
            doc_ids |= {
                id(v)
                for n in ast.walk(tree)
                if isinstance(n, ast.JoinedStr)
                for v in n.values
            }
            for n in ast.walk(tree):
                t = scan.text_of(n)
                if (
                    t
                    and id(n) not in doc_ids
                    and len(t.split()) >= 8
                    and scan.CUES.search(t)
                    and not t.lstrip().startswith(("http", "SELECT", "INSERT"))
                ):
                    hashes[digest(t)] = digest(norm(t))
            if hashes:
                out[str(path.relative_to(ROOT))] = sorted([h, nh] for h, nh in hashes.items())
    return out


def current_state():
    return {"json": json_hashes(scan.PROMPT_FILES), "code": code_literals()}


def repo_of(rel):
    """Repository a path belongs to: ``external/<name>/...`` is <name>, everything else is YWeb."""
    parts = Path(rel).parts
    return parts[1] if len(parts) > 2 and parts[0] == "external" else "YWeb"


def pack_files():
    for base in EN_PACK_DIRS:
        if base.exists():
            yield from sorted(base.rglob("*.json"))
    for sub in ("external", "y_web"):
        base = ROOT / sub
        if base.exists():
            yield from sorted(base.rglob(INTERNAL_PACK_NAME))


def en_pack_hashes():
    """Per repository: (exact hashes, placeholder-normalised hashes) of every string in its English packs."""
    out = {}
    for path in pack_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        exact, normed = out.setdefault(repo_of(path.relative_to(ROOT)), (set(), set()))
        for _, text in walk_json(data):
            exact.add(digest(text))
            normed.add(digest(norm(text)))
    return out


def check(saved, now):
    """A prompt may move inside its own repository (code to pack, pack to pack), never change or vanish."""
    problems = []
    packs = en_pack_hashes()
    code_by_repo = {}
    json_by_repo = {}
    for rel, records in now["code"].items():
        code_by_repo.setdefault(repo_of(rel), set()).update(h for h, _ in records)
    for rel, keys in now["json"].items():
        json_by_repo.setdefault(repo_of(rel), set()).update(keys.values())
    for rel, keys in saved["json"].items():
        repo = repo_of(rel)
        exact = packs.get(repo, (set(), set()))[0] | code_by_repo.get(repo, set()) | json_by_repo.get(repo, set())
        for key, h in keys.items():
            if now["json"].get(rel, {}).get(key) == h or h in exact:
                continue
            problems.append(f"changed or removed template: {rel} :: {key}")
    for rel, records in saved["code"].items():
        repo = repo_of(rel)
        pack_exact, pack_norm = packs.get(repo, (set(), set()))
        exact = pack_exact | code_by_repo.get(repo, set()) | json_by_repo.get(repo, set())
        for h, nh in records:
            if h not in exact and nh not in pack_norm:
                problems.append(f"changed or removed code literal in {rel} (sha256 {h[:12]})")
    return problems


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--out", help="write the snapshot here instead of docs/prompt-hashes.json")
    args = ap.parse_args()
    now = current_state()
    if args.write:
        target = Path(args.out) if args.out else OUT
        target.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        n_json = sum(len(v) for v in now["json"].values())
        n_code = sum(len(v) for v in now["code"].values())
        print(f"wrote {target}: {n_json} template hashes, {n_code} code literal hashes")
        return 0
    saved = json.loads(OUT.read_text(encoding="utf-8"))
    problems = check(saved, now)
    for p in problems:
        print(p)
    print("prompt hashes: OK" if not problems else f"prompt hashes: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
