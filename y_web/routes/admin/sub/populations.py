"""
Population management routes.

Administrative routes for creating, configuring, and managing agent populations
including demographics, personality traits, recommendation systems, and
association with experiments and pages.
"""

import json
import os
import re

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
)
from flask_login import current_user, login_required
from sqlalchemy import delete, func, select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.agents.custom_features import (
    agent_ext_entries_from_population_agent_payload,
    feature_entries_from_population_agent_payload,
    replace_agent_custom_features,
    summarize_agent_custom_features_bulk,
)
from y_web.src.agents.platform import (
    ensure_population_username_type_column,
    infer_population_username_type,
    normalize_population_username_type,
    population_platform_fields,
)
from y_web.src.agents.population import generate_population
from y_web.src.llm.ollama_manager import get_ollama_models
from y_web.src.llm.vllm_manager import get_llm_models
from y_web.src.models import (
    ActivityProfile,
    AgeClass,
    Agent,
    Agent_Ext,
    Agent_Population,
    Agent_Profile,
    Content_Recsys,
    Education,
    Exp_Topic,
    Exps,
    Follow_Recsys,
    Languages,
    Leanings,
    Nationalities,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Profession,
    Topic_List,
    Toxicity_Levels,
)
from y_web.src.system.desktop_file_handler import send_file_desktop
from y_web.src.system.miscellanea import (
    check_privileges,
    llm_backend_status,
    ollama_status,
)

population = Blueprint("population", __name__)

STANDARD_POPULATION_TYPE = None


def _render_custom_population_details(population, exps, agents):
    agent_rows = []
    for agent, _ in agents:
        activity_profile_name = None
        if agent.activity_profile:
            profile = db.session.get(ActivityProfile, agent.activity_profile)
            activity_profile_name = profile.name if profile else None
        ext_fields = {
            ext.feature_name: ext.feature_value
            for ext in db.session.scalars(
                select(Agent_Ext).filter_by(agent_id=agent.id)
            ).all()
        }
        agent_rows.append(
            {
                "id": agent.id,
                "name": agent.name,
                "ag_type": agent.ag_type,
                "activity_profile": activity_profile_name,
                "daily_activity_level": agent.daily_activity_level,
                "ext_fields": ext_fields,
            }
        )

    back_href = (
        f"/admin/custom_agent/{population.pop_type}"
        if population.pop_type
        else "/admin/populations"
    )
    back_label = "Custom Agent Populations" if population.pop_type else "Populations"

    return render_template(
        "admin/custom_population_details.html",
        population=population,
        population_experiments=exps,
        agent_rows=agent_rows,
        live_size=len(agents),
        back_href=back_href,
        back_label=back_label,
    )


def _uniform_distribution_from_ids(selected_ids):
    ids = [str(item).strip() for item in selected_ids if str(item).strip()]
    if not ids:
        return {}
    weight = 100.0 / len(ids)
    return {item_id: weight for item_id in ids}


def _normalize_percentage_distribution(raw_distribution, selected_ids):
    selected = [str(item).strip() for item in selected_ids if str(item).strip()]
    if not selected:
        return {}

    normalized = {}
    for item_id in selected:
        if str(item_id) in raw_distribution:
            try:
                normalized[item_id] = float(raw_distribution[str(item_id)])
            except (TypeError, ValueError):
                continue

    if not normalized:
        return _uniform_distribution_from_ids(selected)

    return normalized


def _distribution_total_is_valid(distribution):
    if not distribution:
        return False
    total = sum(float(v) for v in distribution.values())
    return abs(total - 100.0) < 0.01


