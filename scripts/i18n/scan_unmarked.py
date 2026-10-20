#!/usr/bin/env python3
"""Scanner for user-visible strings that are not marked for translation.

    python scripts/i18n/scan_unmarked.py              # print a summary
    python scripts/i18n/scan_unmarked.py --check      # CI: fail if any file got worse
    python scripts/i18n/scan_unmarked.py --update     # rewrite the baseline

Counts per file (templates, flash()/jsonify() in Python, own JS) are compared with
docs/i18n/scan_baseline.json: a file may never have *more* unmarked strings than its
baseline, and new files start at zero. The baseline only shrinks as the areas of
phases 2-4 are converted; in phase 6 it becomes empty and the check is exact.
Strings that must stay in English (brand names, technical tokens) are listed, with a
reason, in docs/i18n/scan_exceptions.txt (one per line: ``text # reason``).
"""

import argparse
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_strings import ROOT, TextCollector, files, js_literals, read  # noqa: E402

BASELINE = ROOT / "docs" / "i18n" / "scan_baseline.json"
EXCEPTIONS = ROOT / "docs" / "i18n" / "scan_exceptions.txt"
GETTEXT_NAMES = {"_", "gettext", "lazy_gettext", "_l", "ngettext", "pgettext"}
MESSAGE_KEYS = {"error", "message", "msg", "detail"}


def load_exceptions():
    if not EXCEPTIONS.is_file():
        return set()
    out = set()
    for line in EXCEPTIONS.read_text(encoding="utf-8").splitlines():
        text = line.split(" # ", 1)[0].strip()
        if text and not text.startswith("#"):
            out.add(text)
    return out


def scan_template(path, exceptions):
    """Unmarked text: Jinja is stripped first, so ``{{ _('x') }}`` never shows up."""
    from audit_strings import JINJA

    parser = TextCollector()
    parser.feed(JINJA.sub("", read(path)))
    found = [t for t in parser.texts + parser.attrs if t not in exceptions]
    return len(found)


def _is_marked(node):
    return isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Name) and node.func.id in GETTEXT_NAMES)
        or (isinstance(node.func, ast.Attribute) and node.func.attr in GETTEXT_NAMES)
    )


def _is_text(node):
    return isinstance(node, (ast.Constant, ast.JoinedStr)) and (
        not isinstance(node, ast.Constant) or isinstance(node.value, str)
    )


def scan_python(path, exceptions):
    """flash()/jsonify() messages given as plain or f-strings instead of gettext calls."""
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (
            fn.id
            if isinstance(fn, ast.Name)
            else fn.attr if isinstance(fn, ast.Attribute) else ""
        )
        if name == "flash" and node.args:
            arg = node.args[0]
            if _is_text(arg) and not (
                isinstance(arg, ast.Constant) and arg.value in exceptions
            ):
                count += 1
        elif name == "jsonify":
            for kw in node.keywords:
                if kw.arg in MESSAGE_KEYS and _is_text(kw.value):
                    count += 1
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    for key, value in zip(arg.keys, arg.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value in MESSAGE_KEYS
                            and _is_text(value)
                        ):
                            count += 1
    return count


def catalog_keys():
    """English texts already in a browser catalog: data-driven strings (guided
    tutorials) that are translated at render time count as marked."""
    import json

    keys = set()
    for en in (ROOT / "y_web" / "translations" / "js").glob("*/en.json"):
        try:
            keys |= set(json.loads(en.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return keys


def scan_js(path, exceptions):
    src = read(path)
    if (
        path.name in {"app.js", "browser-sync-client.js"}
        or len(src) / max(1, src.count("\n") + 1) > 200
    ):
        return 0  # bundled or minified library
    known = catalog_keys()
    return len([s for s in js_literals(src) if s not in exceptions and s not in known])


def scan_all():
    exceptions = load_exceptions()
    web = ROOT / "y_web"
    counts = {}
    for path in files(web / "templates", ".html"):
        counts[str(path.relative_to(ROOT))] = scan_template(path, exceptions)
    for path in files(web, ".py"):
        n = scan_python(path, exceptions)
        if n:
            counts[str(path.relative_to(ROOT))] = n
    for path in files(web / "static" / "assets" / "js", ".js"):
        n = scan_js(path, exceptions)
        if n:
            counts[str(path.relative_to(ROOT))] = n
    return {k: v for k, v in counts.items() if v}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if a file has more unmarked strings than its baseline",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite the baseline from the current state",
    )
    args = parser.parse_args(argv)

    counts = scan_all()
    if args.update:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(dict(sorted(counts.items())), indent=1) + "\n", encoding="utf-8"
        )
        print(
            f"baseline written: {len(counts)} files, {sum(counts.values())} unmarked strings"
        )
        return 0

    baseline = (
        json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else {}
    )
    worse = {
        f: (baseline.get(f, 0), n) for f, n in counts.items() if n > baseline.get(f, 0)
    }
    better = {
        f: (b, counts.get(f, 0)) for f, b in baseline.items() if counts.get(f, 0) < b
    }
    print(
        f"unmarked strings: {sum(counts.values())} in {len(counts)} files (baseline {sum(baseline.values())})"
    )
    for f, (b, n) in sorted(worse.items()):
        print(f"  WORSE  {f}: {b} -> {n}")
    if better and not worse:
        print(f"  {len(better)} file(s) improved: run --update to lock the gain in")
    if args.check and worse:
        print(
            "i18n: new unmarked strings; wrap them in _()/t() or list them in scan_exceptions.txt"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
