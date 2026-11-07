"""The header image of a plugin's README, shown on the plugin page.

Only an image that lives inside the plugin is used (``docs/banner.png`` and the like): absolute addresses, badges and
anything that leaves the plugin are ignored. An installed plugin always gives its image from its own folder; only a
plugin that is not installed is asked to GitHub (by the server, never by the browser, with the session's token).
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


def _local_sources(text: str):
    """``(relative path, alt)`` of the images of a README that point inside the plugin, in document order."""
    for _pos, src, alt in sorted(_candidates(text), key=lambda c: c[0]):
        src = html.unescape(src).strip().split("#", 1)[0].split("?", 1)[0]
        if not src or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//|^/", src):
            continue  # absolute address, data: URI ...: never fetched
        parts = []
        for part in src.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if not parts:
                    parts = None
                    break
                parts.pop()
                continue
            parts.append(part)
        if not parts or Path(parts[-1]).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        yield "/".join(parts), html.unescape(alt).strip()


def find_banner(folder) -> Optional[Tuple[Path, str]]:
    """``(file, alt)`` of the first local image of the README of *folder*, or None."""
    try:
        base = Path(folder).resolve()
        readme = _readme(base)
        if readme is None:
            return None
        text = readme.read_text(encoding="utf-8", errors="replace")
        for rel, alt in _local_sources(text):
            path = (base / rel).resolve()
            if (
                base in path.parents
                and path.is_file()
                and path.stat().st_size <= _SIZE_LIMIT
            ):
                return path, alt
    except (OSError, ValueError):
        return None
    return None


MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def fetch_remote_banner(spec, github_token=None) -> Optional[Tuple[bytes, str, str]]:
    """``(bytes, mimetype, alt)`` of the header image of the README on GitHub, for a plugin that is not installed.

    Two small API requests (the README, then the image); any failure gives None and the page shows no image.
    The answer is cached for a few minutes with the other remote lookups.
    """
    import requests

    from y_web.src.external_runtime import manager

    def _get(url):
        headers = manager._github_api_headers(github_token)
        headers["Accept"] = "application/vnd.github.raw+json"
        response = requests.get(url, headers=headers, timeout=manager._GITHUB_TIMEOUT)
        response.raise_for_status()
        return response

    def _lookup():
        try:
            readme = _get(f"https://api.github.com/repos/{spec.github_repo}/readme")
            for rel, alt in _local_sources(readme.text):
                image = _get(
                    f"https://api.github.com/repos/{spec.github_repo}/contents/{rel}"
                )
                data = image.content
                if len(data) <= _SIZE_LIMIT:
                    return (data, MIME[Path(rel).suffix.lower()], alt), None
        except (requests.RequestException, ValueError, KeyError) as exc:
            return None, str(exc)
        return None, "no image in the README"

    return manager._remote_cached(
        "banner", spec, "", github_token, _lookup, ttl_ok=600.0
    )[0]