def _parse_json_array_form_value(raw_value, default=None):
    if raw_value in (None, ""):
        return list(default or [])
    if isinstance(raw_value, list):
        values = raw_value
    else:
        try:
            values = json.loads(raw_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            values = [item.strip() for item in str(raw_value).split(",")]
    if not isinstance(values, list):
        return list(default or [])
    cleaned = []
    for value in values:
        text = str(value).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned or list(default or [])


def _parse_percentage_value(raw_value, default=0):
    try:
        return max(0, min(100, int(float(raw_value))))
    except (TypeError, ValueError):
        return int(default)


def _parse_distribution_from_form(prefix):
    distribution = request.form.get(f"{prefix}_distribution", "Uniform")
    param_name = request.form.get(f"{prefix}_distribution_param", "")
    return {
        "min": request.form.get(f"{prefix}_min", "1"),
        "max": request.form.get(f"{prefix}_max", "10"),
        "distribution": distribution,
        "parameter": param_name,
    }


@population.route("/admin/create_population_empty", methods=["POST", "GET"])
@login_required
def create_population_empty():
    """
    Create a new empty population with just name and description.

    Form data:
        empty_population_name: Name for the population
        empty_population_descr: Description of the population

    Returns:
        Redirect to populations list
    """
    check_privileges(current_user.username)
    ensure_population_username_type_column()

    name = request.form.get("empty_population_name")
    descr = request.form.get("empty_population_descr")
    username_type = normalize_population_username_type(
        request.form.get("empty_population_type")
    )

    # add the experiment to the database
    pop = Population(
        name=name,
        descr=descr,
        username_type=username_type,
        pop_type=STANDARD_POPULATION_TYPE,
    )

    db.session.add(pop)
    db.session.commit()

    return populations()


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


def _flag(name):
    """Whether a checkbox of the form is on."""
    return (request.form.get(name) or "").strip().lower() in {"1", "on", "true", "yes"}


def _photo_sharing_available():
    """Whether the Photo Sharing simulator is installed (and visible to this admin)."""
    try:
        from y_web.src.external_runtime import runtime_installed_and_visible

        return bool(runtime_installed_and_visible("photo_sharing", current_user))
    except Exception:
        return False


def _discard_population(population):
    """Remove a population whose generation failed, with its agents: no partial population is kept."""
    db.session.rollback()
    try:
        from y_web.src.dating import population as dp

        dp.remove_agents(population.id)
    except Exception:
        db.session.rollback()
    db.session.execute(
        delete(PopulationActivityProfile).filter_by(population=population.id)
    )
    db.session.execute(delete(Agent_Population).filter_by(population_id=population.id))
    db.session.delete(population)
    db.session.commit()


def _dating_generator_config():
    """The YDating generator parameters of the creation form (the standard sections plus the Dating ones)."""
    from y_web.src.dating import population as dp

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


def _apply_appearance(population):
    """Draw the appearance of the agents just generated (the Appearance section of the form).

    Returns ``(agent ids, picture settings)`` when the profile pictures are requested, else ``None``. With the
    Dating fields on, the traits already come with them (``dating.appearance.*``) and are kept.
    """
    from y_web.src.agents import profile_pictures as pp

    ids = [
        row[0]
        for row in db.session.execute(
            select(Agent_Population.agent_id).where(
                Agent_Population.population_id == population.id
            )
        ).all()
    ]
    if not _flag("include_dating"):
        pp.assign_appearance(ids, pp.appearance_config_from_form(request.form))
    if not _flag("generate_profile_pictures"):
        return None
    return ids, pp.pictures_config_from_form(request.form)


def _complete_with_dating_fields(population):
    """Give the agents just generated their dating fields (the Dating sections of the form)."""
    from y_web.src.dating import population as dp

    config = _dating_generator_config()
    config.pop("archetypes", None)  # the rhythm of the agents is the standard activity profiles'
    dp.complete_population(
        population.id,
        config=config,
        seed=request.form.get("seed") or None,
        language=dp.language_code(request.form.get("languages")) or None,
        apply_activity=True,
    )


@population.route("/admin/create_population", methods=["POST"])
@login_required
def create_population():
    """
    Create a new population with full configuration.

    Creates population with demographics, personality traits, interests,
    toxicity levels, and recommendation system settings. Generates agents
    based on the configuration.

    Form data:
        pop_name, pop_descr, n_agents, user_type,
        education_levels, political_leanings, toxicity_levels,
        nationalities, languages, tags (interests), crecsys, frecsys,
        actions_min, actions_max, actions_distribution, poisson_lambda,
        geometric_p, zipf_s

    Returns:
        Redirect to populations list
    """
    check_privileges(current_user.username)
    ensure_population_username_type_column()
    if (request.form.get("username_type") or "").strip().lower() == "dating":
        return _generate_dating_population()
    name = request.form.get("pop_name")
    descr = request.form.get("pop_descr")
    n_agents = request.form.get("n_agents")
    user_type = request.form.get("user_type")

    llm = request.form.get("host_llm")
    username_type = normalize_population_username_type(
        request.form.get("username_type")
    )
    # A population is not tied to a platform: the dedicated fields of a platform are optional sections of the
    # form (offered only when its simulator is installed), generated on the same agents.
    include_photo_sharing = username_type == "photo_sharing" or _flag(
        "include_photo_sharing"
    )
    include_dating = _flag("include_dating")
    include_appearance = _flag("include_appearance")
    if include_photo_sharing and username_type != "photo_sharing":
        if not _photo_sharing_available():
            flash(_("The Photo Sharing simulator is not installed."), "error")
            return redirect(request.referrer)
    if include_dating:
        from y_web.src.dating import population as dp

        if not dp.runtime_available(current_user):
            flash(_("The Dating simulator is not installed."), "error")
            return redirect(request.referrer)

    # Get gender distribution
    male_percentage = int(request.form.get("male_percentage", "50"))
    female_percentage = int(request.form.get("female_percentage", "50"))
    gender_distribution = {"male": male_percentage, "female": female_percentage}

    age_classes = request.form.getlist("age_classes")
    education_level_ids = request.form.getlist("education_levels")
    political_leaning_ids = request.form.getlist("political_leanings")
    toxicity_level_ids = request.form.getlist("toxicity_levels")

    education_levels = ",".join(education_level_ids)
    political_leanings = ",".join(political_leaning_ids)
    toxicity_levels = ",".join(toxicity_level_ids)

    # Retrieve percentage data for education, political leanings, toxicity, and age classes
    # These will be used in future implementations for weighted distribution
    education_percentages_str = request.form.get("education_levels_percentages", "{}")
    political_percentages_str = request.form.get("political_leanings_percentages", "{}")
    toxicity_percentages_str = request.form.get("toxicity_levels_percentages", "{}")
    age_classes_percentages_str = request.form.get("age_classes_percentages", "{}")

    try:
        education_percentages = json.loads(education_percentages_str)
        political_percentages = json.loads(political_percentages_str)
        toxicity_percentages = json.loads(toxicity_percentages_str)
        age_classes_percentages = json.loads(age_classes_percentages_str)
    except (json.JSONDecodeError, ValueError):
        education_percentages = {}
        political_percentages = {}
        toxicity_percentages = {}
        age_classes_percentages = {}

    education_percentages = _normalize_percentage_distribution(
        education_percentages, education_level_ids
    )
    political_percentages = _normalize_percentage_distribution(
        political_percentages, political_leaning_ids
    )
    toxicity_percentages = _normalize_percentage_distribution(
        toxicity_percentages, toxicity_level_ids
    )
    age_classes_percentages = _normalize_percentage_distribution(
        age_classes_percentages, age_classes
    )

    percentages = {
        "education": education_percentages,
        "political_leanings": political_percentages,
        "toxicity_levels": toxicity_percentages,
        "age_classes": age_classes_percentages,
        "gender": gender_distribution,
    }

    if not name or not str(name).strip():
        flash(_("Population name is required."), "error")
        return redirect(request.referrer)

    try:
        n_agents_value = int(n_agents)
    except (TypeError, ValueError):
        flash(_("Population size must be a valid integer."), "error")
        return redirect(request.referrer)

    if n_agents_value <= 0:
        flash(_("Population size must be greater than zero."), "error")
        return redirect(request.referrer)

    if male_percentage + female_percentage != 100:
        flash(_("Gender distribution must total 100%."), "error")
        return redirect(request.referrer)

    required_distributions = {
        "age classes": age_classes_percentages,
        "education levels": education_percentages,
        "political leanings": political_percentages,
        "toxicity levels": toxicity_percentages,
    }
    for label, distribution in required_distributions.items():
        if not distribution:
            flash(_("Select at least one %(label)s.", label=label), "error")
            return redirect(request.referrer)
        if not _distribution_total_is_valid(distribution):
            flash(
                _("The %(label)s percentages must sum to 100%%.", label=label), "error"
            )
            return redirect(request.referrer)

    nationalities = request.form.get("nationalities")
    languages = request.form.get("languages")
    interests = request.form.get("tags")

    # Get selected profession backgrounds
    profession_backgrounds = request.form.getlist("profession_backgrounds")
    # If no profession backgrounds selected, use all available
    if not profession_backgrounds:
        all_backgrounds = db.session.query(Profession.background).distinct().all()
        profession_backgrounds = [bg[0] for bg in all_backgrounds]

    # Get activity profiles data from the hidden field
    activity_profiles_data = request.form.get("activity_profiles_data", "[]")
    try:
        activity_profiles_json = json.loads(activity_profiles_data)
    except:
        activity_profiles_json = []

    # Get actions per user once active data
    actions_min = request.form.get("actions_min", "1")
    actions_max = request.form.get("actions_max", "10")
    actions_distribution = request.form.get("actions_distribution", "Uniform")

    # Get distribution-specific parameters
    poisson_lambda = request.form.get("poisson_lambda", "0.88")
    geometric_p = request.form.get("geometric_p", "0.6667")
    zipf_s = request.form.get("zipf_s", "2.5")

    # Store actions configuration for future use
    # Note: Not persisted yet, maintaining backward compatibility
    actions_config = {
        "min": actions_min,
        "max": actions_max,
        "distribution": actions_distribution,
        "Poisson": poisson_lambda,
        "Geometric": geometric_p,
        "Zipf": zipf_s,
    }

    photo_sharing_config = None
    if include_photo_sharing:
        photo_story_visibility = {
            "public": _parse_percentage_value(
                request.form.get("photo_story_public_percentage"), 20
            ),
            "followers": _parse_percentage_value(
                request.form.get("photo_story_followers_percentage"), 65
            ),
            "private": _parse_percentage_value(
                request.form.get("photo_story_private_percentage"), 15
            ),
        }
        photo_creator_tier = {
            "standard": _parse_percentage_value(
                request.form.get("photo_creator_standard_percentage"), 60
            ),
            "pro": _parse_percentage_value(
                request.form.get("photo_creator_pro_percentage"), 25
            ),
            "influencer": _parse_percentage_value(
                request.form.get("photo_creator_influencer_percentage"), 15
            ),
        }
        photo_sharing_config = {
            "is_private_percentage": _parse_percentage_value(
                request.form.get("photo_is_private_percentage"), 20
            ),
            "is_verified_percentage": _parse_percentage_value(
                request.form.get("photo_is_verified_percentage"), 10
            ),
            "attention_budget": _parse_distribution_from_form("photo_attention_budget"),
            "favorite_filters": _parse_json_array_form_value(
                request.form.get("photo_favorite_filters"),
                default=["warm", "vintage", "mono", "grain", "bright", "clean"],
            ),
            "story_visibility": photo_story_visibility,
            "creator_tier": photo_creator_tier,
        }

        if not _distribution_total_is_valid(photo_story_visibility):
            flash(_("Photo story visibility percentages must sum to 100%."), "error")
            return redirect(request.referrer)
        if not _distribution_total_is_valid(photo_creator_tier):
            flash(_("Photo creator tier percentages must sum to 100%."), "error")
            return redirect(request.referrer)

        try:
            photo_min = int(photo_sharing_config["attention_budget"]["min"])
            photo_max = int(photo_sharing_config["attention_budget"]["max"])
        except (TypeError, ValueError):
            flash(_("Photo attention budget min/max must be valid integers."), "error")
            return redirect(request.referrer)
        if photo_min <= 0 or photo_max <= 0 or photo_min > photo_max:
            flash(
                _(
                    "Photo attention budget must use positive min/max values with min <= max."
                ),
                "error",
            )
            return redirect(request.referrer)

    population = Population(
        name=name,
        descr=descr,
        size=n_agents_value,
        llm=user_type,
        age_min=None,
        age_max=None,
        education=education_levels,
        leanings=political_leanings,
        nationalities=nationalities,
        languages=languages,
        interests=interests,
        toxicity=toxicity_levels,
        llm_url=llm,
        username_type=username_type,
        pop_type=STANDARD_POPULATION_TYPE,
    )

    db.session.add(population)
    db.session.commit()

    # Store population-activity profile associations
    for profile_data in activity_profiles_json:
        profile_assoc = PopulationActivityProfile(
            population=population.id,
            activity_profile=int(profile_data["id"]),
            percentage=float(profile_data["percentage"]),
        )
        db.session.add(profile_assoc)
    db.session.commit()

    try:
        generate_population(
            name,
            percentages,
            actions_config,
            profession_backgrounds,
            photo_sharing_config,
        )
        if include_dating:
            _complete_with_dating_fields(population)
        appearance_job = _apply_appearance(population) if include_appearance else None
    except Exception as exc:
        _discard_population(population)
        flash(
            _(
                "Population generation failed: %(error)s. No partial population was kept.",
                error=exc,
            ),
            "error",
        )
        return redirect(request.referrer)

    if appearance_job:
        from flask import current_app

        from y_web.src.agents import profile_pictures as pp

        pp.start_generation(
            current_app._get_current_object(), current_user.id, *appearance_job
        )
        flash(
            _(
                "Profile pictures are being generated in the background: follow the progress in the notifications menu."
            ),
            "info",
        )

    from y_web.src.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)
    telemetry.log_event(
        {
            "action": "create_population",
            "data": {"n_agents": n_agents},
        }
    )

    return populations()


