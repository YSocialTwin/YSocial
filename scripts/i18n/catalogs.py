#!/usr/bin/env python3
"""Catalog tooling for the core (gettext) and the pseudo-locale.

    python scripts/i18n/catalogs.py extract   # rewrite y_web/translations/messages.pot
    python scripts/i18n/catalogs.py update    # extract, then merge into every .po
    python scripts/i18n/catalogs.py compile   # .po -> .mo for every language
    python scripts/i18n/catalogs.py check     # fail if the committed .pot/.mo are stale
    python scripts/i18n/catalogs.py pseudo    # build the en-XA pseudo catalog (dev only)
    python scripts/i18n/catalogs.py manifests <plugin_dir> [--domain NAME]
                                              # extract plugin manifest strings to a .pot

Always run ``update`` and ``compile`` before committing a catalog change.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from babel.messages import Catalog  # noqa: E402
from babel.messages.mofile import read_mo, write_mo  # noqa: E402
from babel.messages.pofile import read_po, write_po  # noqa: E402

from y_web.i18n_pseudo import PSEUDO_CARRIER, pseudolocalize  # noqa: E402

TRANSLATIONS = ROOT / "y_web" / "translations"
POT = TRANSLATIONS / "messages.pot"
BABEL_CFG = ROOT / "babel.cfg"


def _pybabel(*args):
    result = subprocess.run(
        [sys.executable, "-m", "babel.messages.frontend", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(result.returncode)


def extract(output=POT):
    _pybabel(
        "extract",
        "-F",
        str(BABEL_CFG),
        "-o",
        str(output),
        "--project=YSocial",
        "--no-location",
        "--sort-output",
        "y_web",
    )


def languages():
    return sorted(
        p.name
        for p in TRANSLATIONS.iterdir()
        if (p / "LC_MESSAGES" / "messages.po").is_file() and p.name != PSEUDO_CARRIER
    )


def update():
    extract()
    for lang in languages():
        _pybabel(
            "update",
            "-i",
            str(POT),
            "-d",
            str(TRANSLATIONS),
            "-l",
            lang,
            "--no-fuzzy-matching",
        )


def compile_all():
    for lang in languages():
        _pybabel("compile", "-d", str(TRANSLATIONS), "-l", lang)


def _msgids(catalog):
    return {m.id for m in catalog if m.id}


def check():
    """Return a list of problems; empty means the catalogs are up to date."""
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "messages.pot"
        extract(fresh)
        fresh_ids = _msgids(read_po(fresh.open("rb")))
    committed_ids = _msgids(read_po(POT.open("rb"))) if POT.is_file() else set()
    if fresh_ids != committed_ids:
        problems.append(
            f"messages.pot is stale ({len(fresh_ids - committed_ids)} new, "
            f"{len(committed_ids - fresh_ids)} removed): run `catalogs.py update` and commit it"
        )
    for lang in languages():
        po = TRANSLATIONS / lang / "LC_MESSAGES" / "messages.po"
        mo = po.with_suffix(".mo")
        po_cat = read_po(po.open("rb"))
        missing = fresh_ids - _msgids(po_cat)
        if missing:
            problems.append(
                f"{lang}: {len(missing)} message(s) missing from the .po (run `update`)"
            )
        if not mo.is_file():
            problems.append(f"{lang}: messages.mo missing (run `compile`)")
            continue
        mo_translated = {_key(m): _norm(m.string) for m in read_mo(mo.open("rb")) if m.id}
        po_translated = {
            _key(m): _norm(m.string)
            for m in po_cat
            if m.id and any(m.string if isinstance(m.string, (list, tuple)) else [m.string])
            and not m.fuzzy
        }
        if mo_translated != po_translated:
            problems.append(
                f"{lang}: messages.mo is out of date with the .po (run `compile`)"
            )
    return problems


def _key(message):
    """Hashable id: plural messages carry a (singular, plural) pair."""
    return tuple(message.id) if isinstance(message.id, (list, tuple)) else message.id


def _norm(string):
    return tuple(string) if isinstance(string, (list, tuple)) else string


def pseudo():
    template = read_po(POT.open("rb"))
    catalog = Catalog(locale=None, project="YSocial", charset="utf-8")
    for message in template:
        if not message.id:
            continue
        if isinstance(message.id, tuple):
            singular, plural = message.id
            catalog.add(
                message.id,
                string=(pseudolocalize(singular), pseudolocalize(plural)),
            )
        else:
            catalog.add(message.id, string=pseudolocalize(message.id))
    out = TRANSLATIONS / PSEUDO_CARRIER / "LC_MESSAGES"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "messages.po").open("wb") as fh:
        write_po(fh, catalog)
    with (out / "messages.mo").open("wb") as fh:
        write_mo(fh, catalog)
    print(f"pseudo catalog: {len(catalog)} messages -> {out}")


def manifests(plugin_dir, domain=None):
    from manifest_extractor import extract_plugin_manifests

    plugin_dir = Path(plugin_dir).resolve()
    domain = domain or plugin_dir.name
    entries = extract_plugin_manifests(plugin_dir)
    catalog = Catalog(project=domain, charset="utf-8")
    for text, where in entries:
        catalog.add(text, locations=[(where, 0)], auto_comments=["manifest string"])
    out = plugin_dir / "translations"
    out.mkdir(exist_ok=True)
    target = out / f"{domain}.pot"
    with target.open("wb") as fh:
        write_po(fh, catalog, width=100, sort_output=True)
    print(f"{len(entries)} manifest strings -> {target}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("extract", "update", "compile", "check", "pseudo"):
        sub.add_parser(name)
    m = sub.add_parser("manifests")
    m.add_argument("plugin_dir")
    m.add_argument("--domain")
    args = parser.parse_args(argv)

    if args.cmd == "extract":
        extract()
    elif args.cmd == "update":
        update()
    elif args.cmd == "compile":
        compile_all()
    elif args.cmd == "pseudo":
        pseudo()
    elif args.cmd == "manifests":
        manifests(args.plugin_dir, args.domain)
    elif args.cmd == "check":
        problems = check()
        for problem in problems:
            print(f"i18n: {problem}")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
