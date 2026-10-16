#!/usr/bin/env python3
"""Mark the user-visible string literals of inline <script> blocks in Jinja templates.

    mark_inline_js.py [--func T] [--dry] template.html ...

Inside a <script> block a literal such as 'Delete this run?' becomes
{{ T('Delete this run?')|tojson }}, which the server renders as a JS string in the
reader's language. Only sentence-like literals are touched (a capital letter followed by
words, or one capitalised word); object keys, comparisons and anything already inside a
Jinja tag are left alone. Review the diff: strings glued with + need a manual rewrite.
"""
import re
import sys

SCRIPT = re.compile(r"(<script\b(?![^>]*\bsrc=)[^>]*>)(.*?)(</script>)", re.S | re.I)
JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
LIT = re.compile(r"""(?<![\w$.\\'"])'((?:[^'\\\n]|\\.){3,})'""")
SENTENCE = re.compile(r"^[A-Z][a-z]+(?: [\w,.'’()%/&:+\-–—…!?]+)*[.!?…:]?$")
WORD = re.compile(r"^[A-Z][a-z]{3,}$")


def unescape(text):
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    return re.sub(r"\\(.)", lambda m: {"n": "\n"}.get(m.group(1), m.group(1)), text)


def jinja_literal(text):
    if "'" not in text:
        return "'" + text.replace("\\", "\\\\") + "'"
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def convert(body, func):
    masks = []

    def mask(m):
        masks.append(m.group(0))
        return "\x00%d\x00" % (len(masks) - 1)

    body = JINJA.sub(mask, body)
    out, last, count = [], 0, 0
    for m in LIT.finditer(body):
        text = unescape(m.group(1))
        if not (SENTENCE.match(text) and (" " in text or WORD.match(text)) or WORD.match(text)):
            continue
        if "{{" in text or "{%" in text or "\x00" in text:
            continue
        before, after = body[: m.start()], body[m.end():]
        if re.match(r"\s*:", after) or re.search(r"(===?|!==?)\s*$", before) or re.match(r"\s*(===?|!==?)", after):
            continue
        if re.search(r"\[\s*$", before) and re.match(r"\s*\]", after):
            continue
        out.append(body[last: m.start()])
        out.append("{{ %s(%s)|tojson }}" % (func, jinja_literal(text)))
        last = m.end()
        count += 1
    out.append(body[last:])
    result = "".join(out)
    return re.sub("\x00(\\d+)\x00", lambda m: masks[int(m.group(1))], result), count


def main(argv):
    func, dry, files = "T", False, []
    it = iter(argv)
    for a in it:
        if a == "--func":
            func = next(it)
        elif a == "--dry":
            dry = True
        else:
            files.append(a)
    total = 0
    for path in files:
        src = open(path, encoding="utf-8").read()
        n = 0

        def repl(m):
            nonlocal n
            body, c = convert(m.group(2), func)
            n += c
            return m.group(1) + body + m.group(3)

        new = SCRIPT.sub(repl, src)
        if n and not dry:
            open(path, "w", encoding="utf-8").write(new)
        print(path, n)
        total += n
    print("total", total)


if __name__ == "__main__":
    main(sys.argv[1:])
