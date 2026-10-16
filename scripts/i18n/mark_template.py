"""Mark plain user-visible strings in Jinja templates with ``_()``.

    python scripts/i18n/mark_template.py y_web/templates/admin/head.html [more files]

Only the unambiguous cases are rewritten: an element whose whole text is a literal
string (``<span>Home</span>``) and the attributes title/placeholder/aria-label/alt/
value-less labels (``title="Close"``). Text mixed with Jinja expressions, fragments
split by inline tags and anything else are left alone and reported, so they can be
handled by hand (named placeholders, ``{% trans %}`` blocks...).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_strings import JINJA, TextCollector, read  # noqa: E402
from scan_unmarked import load_exceptions  # noqa: E402

INLINE = r"(?:a|b|strong|em|code|u|small|kbd)"
INLINE_CLOSE = re.compile(r"^</%s\s*>$" % INLINE, re.I)
INLINE_OPEN = re.compile(r"<%s[\s>]" % INLINE, re.I)
ATTRS = ("title", "placeholder", "aria-label", "alt", "label", "data-tooltip", "data-title")


def quote(text):
    if "'" not in text:
        return "_('%s')" % text
    return '_("%s")' % text.replace('"', '\\"')


def mark(path, exceptions):
    src = Path(path).read_text(encoding="utf-8")
    collector = TextCollector()
    collector.feed(JINJA.sub("", src))
    found = {t for t in collector.texts + collector.attrs if t not in exceptions}
    out = src
    done = set()
    for text in sorted(found, key=len, reverse=True):
        if "\n" in text or "data-cascade" in text:
            continue
        esc = r"\s+".join(re.escape(w) for w in text.split(" "))
        pat_text = re.compile(r"(<[^<>]*>)(\s*)" + esc + r"(\s*)(?=<)")

        def repl(m, text=text, snapshot=out):
            before = m.group(1)
            after = snapshot[m.end():m.end() + 40]
            continues = not text[0].isupper()  # sentence goes on after the tag
            if (INLINE_CLOSE.search(before) and continues) or INLINE_OPEN.match(after):
                return m.group(0)  # sentence fragment next to inline markup
            return "%s%s{{ %s }}%s" % (before, m.group(2), quote(text), m.group(3))

        out, n = pat_text.subn(repl, out)
        for attr in ATTRS:
            pat = re.compile(r'(\s%s=)"%s"' % (attr, esc))
            out, k = pat.subn(lambda m: '%s"{{ %s }}"' % (m.group(1), quote(text).replace('"', "'") if "'" not in text else quote(text).replace('"', "&quot;")), out)
            n += k
        if n:
            done.add(text)
    if out != src:
        Path(path).write_text(out, encoding="utf-8")
    return done, sorted(found - done)


def main(argv):
    ex = load_exceptions()
    for p in argv:
        done, left = mark(p, ex)
        print("%s: marked %d, left %d" % (p, len(done), len(left)))
        for t in left:
            print("   left:", repr(t)[:100])


if __name__ == "__main__":
    main(sys.argv[1:])
