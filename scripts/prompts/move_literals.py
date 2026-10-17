#!/usr/bin/env python3
"""Move prompt-like string literals from Python code into a repository's ``prompts_internal.json`` (step 1).

Each prompt-like literal or f-string becomes ``prompt_store.get("key")`` or ``prompt_store.prompt("key", field=expr, ...)``.
The template keeps every character of the original text; each ``{expression}`` of an f-string becomes a named field and
the expression stays in the code as the value of that field. Nothing is evaluated.

Literals are left alone (and listed) when moving them could change behaviour: logging and error messages, docstrings,
strings used with ``.format``, texts that already contain ``{name}``-looking braces, and parts of f-string expressions.

    python scripts/prompts/move_literals.py --package external/YClient/y_client          # dry run: list what would move
    python scripts/prompts/move_literals.py --package external/YClient/y_client --apply  # rewrite files, extend the pack

``--import-line`` sets the import added to rewritten files (default: ``from <package> import prompt_store``).
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory_scan as scan  # noqa: E402

FIELD = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
LOG_CALLS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "print", "write", "log"}
SKIP_DIRS = ("/tests/", "/test_", "/__pycache__/", "/examples/", "/example/")


def text_of(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    return None


def prompt_like(text):
    return len(text.split()) >= 8 and bool(scan.CUES.search(text)) and not text.lstrip().startswith(("http", "SELECT", "INSERT"))


class Mover:
    def __init__(self, path, pack, package_import):
        self.path = path
        self.pack = pack
        self.package_import = package_import
        self.src = path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)
        self.parents = {}
        for n in ast.walk(self.tree):
            for c in ast.iter_child_nodes(n):
                self.parents[c] = n
        raw = self.src.encode("utf-8")
        self.raw = raw
        self.starts = [0]
        for line in raw.split(b"\n")[:-1]:
            self.starts.append(self.starts[-1] + len(line) + 1)
        self.moved = []
        self.skipped = []
        self.residual = []
        self.edits = []
        self.counters = {}

    # -- context ---------------------------------------------------------------------------------
    def docstring_ids(self):
        ids = set()
        for n in ast.walk(self.tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                if n.body and isinstance(n.body[0], ast.Expr):
                    ids.add(id(n.body[0].value))
        return ids

    def function_name(self, node):
        while node in self.parents:
            node = self.parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return "module"

    def excluded_reason(self, node):
        cur = node
        while cur in self.parents:
            parent = self.parents[cur]
            if isinstance(parent, (ast.JoinedStr, ast.FormattedValue)):
                return "part of an f-string"
            if isinstance(parent, ast.Raise):
                return "raised message"
            if isinstance(parent, ast.Assert):
                return "assert message"
            if isinstance(parent, ast.Dict) and cur in parent.keys:
                return "dict key"
            if isinstance(parent, ast.Call):
                func = parent.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in LOG_CALLS or name.endswith("Error") or name == "Exception":
                    return f"{name}() message"
            if isinstance(parent, ast.Attribute) and parent.attr in ("format", "format_map") and cur is parent.value:
                return "used with .format"
            if isinstance(parent, ast.stmt):
                break
            cur = parent
        return None

    # -- template building -----------------------------------------------------------------------
    def build(self, node, func):
        """Return (template, [(field, expr_source)], sentinel_text) or (None, reason)."""
        fields = []  # (name, expr)
        names = {}

        def field_for(value):
            expr = ast.unparse(value)
            if expr in names:
                return names[expr]
            base = None
            if isinstance(value, ast.Name):
                base = value.id
            elif isinstance(value, ast.Attribute):
                base = value.attr
            elif isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant) and isinstance(value.slice.value, str):
                base = value.slice.value
            if not base or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", base):
                base = f"v{len(names) + 1}"
            name, i = base, 2
            while name in names.values():
                name = f"{base}_{i}"
                i += 1
            names[expr] = name
            fields.append((name, expr))
            return name

        if isinstance(node, ast.Constant):
            # a plain string with {name} fields is a template filled in later (eval or format): moved as it is
            return node.value, [], node.value
        template, sentinel = [], []
        for v in node.values:
            if isinstance(v, ast.Constant):
                if FIELD.search(v.value):
                    return None, "text already contains {name} braces"
                template.append(v.value)
                sentinel.append(v.value)
                continue
            value = v.value
            if v.format_spec is not None:
                if not all(isinstance(x, ast.Constant) for x in v.format_spec.values):
                    return None, "dynamic format spec"
                spec = "".join(x.value for x in v.format_spec.values)
            else:
                spec = None
            expr_src = ast.unparse(value)
            wrapped = None
            if v.conversion != -1 or spec is not None:
                inner = {114: f"repr({expr_src})", 115: f"str({expr_src})", 97: f"ascii({expr_src})"}.get(v.conversion, expr_src)
                wrapped = f"format({inner}, {spec!r})" if spec is not None else inner
                # one field per distinct wrapped expression
                key_node = ast.parse(wrapped, mode="eval").body
                name = field_for(key_node)
            else:
                name = field_for(value)
            template.append("{" + name + "}")
            sentinel.append("\x00" + name + "\x00")
            # words hidden inside the expression (conditional strings) stay in the code: report them
            for sub in ast.walk(value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and re.search(r"[A-Za-z]{3,}", sub.value):
                    self.residual.append((node.lineno, sub.value[:60]))
                    break
        return "".join(template), fields, "".join(sentinel)

    def key_for(self, template, func):
        for key, existing in self.pack.items():
            if existing == template:
                return key
        stem = self.path.stem
        base = f"{stem}__{func.lstrip('_') or 'fn'}"
        n = self.counters.get(base, 0) + 1
        while f"{base}__{n}" in self.pack:
            n += 1
        self.counters[base] = n
        return f"{base}__{n}"

    def offset(self, line, col):
        return self.starts[line - 1] + col

    def run(self):
        docs = self.docstring_ids()
        for node in ast.walk(self.tree):
            text = text_of(node)
            if text is None or id(node) in docs or not prompt_like(text):
                continue
            reason = self.excluded_reason(node)
            if reason == "part of an f-string":
                continue
            if reason:
                self.skipped.append((node.lineno, reason, " ".join(text.split())[:70]))
                continue
            func = self.function_name(node)
            built = self.build(node, func)
            if built[0] is None:
                self.skipped.append((node.lineno, built[1], " ".join(text.split())[:70]))
                continue
            template, fields, sentinel = built
            # self-check: rendering the template with sentinels reproduces the original text
            rendered = template if isinstance(node, ast.Constant) else FIELD.sub(lambda m: "\x00" + m.group(0)[1:-1] + "\x00", template)
            if rendered != sentinel:
                self.skipped.append((node.lineno, "round-trip check failed", " ".join(text.split())[:70]))
                continue
            key = self.key_for(template, func)
            self.pack.setdefault(key, template)
            indent = " " * (node.col_offset + 4)
            if fields:
                args = "".join(f",\n{indent}{name}={expr}" for name, expr in fields)
                call = f'prompt_store.prompt(\n{indent}"{key}"{args},\n{" " * node.col_offset})'
            else:
                call = f'prompt_store.get("{key}")'
            start = self.offset(node.lineno, node.col_offset)
            end = self.offset(node.end_lineno, node.end_col_offset)
            self.edits.append((start, end, call))
            self.moved.append((node.lineno, key, " ".join(text.split())[:70]))

    def rewrite(self):
        if not self.edits:
            return None
        raw = self.raw
        for start, end, call in sorted(self.edits, reverse=True):
            raw = raw[:start] + call.encode("utf-8") + raw[end:]
        text = raw.decode("utf-8")
        if "prompt_store" not in self.src:
            text = self.add_import(text)
        ast.parse(text)  # must still compile
        return text

    def add_import(self, text):
        tree = ast.parse(text)
        last = None
        first_def = min(
            (n.lineno for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))),
            default=10**9,
        )
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)) and n.lineno < first_def:
                if not (isinstance(n, ast.ImportFrom) and n.module == "__future__"):
                    last = n
                elif last is None:
                    last = n
        lines = text.split("\n")
        at = (last.end_lineno if last else 0)
        lines.insert(at, self.package_import)
        return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="package directory, relative to the YWeb root")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--import-line")
    ap.add_argument("--only", help="only files whose path contains this text")
    ap.add_argument("--skip", help="skip files whose path contains this text", action="append", default=[])
    args = ap.parse_args()
    pkg = scan.ROOT / args.package
    pack_path = pkg / "prompts_internal.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8")) if pack_path.exists() else {}
    dotted = ".".join(pkg.relative_to(scan.ROOT).parts[-1:])
    import_line = args.import_line or f"from {dotted} import prompt_store"
    total = 0
    for path in sorted(pkg.rglob("*.py")):
        rel = str(path.relative_to(scan.ROOT))
        if any(s in "/" + rel for s in SKIP_DIRS) or path.name == "prompt_store.py":
            continue
        if args.only and args.only not in rel or any(s in rel for s in args.skip):
            continue
        mover = Mover(path, pack, import_line)
        try:
            mover.run()
        except SyntaxError:
            continue
        if not (mover.moved or mover.skipped):
            continue
        print(f"## {rel}: {len(mover.moved)} moved, {len(mover.skipped)} left")
        for line, key, preview in mover.moved:
            print(f"   MOVE {line:>5} {key}: {preview}")
        for line, reason, preview in mover.skipped:
            print(f"   LEFT {line:>5} ({reason}): {preview}")
        for line, word in mover.residual:
            print(f"   WORDS-IN-CODE {line:>5}: {word!r}")
        total += len(mover.moved)
        if args.apply:
            new = mover.rewrite()
            if new is not None:
                path.write_text(new, encoding="utf-8")
    if args.apply:
        pack_path.write_text(json.dumps(pack, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"total moved: {total}; pack keys: {len(pack)}" + ("" if args.apply else " (dry run)"))


if __name__ == "__main__":
    main()
