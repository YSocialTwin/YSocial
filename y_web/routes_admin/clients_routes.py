import os
import networkx as nx
import random

from flask import (
    Blueprint,
    render_template,
    redirect,
    request,
    flash,
    send_file,
)
from flask_login import login_required, current_user

from y_web.models import (
    Exps,
    Population,
    Agent,
    Agent_Population,
    Page,
    Population_Experiment,
    Page_Population,
    Client,
    Client_Execution, User_mgmt, Agent_Profile
)
from y_web.utils import (
    start_client,
    terminate_client,
    get_ollama_models
)
import json
import shutil
from . import db, experiment_details, population
from y_web.utils.miscellanea import check_privileges

clientsr = Blueprint("clientsr", __name__)


@clientsr.route("/admin/reset_client/<int:uid>")
@login_required
def reset_client(uid):
    check_privileges(current_user.username)

    # delete experiment json files
    client = Client.query.filter_by(id=uid).first()
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()
    path = f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}{population.name}.json"
    if os.path.exists(path):
        os.remove(path)

    path = f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json"
    if os.path.exists(path):
        os.remove(path)

    # copy the original prompts.json file
    BASE = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    shutil.copy(
        f"{BASE}data_schema{os.sep}prompts.json",
        f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

    # delete client execution
    db.session.query(Client_Execution).filter_by(client_id=uid).delete()
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/run_client/<int:uid>/<int:idexp>")
@login_required
def run_client(uid, idexp):
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
    start_client(exp, client, population)

    # set the population_experiment running_status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/resume_client/<int:uid>/<int:idexp>")
@login_required
def resume_client(uid, idexp):
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
    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=True)

    return redirect(request.referrer)


@clientsr.route("/admin/stop_client/<int:uid>/<int:idexp>")
@login_required
def stop_client(uid, idexp):
    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=False)

    return redirect(request.referrer) #experiment_details(idexp)


@clientsr.route("/admin/clients/<idexp>")
@login_required
def clients(idexp):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get population assigned to the experiment
    populations = Population_Experiment.query.filter_by(id_exp=idexp).all()
    # get the populations details
    pops = [Population.query.filter_by(id=p.id_population).first() for p in populations]

    return render_template("admin/clients.html", experiment=exp, populations=pops)


