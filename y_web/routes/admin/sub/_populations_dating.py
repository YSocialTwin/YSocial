"""Dating populations in the population administration: the creation, import, export and details of the populations
whose agents carry the dating fields (plan S2, IR-D-05, decision D-10).

The module belongs to the dating platform and moves to its repository; ``populations`` asks it through the small
functions at the end."""

import json
import os
import re

from flask import flash, redirect, request
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.platforms import registry
from y_web.src.agents import appearance_form as af
from y_web.src.models import (
    ActivityProfile,
    AgeClass,
    Agent,
    Agent_Population,
    Education,
    Languages,
    Leanings,
    Nationalities,
    Population,
    PopulationActivityProfile,
    Profession,
)
from y_web.src.system.miscellanea import check_privileges

from .populations import _unique_population_name, population


def wants_generation(form) -> bool:
    return (form.get("username_type") or "").strip().lower() == "dating"


def wants_upload(form, upload) -> bool:
    return (
        form.get("upload_population_type") or ""
    ).strip().lower() == "dating" or _is_dating_document(upload)


def runtime_missing(user):
    """The message to show when the dating fields were asked for and the dating runtime is not installed, else ``None``."""
    dp = registry.library_or_none("dating", "population")
    if dp is None or not dp.runtime_available(user):
        return _("The Dating simulator is not installed.")
    return None


def is_dating(pop) -> bool:
    return getattr(pop, "username_type", None) == "dating"


def sync_if_needed(pop) -> None:
    """Fill the columns of a dating population the list reads, when they are still empty."""
    if is_dating(pop) and not pop.education:
        _sync_dating_population(pop)


def sync_if_dating(pop) -> None:
    if pop is not None and is_dating(pop):
        _sync_dating_population(pop)


def remove_agents_of(pop) -> None:
    """Remove the agents of a dating population and their custom features (nothing for the others)."""
    if is_dating(pop):
        registry.library("dating", "population").remove_agents(pop.id)


def discard_agents(population_id) -> None:
    registry.library("dating", "population").remove_agents(population_id)


