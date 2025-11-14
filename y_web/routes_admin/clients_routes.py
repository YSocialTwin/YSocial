"""
Client simulation management routes.

Administrative routes for configuring and managing simulation clients,
including behavior parameters, LLM settings, network topology, and
client execution control (start/pause/resume/terminate).
"""

import json
import os
import shutil

import faker
import networkx as nx
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
    Agent,
    Agent_Population,
    Agent_Profile,
    Client,
    Client_Execution,
    Content_Recsys,
    Exp_Topic,
    Exps,
    Follow_Recsys,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Topic_List,
    User_mgmt,
)
from y_web.utils import (
    get_db_type,
    get_llm_models,
    get_ollama_models,
    start_client,
    terminate_client,
)
from y_web.utils.desktop_file_handler import send_file_desktop
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status
from y_web.utils.path_utils import get_resource_path

clientsr = Blueprint("clientsr", __name__)


@clientsr.route("/admin/reset_client/<int:uid>")
@login_required
def reset_client(uid):
    """Handle reset client operation."""
    check_privileges(current_user.username)

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # delete experiment json files
    client = Client.query.filter_by(id=uid).first()
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()
    path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}{population.name}.json"
    if os.path.exists(path):
        os.remove(path)

    path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json"
    if os.path.exists(path):
        os.remove(path)

    # copy the original prompts.json file
    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
        shutil.copy(
            prompts_src,
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json",
        )
    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copy(
            prompts_src,
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json",
        )
    else:
        raise Exception(f"unsupported platform: {exp.platform_type}")

    # delete client execution
    db.session.query(Client_Execution).filter_by(client_id=uid).delete()
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/extend_simulation/<int:id_client>", methods=["POST", "GET"])
@login_required
def extend_simulation(id_client):
    """Handle extend simulation operation."""
    check_privileges(current_user.username)

    # check if the client exists
    client = Client.query.filter_by(id=id_client).first()
    if client is None:
        flash("Client not found.", "error")
        return redirect(request.referrer)

    # get the days from the form
    days = request.form.get("days")

    # get the client execution
    client_execution = Client_Execution.query.filter_by(client_id=id_client).first()

    # extend the simulation
    client_execution.expected_duration_rounds += int(days) * 24

    db.session.commit()

    # update the client days field
    client = db.session.query(Client).filter_by(id=id_client).first()
    client.days = int(client.days) + int(days)
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/run_client/<int:uid>/<int:idexp>")
@login_required
def run_client(uid, idexp):
    """Handle run client operation."""
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return redirect(request.referrer)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()
    start_client(exp, client, population, resume=True)

    # set the population_experiment running_status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    return experiment_details(idexp)


@clientsr.route("/admin/resume_client/<int:uid>/<int:idexp>")
@login_required
def resume_client(uid, idexp):
    """Handle resume client operation."""
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return redirect(request.referrer)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()
    start_client(exp, client, population, resume=True)

    # set the population_experiment running_status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/pause_client/<int:uid>/<int:idexp>")
@login_required
def pause_client(uid, idexp):
    """Handle pause client operation."""
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=True)

    return experiment_details(idexp)  # redirect(request.referrer)


@clientsr.route("/admin/stop_client/<int:uid>/<int:idexp>")
@login_required
def stop_client(uid, idexp):
    """Handle stop client operation."""
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=False)

    return experiment_details(idexp)  # redirect(request.referrer)


@clientsr.route("/admin/clients/<idexp>")
@login_required
def clients(idexp):
    """Handle clients operation."""
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()

    # get only populations already associated with this experiment
    pop_exp_associations = Population_Experiment.query.filter_by(id_exp=idexp).all()
    population_ids = [pe.id_population for pe in pop_exp_associations]

    # get only populations  that are not associated with this experiment
    pops = (
        Population.query.filter(~Population.id.in_(population_ids)).all()
        if population_ids
        else Population.query.all()
    )

    crecsys = Content_Recsys.query.all()
    frecsys = Follow_Recsys.query.all()

    # Check if LLM agents are enabled for this experiment
    llm_agents_enabled = (
        exp.llm_agents_enabled if hasattr(exp, "llm_agents_enabled") else True
    )

    return render_template(
        "admin/clients.html",
        experiment=exp,
        populations=pops,
        crecsys=crecsys,
        frecsys=frecsys,
        llm_agents_enabled=llm_agents_enabled,
    )


