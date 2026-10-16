"""Wrap flash()/message literals of Python modules in gettext calls.

Usage: mark_python.py [--keys message,error] file.py ...
Literal strings become _("..."); f-strings become _("... %(v)s", v=expr).
"""
import ast, re, sys


_BUILTIN = {"str", "format", "len", "int", "round", "sorted", "float", "repr", "abs", "max", "min", "sum"}

def _pname(e):
    """Readable placeholder name for an f-string expression."""
    n = None
    if isinstance(e, ast.Name):
        n = e.id
    elif isinstance(e, ast.Attribute):
        n = e.attr
    elif isinstance(e, ast.Subscript):
        sl = e.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            n = sl.value
        else:
            n = _pname(e.value)
    elif isinstance(e, ast.Call):
        f = e.func
        fn = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
        if fn in _BUILTIN and e.args:
            return _pname(e.args[0])
        n = fn
    elif isinstance(e, (ast.BoolOp, ast.BinOp)):
        vals = e.values if isinstance(e, ast.BoolOp) else [e.left]
        return _pname(vals[0])
    n = re.sub(r"\W+", "_", n or "value").strip("_").lower() or "value"
    if n in ("e", "ex", "exc", "err", "error", "str_e"):
        n = "error"
    if n[0].isdigit():
        n = "v" + n
    return n[:24]

def conv(node):
    """Return source of gettext call for a Constant/JoinedStr node, or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        s = node.value
        if not re.search(r"[A-Za-z]{2}", s):
            return None
        return "_(%r)" % s if '"' in s else '_("%s")' % s.replace("\\", "\\\\").replace("\n", "\\n")
    if isinstance(node, ast.JoinedStr):
        fmt, args, names = "", [], {}
        for v in node.values:
            if isinstance(v, ast.Constant):
                fmt += v.value.replace("%", "%%")
            else:
                expr = v.value
                if v.conversion not in (-1, None) and v.conversion != 115 and v.conversion != 114:
                    return None
                src = ast.unparse(expr)
                if v.format_spec is not None:
                    spec = "".join(x.value for x in v.format_spec.values if isinstance(x, ast.Constant))
                    if len(spec) != len(ast.unparse(v.format_spec)) - 3 and not spec:
                        return None
                    src = "format(%s, %r)" % (src, spec)
                elif v.conversion == 115:
                    src = "str(%s)" % src
                if src in names:
                    nm = names[src]
                else:
                    base = _pname(expr)
                    nm = base; i = 2
                    while nm in names.values():
                        nm = "%s%d" % (base, i); i += 1
                    names[src] = nm
                    args.append("%s=%s" % (nm, src))
                fmt += "%%(%s)s" % nm
        if not re.search(r"[A-Za-z]{2}", re.sub(r"%\(\w+\)s", "", fmt)):
            return None
        q = repr(fmt) if '"' in fmt else '"%s"' % fmt.replace("\\", "\\\\").replace("\n", "\\n")
        return "_(%s, %s)" % (q, ", ".join(args))
    return None

def main(files, keys):
    for fn in files:
        src = open(fn, encoding="utf-8").read()
        tree = ast.parse(src)
        lines = src.splitlines(keepends=True)
        offs = [0]
        for l in lines:
            offs.append(offs[-1] + len(l.encode()))
        b = src.encode()
        edits = []
        def add(node):
            r = conv(node)
            if r:
                edits.append((offs[node.lineno-1] + node.col_offset, offs[node.end_lineno-1] + node.end_col_offset, r))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
                if name == "flash" and n.args:
                    add(n.args[0])
                elif name == "jsonify" and keys:
                    for a in list(n.args) + [k.value for k in n.keywords]:
                        if isinstance(a, ast.Dict):
                            for k, v in zip(a.keys, a.values):
                                if isinstance(k, ast.Constant) and k.value in keys:
                                    add(v)
                    for k in n.keywords:
                        if k.arg in keys:
                            add(k.value)
        if not edits:
            continue
        for s, e, r in sorted(edits, reverse=True):
            b = b[:s] + r.encode() + b[e:]
        out = b.decode()
        has = re.search(r"^from flask_babel import .*\bgettext as _\b", out, re.M)
        uses_us = any(isinstance(t, ast.Name) and t.id == "_" and isinstance(t.ctx, ast.Store) for t in ast.walk(tree))
        if uses_us:
            print("WARN _ assigned in", fn)
        if not has:
            m = list(re.finditer(r"^(from|import) .*$", out, re.M))
            # insert after last top-level import block line before first def/class
            first = re.search(r"^(def|class|@)", out, re.M)
            cand = [x for x in m if not first or x.start() < first.start()]
            pos = cand[-1]
            # handle multi-line parenthesised import
            end = pos.end()
            if out[pos.start():end].rstrip().endswith("("):
                end = out.index("\n)", end) + 2
            out = out[:end] + "\nfrom flask_babel import gettext as _" + out[end:]
        open(fn, "w", encoding="utf-8").write(out)
        print(fn, len(edits))

if __name__ == "__main__":
    a = sys.argv[1:]; keys = set()
    if a and a[0] == "--keys":
        keys = set(a[1].split(",")); a = a[2:]
    main(a, keys)
