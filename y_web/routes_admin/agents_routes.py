import random

from flask import (
    Blueprint,
    render_template,
    request,
)
from flask_login import login_required, current_user

from y_web.models import (
    Population,
    Agent,
    Agent_Population,
    Agent_Profile,
)
from y_web.utils import get_ollama_models

from y_web import db
from y_web.utils.miscellanea import check_privileges
import re

agents = Blueprint("agents", __name__)


@agents.route("/admin/agents")
@login_required
def agent_data():
    check_privileges(current_user.username)

    models = get_ollama_models()

    populations = Population.query.all()
    return render_template("admin/agents.html", populations=populations, models=models)


@agents.route("/admin/agents_data")
@login_required
def agents_data():
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
            if name not in ["name", "gender", "age", "nationality"]:
                name = "name"
            col = getattr(Agent, name)
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
            {
                "id": agent.id,
                "name": " ".join(re.findall("[A-Z][^A-Z]*", agent.name)),
                "age": agent.age,
                "gender": agent.gender,
                "nationality": agent.nationality,
            }
            for agent in res
        ],
        "total": total,
    }


@agents.route("/admin/create_agent", methods=["POST"])
@login_required
def create_agent():
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
    interests = request.form.get("interests")
    oe = request.form.get("oe")
    co = request.form.get("co")
    ex = request.form.get("ex")
    ag = request.form.get("ag")
    ne = request.form.get("ne")
    toxicity = request.form.get("toxicity")
    alt_profile = request.form.get("alt_profile")
    profile_pic = request.form.get("profile_pic")
    daily_activity_level = request.form.get("daily_user_activity")

    agent = Agent(
        name=name,
        age=age,
        ag_type=user_type,
        leaning=leaning,
        interests=interests,
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

    return render_template(
        "admin/agent_details.html",
        agent=agent,
        agent_populations=pops,
        profile=agent_profiles,
        populations=populations,
    )


@agents.route("/admin/add_to_population", methods=["POST"])
@login_required
def add_to_population():
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
    check_privileges(current_user.username)

    agent = Agent.query.filter_by(id=uid).first()
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
