"""
Population management routes.

Administrative routes for creating, configuring, and managing agent populations
including demographics, personality traits, recommendation systems, and
association with experiments and pages.
"""

import json
import os
from pydoc_data.topics import topics

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
)
from flask_login import current_user, login_required

from y_web import db
from y_web.models import (
    ActivityProfile,
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
    Topic_List,
    Toxicity_Levels,
)
from y_web.utils import (
    generate_population,
    get_llm_models,
    get_ollama_models,
)
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
        pop_name, pop_descr, n_agents, user_type, age_min, age_max,
        education_levels, political_leanings, toxicity_levels,
        nationalities, languages, tags (interests), crecsys, frecsys

    Returns:
        Redirect to populations list
    """
    check_privileges(current_user.username)
    name = request.form.get("pop_name")
    descr = request.form.get("pop_descr")
    n_agents = request.form.get("n_agents")
    user_type = request.form.get("user_type")
    age_min = int(request.form.get("age_min"))
    age_max = int(request.form.get("age_max"))

    llm = request.form.get("host_llm")

    education_levels = request.form.getlist("education_levels")
    education_levels = ",".join(education_levels)
    political_leanings = request.form.getlist("political_leanings")
    political_leanings = ",".join(political_leanings)

    toxicity_levels = request.form.getlist("toxicity_levels")
    toxicity_levels = ",".join(toxicity_levels)

    nationalities = request.form.get("nationalities")
    languages = request.form.get("languages")
    interests = request.form.get("tags")

    frecsys = request.form.get("frecsys_type")
    crecsys = request.form.get("recsys_type")

    # Get activity profiles data from the hidden field
    activity_profiles_data = request.form.get("activity_profiles_data", "[]")
    try:
        activity_profiles_json = json.loads(activity_profiles_data)
    except:
        activity_profiles_json = []

    population = Population(
        name=name,
        descr=descr,
        size=n_agents,
        llm=user_type,
        age_min=age_min,
        age_max=age_max,
        education=education_levels,
        leanings=political_leanings,
        nationalities=nationalities,
        languages=languages,
        interests=interests,
        toxicity=toxicity_levels,
        frecsys=frecsys,
        crecsys=crecsys,
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

    generate_population(name)

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

    return {
        "data": [
            {"id": pop.id, "name": pop.name, "descr": pop.descr, "size": pop.size}
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
    ollamas = ollama_status()
    llm_backend = llm_backend_status()
    leanings = Leanings.query.all()
    education_levels = Education.query.all()
    nationalities = Nationalities.query.all()
    languages = Languages.query.all()
    toxicity_levels = Toxicity_Levels.query.all()
    crecsys = Content_Recsys.query.all()
    frecsys = Follow_Recsys.query.all()
    activity_profiles = ActivityProfile.query.all()

    return render_template(
        "admin/populations.html",
        models=models,
        ollamas=ollamas,
        llm_backend=llm_backend,
        leanings=leanings,
        education_levels=education_levels,
        nationalities=nationalities,
        languages=languages,
        toxicity_levels=toxicity_levels,
        crecsys=crecsys,
        frecsys=frecsys,
        activity_profiles=activity_profiles,
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

    ln = {"leanings": [], "total": []}

    for a in agents:
        if a[0].leaning in ln["leanings"]:
            ln["total"][ln["leanings"].index(a[0].leaning)] += 1
        else:
            ln["leanings"].append(a[0].leaning)
            ln["total"].append(1)

    age = {"age": [], "total": []}

    for a in agents:
        if a[0].age in age["age"]:
            age["total"][age["age"].index(a[0].age)] += 1
        else:
            age["age"].append(a[0].age)
            age["total"].append(1)

    sorted_age = dict(sorted(zip(age["age"], age["total"])))

    # Convert back to dictionary format with separate lists
    age = {"age": list(sorted_age.keys()), "total": list(sorted_age.values())}

    edu = {"education": [], "total": []}

    for a in agents:
        if a[0].education_level in edu["education"]:
            edu["total"][edu["education"].index(a[0].education_level)] += 1
        else:
            edu["education"].append(a[0].education_level)
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
        if a[0].toxicity in tox["toxicity"]:
            tox["total"][tox["toxicity"].index(a[0].toxicity)] += 1
        else:
            if a[0].toxicity is not None:
                tox["toxicity"].append(a[0].toxicity)
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

    dd = {
        "age": age,
        "leaning": ln,
        "education": edu,
        "nationalities": nat,
        "languages": lang,
        "toxicity": tox,
        "activity": activity,
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
        population_updated_details = {
            "id": population.id,
            "name": population.name,
            "descr": population.descr,
            "size": len(agents),
            "llm": max(llm, key=llm.get),
            "age_min": min(dd["age"]["age"]),
            "age_max": max(dd["age"]["age"]),
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
    ollamas = ollama_status()
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
        ollamas=ollamas,
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

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    filename = f"{BASE_DIR}{os.sep}experiments{os.sep}temp_data{os.sep}population_{population.name}.json"
    json.dump(res, open(filename, "w"), indent=4)

    return send_file(filename, as_attachment=True)


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

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    filename = f"{BASE_DIR}{os.sep}experiments{os.sep}temp_data{os.sep}{population_file.filename}".replace(
        f"{os.sep}{os.sep}", f"{os.sep}"
    )
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
        flash("Please provide a population name and select at least 2 populations to merge.")
        return redirect(request.referrer)

    # Parse the selected population IDs
    try:
        population_ids = [int(pid.strip()) for pid in selected_ids.split(",") if pid.strip()]
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

    # Create the new merged population with detailed description
    source_names = ", ".join([pop.name for pop in source_populations])
    merged_population = Population(
        name=merged_name,
        descr=f"Merged from: {source_names}"
    )
    db.session.add(merged_population)
    db.session.commit()

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

    # Add unique agents to the new population
    for agent_id in unique_agent_ids:
        agent_population = Agent_Population(
            agent_id=agent_id,
            population_id=merged_population.id
        )
        db.session.add(agent_population)

    # Add unique pages to the new population
    for page_id in unique_page_ids:
        page_population = Page_Population(
            page_id=page_id,
            population_id=merged_population.id
        )
        db.session.add(page_population)

    # Update the size of the new population
    merged_population.size = len(unique_agent_ids)
    
    # Single commit for all operations to ensure atomicity
    db.session.commit()

    flash(f"Successfully created merged population '{merged_name}' with {len(unique_agent_ids)} agents and {len(unique_page_ids)} pages.")
    return populations()