@population.route("/admin/populations_data")
@login_required
def populations_data():
    """
    Display populations management page.

    Returns:
        Rendered populations data template
    """
    ensure_population_username_type_column()
    query = Population.query.filter(Population.pop_type.is_(None))

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(
            db.or_(
                Population.name.like(f"%{search}%"),
            )
        )
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name", "descr", "size", "platform_type", "pop_type"]:
                name = "name"
            if name == "platform_type":
                col = Population.username_type
            else:
                col = getattr(Population, name)
            if direction == "-":
                col = col.desc()
            order.append(col)
        if order:
            query = query.order_by(*order)

    # pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    # response
    res = query.all()

    for pop in res:
        if pop.username_type == "dating" and not pop.education:
            _sync_dating_population(pop)

    # Get activity profiles for each population
    population_profiles = {}
    for pop in res:
        profiles = (
            db.session.query(ActivityProfile)
            .join(
                PopulationActivityProfile,
                ActivityProfile.id == PopulationActivityProfile.activity_profile,
            )
            .filter(PopulationActivityProfile.population == pop.id)
            .all()
        )
        population_profiles[pop.id] = [p.name for p in profiles]

    # Get lookup dictionaries for education, leanings, and toxicity
    education_dict = {
        str(e.id): e.education_level
        for e in db.session.scalars(select(Education)).all()
    }
    leanings_dict = {
        str(l.id): l.leaning for l in db.session.scalars(select(Leanings)).all()
    }
    toxicity_dict = {
        str(t.id): t.toxicity_level
        for t in db.session.scalars(select(Toxicity_Levels)).all()
    }

    return {
        "data": [
            {
                "id": pop.id,
                "name": pop.name,
                "size": pop.size,
                "education": [
                    education_dict.get(e_id.strip(), e_id.strip())
                    for e_id in (pop.education or "").split(",")
                    if e_id.strip()
                ],
                "leanings": [
                    leanings_dict.get(l_id.strip(), l_id.strip())
                    for l_id in (pop.leanings or "").split(",")
                    if l_id.strip()
                ],
                "toxicity": [
                    toxicity_dict.get(t_id.strip(), t_id.strip())
                    for t_id in (pop.toxicity or "").split(",")
                    if t_id.strip()
                ],
                "username_type": infer_population_username_type(pop) or "microblogging",
                "platform_type": infer_population_username_type(pop) or "microblogging",
                "platform_fields": population_platform_fields(pop),
                "pop_type": pop.pop_type or "standard",
                "activity_profiles": population_profiles.get(pop.id, []),
            }
            for pop in res
        ],
        "total": total,
    }


