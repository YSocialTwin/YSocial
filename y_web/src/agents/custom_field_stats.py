"""Statistics on the custom fields of the agents of a population, in blocks ordered by coherent groups.

The agents of any population can carry fields that only some platform reads: the appearance (``appearance.*`` or
``dating.appearance.*``), the Dating fields (``dating.profile.*``, ``dating.latent.*``, ``dating.affective_traits.*``,
the rest of ``dating.*``), the Photo Sharing extensions (``Agent_Ext``) and any other custom feature a person added.
:func:`collect` returns them as groups (title, badge, blocks); each block describes one field with how many agents
have it and either the counts per value (categorical, flag) or a histogram with summary statistics (numeric), ready
for the Chart.js cards of the population details page.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from y_web.i18n import N_

MAX_CATEGORIES = (
    12  # more distinct values than this: the most frequent ones and "other"
)
BINS = 10
MAX_LABEL = 40

# (group id, title, badge): the order of the page
GROUPS: List[Tuple[str, str, Optional[str]]] = [
    ("appearance", N_("Appearance"), None),
    ("dating_profile", N_("Dating profile"), "dating"),
    ("dating_latent", N_("Latent variables"), "dating"),
    ("dating_affective", N_("Affective traits"), "dating"),
    ("dating_other", N_("Other Dating fields"), "dating"),
    ("photo_sharing", N_("Photo Sharing"), "photo"),
    ("other", N_("Other custom fields"), None),
]
_TITLES = {gid: (title, badge) for gid, title, badge in GROUPS}

# readable names of the fields that carry a name of their own
FIELD_LABELS = {
    "creator_tier": N_("Creator tier"),
    "story_visibility": N_("Story visibility"),
    "is_private": N_("Private account"),
    "is_verified": N_("Verified account"),
    "attention_budget": N_("Attention budget"),
    "favorite_filters": N_("Favourite filters"),
    "bio": N_("Has a biography"),
}
PHOTO_FIELDS = tuple(FIELD_LABELS)
_BLOBS = {"photos": N_("Photos per agent")}
# readable names of the fields of the Appearance, the latent variables and the affective traits (as in the form)
NAME_LABELS = {
    "hair_color": N_("Hair colour"), "hair_length": N_("Hair length"), "hair_style": N_("Hair style"),
    "eye_color": N_("Eye colour"), "skin_tone": N_("Skin tone"), "build": N_("Build"),
    "facial_hair": N_("Facial hair"), "distinctive_features": N_("Distinctive features"),
    "mood": N_("Mood in photos"), "photo_style": N_("Photo style"), "height_cm": N_("Height (cm)"),
    "glasses": N_("Wearing glasses"), "attractiveness": N_("Attractiveness"), "selectivity": N_("Selectivity"),
    "responsiveness": N_("Responsiveness"), "sensitivity": N_("Sensitivity"),
    "reward_sensitivity": N_("Reward sensitivity"), "resilience": N_("Resilience"),
    "visibility_need": N_("Need for visibility"),
}  # fmt: skip
_LABELLED = ("appearance", "dating_latent", "dating_affective")
_FLAGS = {"true", "false"}


def classify(key: str) -> Tuple[str, str]:
    """(group id, name of the field inside the group) of a custom feature key."""
    if key.startswith("appearance."):
        return "appearance", key[len("appearance.") :]
    if key.startswith("dating.appearance."):
        return "appearance", key[len("dating.appearance.") :]
    for prefix, gid in (
        ("dating.profile.", "dating_profile"),
        ("dating.latent.", "dating_latent"),
        ("dating.affective_traits.", "dating_affective"),
    ):
        if key.startswith(prefix):
            return gid, key[len(prefix) :]
    if key.startswith("dating."):
        return "dating_other", key[len("dating.") :]
    return "other", key


def _parse(raw: Any):
    """A stored value as a number, a flag or a string; lists and objects as their JSON."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    low = text.lower()
    if low in _FLAGS:
        return low == "true"
    try:
        number = float(text)
        if math.isfinite(number):
            return number
    except ValueError:
        pass
    return text


def _short(label: Any) -> str:
    text = str(label)
    return text if len(text) <= MAX_LABEL else text[: MAX_LABEL - 1] + "…"


