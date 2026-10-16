#!/usr/bin/env python3
"""Per-area, per-language translation coverage (gate G5).

    python scripts/i18n/coverage_report.py [--json] [--min 98]

Areas: core .po, every plugin .po, and every JS catalog directory (reference = en.json).
Exit status 1 when any area is below --min percent for a language.
"""
import argparse
import glob
import json
import sys
from pathlib import Path

from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parents[2]


def po_stats(path, locale):
    with path.open("rb") as fh:
        cat = read_po(fh, locale=locale)
    total = done = 0
    for m in cat:
        if not m.id:
            continue
        total += 1
        s = m.string if isinstance(m.string, (tuple, list)) else (m.string,)
        if all(s) and "fuzzy" not in m.flags:
            done += 1
    return done, total


def collect():
    rows = []
    for po in [ROOT / "y_web/translations"] + sorted(Path(p) for p in glob.glob(str(ROOT / "external/*/translations"))):
        for lang_dir in sorted(po.iterdir()) if po.is_dir() else []:
            files = list((lang_dir / "LC_MESSAGES").glob("*.po")) if (lang_dir / "LC_MESSAGES").is_dir() else []
            for f in files:
                area = "core" if po.parent.name == "y_web" else po.parent.name
                d, t = po_stats(f, lang_dir.name)
                rows.append((area + " (py/html)", lang_dir.name, d, t))
    for jsdir in [ROOT / "y_web/translations/js"] + sorted(Path(p) for p in glob.glob(str(ROOT / "external/*/translations/js"))):
        for dom in sorted(jsdir.iterdir()):
            ref = dom / "en.json"
            if not ref.is_file():
                continue
            keys = set(json.loads(ref.read_text(encoding="utf-8")))
            for f in sorted(dom.glob("[a-z]*.json")):
                lang = f.stem
                if lang == "en":
                    continue
                data = json.loads(f.read_text(encoding="utf-8"))
                done = sum(1 for k in keys if data.get(k))
                rows.append(("js:" + dom.name, lang, done, len(keys)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min", type=float, default=98.0)
    a = ap.parse_args()
    rows = collect()
    bad = 0
    out = []
    for area, lang, d, t in rows:
        pct = 100.0 * d / t if t else 100.0
        out.append({"area": area, "lang": lang, "translated": d, "total": t, "pct": round(pct, 2)})
        bad += pct < a.min
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        for r in out:
            flag = "" if r["pct"] >= a.min else "  <-- below %.0f%%" % a.min
            print("%-34s %-6s %5d/%-5d %6.2f%%%s" % (r["area"], r["lang"], r["translated"], r["total"], r["pct"], flag))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
