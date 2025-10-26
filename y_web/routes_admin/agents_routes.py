"""
Agent management routes.

Administrative routes for creating, editing, and managing individual AI agents
including their profiles, demographics, personality traits, and behavioral
settings.
"""

import random
import re

from flask import Blueprint, flash, render_template, request
from flask_login import current_user, login_required

from y_web import db
from y_web.models import (
    ActivityProfile,
    Agent,
    Agent_Population,
    Agent_Profile,
    Content_Recsys,
    Education,
    Follow_Recsys,
    Languages,
    Leanings,
    Nationalities,
    Population,
    Profession,
    Toxicity_Levels,
)
from y_web.utils import get_llm_models, get_ollama_models
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status

agents = Blueprint("agents", __name__)


@agents.route("/admin/agents")
@login_required
def agent_data():
    """
    Display agent management page.

    Returns:
        Rendered agent data template with available models
    """
    check_privileges(current_user.username)

    models = get_llm_models()  # Use generic function for any LLM server

    populations = Population.query.all()
    ollamas = ollama_status()
    llm_backend = llm_backend_status()

    # get professions
    professions = Profession.query.all()
    nationalities = Nationalities.query.all()
    educations = Education.query.all()
    leanings = Leanings.query.all()
    languages = Languages.query.all()
    toxicity_levels = Toxicity_Levels.query.all()
    crecsys = Content_Recsys.query.all()
    frecsys = Follow_Recsys.query.all()
    activity_profiles = ActivityProfile.query.all()

    return render_template(
        "admin/agents.html",
        populations=populations,
        models=models,
        ollamas=ollamas,
        llm_backend=llm_backend,
        professions=professions,
        nationalities=nationalities,
        education_levels=educations,
        leanings=leanings,
        languages=languages,
        toxicity_levels=toxicity_levels,
        crecsys=crecsys,
        frecsys=frecsys,
        activity_profiles=activity_profiles,
    )


@agents.route("/admin/agents_data")
@login_required
def agents_data():
    """Display agents data page."""
    query = Agent.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Agent.name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in [
                "name",
                "profession",
                "age",
                "daily_activity_level",
                "activity_profile",
            ]:
                name = "name"
            # Handle activity_profile sorting by joining with ActivityProfile table
            if name == "activity_profile":
                col = ActivityProfile.name
                if direction == "-":
                    col = col.desc()
                order.append(col)
            else:
                col = getattr(Agent, name)
                if direction == "-":
                    col = col.desc()
                order.append(col)
        if order:
            # Join with ActivityProfile if sorting by activity_profile
            if any("activity_profile" in str(o) for o in order):
                query = query.outerjoin(
                    ActivityProfile, Agent.activity_profile == ActivityProfile.id
                )
            query = query.order_by(*order)

    # pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    # response
    res = query.all()

    data = []
    for agent in res:
        activity_profile_data = None
        if agent.activity_profile:
            profile = ActivityProfile.query.get(agent.activity_profile)
            if profile:
                activity_profile_data = {"name": profile.name, "hours": profile.hours}

        data.append(
            {
                "id": agent.id,
                "name": " ".join(re.findall("[A-Z][^A-Z]*", agent.name)),
                "age": agent.age,
                "profession": agent.profession,
                "daily_activity_level": agent.daily_activity_level,
                "activity_profile": activity_profile_data,
            }
        )

    return {
        "data": data,
        "total": total,
    }


@agents.route("/admin/create_agent", methods=["POST"])
@login_required
def create_agent():
    """
    Create a new AI agent from form data.

    Returns:
        Redirect to agent data page
    """
    check_privileges(current_user.username)

    user_type = request.form.get("user_type")
    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")
    population = request.form.get("population")
    name = request.form.get("name")
    age = request.form.get("age")
    gender = request.form.get("gender")
    language = request.form.get("language")
    nationality = request.form.get("nationality")
    education_level = request.form.get("education_level")
    leaning = request.form.get("leaning")
    oe = request.form.get("oe")
    co = request.form.get("co")
    ex = request.form.get("ex")
    ag = request.form.get("ag")
    ne = request.form.get("ne")
    toxicity = request.form.get("toxicity")
    alt_profile = request.form.get("alt_profile")
    profile_pic = request.form.get("profile_pic")
    daily_activity_level = request.form.get("daily_user_activity")
    profession = request.form.get("profession")

    agent = Agent(
        name=name,
        age=age,
        ag_type=user_type,
        leaning=leaning,
        ag=ag,
        co=co,
        oe=oe,
        ne=ne,
        ex=ex,
        language=language,
        education_level=education_level,
        round_actions=random.randint(1, 3),
        toxicity=toxicity,
        nationality=nationality,
        gender=gender,
        crecsys=recsys_type,
        frecsys=frecsys_type,
        profile_pic=profile_pic,
        daily_activity_level=int(daily_activity_level),
        profession=profession,
    )

    db.session.add(agent)
    db.session.commit()

    if population != "none":
        ap = Agent_Population(agent_id=agent.id, population_id=population)
        db.session.add(ap)
        db.session.commit()

    if alt_profile != "":
        agent_profile = Agent_Profile(agent_id=agent.id, profile=alt_profile)
        db.session.add(agent_profile)
        db.session.commit()

    return agent_data()