@population.route("/admin/populations")
@login_required
def populations():
    """
    Display main populations overview page.

    Returns:
        Rendered populations template with all populations
    """
    check_privileges(current_user.username)
    ensure_population_username_type_column()

    # Regular expression to match model values

    models = get_llm_models()  # Use generic function for any LLM server
    llm_backend = llm_backend_status()
    leanings = db.session.scalars(select(Leanings)).all()
    education_levels = db.session.scalars(select(Education)).all()
    nationalities = db.session.scalars(select(Nationalities)).all()
    languages = db.session.scalars(select(Languages)).all()
    toxicity_levels = db.session.scalars(select(Toxicity_Levels)).all()
    age_classes = db.session.scalars(select(AgeClass)).all()
    activity_profiles = db.session.scalars(select(ActivityProfile)).all()

    # Get unique profession backgrounds
    profession_backgrounds = (
        db.session.query(Profession.background)
        .distinct()
        .order_by(Profession.background)
        .all()
    )
    profession_backgrounds = [bg[0] for bg in profession_backgrounds]

    return render_template(
        "admin/populations.html",
        models=models,
        llm_backend=llm_backend,
        leanings=leanings,
        education_levels=education_levels,
        nationalities=nationalities,
        languages=languages,
        toxicity_levels=toxicity_levels,
        age_classes=age_classes,
        activity_profiles=activity_profiles,
        profession_backgrounds=profession_backgrounds,
        photo_available=_photo_sharing_available(),
        **_appearance_form_context(),
        **_dating_form_context(),
    )


@population.route("/admin/population_details/<int:uid>")
@login_required
def population_details(uid):
    """Handle population details operation."""
    check_privileges(current_user.username)
    # get population details
    population = db.session.scalars(select(Population).filter_by(id=uid)).first()
    population_row = population
    if population is not None and population.username_type == "dating":
        _sync_dating_population(population)

    # get experiment populations along with experiment names and ids
    experiment_populations = (
        db.session.query(Population_Experiment, Exps)
        .join(Exps)
        .filter(Population_Experiment.id_population == uid)
        .all()
    )

    exps = [(p[1].exp_name, p[1].idexp) for p in experiment_populations]

    # get all agents in the population
    agents = (
        db.session.query(Agent, Agent_Population)
        .join(Agent_Population)
        .filter(Agent_Population.population_id == uid)
        .all()
    )

    if population.pop_type is not None:
        return _render_custom_population_details(population, exps, agents)

    # Fetch label mappings from database
    leanings_map = {
        str(l.id): l.leaning for l in db.session.scalars(select(Leanings)).all()
    }
    education_map = {
        str(e.id): e.education_level
        for e in db.session.scalars(select(Education)).all()
    }
    toxicity_map = {
        str(t.id): t.toxicity_level
        for t in db.session.scalars(select(Toxicity_Levels)).all()
    }

    ln = {"leanings": [], "total": []}

    for a in agents:
        # Convert ID to label
        leaning_label = leanings_map.get(a[0].leaning, a[0].leaning)
        if leaning_label in ln["leanings"]:
            ln["total"][ln["leanings"].index(leaning_label)] += 1
        else:
            ln["leanings"].append(leaning_label)
            ln["total"].append(1)

    # Bin ages according to AgeClass ranges
    age_classes = db.session.scalars(
        select(AgeClass).order_by(AgeClass.age_start)
    ).all()
    age = {"age": [], "total": []}

    # Initialize bins for each age class
    for age_class in age_classes:
        age["age"].append(
            f"{age_class.name} ({age_class.age_start}-{age_class.age_end})"
        )
        age["total"].append(0)

    # Count agents in each age class bin
    for a in agents:
        agent_age = a[0].age
        if agent_age is None:
            continue
        for idx, age_class in enumerate(age_classes):
            if age_class.age_start <= agent_age <= age_class.age_end:
                age["total"][idx] += 1
                break

    edu = {"education": [], "total": []}

    for a in agents:
        # Convert ID to label
        education_label = education_map.get(a[0].education_level, a[0].education_level)
        if education_label in edu["education"]:
            edu["total"][edu["education"].index(education_label)] += 1
        else:
            edu["education"].append(education_label)
            edu["total"].append(1)

    nat = {"nationalities": [], "total": []}
    for a in agents:
        if a[0].nationality in nat["nationalities"]:
            nat["total"][nat["nationalities"].index(a[0].nationality)] += 1
        else:
            nat["nationalities"].append(a[0].nationality)
            nat["total"].append(1)

    lang = {"languages": [], "total": []}
    for a in agents:
        if a[0].language in lang["languages"]:
            lang["total"][lang["languages"].index(a[0].language)] += 1
        else:
            lang["languages"].append(a[0].language)
            lang["total"].append(1)

    tox = {"toxicity": [], "total": []}
    for a in agents:
        if a[0].toxicity is not None:
            # Convert ID to label
            toxicity_label = toxicity_map.get(a[0].toxicity, a[0].toxicity)
            if toxicity_label in tox["toxicity"]:
                tox["total"][tox["toxicity"].index(toxicity_label)] += 1
            else:
                tox["toxicity"].append(toxicity_label)
                tox["total"].append(1)

    activity = {"activity": [], "total": []}
    for a in agents:
        if a[0].daily_activity_level in activity["activity"]:
            activity["total"][
                activity["activity"].index(a[0].daily_activity_level)
            ] += 1
        else:
            if a[0].daily_activity_level is not None:
                activity["activity"].append(a[0].daily_activity_level)
                activity["total"].append(1)

    sorted_activity = dict(sorted(zip(activity["activity"], activity["total"])))

    # Convert back to dictionary format with separate lists
    activity = {
        "activity": list(sorted_activity.keys()),
        "total": list(sorted_activity.values()),
    }

    # Gender distribution
    gender = {"genders": [], "total": []}
    for a in agents:
        if a[0].gender:
            if a[0].gender in gender["genders"]:
                gender["total"][gender["genders"].index(a[0].gender)] += 1
            else:
                gender["genders"].append(a[0].gender)
                gender["total"].append(1)

    # Professions distribution (top-k for wordcloud)
    professions = {}
    for a in agents:
        if a[0].profession:
            professions[a[0].profession] = professions.get(a[0].profession, 0) + 1

    # Sort professions by frequency and prepare for word cloud
    sorted_professions = dict(
        sorted(professions.items(), key=lambda x: x[1], reverse=True)
    )
    prof = {
        "professions": list(sorted_professions.keys()),
        "total": list(sorted_professions.values()),
    }

    # Activity profiles distribution
    activity_prof = {"profiles": [], "total": []}
    for a in agents:
        if a[0].activity_profile:
            # Get activity profile name
            profile = db.session.get(ActivityProfile, a[0].activity_profile)
            if profile:
                profile_name = profile.name
                if profile_name in activity_prof["profiles"]:
                    activity_prof["total"][
                        activity_prof["profiles"].index(profile_name)
                    ] += 1
                else:
                    activity_prof["profiles"].append(profile_name)
                    activity_prof["total"].append(1)

    dd = {
        "age": age,
        "leaning": ln,
        "education": edu,
        "nationalities": nat,
        "languages": lang,
        "toxicity": tox,
        "activity": activity,
        "gender": gender,
        "professions": prof,
        "activity_profiles": activity_prof,
    }

    # most frequent crecsys amon agents
    crecsys = {}
    for a in agents:
        if a[0].crecsys:
            if a[0].crecsys in crecsys:
                crecsys[a[0].crecsys] += 1
            else:
                crecsys[a[0].crecsys] = 1

    # most frequent crecsys amon agents
    frecsys = {}
    for a in agents:
        if a[0].frecsys:
            if a[0].frecsys in frecsys:
                frecsys[a[0].frecsys] += 1
            else:
                frecsys[a[0].frecsys] = 1

    # most frequent crecsys amon agents
    llm = {}
    for a in agents:
        if a[0].ag_type:
            if a[0].ag_type in llm:
                llm[a[0].ag_type] += 1
            else:
                llm[a[0].ag_type] = 1

    # get topics associated to the experiments this population is part of
    exp_topics = (
        db.session.query(Exp_Topic, Topic_List)
        .join(Topic_List)
        .join(Exps, Exp_Topic.exp_id == Exps.idexp)
        .join(Population_Experiment, Population_Experiment.id_exp == Exps.idexp)
        .filter(Population_Experiment.id_population == uid)
        .all()
    )
    topics = [t[1].name for t in exp_topics]

    try:
        # Calculate actual age min/max from agents
        agent_ages = [a[0].age for a in agents if a[0].age is not None]
        age_min_val = min(agent_ages) if agent_ages else None
        age_max_val = max(agent_ages) if agent_ages else None

        population_updated_details = {
            "id": population.id,
            "name": population.name,
            "descr": population.descr,
            "size": len(agents),
            "llm": max(llm, key=llm.get),
            "age_min": age_min_val,
            "age_max": age_max_val,
            "education": ", ".join(dd["education"]["education"]),
            "leanings": ", ".join(dd["leaning"]["leanings"]),
            "nationalities": ", ".join(dd["nationalities"]["nationalities"]),
            "languages": ", ".join(dd["languages"]["languages"]),
            "interests": ", ".join([t for t in topics]),
            "toxicity": ", ".join(dd["toxicity"]["toxicity"]),
            "frecsys": max(frecsys, key=frecsys.get),
            "crecsys": max(crecsys, key=crecsys.get),
        }
        population = population_updated_details
    except:
        pass

    # Get activity profile distribution for this population
    activity_profile_dist = (
        db.session.query(PopulationActivityProfile, ActivityProfile)
        .join(ActivityProfile)
        .filter(PopulationActivityProfile.population == uid)
        .all()
    )

    # Calculate actual agent distribution across activity profiles
    agent_profiles = {"profiles": [], "assigned_count": [], "expected_pct": []}
    for dist, profile in activity_profile_dist:
        agent_profiles["profiles"].append(profile.name)
        agent_profiles["expected_pct"].append(dist.percentage)
        # Count actual agents with this profile
        actual_count = sum(1 for a in agents if a[0].activity_profile == profile.id)
        agent_profiles["assigned_count"].append(actual_count)

    models = get_llm_models()  # Use generic function for any LLM server
    llm_backend = llm_backend_status()

    crecsys = db.session.scalars(select(Content_Recsys)).all()
    frecsys = db.session.scalars(select(Follow_Recsys)).all()

    from y_web.src.agents.custom_field_stats import collect

    custom_fields = collect([a[0].id for a in agents])
    kpis = {
        "agents": len(agents),
        "age_range": (
            f"{min(a[0].age for a in agents if a[0].age is not None)}–"
            f"{max(a[0].age for a in agents if a[0].age is not None)}"
            if any(a[0].age is not None for a in agents)
            else "—"
        ),
        "nationalities": len([n for n in dd["nationalities"]["nationalities"] if n]),
        "languages": len([n for n in dd["languages"]["languages"] if n]),
        "experiments": len(exps),
        "fields": sum(g["count"] for g in custom_fields),
    }

    return render_template(
        "admin/population_details.html",
        custom_fields=custom_fields,
        kpis=kpis,
        platform_fields=population_platform_fields(population_row),
        population=population,
        population_experiments=exps,
        agents=agents,
        data=dd,
        activity_profiles=agent_profiles,
        models=models,
        llm_backend=llm_backend,
        crecsys=crecsys,
        frecsys=frecsys,
        dating=_dating_details(uid, population_row),
    )


