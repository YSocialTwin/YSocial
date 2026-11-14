"""Dating fields of the ad hoc agent form: the ``dating.*`` custom features an agent built by hand can carry.

The module belongs to the dating platform and moves to its repository."""

from flask import request
from flask_login import current_user

from y_web.i18n import gettext as _
from y_web.platforms import registry
from y_web.src.agents import appearance_form as af


def _dating_runtime_available() -> bool:
    dp = registry.library_or_none("dating", "population")
    return dp is not None and dp.runtime_available(current_user)


def _with_dating_features(feature_entries: list[dict]) -> list[dict]:
    """Add the ``dating.*`` custom features described by the dating fields of the form (none when YDating is absent).

    The fields are ignored by every other platform; they let an ad hoc agent take part in a dating simulation.
    Raises ``ValueError`` (shown to the admin) when the filled fields do not satisfy the YDating agent schema.
    """
    agent_form = registry.library_or_none("dating", "agent_form")
    dp = registry.library_or_none("dating", "population")
    form = request.form
    if (
        dp is None
        or not dp.runtime_available(current_user)
        or not agent_form.has_dating_fields(form)
    ):
        return feature_entries
    if form.get(
        "include_appearance"
    ):  # the Appearance section feeds the Dating appearance too
        from werkzeug.datastructures import MultiDict

        form = MultiDict(form)
        for key in list(af.APPEARANCE_LABELS) + ["height_cm", "glasses"]:
            if form.get("appearance_" + key) and not form.get(
                "dating_appearance_" + key
            ):
                form["dating_appearance_" + key] = form.get("appearance_" + key)
    try:
        age = int(str(form.get("age") or "").strip())
    except ValueError:
        raise ValueError(_("A dating agent needs a numeric age.")) from None
    personality = {
        trait: form.get(trait)
        for trait in ("oe", "co", "ex", "ag", "ne")
        if form.get(trait)
    }
    base = {
        "username": (form.get("name") or "").strip(),
        "age": age,
        "gender": form.get("gender"),
        "language": form.get("language"),
        "nationality": form.get("nationality"),
        "education_level": form.get("education_level"),
        "profession": form.get("profession"),
        "leaning": form.get("leaning"),
        "personality": personality or None,
    }
    entries, problems = agent_form.entries_from_form(form, base)
    if problems:
        raise ValueError(
            _("The dating fields are not valid: %(why)s", why=" | ".join(problems[:5]))
        )
    taken = {entry["key"] for entry in entries}
    kept = [
        entry
        for entry in feature_entries
        if not (entry.get("feature_type") == "custom" and entry.get("key") in taken)
    ]
    return kept + entries
