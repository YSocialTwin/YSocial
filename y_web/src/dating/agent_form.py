"""The dating fields of the agent form of the admin (decision D-10).

An agent created in ``admin/agents`` can carry the variables YDating needs (declared preferences, location, bio,
appearance, latent and affective variables, recommender, photos). They are stored like the rest of the dating
fields, as custom features of the namespace ``dating.`` (``y_web.src.dating.agent_fields``): the other platforms
never read them, and a dating experiment rebuilds the agent document from them. The module is pure (no Flask, no
database); the document it builds is validated against the YDating agent schema by
``y_web.src.dating.population.validate_agent_document``.
"""

from typing import Any, Dict, List, Tuple

from y_web.src.dating import agent_fields
from y_web.src.dating.population import (
    AFFECTIVE_TRAITS,
    APPEARANCE_LABELS,
    LATENT_VARIABLES,
    DatingPopulationError,
    _number,
)

FIELD_PREFIX = "dating_"
INTENTS = ("serious", "casual", "friendship", "unsure")


def _text(form, name: str) -> str:
    return str(form.get(FIELD_PREFIX + name) or "").strip()


def has_dating_fields(form) -> bool:
    """Whether the submitted form fills at least one dating field."""
    return any(
        str(value).strip()
        for key, value in form.items()
        if key.startswith(FIELD_PREFIX)
    )


def _lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def dating_fragment(form) -> Dict[str, Any]:
    """The dating part of the agent document described by the form (only the fields that are filled)."""
    doc: Dict[str, Any] = {}
    profile: Dict[str, Any] = {}
    seeking = [
        g.strip() for g in _text(form, "seeking_genders").split(",") if g.strip()
    ]
    if seeking:
        profile["seeking_genders"] = list(dict.fromkeys(seeking))
    for name, kind, low, high in (
        ("age_min", int, 18, 120),
        ("age_max", int, 18, 120),
        ("max_distance_km", float, 0, None),
        ("lat", float, -90, 90),
        ("lon", float, -180, 180),
    ):
        value = _number(form.get(FIELD_PREFIX + name), name, kind, low, high)
        if value is not None:
            profile[name] = value
    if (
        "age_min" in profile
        and "age_max" in profile
        and profile["age_min"] > profile["age_max"]
    ):
        raise DatingPopulationError(["age_min: is greater than age_max"])
    if _text(form, "city"):
        profile["city"] = _text(form, "city")
    intent = _text(form, "intent")
    if intent:
        if intent not in INTENTS:
            raise DatingPopulationError(
                [f"intent: must be one of {', '.join(INTENTS)}"]
            )
        profile["intent"] = intent
    if _text(form, "bio"):
        profile["bio"] = _text(form, "bio")
    answers = {}
    for line in _lines(_text(form, "prompt_answers")):
        question, colon, answer = line.partition(":")
        if not colon or not question.strip() or not answer.strip():
            raise DatingPopulationError(
                [f"prompt_answers: {line!r} is not 'question: answer'"]
            )
        answers[question.strip()] = answer.strip()
    if answers:
        profile["prompt_answers"] = answers
    if profile:
        doc["profile"] = profile
    latent = {}
    for name in LATENT_VARIABLES:
        value = _number(form.get(FIELD_PREFIX + "latent_" + name), name, float, 0, 1)
        if value is not None:
            latent[name] = value
    if latent:
        doc["latent"] = latent
    affective = {}
    for trait in AFFECTIVE_TRAITS:
        value = _number(form.get(FIELD_PREFIX + "affective_" + trait), trait, float, 0)
        if value is not None:
            affective[trait] = value
    if affective:
        doc["affective_traits"] = affective
    appearance: Dict[str, Any] = {}
    for key in APPEARANCE_LABELS:
        if _text(form, "appearance_" + key):
            appearance[key] = _text(form, "appearance_" + key)
    height = _number(
        form.get(FIELD_PREFIX + "appearance_height_cm"), "height_cm", int, 100, 250
    )
    if height is not None:
        appearance["height_cm"] = height
    glasses = _text(form, "appearance_glasses")
    if glasses in ("yes", "no"):
        appearance["glasses"] = glasses == "yes"
    elif glasses:
        raise DatingPopulationError(["glasses: must be yes or no"])
    if appearance:
        doc["appearance"] = appearance
    if _text(form, "match_recsys"):
        doc["match_recsys"] = _text(form, "match_recsys")
    photos = [{"caption": c} for c in _lines(_text(form, "photo_captions"))]
    if photos:
        doc["photos"] = photos
    return doc


def agent_document(form, base: Dict[str, Any]) -> Dict[str, Any]:
    """``base`` (the standard fields: username, age, gender ...) plus the dating fragment of the form."""
    doc = {k: v for k, v in base.items() if v not in (None, "")}
    doc.update(dating_fragment(form))
    return doc


def custom_entries(doc: Dict[str, Any]) -> List[Dict[str, str]]:
    """The ``custom`` feature entries (``dating.*``) of the dating part of an agent document."""
    fragment = {
        k: v
        for k, v in doc.items()
        if k in agent_fields.SECTIONS
        or k in agent_fields.SCALARS
        or k in agent_fields.BLOBS
    }
    _columns, _interests, custom = agent_fields.agent_to_rows(fragment)
    return [
        {"feature_type": "custom", "key": item["key"], "value": item["value"]}
        for item in custom
    ]


def entries_from_form(
    form, base: Dict[str, Any]
) -> Tuple[List[Dict[str, str]], List[str]]:
    """(custom feature entries, problems) of the dating fields of the form; no entries when none is filled."""
    from y_web.src.dating import population as dp

    if not has_dating_fields(form):
        return [], []
    try:
        doc = agent_document(form, base)
    except DatingPopulationError as exc:
        return [], exc.problems
    problems = dp.validate_agent_document(doc)
    if problems:
        return [], problems
    return custom_entries(doc), []
