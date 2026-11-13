"""The Appearance section shared by the population and agent forms of every platform.

Its traits (``appearance.*`` custom features) feed the profile pictures and any platform that shows people; the
schema and the way a form is read are therefore the core's, not a platform's.
"""

import json
from typing import Any, Dict, List, Optional, Tuple


def N_(message):
    """Marks a message for translation; the text is translated where it is shown."""
    return message


# appearance attributes drawn from label weights (same names as the population schema)
APPEARANCE_LABELS = (
    "hair_color",
    "hair_length",
    "hair_style",
    "eye_color",
    "skin_tone",
    "build",
    "facial_hair",
    "distinctive_features",
    "mood",
    "photo_style",
)
APPEARANCE_DEFAULTS: Dict[str, Dict[str, int]] = {
    "hair_color": {"black": 30, "brown": 40, "blond": 20, "red": 5, "gray": 5},
    "hair_length": {"short": 35, "medium": 40, "long": 25},
    "hair_style": {"straight": 50, "wavy": 30, "curly": 20},
    "eye_color": {"brown": 55, "blue": 20, "green": 10, "hazel": 15},
    "skin_tone": {"light": 40, "medium": 30, "tan": 20, "dark": 10},
    "build": {"slim": 30, "average": 40, "athletic": 25, "curvy": 5},
    "mood": {"smiling": 50, "relaxed": 30, "serious": 20},
    "photo_style": {"casual": 60, "outdoor": 25, "professional": 15},
    # optional: not assigned unless the person picks them
    "facial_hair": {},
    "distinctive_features": {},
}
APPEARANCE_OPTIONS: Dict[str, List[str]] = {
    **{k: list(v) for k, v in APPEARANCE_DEFAULTS.items()},
    "facial_hair": ["clean-shaven", "stubble", "beard", "moustache"],
    "distinctive_features": ["freckles", "dimples", "tattoo", "birthmark"],
}
HEIGHT_DEFAULT_RANGE = (155, 195)
GLASSES_DEFAULT_PERCENT = 20

# Small text-to-image models of the Hugging Face hub that the image generator runs as they are (downloaded on first use); any
# other diffusers id can be typed. Sizes are the approximate weights of the model files.
DIFFUSION_MODELS: List[Tuple[str, str]] = [
    ("segmind/tiny-sd", N_("tiny-sd: the smallest, fastest (about 1 GB). Default")),
    (
        "nota-ai/bk-sdm-tiny",
        N_("bk-sdm-tiny: compact Stable Diffusion, similar size (about 1 GB)"),
    ),
    (
        "nota-ai/bk-sdm-small",
        N_("bk-sdm-small: a little larger, better detail (about 1.4 GB)"),
    ),
    (
        "stabilityai/sd-turbo",
        N_(
            "sd-turbo: distilled, 1 to 4 steps, best quality for the time (about 2.6 GB)"
        ),
    ),
]


class AppearanceFormError(ValueError):
    """A value of the form is not valid (``problems`` carry the reasons)."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def number(raw: Any, field: str, kind=float, low=None, high=None):
    """``raw`` as a number of ``kind`` between ``low`` and ``high``; ``None`` when empty."""
    text = str(raw if raw is not None else "").strip()
    if text == "":
        return None
    try:
        value = kind(text)
    except ValueError:
        raise AppearanceFormError([f"{field}: must be a number"]) from None
    if (low is not None and value < low) or (high is not None and value > high):
        raise AppearanceFormError([f"{field}: must be between {low} and {high}"])
    return value


def pair(form, field: str, kind=float, low=None, high=None):
    """The range ``[<field>_min, <field>_max]`` of a form (both empty = not given; one empty = error)."""
    lo = number(form.get(f"{field}_min"), f"{field}_min", kind, low, high)
    hi = number(form.get(f"{field}_max"), f"{field}_max", kind, low, high)
    if lo is None and hi is None:
        return None
    if lo is None or hi is None:
        raise AppearanceFormError([f"{field}: give both the minimum and the maximum"])
    if lo > hi:
        raise AppearanceFormError([f"{field}: the minimum is greater than the maximum"])
    return [lo, hi]


def percentages(
    form, field: str, names: Optional[Dict[str, str]] = None
) -> Dict[str, float]:
    """The ``{label: percent}`` of a multi-select with percentages (``field`` carries the ids, ``field_percentages``
    the JSON ``{id: percent}``); the percentages must sum to 100. ``names`` maps an id to its label.
    """
    ids = [str(i).strip() for i in form.getlist(field) if str(i).strip()]
    if not ids:
        return {}
    try:
        raw = json.loads(form.get(f"{field}_percentages") or "{}")
    except (TypeError, ValueError):
        raw = {}
    out: Dict[str, float] = {}
    for i in ids:
        label = (names or {}).get(i, i)
        try:
            out[label] = float(raw.get(i, 0))
        except (TypeError, ValueError):
            raise AppearanceFormError(
                [f"{field}: invalid percentage for {i}"]
            ) from None
    if any(v < 0 for v in out.values()) or abs(sum(out.values()) - 100.0) > 0.05:
        raise AppearanceFormError([f"{field}: the percentages must sum to 100"])
    return out
