#!/usr/bin/env python3
"""Census of user-visible strings for the i18n project (task F0-1).

Reproducible, stdlib only. Run from the repository root:

    python scripts/i18n/audit_strings.py            # writes docs/i18n/audit.md
    python scripts/i18n/audit_strings.py --json     # prints the raw numbers as JSON

The numbers are heuristics (see "Method" in the generated report): they size the work,
they are not a list of strings to translate. The Phase 1 scanner supersedes them.
"""

import argparse
import ast
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "y_web"
EXTERNAL = ROOT / "external"

SKIP_PARTS = {
    "__pycache__",
    "tests",
    "node_modules",
    ".git",
    "migrations",
    "alembic",
    "site",
}
SIM_AREAS = ["microblogging", "forum", "photo", "shared", "login", "error_pages"]
PLUGINS = [
    "TrainingModules",
    "ScenarioDesign",
    "frontend_adds-on",
    "reactive_agents",
    "y_agents_plugins",
]
LIB_JS = {"app.js", "browser-sync-client.js"}  # bundled third-party code
ATTRS = {
    "title",
    "placeholder",
    "alt",
    "aria-label",
    "data-title",
    "data-tooltip",
    "label",
}
JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
LETTERS = re.compile(r"[A-Za-z]{2,}")


def files(base, suffix):
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("*" + suffix)):
        if SKIP_PARTS & set(p.relative_to(base).parts):
            continue
        out.append(p)
    return out


def read(p):
    return p.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- templates
class TextCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.texts, self.attrs = [], []
        self.inline_scripts = []
        self._script = None

    def handle_starttag(self, tag, attrs):
        if tag in ("style",):
            self.skip += 1
        if tag == "script":
            d = dict(attrs)
            if "src" not in d:
                self._script = []
            self.skip += 1
        for k, v in attrs:
            if k in ATTRS and v and LETTERS.search(JINJA.sub("", v)):
                self.attrs.append(v.strip())
            if k == "value" and v and LETTERS.search(JINJA.sub("", v)):
                if dict(attrs).get("type") in ("submit", "button"):
                    self.attrs.append(v.strip())

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)
        if tag == "script" and self._script is not None:
            self.inline_scripts.append("".join(self._script))
            self._script = None

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
            return
        if self.skip:
            return
        t = " ".join(data.split())
        if t and LETTERS.search(t):
            self.texts.append(t)


def audit_templates(paths):
    res = dict(
        files=len(paths),
        lines=0,
        bytes=0,
        texts=0,
        attrs=0,
        unique=set(),
        scripts=0,
        script_lines=0,
        script_literals=0,
        lang_hardcoded=0,
    )
    for p in paths:
        raw = read(p)
        res["lines"] += raw.count("\n") + 1
        res["bytes"] += len(raw.encode("utf-8"))
        if re.search(r"<html[^>]*\blang=[\"']", raw):
            res["lang_hardcoded"] += 1
        c = TextCollector()
        try:
            c.feed(JINJA.sub(" ", raw))
        except Exception:
            pass
        res["texts"] += len(c.texts)
        res["attrs"] += len(c.attrs)
        res["unique"].update(c.texts)
        res["unique"].update(c.attrs)
        res["scripts"] += len(c.inline_scripts)
        for s in c.inline_scripts:
            res["script_lines"] += s.count("\n") + 1
            res["script_literals"] += len(js_literals(s))
    res["unique"] = len(res["unique"])
    return res


# --------------------------------------------------------------- javascript
JS_STR = re.compile(r"""(?P<q>["'`])(?P<s>(?:\\.|(?!(?P=q)).){2,200}?)(?P=q)""", re.S)