def _is_dating_document(upload):
    """Whether an uploaded JSON file is a YDating population document (it has no ``population_data`` block, which
    every export of YSocial has). The stream is left at its start."""
    try:
        data = json.loads(upload.read().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    finally:
        upload.seek(0)
    return isinstance(data, dict) and "population_data" not in data and "agents" in data


def _dating_generator_config():
    """The YDating generator parameters of the creation form (the standard sections plus the Dating ones)."""
    dp = registry.library("dating", "population")
    return dp.config_from_population_form(
        request.form,
        {
            str(r.id): (r.age_start, r.age_end)
            for r in db.session.scalars(select(AgeClass)).all()
        },
        {
            str(r.id): r.education_level
            for r in db.session.scalars(select(Education)).all()
        },
        {str(r.id): r.leaning for r in db.session.scalars(select(Leanings)).all()},
    )


def _complete_with_dating_fields(population):
    """Give the agents just generated their dating fields (the Dating sections of the form)."""
    dp = registry.library("dating", "population")
    config = _dating_generator_config()
    config.pop(
        "archetypes", None
    )  # the rhythm of the agents is the standard activity profiles'
    dp.complete_population(
        population.id,
        config=config,
        seed=request.form.get("seed") or None,
        language=dp.language_code(request.form.get("languages")) or None,
        apply_activity=True,
    )


def _dating_population_or_none(uid):
    library = registry.library_or_none("dating", "population")
    if library is None:
        return None
    is_dating_population = library.is_dating_population
    pop = db.session.scalars(select(Population).filter_by(id=uid)).first()
    return pop if pop is not None and is_dating_population(pop) else None


def _store_dating_activity_profiles(population_id, profiles):
    """Link the activity profiles (name -> percent) assigned in the form to the population, as the other platforms do."""
    for name, pct in (profiles or {}).items():
        profile = db.session.scalars(
            select(ActivityProfile).filter_by(name=name)
        ).first()
        if profile is not None:
            db.session.add(
                PopulationActivityProfile(
                    population=population_id,
                    activity_profile=profile.id,
                    percentage=float(pct),
                )
            )
    db.session.commit()


def _sync_dating_population(pop):
    """Fill the columns of a dating population that the list and the details page read, from its agents.

    The education, political leanings and nationalities of the ``population`` row, and the activity profile of every
    agent that has an archetype named like one (the archetype of a dating agent is its activity profile).
    """
    agents = db.session.scalars(
        select(Agent)
        .join(Agent_Population, Agent_Population.agent_id == Agent.id)
        .where(Agent_Population.population_id == pop.id)
    ).all()
    changed = False

    def labels(attr, limit):
        seen = []
        for a in agents:
            value = getattr(a, attr, None)
            if value and str(value) not in seen:
                seen.append(str(value))
        return ",".join(seen)[:limit]

    for column, attr, limit in (
        ("education", "education_level", 100),
        ("leanings", "leaning", 200),
        ("nationalities", "nationality", 200),
    ):
        if not getattr(pop, column):
            value = labels(attr, limit)
            if value:
                setattr(pop, column, value)
                changed = True
    by_name = {
        p.name.lower(): p.id for p in db.session.scalars(select(ActivityProfile)).all()
    }
    for a in agents:
        if a.activity_profile is None and a.archetype:
            profile = by_name.get(str(a.archetype).lower())
            if profile is not None:
                a.activity_profile = profile
                changed = True
    if changed:
        db.session.commit()


def _register_dating_population(name, descr, data):
    """Create the ``population`` row and the agents (with their custom features) of a validated population."""
    dp = registry.library("dating", "population")
    size, age_min, age_max = dp.population_row_values(data)
    summary = dp.summarize(data)
    row = Population(
        name=_unique_population_name(name),
        descr=(descr or "")[:200],
        size=size,
        age_min=age_min,
        age_max=age_max,
        interests=",".join(list(summary["interests"])[:30])[:300],
        languages=",".join(summary["languages"])[:100],
        username_type="dating",
    )
    db.session.add(row)
    db.session.commit()
    try:
        dp.store_agents(row.id, data)
    except Exception:
        db.session.rollback()
        db.session.delete(row)
        db.session.commit()
        raise
    _sync_dating_population(row)
    return row


def _dating_form_context():
    """Lists the Dating creation form offers next to the free-text weights (same catalogues as the standard form)."""
    dp = registry.library_or_none("dating", "population")
    return {
        "dating_available": dp is not None and dp.runtime_available(current_user),
        "dating_nationalities": [
            r.nationality for r in db.session.scalars(select(Nationalities)).all()
        ],
        "dating_education_levels": [
            r.education_level for r in db.session.scalars(select(Education)).all()
        ],
        "dating_leanings": [
            r.leaning for r in db.session.scalars(select(Leanings)).all()
        ],
        "dating_languages": [
            r.language for r in db.session.scalars(select(Languages)).all()
        ],
        "dating_professions": [
            r.profession
            for r in db.session.scalars(select(Profession).limit(200)).all()
        ],
        "dating_appearance_labels": af.APPEARANCE_LABELS,
        "dating_defaults": {
            "appearance": af.APPEARANCE_DEFAULTS,
            "appearance_options": af.APPEARANCE_OPTIONS,
            "height": af.HEIGHT_DEFAULT_RANGE,
            "glasses": af.GLASSES_DEFAULT_PERCENT,
            **({} if dp is None else dp.generator_defaults()),
        },
    }


@population.route("/admin/dating_populations")
@login_required
def dating_populations():
    """Dating populations are managed in the populations page, like those of the other platforms."""
    check_privileges(current_user.username)
    return redirect("/admin/populations")


def _upload_dating_population():
    """Validate an uploaded document against the YDating population schema and store it (platform Dating of the
    standard upload form)."""
    dp = registry.library("dating", "population")
    upload = request.files.get("population_file")
    if upload is None or not upload.filename:
        flash(_("Choose a population file first."), "error")
        return redirect("/admin/populations")
    try:
        data = dp.read_upload(upload.read(dp.MAX_UPLOAD_BYTES + 1))
        problems = dp.validate_population(data)
        if problems:
            raise dp.DatingPopulationError(problems)
    except dp.DatingPopulationError as exc:
        flash(
            _(
                "The population is not valid for dating: %(why)s",
                why=" | ".join(exc.problems[:5]),
            ),
            "error",
        )
        return redirect("/admin/populations")
    default_name = os.path.splitext(os.path.basename(upload.filename))[0]
    row = _register_dating_population(
        dp.clean_name(request.form.get("pop_name"))
        or dp.clean_name(default_name)
        or "dating",
        request.form.get("pop_descr"),
        data,
    )
    flash(_("Dating population '%(name)s' imported.", name=row.name), "success")
    return redirect(f"/admin/population_details/{row.id}")


def _generate_dating_population():
    """Generate a synthetic dating population with the generator of YDating (platform Dating of the standard
    creation form)."""
    dp = registry.library("dating", "population")
    try:
        data = dp.generate(
            request.form.get("n_agents"),
            seed=request.form.get("seed"),
            language=dp.language_code(request.form.get("languages")) or None,
            config=dp.config_from_population_form(
                request.form,
                {
                    str(r.id): (r.age_start, r.age_end)
                    for r in db.session.scalars(select(AgeClass)).all()
                },
                {
                    str(r.id): r.education_level
                    for r in db.session.scalars(select(Education)).all()
                },
                {
                    str(r.id): r.leaning
                    for r in db.session.scalars(select(Leanings)).all()
                },
            ),
        )
    except dp.DatingPopulationError as exc:
        flash(
            _(
                "The population could not be generated: %(why)s",
                why=" | ".join(exc.problems[:5]),
            ),
            "error",
        )
        return redirect("/admin/populations")
    dp.give_names(
        data,
        {a for (a,) in db.session.query(Agent.name).all()},
        request.form.get("seed") or None,
    )
    row = _register_dating_population(
        dp.clean_name(request.form.get("pop_name")) or "dating",
        request.form.get("pop_descr"),
        data,
    )
    _store_dating_activity_profiles(row.id, dp.activity_profiles(request.form))
    flash(_("Dating population '%(name)s' generated.", name=row.name), "success")
    return redirect(f"/admin/population_details/{row.id}")


def _dating_details(uid, population):
    """What the details page adds for a dating population: the counts of the runtime summary and a profile card."""
    dp = registry.library_or_none("dating", "population")
    if dp is None or population is None or not dp.has_dating_fields(population):
        return None
    try:
        data = dp.load_document(uid)
    except (
        Exception
    ):  # the runtime that describes the fields is not installed: no card, the statistics remain
        return None
    agents = (data or {}).get("agents") or []
    if not agents:
        return None
    index = request.args.get("agent", type=int, default=0) or 0
    index = max(0, min(index, len(agents) - 1))
    return {
        "summary": dp.summarize(data),
        "card": dp.profile_card(agents[index]),
        "index": index,
        "names": [a["username"] for a in agents[:500]],
    }


@population.route("/admin/dating_population/<int:uid>/download")
@login_required
def download_dating_population(uid):
    """Export the population as a YDating document (the same file that can be uploaded back)."""
    check_privileges(current_user.username)
    from flask import Response

    dp = registry.library("dating", "population")
    pop = _dating_population_or_none(uid)
    data = dp.load_document(uid) if pop is not None else None
    if data is None:
        flash(_("Population not found."), "error")
        return redirect("/admin/populations")
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", pop.name) or "population"
    return Response(
        json.dumps(data, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
    )


def _dating_details_context(uid, population):
    """The template variable the details page of a population reads for the dating card."""
    return {"dating": _dating_details(uid, population)}