@clientsr.route("/admin/create_client", methods=["POST"])
@login_required
def create_client():
    """Create client."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")
    days = request.form.get("days")
    percentage_new_agents_iteration = request.form.get(
        "percentage_new_agents_iteration"
    )
    percentage_removed_agents_iteration = request.form.get(
        "percentage_removed_agents_iteration"
    )
    max_length_thread_reading = request.form.get("max_length_thread_reading")
    reading_from_follower_ratio = request.form.get("reading_from_follower_ratio")
    probability_of_daily_follow = request.form.get("probability_of_daily_follow")
    probability_of_secondary_follow = request.form.get(
        "probability_of_secondary_follow"
    )
    attention_window = request.form.get("attention_window")
    visibility_rounds = request.form.get("visibility_rounds")
    post = request.form.get("post")
    share = request.form.get("share")
    image = request.form.get("image")
    comment = request.form.get("comment")
    read = request.form.get("read")
    news = request.form.get("news")
    search = request.form.get("search")
    vote = request.form.get("vote")
    share_link = request.form.get("share_link")

    # Check if LLM agents are enabled for this experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()
    llm_agents_enabled = (
        exp.llm_agents_enabled if (exp and hasattr(exp, "llm_agents_enabled")) else True
    )

    # Get LLM parameters from form, or use defaults if LLM agents are disabled
    if llm_agents_enabled:
        llm = request.form.get("llm")
        llm_api_key = request.form.get("llm_api_key")
        llm_max_tokens = request.form.get("llm_max_tokens")
        llm_temperature = request.form.get("llm_temperature")
        llm_v_agent = request.form.get("llm_v_agent")
        llm_v = request.form.get("llm_v")
        llm_v_api_key = request.form.get("llm_v_api_key")
        llm_v_max_tokens = request.form.get("llm_v_max_tokens")
        llm_v_temperature = request.form.get("llm_v_temperature")
        user_type = request.form.get("user_type")
    else:
        # Use default values when LLM agents are disabled
        llm = "http://127.0.0.1:11434/v1"
        llm_api_key = "NULL"
        llm_max_tokens = "-1"
        llm_temperature = "1.5"
        llm_v_agent = "minicpm-v"
        llm_v = "http://127.0.0.1:11434/v1"
        llm_v_api_key = "NULL"
        llm_v_max_tokens = "300"
        llm_v_temperature = "0.5"
        user_type = ""

    crecsys = request.form.get("recsys_type")
    frecsys = request.form.get("frecsys_type")

    # Validate simulation parameters
    errors = []
    # Validate numeric fields
    try:
        days = int(days)
    except (ValueError, TypeError):
        errors.append("Days must be a valid integer")
    try:
        max_length_thread_reading = int(max_length_thread_reading)
    except (ValueError, TypeError):
        errors.append("Max Length Thread Reading must be a valid integer")
    try:
        attention_window = int(attention_window)
    except (ValueError, TypeError):
        errors.append("Attention Window must be a valid integer")
    try:
        visibility_rounds = int(visibility_rounds)
    except (ValueError, TypeError):
        errors.append("Visibility Rounds must be a valid integer")

    # Validate probability fields (must be float in [0, 1])
    try:
        percentage_new_agents_iteration = float(percentage_new_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% New Agents (daily) must be a valid number")
        percentage_new_agents_iteration = None
    try:
        percentage_removed_agents_iteration = float(percentage_removed_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% Daily Churn must be a valid number")
        percentage_removed_agents_iteration = None
    try:
        reading_from_follower_ratio = float(reading_from_follower_ratio)
    except (ValueError, TypeError):
        errors.append("Timeline Follower Ratio must be a valid number")
        reading_from_follower_ratio = None
    try:
        probability_of_daily_follow = float(probability_of_daily_follow)
    except (ValueError, TypeError):
        errors.append("Probability Daily Follow must be a valid number")
        probability_of_daily_follow = None
    try:
        probability_of_secondary_follow = float(probability_of_secondary_follow)
    except (ValueError, TypeError):
        errors.append("Probability Secondary Follow must be a valid number")
        probability_of_secondary_follow = None

    # Check probability ranges
    probabilities = {
        "% New Agents (daily)": percentage_new_agents_iteration,
        "% Daily Churn": percentage_removed_agents_iteration,
        "Timeline Follower Ratio": reading_from_follower_ratio,
        "Probability Daily Follow": probability_of_daily_follow,
        "Probability Secondary Follow": probability_of_secondary_follow,
    }
    for field_name, value in probabilities.items():
        if value is not None and not (0 <= value <= 1):
            errors.append(f"{field_name} must be between 0 and 1")

    if errors:
        for error in errors:
            flash(error)
        return redirect(request.referrer)

    # Fetch optional network configuration
    network_model = request.form.get("network_model")
    network_p = request.form.get("network_p")
    network_m = request.form.get("network_m")
    network_file = request.files.get("network_file")

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = request.form.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass  # Ignore invalid values, use defaults

    # get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=exp_id).all()
    topics_ids = [t.topic_id for t in topics]
    # get the topics names from the Topic_list table
    topics = db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    topics = [t.name for t in topics]

    # if name already exists, return to the previous page
    if Client.query.filter_by(name=name).first():
        flash("Client name already exists.", "error")
        return redirect(request.referrer)

    exp = Exps.query.filter_by(idexp=exp_id).first()

    # get population
    population = Population.query.filter_by(id=population_id).first()

    if population is None:
        flash("Population not found.", "error")
        return redirect(request.referrer)

    # check if the population is already assigned to the experiment
    # if not, add it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=exp_id
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp_id)
        db.session.add(pop_exp)
        db.session.commit()

    # create the Client object
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp_id,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        share_link=share_link,
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=llm_max_tokens,
        llm_temperature=llm_temperature,
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=llm_v_max_tokens,
        llm_v_temperature=llm_v_temperature,
        probability_of_secondary_follow=probability_of_secondary_follow,
        crecsys=crecsys,
        frecsys=frecsys,
        status=0,
    )

    db.session.add(client)
    db.session.commit()

    # Get LLM URL from environment (set by y_social.py)
    import os

    # get population activity profiles
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )

    activity_profiles = [a.activity_profile for a in activity_profiles]

    # get all activity profiles from the db where id in activity_profiles
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )

    profiles = {ap.name: ap.hours for ap in activity_profiles}

    annotations = exp.annotations.split(",")
    emotion_annotation = "emotion" in annotations

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    config = {
        "servers": {
            "llm": llm,
            #    "llm_url": llm_url,
            "llm_api_key": llm_api_key,
            "llm_max_tokens": int(llm_max_tokens),
            "llm_temperature": float(llm_temperature),
            "llm_v": llm_v,
            "llm_v_api_key": llm_v_api_key,
            "llm_v_max_tokens": int(llm_v_max_tokens),
            "llm_v_temperature": float(llm_v_temperature),
            "api": f"http://{exp.server}:{exp.port}/",
        },
        "simulation": {
            "name": name,
            "population": population.name,
            "client": "YClientWeb",
            "days": int(days),
            "slots": 24,
            "percentage_new_agents_iteration": float(percentage_new_agents_iteration),
            "percentage_removed_agents_iteration": float(
                percentage_removed_agents_iteration
            ),
            "activity_profiles": profiles,
            "hourly_activity": hourly_activity,
            "actions_likelihood": {
                "post": float(post),
                "image": float(image) if image is not None else 0,
                "news": float(news) if news is not None else 0,
                "comment": float(comment) if comment is not None else 0,
                "read": float(read) if read is not None else 0,
                "share": float(share) if share is not None else 0,
                "search": float(search) if search is not None else 0,
                "cast": float(vote) if vote is not None else 0,
                "share_link": float(share_link) if share_link is not None else 0,
            },
            "emotion_annotation": emotion_annotation,
        },
        "posts": {
            "visibility_rounds": int(visibility_rounds),
            "emotions": {
                "admiration": None,
                "amusement": None,
                "anger": None,
                "annoyance": None,
                "approval": None,
                "caring": None,
                "confusion": None,
                "curiosity": None,
                "desire": None,
                "disappointment": None,
                "disapproval": None,
                "disgust": None,
                "embarrassment": None,
                "excitement": None,
                "fear": None,
                "gratitude": None,
                "grief": None,
                "joy": None,
                "love": None,
                "nervousness": None,
                "optimism": None,
                "pride": None,
                "realization": None,
                "relief": None,
                "remorse": None,
                "sadness": None,
                "surprise": None,
                "trust": None,
            },
        },
        "agents": {
            "llm_v_agent": "minicpm-v",
            "reading_from_follower_ratio": float(reading_from_follower_ratio),
            "max_length_thread_reading": int(max_length_thread_reading),
            "attention_window": int(attention_window),
            "probability_of_daily_follow": float(probability_of_daily_follow),
            "probability_of_secondary_follow": float(probability_of_secondary_follow),
            "age": {"min": 18, "max": 65},
            "political_leaning": [],
            "toxicity_levels": [],
            "languages": [],
            "llm_agents": [],
            "education_levels": [],
            "round_actions": {"min": 1, "max": 3},
            "n_interests": {"min": 1, "max": 5},
            "interests": [],
            "big_five": {
                "oe": ["inventive/curious", "consistent/cautious"],
                "co": ["extravagant/careless", "efficient/organized"],
                "ex": ["outgoing/energetic", "solitary/reserved"],
                "ag": ["critical/judgmental", "friendly/compassionate"],
                "ne": ["resilient/confident", "sensitive/nervous"],
            },
        },
    }

    # get population agents
    agents = Agent_Population.query.filter_by(population_id=population_id).all()
    # get agents political leaning
    political_leaning = set(
        [Agent.query.filter_by(id=a.agent_id).first().leaning for a in agents]
    )
    # get agents' age
    age = set([Agent.query.filter_by(id=a.agent_id).first().age for a in agents])
    # get agents toxicity levels
    toxicity = set(
        [Agent.query.filter_by(id=a.agent_id).first().toxicity for a in agents]
    )
    # get agents' language
    language = set(
        [Agent.query.filter_by(id=a.agent_id).first().language for a in agents]
    )
    # get agents' type
    ag_type = set(
        [Agent.query.filter_by(id=a.agent_id).first().ag_type for a in agents]
    )
    # get agents' education level
    education_level = set(
        [Agent.query.filter_by(id=a.agent_id).first().education_level for a in agents]
    )

    config["agents"]["political_leanings"] = list(political_leaning)
    config["agents"]["age"]["min"] = min(age)
    config["agents"]["age"]["max"] = max(age)
    config["agents"]["toxicity_levels"] = list(toxicity)
    config["agents"]["languages"] = list(language)
    config["agents"]["llm_agents"] = list(ag_type)
    config["agents"]["education_levels"] = list(education_level)
    config["agents"]["round_actions"] = {"min": 1, "max": 3}
    config["agents"]["n_interests"] = {"min": 1, "max": 5}

    # check db type
    if "database_server.db" in exp.db_name:  # sqlite
        uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    with open(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f, indent=4)

    data_base_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    # copy prompts.json into the experiment folder

    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
        shutil.copyfile(
            prompts_src,
            f"{data_base_path}prompts.json",
        )

    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copyfile(
            prompts_src,
            f"{data_base_path}prompts.json",
        )
    else:
        raise Exception(f"unsupported platform: {exp.platform_type}")

    # Create agent population file
    writable_base = get_writable_path()

    if "database_server.db" in exp.db_name:
        # exp.db_name is like "experiments/uid/database_server.db"
        filename = os.path.join(
            writable_base,
            "y_web",
            exp.db_name.split("database_server.db")[0],
            f"{population.name.replace(' ', '')}.json",
        )
    else:
        # Legacy format
        filename = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp.db_name.replace("experiments_", ""),
            f"{population.name.replace(' ', '')}.json",
        )

    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    # get the agent details
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    res = {"agents": []}
    for a in agents:
        custom_prompt = Agent_Profile.query.filter_by(agent_id=a.id).first()

        if custom_prompt:
            custom_prompt = custom_prompt.profile

        # randomly select from 1 to 5 topics without replacement and save as interests
        fake = faker.Faker()

        interests = list(
            set(
                fake.random_elements(
                    elements=set(topics),
                    length=fake.random_int(
                        min=1,
                        max=5,
                    ),
                )
            )
        )

        ints = [interests, len(interests)]

        res["agents"].append(
            {
                "name": a.name,
                "email": f"{a.name}@ysocial.it",
                "password": f"{a.name}",
                "age": a.age,
                "type": user_type,  # ,a.ag_type,
                "leaning": a.leaning,
                "interests": ints,
                "oe": a.oe,
                "co": a.co,
                "ex": a.ex,
                "ag": a.ag,
                "ne": a.ne,
                "rec_sys": crecsys,
                "frec_sys": frecsys,
                "language": a.language,
                "owner": exp.owner,
                "education_level": a.education_level,
                "round_actions": int(a.round_actions),
                "gender": a.gender,
                "nationality": a.nationality,
                "toxicity": a.toxicity,
                "is_page": 0,
                "prompts": custom_prompt if custom_prompt else None,
                "daily_activity_level": a.daily_activity_level,
                "profession": a.profession,
                "activity_profile": db.session.query(ActivityProfile)
                .filter_by(id=a.activity_profile)
                .first()
                .name,
            }
        )

    # get the pages associated with the population
    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

    for p in pages:
        # get pages topics
        page_topics = (
            db.session.query(Exp_Topic, Topic_List)
            .join(Topic_List)
            .filter(Exp_Topic.exp_id == exp_id, Exp_Topic.topic_id == Topic_List.id)
            .all()
        )
        page_topics = [t[1].name for t in page_topics]
        page_topics = list(set(page_topics) & set(topics))

        res["agents"].append(
            {
                "name": p.name,
                "email": f"{p.name}@ysocial.it",
                "password": f"{p.name}",
                "age": 0,
                "type": user_type,
                "leaning": p.leaning,
                "interests": [page_topics, len(page_topics)],
                "oe": "",
                "co": "",
                "ex": "",
                "ag": "",
                "ne": "",
                "rec_sys": "",
                "frec_sys": "",
                "language": "english",
                "owner": exp.owner,
                "education_level": "",
                "round_actions": 3,
                "gender": "",
                "nationality": "",
                "toxicity": "none",
                "is_page": 1,
                "feed_url": p.feed,
                "activity_profile": db.session.query(ActivityProfile)
                .filter_by(id=p.activity_profile)
                .first()
                .name,
            }
        )

    print(f"Saving agents to {filename}")
    json.dump(res, open(filename, "w"), indent=4)

    # Handle optional network configuration
    if network_model or network_file:
        # get populations for client
        populations = Population.query.filter_by(id=client.population_id).all()
        # get agents for the populations
        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

        from y_web.utils.path_utils import get_writable_path

        BASE = get_writable_path()
        dbtypte = get_db_type()

        if dbtypte == "sqlite":
            exp_folder = exp.db_name.split(os.sep)[1]
        else:
            exp_folder = exp.db_name.removeprefix("experiments_")

        network_path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w") as o:
                    error, error2 = False, False
                    with open(temp_path, "r") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            agent_1 = Agent.query.filter_by(name=l[0]).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = Page.query.filter_by(name=l[0]).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            agent_2 = Agent.query.filter_by(name=l[1]).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = Page.query.filter_by(name=l[1]).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    f"Agent {l[0]} or {l[1]} not found in network file.",
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    "Network file format error: provide a csv file containing two columns with agent names. No header required.",
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1

            if network_model == "BA":
                g = nx.barabasi_albert_graph(len(agent_ids), m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(len(agent_ids), p=p)
            else:
                g = None

            if g:
                # since the network is undirected and Y assume directed relations we need to write the edges in both directions
                with open(network_path, "w") as f:
                    for n in g.edges:
                        f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
                        f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()

    # load experiment_details page
    from .experiments_routes import experiment_details

    return experiment_details(int(exp_id))


@clientsr.route("/admin/delete_client/<int:uid>")
@login_required
def delete_client(uid):
    """Delete client."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    exp_id = client.id_exp
    pop_id = client.population_id

    Client_Execution.query.filter_by(client_id=uid).delete()
    db.session.commit()

    # delete association of population and experiment if no other client is using it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=client.population_id, id_exp=exp_id
    ).first()
    if pop_exp:
        other_clients = Client.query.filter_by(
            id_exp=exp_id, population_id=client.population_id
        ).all()
        if len(other_clients) == 0:
            db.session.delete(pop_exp)
            db.session.commit()

    db.session.delete(client)
    db.session.commit()

    from y_web.utils.path_utils import get_writable_path

    # remove the db file on the client
    BASE_PATH = get_writable_path()
    path = f"{BASE_PATH}{os.sep}external{os.sep}YClient{os.sep}experiments{os.sep}{client.name}.db"
    if os.path.exists(path):
        os.remove(path)
    else:
        print(f"File {path} does not exist.")

    # remove agent population
    Population_Experiment.query.filter_by(id_population=pop_id).delete()
    db.session.commit()

    from .experiments_routes import experiment_details

    return experiment_details(exp_id)