@population.route("/admin/add_to_experiment", methods=["POST"])
@login_required
def add_to_experiment():
    """
    Associate a population with an experiment.

    Returns:
        Redirect to population details
    """
    check_privileges(current_user.username)

    population_id = request.form.get("population_id")
    experiment_id = request.form.get("experiment_id")

    # check if the population is already in the experiment
    ap = db.session.scalars(
        select(Population_Experiment).filter_by(
            id_population=population_id, id_exp=experiment_id
        )
    ).first()
    if ap:
        return population_details(population_id)

    ap = Population_Experiment(id_population=population_id, id_exp=experiment_id)

    db.session.add(ap)
    db.session.commit()

    return population_details(population_id)


@population.route("/admin/delete_population/<int:uid>")
@login_required
def delete_population(uid):
    """Delete population."""
    check_privileges(current_user.username)

    population = db.session.scalars(select(Population).filter_by(id=uid)).first()

    # check if the population is assigned to any experiment
    pop_exp = db.session.scalars(
        select(Population_Experiment).filter_by(id_population=uid)
    ).first()
    if pop_exp:
        # if the population is assigned to any experiment, do not delete raise a warning
        flash(_("Population is assigned to an experiment. Cannot delete."))
        return populations()

    if population.pop_type is not None:
        linked_agents = db.session.scalars(
            select(Agent_Population).filter_by(population_id=uid)
        ).all()
        for link in linked_agents:
            assigned_count = db.session.scalar(
                select(func.count())
                .select_from(Agent_Population)
                .filter_by(agent_id=link.agent_id)
            )
            agent = db.session.scalars(
                select(Agent).filter_by(id=link.agent_id)
            ).first()
            if agent and agent.ag_type == population.pop_type and assigned_count <= 1:
                flash(
                    _(
                        "Cannot delete this custom population because at least one custom agent would be left without a population."
                    ),
                    "error",
                )
                return redirect(f"/admin/custom_agent/{population.pop_type}")

    if population.username_type == "dating":
        from y_web.src.dating.population import remove_agents

        remove_agents(
            population.id
        )  # the agents of the population and their custom features

    db.session.delete(population)
    db.session.commit()

    # delete agent_population entries
    agent_population = db.session.scalars(
        select(Agent_Population).filter_by(population_id=uid)
    ).all()
    for ap in agent_population:
        db.session.delete(ap)
        db.session.commit()

    # delete population_experiment entries
    population_experiment = db.session.scalars(
        select(Population_Experiment).filter_by(id_population=uid)
    ).all()
    for pe in population_experiment:
        db.session.delete(pe)
        db.session.commit()

    if population.pop_type is not None:
        return redirect(f"/admin/custom_agent/{population.pop_type}")
    return populations()