@clientsr.route("/admin/create_client", methods=["POST"])
@login_required
def create_client():
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
    llm = request.form.get("llm")
    llm_api_key = request.form.get("llm_api_key")
    llm_max_tokens = request.form.get("llm_max_tokens")
    llm_temperature = request.form.get("llm_temperature")
    llm_v_agent = request.form.get("llm_v_agent")
    llm_v = request.form.get("llm_v")
    llm_v_api_key = request.form.get("llm_v_api_key")
    llm_v_max_tokens = request.form.get("llm_v_max_tokens")
    llm_v_temperature = request.form.get("llm_v_temperature")

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
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=llm_max_tokens,
        llm_temperature=llm_temperature,
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=llm_v_max_tokens,
        llm_v_temperature=llm_v_temperature,
        status=0,
    )

    db.session.add(client)
    db.session.commit()

    config = {
        "servers": {
            "llm": llm,
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
            "percentage_removed_agents_iteration": float(percentage_removed_agents_iteration),
            "hourly_activity": {
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
            },
            "actions_likelihood": {
                "post": float(post),
                "image": float(image),
                "news": float(news),
                "comment": float(comment),
                "read": float(read),
                "share": float(share),
                "search": float(search),
                "cast": float(vote),
            },
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

    #get population agents
    agents = Agent_Population.query.filter_by(population_id=population_id).all()
    # get agents political leaning
    political_leaning = set([Agent.query.filter_by(id=a.agent_id).first().leaning for a in agents])
    # get agents age
    age = set([Agent.query.filter_by(id=a.agent_id).first().age for a in agents])
    # get agents toxicity levels
    toxicity = set([Agent.query.filter_by(id=a.agent_id).first().toxicity for a in agents])
    # get agents language
    language = set([Agent.query.filter_by(id=a.agent_id).first().language for a in agents])
    # get agents type
    ag_type = set([Agent.query.filter_by(id=a.agent_id).first().ag_type for a in agents])
    # get agents education level
    education_level = set([Agent.query.filter_by(id=a.agent_id).first().education_level for a in agents])

    config["agents"]["political_leanings"] = list(political_leaning)
    config["agents"]["age"]['min'] = min(age)
    config["agents"]["age"]['max'] = max(age)
    config["agents"]["toxicity_levels"] = list(toxicity)
    config["agents"]["languages"] = list(language)
    config["agents"]["llm_agents"] = list(ag_type)
    config["agents"]["education_levels"] = list(education_level)
    config["agents"]["round_actions"] = {"min": 1, "max": 3}
    config["agents"]["n_interests"] = {"min": 1, "max": 5}

    # get a random element of a list
    ag = random.choice(agents)
    # get agent interests
    interests = Agent.query.filter_by(id=ag.agent_id).first().interests
    config["agents"]["interests"] = interests.split(",")

    uid = exp.db_name.split(os.sep)[1]

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]

    with open(
        f"{BASE_DIR}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f)

    # copy prompts.json into the experiment folder
    data_base_path = f"{BASE_DIR}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    shutil.copyfile(f"{BASE_DIR}data_schema{os.sep}prompts.json".replace("/y_web/utils", ""),
                        f"{data_base_path}prompts.json")

    # Create agent population file
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    filename = f"{BASE_DIR}{os.sep}{exp.db_name.split('database_server.db')[0]}{population.name.replace(' ', '')}.json"

    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    # get the agent details
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    res = {"agents": []}
    for a in agents:

        custom_prompt = Agent_Profile.query.filter_by(agent_id=a.id).first()

        if custom_prompt:
            custom_prompt = custom_prompt.profile

        res["agents"].append(
            {
                "name": a.name,
                "email": f"{a.name}@ysocial.it",
                "password": f"{a.name}",
                "age": a.age,
                "type": a.ag_type,
                "leaning": a.leaning,
                "interests": [
                    [x.strip() for x in a.interests.split(",")],
                    [len([x for x in a.interests.split(",")])],
                ] if a.interests else [[], 0],
                "oe": a.oe,
                "co": a.co,
                "ex": a.ex,
                "ag": a.ag,
                "ne": a.ne,
                "rec_sys": a.crecsys,
                "frec_sys": a.frecsys,
                "language": a.language,
                "owner": exp.owner,
                "education_level": a.education_level,
                "round_actions": int(a.round_actions),
                "gender": a.gender,
                "nationality": a.nationality,
                "toxicity": a.toxicity,
                "is_page": 0,
                "prompts": custom_prompt if custom_prompt else None,
                "daily_activity_level": a.daily_activity_level
            }
        )

    # get the pages associated with the population
    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

    for p in pages:
        res["agents"].append(
            {
                "name": p.name,
                "email": f"{p.name}@ysocial.it",
                "password": f"{p.name}",
                "age": 0,
                "type": p.pg_type,
                "leaning": p.leaning,
                "interests": [[], 0],
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
            }
        )

    json.dump(res, open(filename, "w"), indent=4)

    # load experiment_details page
    return experiment_details(int(exp_id))


@clientsr.route("/admin/delete_client/<int:uid>")
@login_required
def delete_client(uid):
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    db.session.delete(client)
    db.session.commit()

    # remove the db file on the client
    BASE_PATH = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    path = f"{BASE_PATH}external{os.sep}YClient{os.sep}experiments{os.sep}{client.name}.db"
    if os.path.exists(path):
        os.remove(path)
    else:
        print(f"File {path} does not exist.")

    return redirect(request.referrer)


@clientsr.route("/admin/client_details/<int:uid>")
@login_required
def client_details(uid):
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
    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json".replace(
        f"routes_admin{os.sep}", "")

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
    else:
        config = None

    activity = config["simulation"]["hourly_activity"]

    data = []
    idx = []

    for x in range(0, 24):
        idx.append(str(x))
        data.append(activity[str(x)])

    models = get_ollama_models()

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

    )