@clientsr.route("/admin/client_details/<int:uid>")
@login_required
def client_details(uid):
    """Handle client details operation."""
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()

    # get population for the client
    population = Population.query.filter_by(id=client.population_id).first()
    # get the pages included to the population
    pages = (
        db.session.query(Page, Page_Population)
        .join(Page_Population)
        .filter(Page_Population.population_id == client.population_id)
        .all()
    )

    # get the client configuration file
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = experiment.db_name.split(os.sep)[1]
    else:
        exp_folder = experiment.db_name.removeprefix("experiments_")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
    else:
        config = None

    # open the agent population file to get the number of agents
    path_agents = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{population.name}.json"

    if os.path.exists(path_agents):
        with open(path_agents, "r") as f:
            agents = json.load(f)
    else:
        agents = None

    llms = []
    if agents is not None:
        for agent in agents["agents"]:
            llms.append(agent["type"])

    llms = ",".join(list(set(llms)))

    activity = config["simulation"]["hourly_activity"]

    data = []
    idx = []

    for x in range(0, 24):
        idx.append(str(x))
        data.append(activity[str(x)])

    models = get_llm_models()  # Use generic function for any LLM server

    llm_backend = llm_backend_status()

    frecsys = Follow_Recsys.query.all()
    crecsys = Content_Recsys.query.all()

    return render_template(
        "admin/client_details.html",
        data=data,
        idx=idx,
        activity=activity,
        client=client,
        experiment=experiment,
        population=population,
        pages=pages,
        models=models,
        llm_backend=llm_backend,
        frecsys=frecsys,
        crecsys=crecsys,
        llms=llms,
    )


