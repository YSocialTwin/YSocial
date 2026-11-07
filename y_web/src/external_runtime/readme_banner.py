"""The header image of a plugin's README, shown on the plugin page.

Only an image that lives inside the plugin folder is used (``docs/banner.png`` and the like): absolute addresses,
badges and anything that leaves the folder are ignored, so the page never reaches out to another site and the file
that is served is always inside the plugin.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional, Tuple

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_HTML_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HTML_ATTR = re.compile(r"""\b(src|alt)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
_MD_IMG = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^)]*[\"'])?\s*\)")
_SIZE_LIMIT = 6 * 1024 * 1024


def _candidates(text: str):
    """(position, source, alt) of every image of the README, in document order."""
    for m in _HTML_IMG.finditer(text):
        attrs = {k.lower(): (a or b) for k, a, b in _HTML_ATTR.findall(m.group(0))}
        if attrs.get("src"):
            yield m.start(), attrs["src"], attrs.get("alt", "")
    for m in _MD_IMG.finditer(text):
        yield m.start(), m.group(2), m.group(1)


def _readme(folder: Path) -> Optional[Path]:
    for child in sorted(folder.iterdir()) if folder.is_dir() else ():
        if child.is_file() and child.name.lower() in ("readme.md", "readme.markdown"):
            return child
    return None


def find_banner(folder) -> Optional[Tuple[Path, str]]:
    """``(file, alt)`` of the first local image of the README of *folder*, or None."""
    try:
        base = Path(folder).resolve()
        readme = _readme(base)
        if readme is None:
            return None
        text = readme.read_text(encoding="utf-8", errors="replace")
        for _pos, src, alt in sorted(_candidates(text), key=lambda c: c[0]):
            src = html.unescape(src).strip().split("#", 1)[0].split("?", 1)[0]
            if not src or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//", src):
                continue  # absolute address, data: URI ...: never fetched
            path = (base / src).resolve()
            if (
                base not in path.parents
                or path.suffix.lower() not in IMAGE_EXTENSIONS
                or not path.is_file()
                or path.stat().st_size > _SIZE_LIMIT
            ):
                continue
            return path, html.unescape(alt).strip()
    except (OSError, ValueError):
        return None
    return None
