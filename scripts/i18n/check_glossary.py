#!/usr/bin/env python3
"""Check that the Italian catalogs use the approved glossary (docs/i18n/glossary.csv).

    python scripts/i18n/check_glossary.py            # report violations, exit 1 if any
    python scripts/i18n/check_glossary.py --list     # print the glossary

For every message whose English text contains a glossary term, the translation must not contain a
variant listed in ``forbid_it`` (a regular expression) unless it also uses the approved word.
Messages whose English text is a code-like token (``agent_ids``) are skipped.
"""

import csv
import glob
import re
import sys
from pathlib import Path

from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parents[2]


def load_glossary():
    with (ROOT / "docs" / "i18n" / "glossary.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def catalogs():
    files = [ROOT / "y_web/translations/it/LC_MESSAGES/messages.po"]
    files += sorted(
        Path(p)
        for p in glob.glob(str(ROOT / "external/*/translations/it/LC_MESSAGES/*.po"))
    )
    return [f for f in files if f.is_file()]


def check():
    terms = []
    for row in load_glossary():
        if row["forbid_it"]:
            terms.append(
                (
                    row,
                    re.compile(r"\b%ss?\b" % re.escape(row["en"]), re.I),
                    re.compile(row["forbid_it"], re.I),
                    re.compile(re.escape(row["it"]), re.I),
                )
            )
    problems = []
    for path in catalogs():
        with path.open("rb") as fh:
            catalog = read_po(fh, locale="it")
        for message in catalog:
            if not message.id:
                continue
            ids = message.id if isinstance(message.id, tuple) else (message.id,)
            strings = (
                message.string
                if isinstance(message.string, tuple)
                else (message.string,)
            )
            source, target = " ".join(ids), " ".join(s for s in strings if s)
            if not target or re.fullmatch(r"[\w.\-]+", source):
                continue
            for row, in_source, forbidden, approved in terms:
                if (
                    in_source.search(source)
                    and forbidden.search(target)
                    and not approved.search(target)
                ):
                    problems.append(
                        (
                            path.parent.parent.parent.parent.name,
                            row["en"],
                            source[:80],
                            target[:80],
                        )
                    )
    return problems


def main(argv):
    if argv[:1] == ["--list"]:
        for row in load_glossary():
            print("%-12s %-16s %s" % (row["en"], row["it"], row["note"]))
        return 0
    problems = check()
    for where, term, source, target in problems:
        print("%s [%s]: %r -> %r" % (where, term, source, target))
    print("glossary violations: %d" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