@agents.route("/admin/agent_details/<int:uid>")
@login_required
def agent_details(uid):
    """Handle agent details operation."""
    check_privileges(current_user.username)
    # get agent details
    agent = Agent.query.filter_by(id=uid).first()

    # get agent populations along with population names and ids
    agent_populations = (
        db.session.query(Agent_Population, Population)
        .join(Population)
        .filter(Agent_Population.agent_id == uid)
        .all()
    )

    # get agent profiles
    agent_profiles = Agent_Profile.query.filter_by(agent_id=uid).first()

    pops = [(p[1].name, p[1].id) for p in agent_populations]

    # get all populations
    populations = Population.query.all()

    # Get agent's activity profile
    activity_profile = None
    if agent.activity_profile:
        activity_profile = ActivityProfile.query.filter_by(
            id=agent.activity_profile
        ).first()

    ollamas = ollama_status()
    llm_backend = llm_backend_status()

    return render_template(
        "admin/agent_details.html",
        agent=agent,
        agent_populations=pops,
        profile=agent_profiles,
        populations=populations,
        activity_profile=activity_profile,
        ollamas=ollamas,
        llm_backend=llm_backend,
    )


@agents.route("/admin/add_to_population", methods=["POST"])
@login_required
def add_to_population():
    """
    Add an agent to a population from form data.

    Returns:
        Redirect to agent details page
    """
    check_privileges(current_user.username)

    agent_id = request.form.get("agent_id")
    population_id = request.form.get("population_id")

    # check if the agent is already in the population
    ap = Agent_Population.query.filter_by(
        agent_id=agent_id, population_id=population_id
    ).first()
    if ap:
        return agent_details(agent_id)

    ap = Agent_Population(agent_id=agent_id, population_id=population_id)

    db.session.add(ap)
    db.session.commit()

    return agent_details(agent_id)


@agents.route("/admin/delete_agent/<int:uid>")
@login_required
def delete_agent(uid):
    """Delete agent."""
    check_privileges(current_user.username)

    agent = Agent.query.filter_by(id=uid).first()

    # check if the agent is assigned to any population
    agent_pop = Agent_Population.query.filter_by(agent_id=uid).first()
    if agent_pop:
        # if the agent is assigned to any population, do not delete raise a warning
        flash("Agent is assigned to a population. Cannot delete.")
        return agent_data()

    db.session.delete(agent)
    db.session.commit()

    # delete agent_population entries
    agent_population = Agent_Population.query.filter_by(agent_id=uid).all()
    for ap in agent_population:
        db.session.delete(ap)
        db.session.commit()

    # delete agent_profile entries
    agent_profile = Agent_Profile.query.filter_by(agent_id=uid).all()
    for ap in agent_profile:
        db.session.delete(ap)
        db.session.commit()

    return agent_data()


@agents.route("/admin/delete_orphaned_agents", methods=["POST"])
@login_required
def delete_orphaned_agents():
    """Delete all agents that do not belong to any population."""
    check_privileges(current_user.username)

    # Find all agents that don't have any population assignment
    # Using a subquery to find agents not in Agent_Population
    orphaned_agents = (
        Agent.query.outerjoin(Agent_Population, Agent.id == Agent_Population.agent_id)
        .filter(Agent_Population.id == None)
        .all()
    )

    deleted_count = 0
    for agent in orphaned_agents:
        # Delete associated agent profiles first
        agent_profiles = Agent_Profile.query.filter_by(agent_id=agent.id).all()
        for profile in agent_profiles:
            db.session.delete(profile)

        # Delete the agent
        db.session.delete(agent)
        deleted_count += 1

    db.session.commit()

    flash(f"Successfully deleted {deleted_count} orphaned agent(s).")
    return agent_data()