@population.route("/admin/download_population/<int:uid>")
@login_required
def download_population(uid):
    """Download population."""
    check_privileges(current_user.username)
    ensure_population_username_type_column()
    if _dating_population_or_none(uid) is not None:
        return redirect(f"/admin/dating_population/{uid}/download")

    # get all agents in the population
    agents = (
        db.session.query(Agent, Agent_Population)
        .join(Agent_Population)
        .filter(Agent_Population.population_id == uid)
        .all()
    )

    pages = (
        db.session.query(Page, Page_Population)
        .join(Page_Population)
        .filter(Page_Population.population_id == uid)
        .all()
    )

    # get population details
    population = db.session.scalars(select(Population).filter_by(id=uid)).first()
    feature_map = summarize_agent_custom_features_bulk([a[0].id for a in agents])

    res = {
        "population_data": {
            "name": population.name,
            "descr": population.descr,
            "username_type": infer_population_username_type(population)
            or "microblogging",
        },
        "agents": [],
        "pages": [],
    }

    for a in agents:
        structured = feature_map.get(a[0].id, {})
        # Get activity profile name if set
        activity_profile_name = None
        if a[0].activity_profile:
            activity_profile_obj = db.session.get(
                ActivityProfile, a[0].activity_profile
            )
            if activity_profile_obj:
                activity_profile_name = activity_profile_obj.name

        agent_row = {
            "id": a[0].id,
            "name": a[0].name,
            "ag_type": a[0].ag_type,
            "leaning": a[0].leaning,
            "oe": a[0].oe,
            "co": a[0].co,
            "ex": a[0].ex,
            "ag": a[0].ag,
            "ne": a[0].ne,
            "language": a[0].language,
            "education": a[0].education_level,
            "round_actions": a[0].round_actions,
            "nationality": a[0].nationality,
            "toxicity": a[0].toxicity,
            "age": a[0].age,
            "gender": a[0].gender,
            "crecsys": a[0].crecsys,
            "frecsys": a[0].frecsys,
            "profile_pic": a[0].profile_pic,
            "cover_image": a[0].cover_image,
            "daily_activity_level": a[0].daily_activity_level,
            "profession": a[0].profession,
            "activity_profile": activity_profile_name,
            "profile": (
                db.session.scalars(select(Agent_Profile).filter_by(agent_id=a[0].id))
                .first()
                .profile
                if db.session.scalars(
                    select(Agent_Profile).filter_by(agent_id=a[0].id)
                ).first()
                is not None
                else None
            ),
        }
        if structured.get("interests"):
            agent_row["interests"] = [
                list(structured["interests"]),
                len(structured["interests"]),
            ]
        if structured.get("opinions"):
            agent_row["opinions"] = dict(structured["opinions"])
        if structured.get("stubborn_topics"):
            agent_row["stubborn_topics"] = dict(structured["stubborn_topics"])
        if structured.get("custom_features"):
            agent_row["custom_features"] = dict(structured["custom_features"])
        res["agents"].append(agent_row)

    for p in pages:
        # Get activity profile name if set
        page_activity_profile_name = None
        if p[0].activity_profile:
            page_activity_profile_obj = db.session.get(
                ActivityProfile, p[0].activity_profile
            )
            if page_activity_profile_obj:
                page_activity_profile_name = page_activity_profile_obj.name

        res["pages"].append(
            {
                "id": p[0].id,
                "name": p[0].name,
                "descr": p[0].descr,
                "page_type": p[0].page_type,
                "feed": p[0].feed,
                "keywords": p[0].keywords,
                "logo": p[0].logo,
                "pg_type": p[0].pg_type,
                "leaning": p[0].leaning,
                "activity_profile": page_activity_profile_name,
            }
        )

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # Ensure temp_data directory exists
    temp_data_dir = os.path.join(BASE_DIR, f"experiments{os.sep}temp_data")
    os.makedirs(temp_data_dir, exist_ok=True)

    filename = os.path.join(temp_data_dir, f"population_{population.name}.json")
    json.dump(res, open(filename, "w", encoding="utf-8"), indent=4)

    return send_file_desktop(filename, as_attachment=True)


