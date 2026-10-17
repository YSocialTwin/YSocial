#!/usr/bin/env python3
"""Static scan that feeds docs/prompt-inventory.md (step 0 of the multilingual prompts task).

Reports, for every repository that talks to an LLM:
  * prompt-like string literals written in the code (instructions, formats, rules);
  * eval/exec sites and str.format() renderers;
  * places where a model answer is compared with a protocol token.

It only reads files. Run from the YWeb root: ``python scripts/prompts/inventory_scan.py [--json]``.
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

# PROMPTS_ROOT lets the scan run on a copy of the repositories (for example a checkout of the baseline).
ROOT = Path(os.environ.get("PROMPTS_ROOT") or Path(__file__).resolve().parents[2])
REPOS = {
    "YWeb": ROOT / "y_web",
    "YClient": ROOT / "external" / "YClient" / "y_client",
    "YClientReddit": ROOT / "external" / "YClientReddit" / "y_client",
    "YSimulator": ROOT / "external" / "YSimulator" / "YSimulator",
    "YPhotoSharing": ROOT / "external" / "YPhotoSharing" / "YPhotoSharing",
    "y_agents_plugins": ROOT / "external" / "y_agents_plugins" / "src",
    "reactive_agents": ROOT / "external" / "reactive_agents" / "src",
}
SKIP = ("/tests/", "/test_", "/example", "/__pycache__/", "/migrations/", "/translations/")
CUES = re.compile(
    r"\b(you are|you will|respond|reply|return|output|answer|write|classify|choose|"
    r"do not|only|json|format|summar|generate|decide|identify)\b",
    re.I,
)
TOKENS = ("COMMENT", "FOLLOW", "NONE", "IGNORE", "REACT", "SHARE", "POST", "SEARCH", "CAST", "UNFOLLOW")


def py_files(base):
    for p in sorted(base.rglob("*.py")):
        s = str(p).replace("\\", "/")
        if any(k in s for k in SKIP):
            continue
        yield p


def text_of(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) else "{}" for v in node.values
        )
    return None


def scan_file(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    out = {"literals": [], "eval": [], "format": [], "parsers": []}
    doc_ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            if n.body and isinstance(n.body[0], ast.Expr):
                doc_ids.add(id(n.body[0].value))
    doc_ids |= {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    for n in ast.walk(tree):
        t = text_of(n)
        if t and id(n) not in doc_ids and len(t.split()) >= 8 and CUES.search(t):
            if not t.lstrip().startswith(("http", "SELECT", "INSERT")):
                out["literals"].append((n.lineno, " ".join(t.split())[:90]))
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            if name in ("eval", "exec"):
                out["eval"].append((n.lineno, name))
            if name == "format" and isinstance(f, ast.Attribute):
                out["format"].append((n.lineno, "str.format"))
        if isinstance(n, ast.Compare):
            segs = [text_of(c) for c in [n.left] + n.comparators]
            if any(s and s.strip().upper() in TOKENS for s in segs):
                out["parsers"].append((n.lineno, " ".join(s for s in segs if s)[:60]))
    # token tests written as ``"X" in answer.upper()``
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"\b(%s)\b" % "|".join(TOKENS), line) and re.search(
            r"\.(upper|lower|strip|split|startswith|find)\(|\bin\b|==", line
        ):
            if re.search(r"[\"'](%s)[\"']" % "|".join(TOKENS), line):
                out["parsers"].append((i, line.strip()[:80]))
    out["parsers"] = sorted(set(out["parsers"]))
    return out


PROMPT_FILES = [
    "data_schema/prompts.json",
    "data_schema/prompts_forum.json",
    "data_schema/prompts_hpc.json",
    "data_schema/prompts_ygram.json",
    "external/YClient/config_files/prompts.json",
    "external/YClientReddit/config_files/prompts.json",
    "external/YPhotoSharing/example/prompts_ygram.json",
]
LLM_HINT = re.compile(r"chat_messages|llm|completion|annotat|generate_reply|vllm", re.I)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)


def prompt_file_rows():
    import hashlib

    rows = []
    for rel in PROMPT_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        holders = set()
        for t in _strings(data):
            holders.update(re.findall(r"\{([A-Za-z_][\w.\[\]'\"(),]*)\}", t))
        rows.append(
            (
                rel,
                len(data),
                sum(1 for v in data.values() if isinstance(v, dict)),
                hashlib.sha256(path.read_bytes()).hexdigest()[:12],
                sorted(holders),
            )
        )
    return rows


TOKEN = re.compile(r"^[A-Z][A-Z_]{1,}$")
WORDS = {
    "yes", "no", "none", "null", "neutral", "agree", "disagree", "like", "love", "laugh",
    "angry", "skip", "ignore", "accept", "follow", "unfollow", "comment", "post", "read",
    "search", "share", "react", "reply",
}


def answer_parsers():
    """Functions that compare something with a protocol-looking word, per LLM-facing file.

    Candidates only: internal action names (``follow``, ``comment``) and configuration values
    (``NULL``, ``INT``) also match and are triaged by hand in docs/prompt-inventory.md.
    """
    found = {}
    for repo, base in REPOS.items():
        if not base.exists() or repo == "YWeb":
            continue
        for path in py_files(base):
            src = path.read_text(encoding="utf-8", errors="replace")
            if not LLM_HINT.search(src):
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            parents = {}
            for n in ast.walk(tree):
                for c in ast.iter_child_nodes(n):
                    parents[c] = n

            def enclosing(n):
                while n in parents:
                    n = parents[n]
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        return n.name
                return "<module>"

            hits = {}
            for n in ast.walk(tree):
                if not isinstance(n, ast.Compare):
                    continue
                for c in [n.left] + n.comparators:
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        vals = [c.value]
                    elif isinstance(c, (ast.Tuple, ast.List, ast.Set)):
                        vals = [e.value for e in c.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                    else:
                        continue
                    for v in vals:
                        if TOKEN.match(v) or v.strip().lower() in WORDS:
                            hits.setdefault(enclosing(n), set()).add(v)
            if hits:
                found[str(path.relative_to(ROOT))] = {k: sorted(v) for k, v in hits.items()}
    return found


def markdown(report):
    out = ["## Generated tables", "", "### Prompt files", ""]
    out += ["| File | Keys | Nested groups | sha256 (12) |", "| --- | --- | --- | --- |"]
    fields = set()
    for rel, n, nested, digest, holders in prompt_file_rows():
        out.append(f"| `{rel}` | {n} | {nested} | `{digest}` |")
        fields.update(holders)
    out += ["", "### Template fields found in the prompt files", "", ", ".join(f"`{f}`" for f in sorted(fields)), ""]
    out += ["### Code scan per repository", "", "| Repository | Prompt-like literals | eval/exec | str.format | Answer comparisons |", "| --- | --- | --- | --- | --- |"]
    for repo, files in report.items():
        tot = {k: sum(len(f[k]) for f in files.values()) for k in ("literals", "eval", "format", "parsers")}
        out.append(f"| {repo} | {tot['literals']} | {tot['eval']} | {tot['format']} | {tot['parsers']} |")
    out += ["", "### eval / exec sites", ""]
    for repo, files in report.items():
        for path, r in files.items():
            for ln, name in r["eval"]:
                out.append(f"- `{path}:{ln}` {name}")
    out += ["", "### Files with prompt-like literals", "", "| File | Literals |", "| --- | --- |"]
    for repo, files in report.items():
        for path, r in files.items():
            if len(r["literals"]) >= 3:
                out.append(f"| `{path}` | {len(r['literals'])} |")
    out += ["", "### Answer comparisons in LLM-facing files", "", "| File | Lines |", "| --- | --- |"]
    for repo, files in report.items():
        for path, r in files.items():
            if not r["parsers"]:
                continue
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            if LLM_HINT.search(text):
                out.append(f"| `{path}` | {', '.join(str(ln) for ln, _ in r['parsers'][:25])} |")
    out += ["", "### Parser candidates (function and the protocol-looking words it compares)", ""]
    for path, funcs in answer_parsers().items():
        out.append(f"- `{path}`")
        for func, vals in funcs.items():
            out.append(f"  - `{func}`: " + ", ".join(f"`{v}`" for v in vals))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    report = {}
    for repo, base in REPOS.items():
        if not base.exists():
            continue
        files = {}
        for p in py_files(base):
            r = scan_file(p)
            if r and any(r.values()):
                files[str(p.relative_to(ROOT))] = r
        report[repo] = files
    if args.json:
        json.dump(report, sys.stdout, indent=1)
        return
    if args.markdown:
        print(markdown(report))
        return
    for repo, files in report.items():
        tot = {k: sum(len(f[k]) for f in files.values()) for k in ("literals", "eval", "format", "parsers")}
        print(f"## {repo}: {tot}")
        for path, r in files.items():
            print(f"  {path}: " + ", ".join(f"{k}={len(v)}" for k, v in r.items() if v))


if __name__ == "__main__":
    main()
