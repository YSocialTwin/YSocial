"""Display label, icon and order of a platform type (``Exps.platform_type``).

The known platforms have a curated label and icon; any other type (a platform added later, or by a plugin) gets a label
derived from its name and a generic icon, and sorts after the known ones, so menus grouped by platform adapt on their own.
"""

from __future__ import annotations

from itertools import groupby
from typing import Any, Dict, Iterable, List

from y_web.i18n import N_, gettext

KNOWN_PLATFORMS: Dict[str, Dict[str, str]] = {
    "microblogging": {"label": N_("Microblogging"), "icon": "message-circle"},
    "forum": {"label": N_("Forum"), "icon": "message-square"},
    "photo_sharing": {"label": N_("Photo sharing"), "icon": "camera"},
    "instant_messaging": {"label": N_("Instant messaging"), "icon": "send"},
    "dating": {"label": N_("Dating"), "icon": "heart"},
}
DEFAULT_ICON = "layers"


def platform_label(platform_type: Any) -> str:
    """Human label of a platform type: the curated one, else the name with spaces and a capital ('video_chat' -> 'Video chat')."""
    key = str(platform_type or "").strip()
    if key in KNOWN_PLATFORMS:
        return gettext(KNOWN_PLATFORMS[key]["label"])
    text = key.replace("_", " ").replace("-", " ").strip()
    return (text[:1].upper() + text[1:]) if text else gettext("Other")


def platform_icon(platform_type: Any) -> str:
    return KNOWN_PLATFORMS.get(str(platform_type or "").strip(), {}).get(
        "icon", DEFAULT_ICON
    )


def group_experiments_by_platform(experiments: Iterable[Any]) -> List[Dict[str, Any]]:
    """``[{type, label, icon, experiments}]``: the experiments split by platform type, known platforms first (in their usual
    order), then the others by label; inside a group, by experiment name."""
    order = {key: i for i, key in enumerate(KNOWN_PLATFORMS)}

    def type_of(exp):
        return str(getattr(exp, "platform_type", "") or "").strip() or "microblogging"

    def group_key(exp):
        t = type_of(exp)
        return (order.get(t, len(order)), platform_label(t).lower(), t)

    ordered = sorted(
        experiments,
        key=lambda e: (group_key(e), str(getattr(e, "exp_name", "")).lower()),
    )
    return [
        {
            "type": key[2],
            "label": platform_label(key[2]),
            "icon": platform_icon(key[2]),
            "experiments": list(items),
        }
        for key, items in groupby(ordered, key=group_key)
    ]