@clientsr.route('/admin/progress/<int:client_id>')
def get_progress(client_id):
    """Return the current progress as JSON."""
    # get client_execution
    client_execution = Client_Execution.query.filter_by(client_id=client_id).first()

    if client_execution is None:
        return json.dumps({"progress": 0})
    progress = int(100 * float(client_execution.elapsed_time)/float(client_execution.expected_duration_rounds)) if client_execution.expected_duration_rounds > 0 else 0
    return json.dumps({"progress": progress})


@clientsr.route("/admin/set_network/<int:uid>", methods=["POST"])
@login_required
def set_network(uid):
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations for client uid
    populations = Population.query.filter_by(id=client.population_id).all()
    # get agents for the populations
    agents = Agent_Population.query.filter(Agent_Population.population_id.in_([p.id for p in populations])).all()
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
    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = exp.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv".replace(f"routes_admin{os.sep}", "")

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
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    BASE = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0][:-1]
    exp_folder = exp.db_name.split(os.sep)[1]

    network = request.files["network_file"]
    network.save(f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network_temp.csv")

    path = f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}".replace(
        f"routes_admin{os.sep}", "")

    try:
        with open(f"{path}_network.csv", "w") as o:
            error, error2 = False, False
            with open(f"{path}_network_temp.csv", "r") as f:
                for l in f:
                    l = l.rstrip().split(",")

                    agent_1 = Agent.query.filter_by(name=l[0]).first()
                    if agent_1 is not None:
                        # check if in population
                        test = Agent_Population.query.filter_by(agent_id=agent_1.id, population_id=client.population_id).all()
                        error = len(test) == 0
                    else:
                        agent_1 = Page.query.filter_by(name=l[0]).first()
                        if agent_1 is not None:
                            # check if in population
                            test = Page_Population.query.filter_by(page_id=agent_1.id, population_id=client.population_id).all()
                            error = len(test) == 0
                        if agent_1 is None:
                            error = True

                    agent_2 = Agent.query.filter_by(name=l[1]).first()
                    if agent_2 is not None:
                        # check if in population
                        test = Agent_Population.query.filter_by(agent_id=agent_2.id, population_id=client.population_id).all()
                        error2 = len(test) == 0
                    else:
                        agent_2 = Page.query.filter_by(name=l[1]).first()
                        if agent_2 is not None:
                            # check if in population
                            test = Page_Population.query.filter_by(page_id=agent_2.id, population_id=client.population_id).all()
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
        flash("File format error: provide a csv file containing two columns with agent names. No header required.", "error")
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
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations associated to the client
    populations = Population_Experiment.query.filter_by(id_exp=client.id_exp).all()

    # get agents in the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id_population for p in populations])).all()

    # get the experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = exp.db_name.split(os.sep)[1]

    with open(f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv", "w") as f:
        for a in agents:
            agent = Agent.query.filter_by(id=a.agent_id).first()
            f.write(f"{agent.name}\n")
        f.flush()

    return send_file(f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv", as_attachment=True)


@clientsr.route("/admin/update_agents_activity/<int:uid>", methods=["POST"])
@login_required
def update_agents_activity(uid):
    check_privileges(current_user.username)

    # get data from form
    activity = {}
    for x in request.form:
        activity[str(x)] = float(request.form.get(str(x)))

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json".replace(
        f"routes_admin{os.sep}", "")

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
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json".replace(
        f"routes_admin{os.path.sep}", "")

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
    check_privileges(current_user.username)

    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")

    client = Client.query.filter_by(id=uid).first()

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

    population.crecsys = recsys_type
    population.frecsys = frecsys_type

    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/update_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_llm(uid):
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