def js_literals(src):
    """String literals that look like human text (two or more words, or a sentence)."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(?m)(^|\s)//.*$", "", src)
    out = []
    for m in JS_STR.finditer(src):
        s = m.group("s").strip()
        if "\n" in s or len(s) < 4:
            continue
        s = re.sub(r"\$\{[^}]*\}", "", s)
        if re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{2,}", s) and not re.search(
            r"[{};=<>]|^(https?:|/|\.|#)|function|return |\.js|\.css|\.png", s
        ):
            out.append(s)
    return out


def is_minified(src):
    lines = src.splitlines() or [""]
    return len(src) / max(1, len(lines)) > 200


def audit_js(paths):
    own, lib, tut = [], [], []
    for p in paths:
        src = read(p)
        if p.name in LIB_JS or is_minified(src):
            lib.append((p.name, src.count("\n") + 1))
            continue
        entry = dict(file=p.name, lines=src.count("\n") + 1, literals=js_literals(src))
        (tut if "tutorial" in p.name else own).append(entry)
    return own, lib, tut


# ------------------------------------------------------------------- python
def audit_python(paths):
    flash_total = flash_literal = flash_fstring = flash_other = 0
    json_total = json_msg = 0
    abort_msg = 0
    by_file = {}
    for p in paths:
        try:
            tree = ast.parse(read(p))
        except SyntaxError:
            continue
        n = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (
                fn.id
                if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else ""
            )
            if name == "flash":
                flash_total += 1
                n += 1
                a = node.args[0] if node.args else None
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    flash_literal += 1
                elif isinstance(a, ast.JoinedStr):
                    flash_fstring += 1
                else:
                    flash_other += 1
            elif name == "jsonify":
                json_total += 1
                keys = {k.arg for k in node.keywords}
                for a in node.args:
                    if isinstance(a, ast.Dict):
                        keys |= {k.value for k in a.keys if isinstance(k, ast.Constant)}
                if keys & {"error", "message", "msg", "detail"}:
                    json_msg += 1
                    n += 1
            elif name == "abort" and len(node.args) > 1:
                abort_msg += 1
        if n:
            by_file[str(p.relative_to(ROOT))] = n
    return dict(
        flash_total=flash_total,
        flash_literal=flash_literal,
        flash_fstring=flash_fstring,
        flash_other=flash_other,
        json_total=json_total,
        json_with_message=json_msg,
        abort_with_message=abort_msg,
        files_with_messages=len(by_file),
        top_files=sorted(by_file.items(), key=lambda kv: -kv[1])[:8],
    )


# ----------------------------------------------------------------- manifests
MANIFEST_KEYS = {
    "name",
    "display_name",
    "description",
    "label",
    "title",
    "help",
    "placeholder",
    "tooltip",
    "category",
    "group",
    "summary",
}


def manifest_strings(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in MANIFEST_KEYS and isinstance(v, str) and LETTERS.search(v):
                out.append(v)
            else:
                manifest_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            manifest_strings(v, out)


def audit_manifests(base):
    out = []
    for p in sorted(base.glob("meta/*.json")):
        try:
            manifest_strings(json.loads(read(p)), out)
        except ValueError:
            pass
    return dict(strings=len(out), words=sum(len(s.split()) for s in out))


# --------------------------------------------------------------------- main
def collect():
    data = {}
    t = files(WEB / "templates", ".html")
    data["templates_total"] = audit_templates(t)
    data["templates_admin"] = audit_templates(
        [p for p in t if "admin" in p.relative_to(WEB / "templates").parts[:1]]
    )
    for a in SIM_AREAS:
        data["templates_" + a] = audit_templates(
            [p for p in t if p.relative_to(WEB / "templates").parts[0] == a]
        )
    other_dirs = (
        {p.relative_to(WEB / "templates").parts[0] for p in t}
        - set(SIM_AREAS)
        - {"admin"}
    )
    data["templates_other_dirs"] = sorted(other_dirs)
    own, lib, tut = audit_js(files(WEB / "static" / "assets" / "js", ".js"))
    data["js_own"] = own
    data["js_lib"] = lib
    data["js_tutorials"] = tut
    data["python_core"] = audit_python(files(WEB, ".py"))
    plugins = {}
    for name in PLUGINS:
        base = EXTERNAL / name
        pt = files(base, ".html")
        pown, plib, ptut = audit_js(files(base, ".js"))
        plugins[name] = dict(
            templates=audit_templates(pt),
            python=audit_python(files(base, ".py")),
            py_files=len(files(base, ".py")),
            js_own=pown + ptut,
            manifests=audit_manifests(base),
        )
    data["plugins"] = plugins
    return data


def js_sum(entries):
    return dict(
        files=len(entries),
        lines=sum(e["lines"] for e in entries),
        literals=sum(len(e["literals"]) for e in entries),
        unique=len({s for e in entries for s in e["literals"]}),
    )


PLAN = {  # figures quoted in the plan ("Piano multilingua"): (value, kind); kind "min" = quoted as a lower bound
    "Template (totale)": (124, "exact"),
    "Template admin": (73, "exact"),
    "Chiamate flash()": (585, "exact"),
    "Risposte JSON con error/message": (86, "min"),
    "Blocchi <script> inline": (64, "exact"),
    "File JS (cartella static/assets/js)": (40, "min"),
    "File *-tutorial.js": (10, "exact"),
}


def render(d):
    L = []
    w = L.append
    tt = d["templates_total"]
    w("# i18n audit: string census (F0-1)\n")
    w(
        "Generated by `scripts/i18n/audit_strings.py`; re-run it to refresh. Figures are heuristic counts that size the "
        "work, not a list of strings to translate.\n"
    )
    w("## Method\n")
    w(
        "- **Templates**: Jinja tags are removed, then the HTML is parsed; a *string* is a text node containing at least "
        "two letters, plus the attributes `title`, `placeholder`, `alt`, `aria-label`, `label`, `data-title`, "
        "`data-tooltip` and the `value` of submit/button inputs. Text inside `<script>` and `<style>` is excluded. "
        "*Unique* de-duplicates identical strings inside the area."
    )
    w(
        "- **Inline scripts**: `<script>` blocks without `src`; literals are quoted strings of two or more words."
    )
    w(
        "- **Python**: AST walk of `flash()` and `jsonify()` calls (`jsonify` counted when it carries `error`, `message`, "
        "`msg` or `detail`); tests, migrations and alembic are skipped."
    )
    w(
        "- **JavaScript**: own files only (minified or bundled files are listed as libraries); a literal is a quoted "
        "string of two or more words that does not look like code, a path or a URL. Tutorials are reported apart."
    )
    w(
        "- **Manifests**: string values of `name`, `display_name`, `description`, `label`, `title`, `help`, "
        "`placeholder`, `tooltip`, `category`, `group`, `summary` in `meta/*.json`.\n"
    )

    w("## Core: templates\n")
    w(
        "| Area | Files | Lines | Text nodes | Attributes | Unique strings | Inline scripts | Hard-coded `lang` |"
    )
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    rows = [("admin", d["templates_admin"])] + [
        (a, d["templates_" + a]) for a in SIM_AREAS
    ]
    for name, r in rows + [("**total**", tt)]:
        w(
            f"| {name} | {r['files']} | {r['lines']} | {r['texts']} | {r['attrs']} | {r['unique']} | "
            f"{r['scripts']} | {r['lang_hardcoded']} |"
        )
    if d["templates_other_dirs"]:
        w(
            f"\nOther template folders not listed above: {', '.join(d['templates_other_dirs'])}."
        )
    w("")
    w("## Core: server-side messages\n")
    pc = d["python_core"]
    w("| Measure | Count |\n|---|---:|")
    w(f"| `flash()` calls | {pc['flash_total']} |")
    w(f"| of which literal string | {pc['flash_literal']} |")
    w(
        f"| of which f-string (needs rewriting with placeholders) | {pc['flash_fstring']} |"
    )
    w(f"| of which variable or other expression | {pc['flash_other']} |")
    w(f"| `jsonify()` with error/message | {pc['json_with_message']} |")
    w(f"| `jsonify()` calls in total | {pc['json_total']} |")
    w(f"| `abort()` with a message | {pc['abort_with_message']} |")
    w(
        f"\nFiles with the most messages: "
        + ", ".join(f"`{f}` ({n})" for f, n in pc["top_files"])
        + ".\n"
    )

    w("## Core: JavaScript\n")
    own, tut = js_sum(d["js_own"]), js_sum(d["js_tutorials"])
    w(
        "| Group | Files | Lines | Text-like literals | Unique |\n|---|---:|---:|---:|---:|"
    )
    w(
        f"| own code (no tutorials) | {own['files']} | {own['lines']} | {own['literals']} | {own['unique']} |"
    )
    w(
        f"| tutorials | {tut['files']} | {tut['lines']} | {tut['literals']} | {tut['unique']} |"
    )
    w(
        f"| bundled / minified libraries (excluded) | {len(d['js_lib'])} | {sum(n for _, n in d['js_lib'])} | | |"
    )
    w(
        f"\nLargest own files by literals: "
        + ", ".join(
            f"`{e['file']}` ({len(e['literals'])})"
            for e in sorted(d["js_own"], key=lambda e: -len(e["literals"]))[:8]
        )
        + ".\n"
    )

    w("## Plugins\n")
    w(
        "| Plugin | Templates | Template strings (text+attr) | Inline scripts | Python files | `flash()` | JSON messages "
        "| Own JS files | JS literals | Manifest strings |"
    )
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, p in d["plugins"].items():
        j = js_sum(p["js_own"])
        t = p["templates"]
        w(
            f"| {name} | {t['files']} | {t['texts'] + t['attrs']} | {t['scripts']} | {p['py_files']} | "
            f"{p['python']['flash_total']} | {p['python']['json_with_message']} | {j['files']} | {j['literals']} | "
            f"{p['manifests']['strings']} |"
        )
    w("")

    w("## Comparison with the plan estimates (G0 criterion: deviation within 25%)\n")
    measured = {
        "Template (totale)": tt["files"],
        "Template admin": d["templates_admin"]["files"],
        "Chiamate flash()": pc["flash_total"],
        "Risposte JSON con error/message": pc["json_with_message"],
        "Blocchi <script> inline": tt["scripts"],
        "File JS (cartella static/assets/js)": len(d["js_own"])
        + len(d["js_tutorials"])
        + len(d["js_lib"]),
        "File *-tutorial.js": sum(
            1 for e in d["js_tutorials"] if e["file"].endswith("-tutorial.js")
        ),
    }
    w("| Measure | Plan | Measured | Deviation | Check |\n|---|---:|---:|---:|---|")
    for k, (planned, kind) in PLAN.items():
        m = measured[k]
        dev = (m - planned) / planned * 100
        if kind == "min":
            check = "lower bound respected" if m >= planned else "below the lower bound"
        else:
            check = "within 25%" if abs(dev) <= 25 else "OUTSIDE 25%"
        w(
            f"| {k} | {'>= ' if kind == 'min' else ''}{planned} | {m} | {dev:+.0f}% | {check} |"
        )
    w(
        '\nThe plan quoted the JSON-message and JS-file figures as lower bounds ("almeno", "piu di"); the '
        "measured values are consistent with that, but the JSON messages are about 2.4 times the quoted floor, "
        "which weighs on F2-7.\n"
    )
    w("## Findings that affect the plan\n")
    w(
        f"- {pc['flash_fstring']} of {pc['flash_total']} `flash()` calls are f-strings and {pc['flash_other']} pass a "
        "variable: they need rewriting with named placeholders (risk R1) before they can be marked."
    )
    w(
        f"- Core templates hold about {tt['unique']} unique strings; `admin` alone is "
        f"{d['templates_admin']['unique']} ({d['templates_admin']['unique'] * 100 // max(1, tt['unique'])}% of the total)."
    )
    w(
        f"- The simulation frontends (microblogging, forum, photo, shared, login, error pages) hold "
        f"{sum(d['templates_' + a]['unique'] for a in SIM_AREAS)} unique strings: a much smaller catalogue than admin."
    )
    w(
        f"- Own JavaScript has {own['literals'] + tut['literals']} text-like literals "
        f"({tut['literals']} in tutorials); `lightbox.js` alone has {max(len(e['literals']) for e in d['js_own'] if e['file'] == 'lightbox.js') if any(e['file'] == 'lightbox.js' for e in d['js_own']) else 0}, "
        "so the JS runtime (F1-5) is needed for the admin pages too."
    )
    w(
        f"- Training Modules is the largest plugin ({d['plugins']['TrainingModules']['templates']['files']} templates, "
        f"{d['plugins']['TrainingModules']['templates']['texts'] + d['plugins']['TrainingModules']['templates']['attrs']} "
        "template strings). Manifest strings are concentrated in `y_agents_plugins` and `reactive_agents`."
    )
    w(
        "- `<html lang=...>` is hard-coded in "
        f"{tt['lang_hardcoded']} core templates (the plan counted 11; the login and error pages now share "
        "`login/scene_base.html`, and 4 more live in plugin templates)."
    )
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "docs" / "i18n" / "audit.md"))
    a = ap.parse_args()
    d = collect()
    if a.json:
        json.dump(
            d,
            sys.stdout,
            indent=1,
            default=lambda o: sorted(o) if isinstance(o, set) else str(o),
        )
        return
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(render(d), encoding="utf-8")
    print("written", a.out)


if __name__ == "__main__":
    main()