@population.route("/admin/upload_population", methods=["POST"])
@login_required
def upload_population():
    """
    Upload population data from JSON file.

    Returns:
        Redirect to populations page
    """
    check_privileges(current_user.username)
    ensure_population_username_type_column()

    population_file = request.files["population_file"]
    # a file is either a YSocial population export or a YDating population document: told apart by content
    if (
        request.form.get("upload_population_type") or ""
    ).strip().lower() == "dating" or _is_dating_document(population_file):
        return _upload_dating_population()

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # Ensure temp_data directory exists
    temp_data_dir = os.path.join(BASE_DIR, f"experiments{os.sep}temp_data")
    os.makedirs(temp_data_dir, exist_ok=True)

    filename = os.path.join(temp_data_dir, population_file.filename)
    population_file.save(filename)

    data = json.load(open(filename, "r", encoding="utf-8"))
    population_type = normalize_population_username_type(
        data.get("population_data", {}).get("username_type")
        or request.form.get("upload_population_type")
    )

    # Handle population name duplicates by adding incremental suffix
    population_data = data.get("population_data", {})
    base_name = population_data["name"]
    population_name = base_name
    suffix = 0
    while db.session.scalars(
        select(Population).filter_by(name=population_name)
    ).first():
        suffix += 1
        population_name = f"{base_name}_{suffix}"

    # add the population to the database
    population = Population(
        name=population_name,
        descr=population_data.get("descr", ""),
        username_type=population_type,
    )
    db.session.add(population)
    db.session.commit()

    agent_populations = []
    agent_ext_rows = []
    # add the agents to the database
    for a in data.get("agents", []):
        # check if the agent already exists
        agent = db.session.scalars(select(Agent).filter_by(name=a["name"])).first()
        if not agent:
            # Resolve activity_profile by name if provided
            activity_profile_id = None
            if a.get("activity_profile"):
                activity_profile_obj = db.session.scalars(
                    select(ActivityProfile).filter_by(name=a["activity_profile"])
                ).first()
                if activity_profile_obj:
                    activity_profile_id = activity_profile_obj.id

            agent = Agent(
                name=a["name"],
                ag_type=a["ag_type"],
                leaning=a["leaning"],
                oe=a["oe"],
                co=a["co"],
                ex=a["ex"],
                ag=a["ag"],
                ne=a["ne"],
                language=a["language"],
                education_level=a["education"],
                round_actions=a["round_actions"],
                nationality=a["nationality"],
                toxicity=a["toxicity"],
                age=a["age"],
                gender=a["gender"],
                crecsys=a["crecsys"],
                frecsys=a["frecsys"],
                profile_pic=a["profile_pic"],
                cover_image=a.get("cover_image", ""),
                daily_activity_level=a.get("daily_activity_level", 1),
                profession=a.get("profession", ""),
                activity_profile=activity_profile_id,
            )
            db.session.add(agent)
            db.session.commit()

            if a.get("profile"):
                agent_profile = Agent_Profile(agent_id=agent.id, profile=a["profile"])
                db.session.add(agent_profile)
                db.session.commit()
            feature_entries = feature_entries_from_population_agent_payload(a)
            if feature_entries:
                replace_agent_custom_features(agent.id, feature_entries)
                db.session.commit()
            db.session.execute(delete(Agent_Ext).filter_by(agent_id=agent.id))
            for ext_entry in agent_ext_entries_from_population_agent_payload(a):
                agent_ext_rows.append(
                    Agent_Ext(
                        agent_id=agent.id,
                        feature_name=ext_entry["feature_name"],
                        feature_value=ext_entry["feature_value"],
                    )
                )
        else:
            feature_entries = feature_entries_from_population_agent_payload(a)
            if feature_entries:
                replace_agent_custom_features(agent.id, feature_entries)
                db.session.commit()
            db.session.execute(delete(Agent_Ext).filter_by(agent_id=agent.id))
            for ext_entry in agent_ext_entries_from_population_agent_payload(a):
                agent_ext_rows.append(
                    Agent_Ext(
                        agent_id=agent.id,
                        feature_name=ext_entry["feature_name"],
                        feature_value=ext_entry["feature_value"],
                    )
                )

        agent_populations.append(
            Agent_Population(agent_id=agent.id, population_id=population.id)
        )

    if agent_ext_rows:
        db.session.bulk_save_objects(agent_ext_rows)
    if agent_populations:
        db.session.bulk_save_objects(agent_populations)
    db.session.commit()

    # add the pages to the database
    for p in data.get("pages", []):
        # check if the page already exists
        page = db.session.scalars(select(Page).filter_by(name=p["name"])).first()
        if not page:
            # Resolve activity_profile by name if provided
            page_activity_profile_id = None
            if p.get("activity_profile"):
                page_activity_profile_obj = db.session.scalars(
                    select(ActivityProfile).filter_by(name=p["activity_profile"])
                ).first()
                if page_activity_profile_obj:
                    page_activity_profile_id = page_activity_profile_obj.id

            page = Page(
                name=p["name"],
                descr=p["descr"],
                page_type=p["page_type"],
                feed=p["feed"],
                keywords=p["keywords"],
                logo=p["logo"],
                pg_type=p["pg_type"],
                leaning=p["leaning"],
                activity_profile=page_activity_profile_id,
            )
            db.session.add(page)
            db.session.commit()

        page_population = Page_Population(page_id=page.id, population_id=population.id)
        db.session.add(page_population)
        db.session.commit()

    return redirect(request.referrer)


@population.route("/admin/update_population_recsys/<int:uid>", methods=["POST"])
@login_required
def update_recsys(uid):
    """Update recsys."""
    check_privileges(current_user.username)

    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")

    # get populations for client uid
    population = db.session.scalars(select(Population).filter_by(id=uid)).first()
    # get agents for the populations
    agents = db.session.scalars(
        select(Agent_Population).filter_by(population_id=uid)
    ).all()

    # updating the recommenders of the agents in the specific simulation instance (not in the population)
    for agent in agents:
        ag = db.session.scalars(select(Agent).filter_by(id=agent.agent_id)).first()
        ag.frecsys = frecsys_type
        ag.crecsys = recsys_type
        db.session.commit()

    population.crecsys = recsys_type
    population.frecsys = frecsys_type

    db.session.commit()
    return redirect(request.referrer)


@population.route("/admin/update_population_llm/<int:uid>", methods=["POST"])
@login_required
def update_llm(uid):
    """Update llm."""
    check_privileges(current_user.username)

    user_type = request.form.get("user_type")

    # get populations for client uid
    population = db.session.scalars(select(Population).filter_by(id=uid)).first()
    # get agents for the populations
    agents = db.session.scalars(
        select(Agent_Population).filter_by(population_id=population.id)
    ).all()

    for agent in agents:
        ag = db.session.scalars(select(Agent).filter_by(id=agent.agent_id)).first()
        ag.ag_type = user_type
        db.session.commit()

    population.llm = user_type

    db.session.commit()
    return redirect(request.referrer)


