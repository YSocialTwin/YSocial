"""
Population management routes.

Administrative routes for creating, configuring, and managing agent populations
including demographics, personality traits, recommendation systems, and
association with experiments and pages.
"""

import json
import os

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
)
from flask_login import current_user, login_required

from y_web import db
from y_web.models import (
    ActivityProfile,
    AgeClass,
    Agent,
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
from y_web.utils import (
    generate_population,
    get_llm_models,
    get_ollama_models,
)
from y_web.utils.desktop_file_handler import send_file_desktop
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status

population = Blueprint("population", __name__)


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

    name = request.form.get("empty_population_name")
    descr = request.form.get("empty_population_descr")

    # add the experiment to the database
    pop = Population(name=name, descr=descr)

    db.session.add(pop)
    db.session.commit()

    return populations()


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
    name = request.form.get("pop_name")
    descr = request.form.get("pop_descr")
    n_agents = request.form.get("n_agents")
    user_type = request.form.get("user_type")

    llm = request.form.get("host_llm")

    # Get gender distribution
    male_percentage = int(request.form.get("male_percentage", "50"))
    female_percentage = int(request.form.get("female_percentage", "50"))
    gender_distribution = {"male": male_percentage, "female": female_percentage}

    education_levels = request.form.getlist("education_levels")
    education_levels = ",".join(education_levels)
    political_leanings = request.form.getlist("political_leanings")
    political_leanings = ",".join(political_leanings)

    toxicity_levels = request.form.getlist("toxicity_levels")
    toxicity_levels = ",".join(toxicity_levels)

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

    percentages = {
        "education": education_percentages,
        "political_leanings": political_percentages,
        "toxicity_levels": toxicity_percentages,
        "age_classes": age_classes_percentages,
        "gender": gender_distribution,
    }

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

    population = Population(
        name=name,
        descr=descr,
        size=n_agents,
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

    generate_population(name, percentages, actions_config, profession_backgrounds)

    from y_web.telemetry import Telemetry

    telemetry = Telemetry()
    telemetry.log_event(
        {
            "event": "create_population",
            "data":{
                "n_agents": n_agents,
                "interests": interests,
            }
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
    query = Population.query

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
            if name not in ["name", "descr", "size"]:
                name = "name"
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
    education_dict = {str(e.id): e.education_level for e in Education.query.all()}
    leanings_dict = {str(l.id): l.leaning for l in Leanings.query.all()}
    toxicity_dict = {str(t.id): t.toxicity_level for t in Toxicity_Levels.query.all()}

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

    # Regular expression to match model values

    models = get_llm_models()  # Use generic function for any LLM server
    llm_backend = llm_backend_status()
    leanings = Leanings.query.all()
    education_levels = Education.query.all()
    nationalities = Nationalities.query.all()
    languages = Languages.query.all()
    toxicity_levels = Toxicity_Levels.query.all()
    age_classes = AgeClass.query.all()
    activity_profiles = ActivityProfile.query.all()

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
    )


@population.route("/admin/population_details/<int:uid>")
@login_required
def population_details(uid):
    """Handle population details operation."""
    check_privileges(current_user.username)
    # get population details
    population = Population.query.filter_by(id=uid).first()

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

    # Fetch label mappings from database
    leanings_map = {str(l.id): l.leaning for l in Leanings.query.all()}
    education_map = {str(e.id): e.education_level for e in Education.query.all()}
    toxicity_map = {str(t.id): t.toxicity_level for t in Toxicity_Levels.query.all()}

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
    age_classes = AgeClass.query.order_by(AgeClass.age_start).all()
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
            profile = ActivityProfile.query.get(a[0].activity_profile)
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

    crecsys = Content_Recsys.query.all()
    frecsys = Follow_Recsys.query.all()

    return render_template(
        "admin/population_details.html",
        population=population,
        population_experiments=exps,
        agents=agents,
        data=dd,
        activity_profiles=agent_profiles,
        models=models,
        llm_backend=llm_backend,
        crecsys=crecsys,
        frecsys=frecsys,
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
    ap = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=experiment_id
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

    population = Population.query.filter_by(id=uid).first()

    # check if the population is assigned to any experiment
    pop_exp = Population_Experiment.query.filter_by(id_population=uid).first()
    if pop_exp:
        # if the population is assigned to any experiment, do not delete raise a warning
        flash("Population is assigned to an experiment. Cannot delete.")
        return populations()

    db.session.delete(population)
    db.session.commit()

    # delete agent_population entries
    agent_population = Agent_Population.query.filter_by(population_id=uid).all()
    for ap in agent_population:
        db.session.delete(ap)
        db.session.commit()

    # delete population_experiment entries
    population_experiment = Population_Experiment.query.filter_by(
        id_population=uid
    ).all()
    for pe in population_experiment:
        db.session.delete(pe)
        db.session.commit()

    return populations()


@population.route("/admin/download_population/<int:uid>")
@login_required
def download_population(uid):
    """Download population."""
    check_privileges(current_user.username)

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
    population = Population.query.filter_by(id=uid).first()

    res = {
        "population_data": {
            "name": population.name,
            "descr": population.descr,
        },
        "agents": [],
        "pages": [],
    }

    for a in agents:
        res["agents"].append(
            {
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
                "daily_activity_level": a[0].daily_activity_level,
                "profile": (
                    Agent_Profile.query.filter_by(agent_id=a[0].id).first().profile
                    if Agent_Profile.query.filter_by(agent_id=a[0].id).first()
                    is not None
                    else None
                ),
            }
        )

    for p in pages:
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
            }
        )

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # Ensure temp_data directory exists
    temp_data_dir = os.path.join(BASE_DIR, f"experiments{os.sep}temp_data")
    os.makedirs(temp_data_dir, exist_ok=True)

    filename = os.path.join(temp_data_dir, f"population_{population.name}.json")
    json.dump(res, open(filename, "w"), indent=4)

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

    population_file = request.files["population_file"]

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # Ensure temp_data directory exists
    temp_data_dir = os.path.join(BASE_DIR, f"experiments{os.sep}temp_data")
    os.makedirs(temp_data_dir, exist_ok=True)

    filename = os.path.join(temp_data_dir, population_file.filename)
    population_file.save(filename)

    data = json.load(open(filename, "r"))

    # check if the population already exists
    population = Population.query.filter_by(
        name=data["population_data"]["name"]
    ).first()
    if population:
        flash("Population already exists.")
        return redirect(request.referrer)

    # add the population to the database
    population = Population(
        name=data["population_data"]["name"], descr=data["population_data"]["descr"]
    )
    db.session.add(population)
    db.session.commit()

    # add the agents to the database
    for a in data["agents"]:
        # check if the agent already exists
        agent = Agent.query.filter_by(name=a["name"]).first()
        if not agent:
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
                daily_activity_level=(
                    a["daily_activity_level"] if "daily_activity_level" in a else 1
                ),
            )
            db.session.add(agent)
            db.session.commit()

            if a["profile"]:
                agent_profile = Agent_Profile(agent_id=agent.id, profile=a["profile"])
                db.session.add(agent_profile)
                db.session.commit()

        agent_population = Agent_Population(
            agent_id=agent.id, population_id=population.id
        )
        db.session.add(agent_population)
        db.session.commit()

    # add the pages to the database
    for p in data["pages"]:
        # check if the page already exists
        page = Page.query.filter_by(name=p["name"]).first()
        if not page:
            page = Page(
                name=p["name"],
                descr=p["descr"],
                page_type=p["page_type"],
                feed=p["feed"],
                keywords=p["keywords"],
                logo=p["logo"],
                pg_type=p["pg_type"],
                leaning=p["leaning"],
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
    population = Population.query.filter_by(id=uid).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=uid).all()

    # updating the recommenders of the agents in the specific simulation instance (not in the population)
    for agent in agents:
        ag = Agent.query.filter_by(id=agent.agent_id).first()
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
    population = Population.query.filter_by(id=uid).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=population.id).all()

    for agent in agents:
        ag = Agent.query.filter_by(id=agent.agent_id).first()
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

    merged_name = request.form.get("merged_population_name")
    selected_ids = request.form.get("selected_population_ids")

    if not merged_name or not selected_ids:
        flash(
            "Please provide a population name and select at least 2 populations to merge."
        )
        return redirect(request.referrer)

    # Parse the selected population IDs
    try:
        population_ids = [
            int(pid.strip()) for pid in selected_ids.split(",") if pid.strip()
        ]
    except ValueError:
        flash("Invalid population IDs provided.")
        return redirect(request.referrer)

    if len(population_ids) < 2:
        flash("Please select at least 2 populations to merge.")
        return redirect(request.referrer)

    # Check if merged population name already exists
    existing_pop = Population.query.filter_by(name=merged_name).first()
    if existing_pop:
        flash(f"Population with name '{merged_name}' already exists.")
        return redirect(request.referrer)

    # Verify all selected populations exist
    source_populations = []
    for pop_id in population_ids:
        pop = Population.query.filter_by(id=pop_id).first()
        if not pop:
            flash(f"Population with ID {pop_id} not found.")
            return redirect(request.referrer)
        source_populations.append(pop)

    # Collect unique agent IDs from all selected populations (optimized query)
    agent_populations = Agent_Population.query.filter(
        Agent_Population.population_id.in_(population_ids)
    ).all()
    unique_agent_ids = set(ap.agent_id for ap in agent_populations)

    # Collect unique page IDs from all selected populations (optimized query)
    page_populations = Page_Population.query.filter(
        Page_Population.population_id.in_(population_ids)
    ).all()
    unique_page_ids = set(pp.page_id for pp in page_populations)

    # Fetch all unique agents to aggregate their properties
    agents = (
        Agent.query.filter(Agent.id.in_(unique_agent_ids)).all()
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
        f"Successfully created merged population '{merged_name}' with {len(unique_agent_ids)} agents and {len(unique_page_ids)} pages."
    )
    return populations()
