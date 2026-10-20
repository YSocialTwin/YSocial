"""Canonical form of hashtags, shared by every YSocial component (keep the copies identical).

A hashtag is stored WITHOUT the leading ``#``; the ``#`` is added when it is shown. Letters (accented ones
included), digits and ``_`` belong to a hashtag, and so do apostrophes between two such characters
(``#c'e`` ``#c’èdavvero``), so a tag is no longer cut at the first apostrophe. Texts are Unicode
NFC. Two tags that differ only in case or in a leading ``#`` are the same hashtag: look them up with
:func:`hashtag_key`; the first spelling stored is the one shown.
"""

import re
import unicodedata

APOSTROPHES = "'’ʼ"
# '#' followed by word characters, joined by single apostrophes (no trailing apostrophe)
HASHTAG_PATTERN = r"#\w+(?:['’ʼ]\w+)*"
_HASHTAG = re.compile(HASHTAG_PATTERN)


def normalize_hashtag(tag):
    """``tag`` as it is stored: no leading ``#``, NFC, no surrounding spaces or apostrophes; ``""`` if nothing is left."""
    if tag is None:
        return ""
    text = unicodedata.normalize("NFC", str(tag)).strip().lstrip("#").strip()
    text = text.strip(APOSTROPHES + " ")
    return text if re.fullmatch(r"\w+(?:['’ʼ]\w+)*", text) else _first_word(text)


def _first_word(text):
    """A tag that still holds separators (``a-b``, ``a b``) keeps its first run, as a regex scan would."""
    match = re.match(r"\w+(?:['’ʼ]\w+)*", text)
    return match.group(0) if match else ""


def hashtag_key(tag):
    """The identity of a hashtag: normalized and case-folded."""
    return normalize_hashtag(tag).casefold()


def extract_hashtags(text):
    """The hashtags written in ``text``, normalized, in order of appearance, without duplicates."""
    seen, out = set(), []
    for match in _HASHTAG.findall(unicodedata.normalize("NFC", text or "")):
        tag = normalize_hashtag(match)
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            out.append(tag)
    return out