@population.route("/admin/merge_populations", methods=["POST"])
@login_required
def merge_populations():
    """
    Merge multiple populations into a new one.

    Creates a new population and assigns agents and pages from selected populations,
    avoiding duplicates.

    Form data:
        merged_population_name: Name for the new merged population
        selected_population_ids: Comma-separated list of population IDs to merge

    Returns:
        Redirect to populations page
    """
    check_privileges(current_user.username)
    ensure_population_username_type_column()

    merged_name = request.form.get("merged_population_name")
    selected_ids = request.form.get("selected_population_ids")
    merged_population_type = normalize_population_username_type(
        request.form.get("merged_population_type")
    )

    if not merged_name or not selected_ids:
        flash(
            _(
                "Please provide a population name and select at least 2 populations to merge."
            )
        )
        return redirect(request.referrer)

    # Parse the selected population IDs
    try:
        population_ids = [
            int(pid.strip()) for pid in selected_ids.split(",") if pid.strip()
        ]
    except ValueError:
        flash(_("Invalid population IDs provided."))
        return redirect(request.referrer)

    if len(population_ids) < 2:
        flash(_("Please select at least 2 populations to merge."))
        return redirect(request.referrer)

    # Check if merged population name already exists
    existing_pop = db.session.scalars(
        select(Population).filter_by(name=merged_name)
    ).first()
    if existing_pop:
        flash(
            _(
                "Population with name '%(merged_name)s' already exists.",
                merged_name=merged_name,
            )
        )
        return redirect(request.referrer)

    # Verify all selected populations exist
    source_populations = []
    for pop_id in population_ids:
        pop = db.session.scalars(select(Population).filter_by(id=pop_id)).first()
        if not pop:
            flash(_("Population with ID %(pop_id)s not found.", pop_id=pop_id))
            return redirect(request.referrer)
        source_populations.append(pop)

    # populations of any platform can be merged: the custom fields of the agents are kept with them

    # Collect unique agent IDs from all selected populations (optimized query)
    agent_populations = db.session.scalars(
        select(Agent_Population).filter(
            Agent_Population.population_id.in_(population_ids)
        )
    ).all()
    unique_agent_ids = set(ap.agent_id for ap in agent_populations)

    # Collect unique page IDs from all selected populations (optimized query)
    page_populations = db.session.scalars(
        select(Page_Population).filter(
            Page_Population.population_id.in_(population_ids)
        )
    ).all()
    unique_page_ids = set(pp.page_id for pp in page_populations)

    # Fetch all unique agents to aggregate their properties
    agents = (
        db.session.scalars(select(Agent).filter(Agent.id.in_(unique_agent_ids))).all()
        if unique_agent_ids
        else []
    )

    # Aggregate properties from all agents
    ages = [a.age for a in agents if a.age is not None]
    age_min = min(ages) if ages else None
    age_max = max(ages) if ages else None

    education_set = set(a.education_level for a in agents if a.education_level)
    education_levels = ",".join(sorted(education_set)) if education_set else None

    leanings_set = set(a.leaning for a in agents if a.leaning)
    leanings = ",".join(sorted(leanings_set)) if leanings_set else None

    nationalities_set = set(a.nationality for a in agents if a.nationality)
    nationalities = ",".join(sorted(nationalities_set)) if nationalities_set else None

    languages_set = set(a.language for a in agents if a.language)
    languages = ",".join(sorted(languages_set)) if languages_set else None

    toxicity_set = set(a.toxicity for a in agents if a.toxicity)
    toxicity = ",".join(sorted(toxicity_set)) if toxicity_set else None

    # Get most common LLM type
    llm_types = [a.ag_type for a in agents if a.ag_type]
    llm = max(set(llm_types), key=llm_types.count) if llm_types else None

    # Get most common recommendation systems
    crecsys_list = [a.crecsys for a in agents if a.crecsys]
    crecsys = max(set(crecsys_list), key=crecsys_list.count) if crecsys_list else None

    frecsys_list = [a.frecsys for a in agents if a.frecsys]
    frecsys = max(set(frecsys_list), key=frecsys_list.count) if frecsys_list else None

    # Aggregate interests from source populations
    interests_set = set()
    for pop in source_populations:
        if pop.interests:
            interests_set.update(pop.interests.split(","))
    interests = ",".join(sorted(interests_set)) if interests_set else None

    # Get LLM URL from first population that has it
    llm_url = None
    for pop in source_populations:
        if pop.llm_url:
            llm_url = pop.llm_url
            break

    # Create the new merged population with detailed description and all aggregated properties
    source_names = ", ".join([pop.name for pop in source_populations])
    merged_population = Population(
        name=merged_name,
        descr=f"Merged from: {source_names}",
        size=len(unique_agent_ids),
        llm=llm,
        age_min=age_min,
        age_max=age_max,
        education=education_levels,
        leanings=leanings,
        nationalities=nationalities,
        languages=languages,
        interests=interests,
        toxicity=toxicity,
        crecsys=crecsys,
        frecsys=frecsys,
        llm_url=llm_url,
        username_type=merged_population_type,
    )
    db.session.add(merged_population)
    db.session.flush()  # Flush to get the ID without committing

    # Add unique agents to the new population
    for agent_id in unique_agent_ids:
        agent_population = Agent_Population(
            agent_id=agent_id, population_id=merged_population.id
        )
        db.session.add(agent_population)

    # Add unique pages to the new population
    for page_id in unique_page_ids:
        page_population = Page_Population(
            page_id=page_id, population_id=merged_population.id
        )
        db.session.add(page_population)

    # Single commit for all operations to ensure atomicity
    db.session.commit()

    flash(
        _(
            "Successfully created merged population '%(merged_name)s' with %(unique_agent_ids)s agents and %(unique_page_ids)s pages.",
            merged_name=merged_name,
            unique_agent_ids=len(unique_agent_ids),
            unique_page_ids=len(unique_page_ids),
        )
    )
    return populations()


# ---------------------------------------------------------------------------------------------------
# Dating populations (plan S2, IR-D-05, decision D-10): one ``population`` row, standard ``agents`` rows and the
# dating-only fields as custom features of the agents; no file
# ---------------------------------------------------------------------------------------------------
def _dating_population_or_none(uid):
    from y_web.src.dating.population import is_dating_population

    pop = db.session.scalars(select(Population).filter_by(id=uid)).first()
    return pop if pop is not None and is_dating_population(pop) else None


def _unique_population_name(base_name):
    name = base_name
    suffix = 0
    while db.session.scalars(select(Population).filter_by(name=name)).first():
        suffix += 1
        tail = f"_{suffix}"
        name = f"{base_name[: 50 - len(tail)]}{tail}"
    return name


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
    from y_web.src.dating import population as dp

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


def _appearance_form_context():
    """Defaults and availability of the Appearance section (independent of the platforms)."""
    from y_web.src.agents import profile_pictures as pp

    return {
        "appearance_defaults": pp.defaults(),
        "images_available": pp.available(),
    }


@population.route("/media/agents/<path:filename>")
def agent_media(filename):
    """The profile pictures generated for the agents (media folder); public, like the avatars."""
    from flask import abort, send_from_directory

    from y_web.src.agents import profile_pictures as pp

    if filename != os.path.basename(filename) or filename.startswith("."):
        abort(404)
    return send_from_directory(pp.media_dir(), filename)


def _dating_form_context():
    """Lists the Dating creation form offers next to the free-text weights (same catalogues as the standard form)."""
    from y_web.src.dating import population as dp

    return {
        "dating_available": dp.runtime_available(current_user),
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
        "dating_appearance_labels": dp.APPEARANCE_LABELS,
        "dating_defaults": {
            "intents": dp.INTENT_DEFAULTS,
            "seeking": dp.SEEKING_DEFAULTS,
            "seeking_sets": dp.SEEKING_SETS,
            "appearance": dp.APPEARANCE_DEFAULTS,
            "appearance_options": dp.APPEARANCE_OPTIONS,
            "latent": dp.LATENT_DEFAULTS,
            "affective": dp.AFFECTIVE_DEFAULT_RANGE,
            "activity": dp.ACTIVITY_DEFAULT_RANGE,
            "height": dp.HEIGHT_DEFAULT_RANGE,
            "glasses": dp.GLASSES_DEFAULT_PERCENT,
            "photos": dp.PHOTOS_DEFAULT_RANGE,
            "age_window": dp.AGE_WINDOW_DEFAULT_RANGE,
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
    from y_web.src.dating import population as dp

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
    from y_web.src.dating import population as dp

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
    from y_web.src.dating import population as dp

    if population is None or not dp.has_dating_fields(population):
        return None
    try:
        data = dp.load_document(uid)
    except Exception:  # the runtime that describes the fields is not installed: no card, the statistics remain
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

    from y_web.src.dating import population as dp

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