@clientsr.route("/admin/progress/<int:client_id>")
def get_progress(client_id):
    """Return the current progress as JSON."""
    # get client_execution
    client_execution = Client_Execution.query.filter_by(client_id=client_id).first()

    if client_execution is None:
        return json.dumps({"progress": 0})

    # Calculate progress and cap at 100%
    if client_execution.expected_duration_rounds > 0:
        progress = int(
            100
            * float(client_execution.elapsed_time)
            / float(client_execution.expected_duration_rounds)
        )
        # Cap progress at 100% to prevent overflow
        progress = min(100, max(0, progress))
    else:
        progress = 0

    return json.dumps({"progress": progress})


@clientsr.route("/admin/set_network/<int:uid>", methods=["POST"])
@login_required
def set_network(uid):
    """Handle set network operation."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations for client uid
    populations = Population.query.filter_by(id=client.population_id).all()
    # get agents for the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id for p in populations])
    ).all()
    # get agent ids for all agents in populations
    agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

    # get data from form
    network = request.form.get("network_model")

    m = int(request.form.get("m"))
    p = float(request.form.get("p"))

    if network == "BA":
        g = nx.barabasi_albert_graph(len(agent_ids), m=m)
    else:
        g = nx.erdos_renyi_graph(len(agent_ids), p=p)

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

    # since the network is undirected and Y assume directed relations we need to write the edges in both directions
    with open(path, "w") as f:
        for n in g.edges:
            f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
            f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
        f.flush()

    client.network_type = network
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/upload_network/<int:uid>", methods=["POST"])
@login_required
def upload_network(uid):
    """Upload network."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    network = request.files["network_file"]
    network.save(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network_temp.csv"
    )

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}"

    try:
        with open(f"{path}_network.csv", "w") as o:
            error, error2 = False, False
            with open(f"{path}_network_temp.csv", "r") as f:
                for l in f:
                    l = l.rstrip().split(",")

                    agent_1 = Agent.query.filter_by(name=l[0]).all()
                    aids = [a.id for a in agent_1]

                    if agent_1 is not None:
                        # check if in population
                        test = Agent_Population.query.filter(
                            Agent_Population.agent_id.in_(aids),
                            Agent_Population.population_id == client.population_id,
                        ).all()
                        error = len(test) == 0
                    else:
                        agent_1 = Page.query.filter_by(name=l[0]).all()
                        aids = [a.id for a in agent_1]

                        if agent_1 is not None:
                            # check if in population
                            test = Page_Population.query.filter(
                                Page_Population.page_id.in_(aids),
                                Page_Population.population_id == client.population_id,
                            ).all()
                            error = len(test) == 0
                        if agent_1 is None:
                            error = True

                    agent_2 = Agent.query.filter_by(name=l[1]).all()
                    aids = [a.id for a in agent_2]

                    if agent_2 is not None:
                        # check if in population
                        test = Agent_Population.query.filter(
                            Agent_Population.agent_id.in_(aids),
                            Agent_Population.population_id == client.population_id,
                        ).all()
                        error2 = len(test) == 0
                    else:
                        agent_2 = Page.query.filter_by(name=l[1]).all()
                        aids = [a.id for a in agent_2]

                        if agent_2 is not None:
                            # check if in population
                            test = Page_Population.query.filter(
                                Page_Population.page_id.in_(aids),
                                Page_Population.population_id == client.population_id,
                            ).all()
                            error2 = len(test) == 0

                        if agent_2 is None:
                            error2 = True

                    if not error and not error2:
                        o.write(f"{l[0]},{l[1]}\n")
                    else:
                        flash(f"Agent {l[0]} or {l[1]} not found.", "error")
                        os.remove(f"{path}_network_temp.csv")
                        os.remove(f"{path}_network.csv")
                        return redirect(request.referrer)
    except:
        flash(
            "File format error: provide a csv file containing two columns with agent names. No header required.",
            "error",
        )
        os.remove(f"{path}_network_temp.csv")
        os.remove(f"{path}_network.csv")
        return redirect(request.referrer)

    # delete the temp file
    os.remove(f"{path}_network_temp.csv")

    client.network_type = "Custom Network"
    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/download_agent_list/<int:uid>")
