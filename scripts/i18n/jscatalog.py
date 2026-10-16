#!/usr/bin/env python3
"""Maintain browser-side catalogs whose keys are the English texts.

    jscatalog.py sync    <domain> <js files...>   # write en.json from YI18n.t('...') calls
    jscatalog.py missing <domain> <lang>          # list keys without a translation
    jscatalog.py check   <domain> <lang>          # placeholder consistency + missing count
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAT = ROOT / "y_web" / "translations" / "js"
CALL = re.compile(r"YI18n\.(?:t|tn)\(\s*'((?:\\.|[^'\\])*)'")
PH = re.compile(r"\{(\w+)\}")


def unescape(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n"}.get(m.group(1), m.group(1)), s)


def load(domain, lang):
    p = CAT / domain / f"{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def dump(domain, lang, data):
    p = CAT / domain / f"{lang}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv):
    cmd, domain = argv[0], argv[1]
    if cmd == "sync":
        keys = set(load(domain, "en"))
        for f in argv[2:]:
            keys |= {unescape(k) for k in CALL.findall(Path(f).read_text(encoding="utf-8"))}
        dump(domain, "en", {k: k for k in keys})
        print(len(keys), "keys")
    elif cmd in ("missing", "check"):
        lang = argv[2]
        en, tr = load(domain, "en"), load(domain, lang)
        miss = [k for k in en if k not in tr or (not isinstance(tr[k], dict) and tr[k] == "" )]
        bad = [k for k in en if k in tr and isinstance(tr[k], str) and set(PH.findall(k)) != set(PH.findall(tr[k]))]
        if cmd == "missing":
            for k in miss:
                print(json.dumps(k, ensure_ascii=False))
        else:
            print("missing", len(miss), "placeholder-mismatch", len(bad))
            for k in bad:
                print("  ", k)
            return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