def _numeric_block(values: List[float]) -> Dict[str, Any]:
    low, high = min(values), max(values)
    whole = all(float(v).is_integer() for v in values)
    if low == high:
        edges = [low, low]
        counts = [len(values)]
        labels = [f"{low:g}"]
    else:
        bins = min(BINS, int(high - low) + 1) if whole else BINS
        width = (high - low) / bins
        edges = [low + i * width for i in range(bins + 1)]
        counts = [0] * bins
        for v in values:
            counts[min(int((v - low) / width), bins - 1)] += 1
        if whole and width == 1:
            labels = [f"{int(edges[i])}" for i in range(bins)]
        else:
            labels = [f"{edges[i]:.3g}–{edges[i + 1]:.3g}" for i in range(bins)]
    return {
        "kind": "numeric",
        "labels": labels,
        "data": counts,
        "summary": {
            "min": round(low, 4),
            "max": round(high, 4),
            "mean": round(statistics.fmean(values), 4),
            "median": round(statistics.median(values), 4),
            "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        },
    }


def _categorical_block(values: List[Any], flag: bool = False) -> Dict[str, Any]:
    counter = Counter(("yes" if v else "no") if flag else str(v) for v in values)
    ranked = counter.most_common()
    if len(ranked) > MAX_CATEGORIES:
        head, tail = ranked[: MAX_CATEGORIES - 1], ranked[MAX_CATEGORIES - 1 :]
        ranked = head + [("…", sum(c for _v, c in tail))]
    return {
        "kind": "flag" if flag else "categorical",
        "labels": [_short(v) for v, _c in ranked],
        "data": [c for _v, c in ranked],
        "distinct": len(counter),
        "top": ranked[0][0] if ranked else None,
    }


def describe(
    name: str, values: List[Any], total: int, title: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """The block of one field: ``values`` are the parsed values of the agents that have it (``None`` skipped)."""
    values = [v for v in values if v is not None]
    if not values:
        return None
    if all(isinstance(v, bool) for v in values):
        block = _categorical_block(values, flag=True)
    elif all(isinstance(v, float) for v in values):
        block = _numeric_block(values)
    else:
        block = _categorical_block(
            [("yes" if v else "no") if isinstance(v, bool) else v for v in values]
        )
    block.update(
        {
            "key": name,
            "title": title or name.replace("_", " ").replace(".", " · ").capitalize(),
            "n": len(values),
            "total": total,
            "coverage": round(100 * len(values) / total) if total else 0,
        }
    )
    return block


def _list_values(raw: Any) -> Optional[List[str]]:
    """Items of a stored list (JSON array or comma separated), ``None`` when the value is not a list."""
    text = str(raw or "").strip()
    if text.startswith("["):
        try:
            loaded = json.loads(text)
            return [str(i) for i in loaded] if isinstance(loaded, list) else None
        except ValueError:
            return None
    return None


def build(
    custom: Dict[str, Dict[int, Any]], ext: Dict[str, Dict[int, Any]], total: int
) -> List[Dict[str, Any]]:
    """Groups from ``custom`` (``{key: {agent id: raw value}}``) and ``ext`` (the same for the Photo Sharing extensions)."""
    grouped: Dict[str, List[Dict[str, Any]]] = {gid: [] for gid, _t, _b in GROUPS}
    seen_appearance: Dict[str, Dict[int, Any]] = {}
    for key in sorted(custom):
        gid, name = classify(key)
        if (
            gid == "appearance"
        ):  # the generic traits win over the Dating ones of the same agent
            merged = seen_appearance.setdefault(name, {})
            for agent_id, raw in custom[key].items():
                if key.startswith("appearance.") or agent_id not in merged:
                    merged[agent_id] = raw
            continue
        if gid == "dating_other" and name in _BLOBS:
            counts = []
            for raw in custom[key].values():
                try:
                    loaded = json.loads(raw)
                    counts.append(
                        float(len(loaded)) if isinstance(loaded, list) else None
                    )
                except (TypeError, ValueError):
                    counts.append(None)
            block = describe(name, counts, total, title=_BLOBS[name])
        else:
            lists = [_list_values(r) for r in custom[key].values()]
            if lists and all(i is not None for i in lists):
                block = describe(
                    name, [item for items in lists for item in items], total
                )
                if block:
                    block["n"] = len(lists)
                    block["coverage"] = round(100 * len(lists) / total) if total else 0
            else:
                block = describe(
                    name,
                    [_parse(r) for r in custom[key].values()],
                    total,
                    title=NAME_LABELS.get(name) if gid in _LABELLED else None,
                )
        if block:
            if gid == "other" and "." in key:
                block["title"] = key.replace("_", " ").replace(".", " · ")
            grouped[gid].append(block)
    for name in sorted(seen_appearance):
        block = describe(
            name,
            [_parse(r) for r in seen_appearance[name].values()],
            total,
            title=NAME_LABELS.get(name),
        )
        if block:
            grouped["appearance"].append(block)
    for name in PHOTO_FIELDS:
        if name not in ext:
            continue
        raws = ext[name]
        if name == "bio":
            block = describe(
                name,
                [bool(str(r or "").strip()) for r in raws.values()],
                total,
                title=FIELD_LABELS[name],
            )
        else:
            lists = [_list_values(r) for r in raws.values()]
            if lists and all(i is not None for i in lists):
                block = describe(
                    name,
                    [i for items in lists for i in items],
                    total,
                    title=FIELD_LABELS[name],
                )
                if block:
                    block["n"], block["coverage"] = len(lists), (
                        round(100 * len(lists) / total) if total else 0
                    )
            else:
                block = describe(
                    name,
                    [_parse(r) for r in raws.values()],
                    total,
                    title=FIELD_LABELS[name],
                )
        if block:
            grouped["photo_sharing"].append(block)
    out = []
    for gid, title, badge in GROUPS:
        blocks = grouped[gid]
        if blocks:
            out.append(
                {
                    "id": gid,
                    "title": title,
                    "badge": badge,
                    "blocks": blocks,
                    "count": len(blocks),
                }
            )
    return out


def collect(agent_ids: Iterable[int]) -> List[Dict[str, Any]]:
    """Groups of statistics of the custom fields of the agents (empty when none has any)."""
    from sqlalchemy import select

    from y_web import db
    from y_web.src.models import Agent_Custom_Feature, Agent_Ext

    ids = [int(i) for i in agent_ids]
    if not ids:
        return []
    custom: Dict[str, Dict[int, Any]] = {}
    ext: Dict[str, Dict[int, Any]] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        for agent_id, key, value in db.session.execute(
            select(
                Agent_Custom_Feature.agent_id,
                Agent_Custom_Feature.key,
                Agent_Custom_Feature.value,
            ).where(
                Agent_Custom_Feature.agent_id.in_(chunk),
                Agent_Custom_Feature.feature_type == "custom",
            )
        ):
            custom.setdefault(key, {})[agent_id] = value
        for agent_id, name, value in db.session.execute(
            select(
                Agent_Ext.agent_id, Agent_Ext.feature_name, Agent_Ext.feature_value
            ).where(
                Agent_Ext.agent_id.in_(chunk), Agent_Ext.feature_name.in_(PHOTO_FIELDS)
            )
        ):
            ext.setdefault(name, {})[agent_id] = value
    return build(custom, ext, len(ids))


_LONG = 140  # longer texts are shown as a paragraph
_UNIT_FIELDS = (
    "dating_latent",
    "dating_affective",
)  # values in 0..1 are drawn as a bar


def _pretty(name: str) -> str:
    return name.replace("_", " ").replace(".", " · ").capitalize()


def _field(
    name: str, raw: Any, label: Optional[str] = None, unit: bool = False
) -> Optional[Dict[str, Any]]:
    """One field of one agent: ``kind`` is text, flag, number, bar (0..1), chips or long."""
    if raw is None or str(raw).strip() == "":
        return None
    entry: Dict[str, Any] = {"name": name, "label": label or _pretty(name)}
    items = _list_values(raw)
    if items is not None:
        if not items:
            return None
        entry.update(kind="chips", tags=items)
        return entry
    value = _parse(raw)
    if isinstance(value, bool):
        entry.update(kind="flag", value=value)
    elif isinstance(value, float):
        shown = f"{value:g}"
        if unit and 0.0 <= value <= 1.0:
            entry.update(kind="bar", value=shown, pct=round(value * 100))
        else:
            entry.update(kind="number", value=shown)
    else:
        text = str(value)
        entry.update(kind="long" if len(text) > _LONG else "text", value=text)
    return entry


def agent_groups(custom: Dict[str, Any], ext: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The custom attributes of one agent in the ordered groups of the population statistics.

    ``custom`` is ``{key: value}`` of its custom features and ``ext`` the same for its Photo Sharing extensions; the
    result is ``[{id, title, badge, fields}]`` for the groups that have something to show.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {gid: [] for gid, _t, _b in GROUPS}
    appearance: Dict[str, Any] = {}
    for key in sorted(custom):
        gid, name = classify(key)
        if gid == "appearance":  # the generic traits win over the Dating ones
            if key.startswith("appearance.") or name not in appearance:
                appearance[name] = custom[key]
            continue
        if gid == "dating_other" and name in _BLOBS:
            try:
                loaded = json.loads(custom[key])
                count = len(loaded) if isinstance(loaded, list) else None
            except (TypeError, ValueError):
                count = None
            entry = (
                _field(name, count, _BLOBS[name])
                if count is not None
                else _field(name, custom[key])
            )
        else:
            entry = _field(
                name,
                custom[key],
                NAME_LABELS.get(name) if gid in _LABELLED else None,
                unit=gid in _UNIT_FIELDS,
            )
        if entry:
            grouped[gid].append(entry)
    for name in sorted(appearance):
        entry = _field(name, appearance[name], NAME_LABELS.get(name))
        if entry:
            grouped["appearance"].append(entry)
    for name in PHOTO_FIELDS:
        if name in ext:
            entry = _field(name, ext[name], FIELD_LABELS[name])
            if entry:
                grouped["photo_sharing"].append(entry)
    return [
        {"id": gid, "title": title, "badge": badge, "fields": grouped[gid]}
        for gid, title, badge in GROUPS
        if grouped[gid]
    ]