@login_required
def download_agent_list(uid):
    """Download agent list."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations associated to the client
    populations = Population_Experiment.query.filter_by(id_exp=client.id_exp).all()

    # get agents in the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id_population for p in populations])
    ).all()

    # get the experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()

    from y_web.utils.path_utils import get_writable_path

    # get the experiment folder
    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    with open(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv",
        "w",
    ) as f:
        for a in agents:
            agent = Agent.query.filter_by(id=a.agent_id).first()
            f.write(f"{agent.name}\n")
        f.flush()

    return send_file_desktop(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv",
        as_attachment=True,
    )


@clientsr.route("/admin/update_agents_activity/<int:uid>", methods=["POST"])
@login_required
def update_agents_activity(uid):
    """Update agents activity."""
    check_privileges(current_user.username)

    # get data from form
    activity = {}
    for x in request.form:
        activity[str(x)] = float(request.form.get(str(x)))

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
            config["simulation"]["hourly_activity"] = activity
            # save the new configuration
            json.dump(config, open(path, "w"), indent=4)
    else:
        flash("Configuration file not found.", "error")

    return redirect(request.referrer)


@clientsr.route("/admin/reset_agents_activity/<int:uid>")
@login_required
def reset_agents_activity(uid):
    """Handle reset agents activity operation."""
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
            config["simulation"]["hourly_activity"] = {
                "10": 0.021,
                "16": 0.032,
                "8": 0.020,
                "12": 0.024,
                "15": 0.032,
                "17": 0.032,
                "23": 0.025,
                "6": 0.017,
                "18": 0.032,
                "11": 0.022,
                "13": 0.027,
                "14": 0.030,
                "20": 0.030,
                "21": 0.029,
                "7": 0.018,
                "22": 0.027,
                "9": 0.020,
                "3": 0.020,
                "5": 0.017,
                "4": 0.018,
                "1": 0.021,
                "2": 0.020,
                "0": 0.023,
                "19": 0.031,
            }
            # save the new configuration
            json.dump(config, open(path, "w"), indent=4)
    else:
        flash("Configuration file not found.", "error")

    return redirect(request.referrer)


@clientsr.route("/admin/update_recsys/<int:uid>", methods=["POST"])
@login_required
def update_recsys(uid):
    """Update recsys."""
    check_privileges(current_user.username)

    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")

    client = Client.query.filter_by(id=uid).first()

    # Update client's recsys settings
    client.crecsys = recsys_type
    client.frecsys = frecsys_type

    # get populations for client uid
    population = Population.query.filter_by(id=client.population_id).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=population.id).all()

    # updating the recommenders of the agents in the specific simulation instance (not in the population)
    for agent in agents:
        try:
            a = Agent.query.filter_by(id=agent.agent_id).first()
            user = (User_mgmt.query.filter_by(username=a.name)).first()
            user.frecsys_type = frecsys_type
            user.recsys_type = recsys_type
            db.session.commit()
        except:
            flash("The experiment needs to be activated first.", "error")
            return redirect(request.referrer)

    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/update_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_llm(uid):
    """Update llm."""
    check_privileges(current_user.username)

    user_type = request.form.get("user_type")

    client = Client.query.filter_by(id=uid).first()

    # get populations for client uid
    population = Population.query.filter_by(id=client.population_id).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=population.id).all()

    for agent in agents:
        try:
            a = Agent.query.filter_by(id=agent.agent_id).first()
            user = (User_mgmt.query.filter_by(username=a.name)).first()
            user.user_type = user_type
            db.session.commit()
        except:
            flash("The experiment needs to be activated first.", "error")
            return redirect(request.referrer)

    population.llm = user_type

    db.session.commit()
    return redirect(request.referrer)
