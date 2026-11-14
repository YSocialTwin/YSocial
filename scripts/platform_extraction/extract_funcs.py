"""Cut named top-level functions (with decorators) out of a module; report what they need."""

import ast, sys, io, re
from pyflakes import api as pf
from pyflakes.reporter import Reporter


def extract(path, names, write_back=True):
    src = open(path).read()
    tree = ast.parse(src)
    lines = src.split("\n")
    pieces, spans = [], []
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        ):
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            # include a directly preceding comment block
            while start > 1 and lines[start - 2].lstrip().startswith("#"):
                start -= 1
            spans.append((start, node.end_lineno))
            pieces.append("\n".join(lines[start - 1 : node.end_lineno]))
    found = {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef,)) and n.name in names
    }
    missing = set(names) - found
    if missing:
        raise SystemExit(f"not found: {missing}")
    if write_back:
        for s, e in sorted(spans, reverse=True):
            del lines[s - 1 : e]
        open(path, "w").write(re.sub(r"\n{4,}", "\n\n\n", "\n".join(lines)))
    return "\n\n\n".join(pieces)


def imports_of(path):
    """name -> import source line(s), for every import at module level of path."""
    src = open(path).read()
    tree = ast.parse(src)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                nm = a.asname or a.name
                mod = ("." * node.level) + (node.module or "")
                out[nm] = (mod, a.name, a.asname)
        elif isinstance(node, ast.Import):
            for a in node.names:
                out[(a.asname or a.name).split(".")[0]] = (None, a.name, a.asname)
    # module-level assignments / defs
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defs[node.name] = "def"
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defs[t.id] = "assign"
    return out, defs


def undefined(code):
    buf = io.StringIO()
    pf.check(code, "x", Reporter(buf, buf))
    return sorted(set(re.findall(r"undefined name '([^']+)'", buf.getvalue())))
