"""Icons for forum communities (Material Design Icons, shown in the round avatars next to community names).

Each community gets an icon from its name when a keyword matches (``linux`` -> the Linux logo), otherwise one from a
pool picked by a stable hash. Assignment goes over the sorted list of known communities and skips icons already
taken, so two communities share an icon only when there are more communities than icons.
"""

import zlib
from typing import Dict, Iterable

DEFAULT_ICON = "mdi-forum-outline"

# keyword (substring of the community name) -> icon
KEYWORD_ICONS = (
    ("linux", "mdi-linux"),
    ("ubuntu", "mdi-ubuntu"),
    ("windows", "mdi-microsoft-windows"),
    ("macos", "mdi-apple"),
    ("apple", "mdi-apple-finder"),
    ("android", "mdi-android"),
    ("python", "mdi-language-python"),
    ("javascript", "mdi-language-javascript"),
    ("programming", "mdi-code-braces"),
    ("coding", "mdi-code-tags"),
    ("security", "mdi-shield-lock-outline"),
    ("hardware", "mdi-memory"),
    ("gaming", "mdi-gamepad-variant-outline"),
    ("game", "mdi-controller-classic-outline"),
    ("music", "mdi-music-note"),
    ("movie", "mdi-movie-open-outline"),
    ("film", "mdi-filmstrip"),
    ("tv", "mdi-television-classic"),
    ("sport", "mdi-trophy-outline"),
    ("football", "mdi-soccer"),
    ("soccer", "mdi-soccer"),
    ("basket", "mdi-basketball"),
    ("travel", "mdi-airplane"),
    ("food", "mdi-silverware-fork-knife"),
    ("cook", "mdi-chef-hat"),
    ("science", "mdi-flask-outline"),
    ("space", "mdi-rocket-launch-outline"),
    ("physics", "mdi-atom"),
    ("health", "mdi-heart-pulse"),
    ("fitness", "mdi-dumbbell"),
    ("politic", "mdi-gavel"),
    ("news", "mdi-newspaper-variant-outline"),
    ("econom", "mdi-chart-line"),
    ("financ", "mdi-bank-outline"),
    ("money", "mdi-cash-multiple"),
    ("crypto", "mdi-bitcoin"),
    ("tech", "mdi-chip"),
    ("ai", "mdi-robot-outline"),
    ("art", "mdi-palette-outline"),
    ("photo", "mdi-camera-outline"),
    ("book", "mdi-book-open-variant"),
    ("school", "mdi-school-outline"),
    ("academia", "mdi-school-outline"),
    ("education", "mdi-human-male-board"),
    ("pet", "mdi-paw"),
    ("animal", "mdi-paw"),
    ("nature", "mdi-leaf"),
    ("environment", "mdi-earth"),
    ("climate", "mdi-weather-partly-cloudy"),
    ("car", "mdi-car-outline"),
    ("humor", "mdi-emoticon-happy-outline"),
    ("meme", "mdi-emoticon-cool-outline"),
    ("fashion", "mdi-hanger"),
    ("work", "mdi-briefcase-outline"),
    ("career", "mdi-briefcase-account-outline"),
)

# generic pool for the other communities
ICON_POOL = (
    "mdi-comment-text-multiple-outline", "mdi-lightbulb-on-outline", "mdi-star-outline", "mdi-fire",
    "mdi-compass-outline", "mdi-puzzle-outline", "mdi-telescope", "mdi-microscope", "mdi-dna",
    "mdi-hammer-wrench", "mdi-server-network", "mdi-database-outline", "mdi-cloud-outline", "mdi-lan",
    "mdi-console-line", "mdi-monitor", "mdi-cellphone", "mdi-headphones", "mdi-bike", "mdi-hiking",
    "mdi-train", "mdi-sail-boat", "mdi-tree-outline", "mdi-flower-outline", "mdi-coffee-outline",
    "mdi-glass-cocktail", "mdi-guitar-electric", "mdi-theater", "mdi-palette-swatch-outline", "mdi-pencil-outline",
    "mdi-map-marker-outline", "mdi-scale-balance", "mdi-flag-outline", "mdi-handshake-outline", "mdi-account-group-outline",
    "mdi-history", "mdi-diamond-stone", "mdi-anchor", "mdi-bell-outline", "mdi-key-outline",
    "mdi-magnet", "mdi-medal-outline", "mdi-owl", "mdi-pine-tree", "mdi-snowflake",
    "mdi-umbrella-outline", "mdi-wrench-outline", "mdi-clock-outline", "mdi-cube-outline", "mdi-hexagon-multiple-outline",
)


def _stable_hash(text: str) -> int:
    return zlib.crc32(text.encode("utf-8"))


def assign_icons(slugs: Iterable[str]) -> Dict[str, str]:
    """Return ``{slug: mdi-icon}`` for every slug, avoiding repeated icons while the pool allows it."""
    names = sorted({str(s).strip().lower() for s in slugs if str(s).strip()})
    taken = set()
    result: Dict[str, str] = {}
    for name in names:
        icon = next(
            (i for key, i in KEYWORD_ICONS if key in name and i not in taken), None
        )
        if icon is None:
            start = _stable_hash(name) % len(ICON_POOL)
            for step in range(len(ICON_POOL)):
                candidate = ICON_POOL[(start + step) % len(ICON_POOL)]
                if candidate not in taken:
                    icon = candidate
                    break
            else:  # more communities than icons: reuse deterministically
                icon = ICON_POOL[start]
        taken.add(icon)
        result[name] = icon
    return result


def icon_for(slug: str, icons: Dict[str, str]) -> str:
    return icons.get(str(slug or "").strip().lower(), DEFAULT_ICON)
