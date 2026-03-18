"""Forum avatar helpers with a local deterministic fallback."""

from __future__ import annotations

import hashlib
import os
from urllib.parse import quote


def discover_forum_avatar_urls():
    """Return static forum avatar URLs when local avatar assets are available."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        avatars_dir = os.path.normpath(
            os.path.join(
                base_dir,
                "..",
                "static",
                "assets",
                "img",
                "reddit",
                "avatars",
            )
        )
        if not os.path.isdir(avatars_dir):
            return []
        files = [
            name
            for name in os.listdir(avatars_dir)
            if os.path.isfile(os.path.join(avatars_dir, name))
            and name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"))
            and not name.startswith(".")
        ]
        files.sort()
        return [f"/static/assets/img/reddit/avatars/{name}" for name in files]
    except Exception:
        return []


def _deterministic_color(username: str) -> str:
    palette = [
        "#0f766e",
        "#1d4ed8",
        "#7c3aed",
        "#b45309",
        "#be123c",
        "#047857",
        "#4338ca",
        "#92400e",
    ]
    digest = hashlib.sha256(str(username or "forum").encode("utf-8")).hexdigest()
    return palette[int(digest[:8], 16) % len(palette)]


def _initials(username: str) -> str:
    cleaned = " ".join(str(username or "").replace("_", " ").replace("-", " ").split()).strip()
    if not cleaned:
        return "?"
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[1][:1]).upper()


def _fallback_avatar_data_url(username: str) -> str:
    initials = _initials(username)
    color = _deterministic_color(username)
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='96' height='96' viewBox='0 0 96 96'>
      <rect width='96' height='96' rx='48' fill='{color}'/>
      <text x='48' y='55' text-anchor='middle' font-family='Arial, sans-serif' font-size='34' font-weight='700' fill='white'>{initials}</text>
    </svg>
    """.strip()
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def deterministic_forum_avatar_url(username: str) -> str:
    """Return a deterministic avatar URL for a forum username."""
    urls = discover_forum_avatar_urls()
    if urls:
        digest = hashlib.sha256(str(username or "forum").encode("utf-8")).hexdigest()
        return urls[int(digest[:8], 16) % len(urls)]
    return _fallback_avatar_data_url(username)
