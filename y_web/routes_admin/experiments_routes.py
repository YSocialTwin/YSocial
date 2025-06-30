import os

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
    Admin_users,
    Exp_stats,
    User_mgmt,
    Rounds,
    Population,
    Population_Experiment,
    User_Experiment,
    Client,
    Client_Execution,
    Agent,
    Agent_Population,
    Agent_Profile,
    Page,
    Page_Population,
    Languages,
    Leanings,
    Nationalities,
    Profession,
    Education,
)
from y_web.utils import terminate_process_on_port, start_server
import json
import pathlib, shutil
import uuid
from y_web import db, app
from y_web.utils.miscellanea import check_privileges, reload_current_user, ollama_status

experiments = Blueprint("experiments", __name__)


@experiments.route("/admin/experiments")
@login_required
def settings():
    check_privileges(current_user.username)

    # load all experiments
    experiments = Exps.query.limit(5).all()
    users = Admin_users.query.all()

    # check if current db is the same of the active experiment
    exp = Exps.query.filter_by(status=1).first()
    if exp:
        active_db = app.config["SQLALCHEMY_BINDS"]["db_exp"]
        if not exp.exp_name in active_db:
            # change the active experiment
            db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})

    ollamas = ollama_status()

    return render_template(
        "admin/settings.html", experiments=experiments, users=users, ollamas=ollamas
    )


@experiments.route("/admin/join_simulation")
@login_required
def join_simulation():
    # get user id for the current user logged in
    user_id = (
        db.session.query(User_mgmt).filter_by(username=current_user.username).first().id
    )

    # check which experiment is active
    exp = Exps.query.filter_by(status=1).first()
    if exp is None:
        flash("No active experiment. Please load an experiment.")
        return redirect(request.referrer)

    # route the simulation home for the user
    if exp.platform_type == "microblogging":
        return redirect(f"/feed/{user_id}/feed/rf/1")

    elif exp.platform_type == "forum":
        return redirect(f"/rfeed/{user_id}/feed/rf/1")

    else:
        flash("Wrong Platform Type. Please load an experiment.")
        return redirect(request.referrer)


@experiments.route("/admin/select_experiment/<int:exp_id>")
@login_required
def change_active_experiment(exp_id):
    check_privileges(current_user.username)
    uname = current_user.username

    exp = Exps.query.filter_by(idexp=exp_id).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    app.config["SQLALCHEMY_BINDS"]["db_exp"] = f"sqlite:///{BASE_DIR}/{exp.db_name}"

    # check if the user is present in the User_mgmt table
    user = db.session.query(User_mgmt).filter_by(username=current_user.username).first()

    if user is None:
        new_user = User_mgmt(
            email=current_user.email,
            username=current_user.username,
            password=current_user.password,
            user_type="user",
            leaning="neutral",
            age=0,
            recsys_type="default",
            language="en",
            frecsys_type="default",
            round_actions=1,
            toxicity="no",
        )
        db.session.add(new_user)
        db.session.commit()

        # ad to experiment if not present
        user_exp = (
            db.session.query(User_Experiment)
            .filter_by(user_id=current_user.id, exp_id=exp_id)
            .first()
        )
        if user_exp is None:
            user_exp = User_Experiment(user_id=current_user.id, exp_id=exp_id)
            db.session.add(user_exp)
            db.session.commit()

    db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})
    db.session.query(Exps).filter_by(db_name=exp.db_name).update({Exps.status: 1})
    db.session.commit()

    reload_current_user(uname)

    return redirect(request.referrer)


@experiments.route("/admin/upload_experiment", methods=["POST"])
@login_required
def upload_experiment():
    check_privileges(current_user.username)

    experiment = request.files["experiment"]
    uid = uuid.uuid4()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]

    pathlib.Path(f"{BASE_DIR}experiments{os.sep}{uid}").mkdir()

    experiment.save(f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}exp.zip")
    # unzip the file
    shutil.unpack_archive(
        f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}exp.zip",
        f"{BASE_DIR}experiments{os.sep}{uid}",
    )
    # remove the zip file
    os.remove(f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}exp.zip")
    # create the experiment in the database from the config_server.json file
    try:
        # list the files in the directory
        files = os.listdir(f"{BASE_DIR}experiments{os.sep}{uid}")
        experiment = json.load(
            open(f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}config_server.json")
        )
        name = experiment["name"]

        # check if the experiment already exists
        exp = Exps.query.filter_by(exp_name=name).first()

        if exp:
            flash(
                "The experiment already exists. Please check the experiment name and try again."
            )
            shutil.rmtree(f"{BASE_DIR}experiments{os.sep}{uid}", ignore_errors=True)
            return settings()

        exp = Exps(
            exp_name=name,
            db_name=f"experiments{os.sep}{uid}{os.sep}database_server.db",
            owner=current_user.username,
            exp_descr="",
            status=0,
            port=experiment["port"],
            server=experiment["host"],
            platform_type= experiment["platform_type"],
        )

        db.session.add(exp)
        db.session.commit()

        exp_stats = Exp_stats(
            exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0
        )
        db.session.add(exp_stats)
        db.session.commit()

    except:
        flash(
            "There was an error loading the experiment files. Please check the files and try again."
        )
        # remove the directory containing the files
        shutil.rmtree(f"{BASE_DIR}experiments{os.sep}{uid}", ignore_errors=True)
        return redirect(request.referrer)

    # get the json files that do not start with "client"
    populations = [
        f
        for f in os.listdir(f"{BASE_DIR}experiments{os.sep}{uid}")
        if f.endswith(".json")
        and not f.startswith("client")
        and f != "config_server.json"
        and f != "prompts.json"
    ]

    for population in populations:
        name = population.split(".")[0]
        pop = json.load(open(f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}{population}"))

        # check if the population already exists
        population = Population.query.filter_by(name=name).first()
        if population:
            flash(
                "The population already exists. Please check the population name and try again."
            )
            shutil.rmtree(f"{BASE_DIR}experiments{os.sep}{uid}", ignore_errors=True)
            return redirect(request.referrer)

        population = Population(name=name, descr="")
        db.session.add(population)
        db.session.commit()

        pop_exp = Population_Experiment(id_exp=exp.idexp, id_population=population.id)
        db.session.add(pop_exp)
        db.session.commit()

        for agent in pop["agents"]:
            if agent["is_page"] == 1:
                # check if the page already exists
                page = Page.query.filter_by(name=agent["name"]).first()

                if page:
                    # add page to the population
                    ap = Page_Population(page_id=page.id, population_id=population.id)
                    db.session.add(ap)
                    db.session.commit()

                else:
                    # add page to the database
                    page = Page(
                        name=agent["name"],
                        descr="",
                        page_type="",
                        feed=agent["feed_url"],
                        keywords="",
                        pg_type=agent["type"],
                        leaning=agent["leaning"],
                        logo="",
                    )
                    db.session.add(page)
                    db.session.commit()

                    # add page to the population
                    ap = Page_Population(page_id=page.id, population_id=population.id)
                    db.session.add(ap)
                    db.session.commit()

            # add agent to the database
            else:
                ag = Agent(
                    name=agent["name"],
                    age=agent["age"],
                    ag_type=agent["type"],
                    leaning=agent["leaning"],
                    interests=",".join(agent["interests"][0]),
                    oe=agent["oe"],
                    co=agent["co"],
                    ne=agent["ne"],
                    ag=agent["ag"],
                    ex=agent["ex"],
                    language=agent["language"],
                    education_level=agent["education_level"],
                    round_actions=agent["round_actions"],
                    nationality=agent["nationality"],
                    toxicity=agent["toxicity"],
                    gender=agent["gender"],
                    crecsys=agent["rec_sys"],
                    frecsys=agent["frec_sys"],
                    profile_pic="",
                    daily_activity_level=agent["daily_activity_level"],
                    profession=agent["profession"] if "profession" in agent else "",
                )
                db.session.add(ag)
                db.session.commit()

                if "prompts" in agent and agent["prompts"] is not None:
                    ag_profile = Agent_Profile(agent_id=ag.id, profile=agent["prompts"])
                    db.session.add(ag_profile)
                    db.session.commit()

                # add agent to population
                ap = Agent_Population(agent_id=ag.id, population_id=population.id)
                db.session.add(ap)
                db.session.commit()

        # get the json file that start with "client" and contains "population"
        client = [
            f
            for f in os.listdir(f"{BASE_DIR}experiments{os.sep}{uid}")
            if f.endswith(".json") and f.startswith("client") and name in f
        ]
        if len(client) == 0:
            flash("No client file found for the population")
            shutil.rmtree(f"{BASE_DIR}experiments{os.sep}{uid}", ignore_errors=True)
            return redirect(request.referrer)

        client = json.load(
            open(f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}{client[0]}")
        )

        # add client to the database
        cl = Client(
            id_exp=exp.idexp,
            population_id=population.id,
            status=0,
            name=client["simulation"]["name"],
            descr="",
            days=client["simulation"]["days"],
            percentage_new_agents_iteration=client["simulation"][
                "percentage_new_agents_iteration"
            ],
            percentage_removed_agents_iteration=client["simulation"][
                "percentage_removed_agents_iteration"
            ],
            max_length_thread_reading=client["agents"]["max_length_thread_reading"],
            reading_from_follower_ratio=client["agents"]["reading_from_follower_ratio"],
            probability_of_daily_follow=client["agents"]["probability_of_daily_follow"],
            attention_window=client["agents"]["attention_window"],
            visibility_rounds=client["posts"]["visibility_rounds"],
            post=client["simulation"]["actions_likelihood"]["post"],
            share=client["simulation"]["actions_likelihood"]["share"],
            image=client["simulation"]["actions_likelihood"]["image"],
            comment=client["simulation"]["actions_likelihood"]["comment"],
            read=client["simulation"]["actions_likelihood"]["read"],
            news=client["simulation"]["actions_likelihood"]["news"],
            search=client["simulation"]["actions_likelihood"]["search"],
            vote=client["simulation"]["actions_likelihood"]["cast"],
            llm=client["servers"]["llm"],
            llm_api_key=client["servers"]["llm_api_key"],
            llm_max_tokens=client["servers"]["llm_max_tokens"],
            llm_temperature=client["servers"]["llm_temperature"],
            llm_v_agent=client["agents"]["llm_v_agent"],
            llm_v=client["servers"]["llm_v"],
            llm_v_api_key=client["servers"]["llm_v_api_key"],
            llm_v_max_tokens=client["servers"]["llm_v_max_tokens"],
            llm_v_temperature=client["servers"]["llm_v_temperature"],
        )
        db.session.add(cl)
        db.session.commit()

        client_exec = Client_Execution(
            client_id=cl.id,
            last_active_hour=0,
            last_active_day=0,
            expected_duration_rounds=cl.days * client["simulation"]["slots"],
        )
        db.session.add(client_exec)
        db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/upload_database", methods=["POST"])
@login_required
def upload_database():
    check_privileges(current_user.username)

    database = request.files["sqlite_filename"]
    config = request.files["yserver_filename"]
    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    database.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db")
    config.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json")

    try:
        experiment = json.load(
            open(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json")
        )
        experiment = experiment["name"]

        # check if the experiment already exists
        exp = Exps.query.filter_by(exp_name=experiment).first()

        if exp:
            flash(
                "The experiment already exists. Please check the experiment name and try again."
            )
            shutil.rmtree(f"y_web{os.sep}experiments{os.sep}{uid}", ignore_errors=True)
            return settings()

        exp = Exps(
            exp_name=experiment,
            db_name=f"experiments{os.sep}{uid}{os.sep}{database.filename}",
            owner="",
            exp_descr="",
            status=0,
        )

        db.session.add(exp)
        db.session.commit()

        exp_stats = Exp_stats(
            exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0
        )

        db.session.add(exp_stats)
        db.session.commit()

    except:
        flash(
            "There was an error loading the experiment files. Please check the files and try again."
        )
        # remove the directory containing the files
        shutil.rmtree(f"y_web{os.sep}experiments{os.sep}{uid}", ignore_errors=True)

    return settings()


@experiments.route("/admin/create_experiment", methods=["POST", "GET"])
@login_required
def create_experiment():
    check_privileges(current_user.username)

    exp_name = request.form.get("exp_name")
    exp_descr = request.form.get("exp_descr")
    owner = request.form.get("owner")
    platform_type = request.form.get("platform_type")
    host = request.form.get("host")
    port = int(request.form.get("port"))
    perspective_api = request.form.get("perspective_api")
    
    # Handle RSS feeds file upload for forum experiments
    rss_feeds_file = None
    if platform_type == "forum" and "rss_feeds" in request.files:
        rss_feeds_file = request.files["rss_feeds"]
        if rss_feeds_file and rss_feeds_file.filename != "":
            # Validate it's a JSON file
            if not rss_feeds_file.filename.lower().endswith('.json'):
                flash("RSS feeds file must be a JSON file")
                return redirect(request.referrer)

    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    # copy the clean database to the experiments folder
    if platform_type == "microblogging" or platform_type == "forum":
        shutil.copyfile(
            f"data_schema{os.sep}database_clean_server.db",
            f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db",
        )
    else:
        raise NotImplementedError(f"Unsupported platform {platform_type}")

    config = {
        "platform_type": platform_type,
        "name": exp_name,
        "host": host,
        "port": port,
        "debug": "False",
        "reset_db": "False",
        "modules": ["news", "voting", "image"],
        "perspective_api": perspective_api if len(perspective_api) > 0 else None,
    }

    with open(
        f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json", "w"
    ) as f:
        json.dump(config, f)

    # Save RSS feeds file if uploaded for forum experiments
    if rss_feeds_file and rss_feeds_file.filename != "":
        try:
            # Validate JSON format by trying to parse it
            rss_content = rss_feeds_file.read()
            rss_data = json.loads(rss_content.decode('utf-8'))
            
            # Save the RSS file to experiment directory
            with open(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}rss_feeds.json", "w") as f:
                json.dump(rss_data, f, indent=2)
                
            flash(f"RSS feeds file uploaded successfully with {len(rss_data)} feeds")
            
        except json.JSONDecodeError:
            flash("Invalid JSON format in RSS feeds file")
            return redirect(request.referrer)
        except Exception as e:
            flash(f"Error processing RSS feeds file: {str(e)}")
            return redirect(request.referrer)

    # add the experiment to the database

    exp = Exps(
        exp_name=exp_name,
        platform_type=platform_type,
        db_name=f"experiments{os.sep}{uid}{os.sep}database_server.db",
        owner=db.session.query(Admin_users).filter_by(id=owner).first().username,
        exp_descr=exp_descr,
        status=0,
        port=int(port),
        server=host,
    )

    db.session.add(exp)
    db.session.commit()

    exp_stats = Exp_stats(
        exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0
    )

    db.session.add(exp_stats)
    db.session.commit()

    # add first round to the simulation
    rnd = Rounds(day=0, hour=0)

    db.session.add(rnd)
    db.session.commit()

    return settings()


@experiments.route("/admin/delete_simulation/<int:exp_id>")
@login_required
def delete_simulation(exp_id):
    # get the experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if exp:
        # remove the experiment folder
        shutil.rmtree(
            f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}",
            ignore_errors=True,
        )

        # delete the experiment
        db.session.delete(exp)
        db.session.commit()

        # remove the experiment folder
        shutil.rmtree(
            f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[0]}{os.sep}{exp.db_name.split(os.sep)[1]}",
            ignore_errors=True,
        )

        # remove populaiton_experiment
        db.session.query(Population_Experiment).filter_by(id_exp=exp_id).delete()
        db.session.commit()

        # delete user experiment
        db.session.query(User_Experiment).filter_by(exp_id=exp_id).delete()
        db.session.commit()

        # get clients ids for the experiment
        clients = db.session.query(Client).filter_by(id_exp=exp_id).all()
        cids = [c.id for c in clients]

        # delete the clients
        db.session.query(Client).filter_by(id_exp=exp_id).delete()
        db.session.commit()

        # delete exp stats
        db.session.query(Exp_stats).filter_by(exp_id=exp_id).delete()
        db.session.commit()

        for cid in cids:
            # delete the client executions
            db.session.query(Client_Execution).filter_by(client_id=cid).delete()
            db.session.commit()

    return settings()


@experiments.route("/admin/experiments_data")
@login_required
def experiments_data():
    query = Exps.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Exps.exp_name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["exp_name", "exp_descr", "owner"]:
                name = "name"
            col = getattr(Exps, name)
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
                "idexp": exp.idexp,
                "exp_name": exp.exp_name,
                "exp_descr": exp.exp_descr,
                "platform_type": exp.platform_type,
                "owner": exp.owner,
                "web": "Loaded" if exp.status == 1 else "Not loaded",
                "running": "Running" if exp.running == 1 else "Stopped",
            }
            for exp in res
        ],
        "total": total,
    }


@experiments.route("/admin/experiment_details/<int:uid>")
@login_required
def experiment_details(uid):
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()

    # get experiment populations along with population names and ids
    experiment_populations = (
        db.session.query(Population_Experiment, Population)
        .join(Population)
        .filter(Population_Experiment.id_exp == uid)
        .all()
    )

    users = (
        db.session.query(Admin_users, User_Experiment)
        .join(User_Experiment)
        .filter(User_Experiment.exp_id == uid)
        .all()
    )

    # get experiment clients
    clients = Client.query.filter_by(id_exp=uid).all()

    ollamas = ollama_status()

    return render_template(
        "admin/experiment_details.html",
        experiment=experiment,
        clients=clients,
        users=users,
        len=len,
        ollamas=ollamas,
    )


@experiments.route("/admin/start_experiment/<int:uid>")
@login_required
def start_experiment(uid):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=uid).first()

    # check if the experiment is already running
    if exp.running == 1:
        return experiment_details(uid)

    # update the experiment status
    db.session.query(Exps).filter_by(idexp=uid).update({Exps.running: 1})
    db.session.commit()

    # start the yserver
    start_server(exp)

    return redirect(request.referrer)  # experiment_details(uid)


@experiments.route("/admin/stop_experiment/<int:uid>")
@login_required
def stop_experiment(uid):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return experiment_details(uid)

    # stop the yserver
    terminate_process_on_port(exp.port)

    # the clients are killed as soon as the server stops
    # update client statuses
    # get all populations for the experiment and update the client_running status
    populations = Client.query.filter_by(id_exp=uid).all()
    for pop in populations:
        db.session.query(Client).filter_by(id=pop.population_id).update(
            {Client.status: 0}
        )
        db.session.commit()

    # update the experiment status
    db.session.query(Exps).filter_by(idexp=uid).update({Exps.running: 0})
    db.session.commit()

    return redirect(request.referrer)  # experiment_details(uid)


@experiments.route("/admin/prompts/<int:uid>")
@login_required
def prompts(uid):
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()
    # get the prompts file for the experiment
    prompts = f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json"

    # read the prompts file
    prompts = json.load(open(prompts))

    ollamas = ollama_status()

    return render_template(
        "admin/prompts.html", experiment=experiment, prompts=prompts, ollamas=ollamas
    )


@experiments.route("/admin/update_prompts/<int:uid>", methods=["POST"])
@login_required
def update_prompts(uid):
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()
    # get the prompts file for the experiment
    prompts_filename = f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json"

    # read the prompts file
    prompts = json.load(open(prompts_filename))

    # update the prompts
    for key in request.form.keys():
        prompts[key] = request.form[key]

    # write the updated prompts
    json.dump(prompts, open(prompts_filename, "w"), indent=4)

    return redirect(request.referrer)


@experiments.route("/admin/download_experiment/<int:eid>", methods=["POST", "GET"])
@login_required
def download_experiment_file(eid):
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=eid).first()
    # get the prompts file for the experiment
    folder = f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}"
    # compress the folder and send the file
    shutil.make_archive(folder, "zip", folder)
    # move th file to the temp_data folder
    shutil.move(
        f"{folder}.zip",
        f"y_web{os.sep}experiments{os.sep}temp_data{os.sep}{folder.split(os.sep)[-1]}.zip",
    )
    # return the file
    return send_file(
        f"experiments{os.sep}temp_data{os.sep}{folder.split(os.sep)[-1]}.zip",
        as_attachment=True,
    )


@experiments.route("/admin/miscellanea/", methods=["GET"])
@login_required
def miscellanea():
    check_privileges(current_user.username)

    ollamas = ollama_status()

    return render_template("admin/miscellanea.html", ollamas=ollamas)


@experiments.route("/admin/languages_data")
@login_required
def languages_data():
    query = Languages.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Languages.language.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["language"]:
                name = "name"
            col = getattr(Exps, name)
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

    res = {
        "data": [
            {
                "id": exp.id,
                "language": exp.language,
            }
            for exp in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/leanings_data")
@login_required
def leanings_data():
    query = Leanings.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Leanings.leaning.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["leaning"]:
                name = "name"
            col = getattr(Exps, name)
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

    res = {
        "data": [
            {
                "id": exp.id,
                "leaning": exp.leaning,
            }
            for exp in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/nationalities_data")
@login_required
def nationalities_data():
    query = Nationalities.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Nationalities.nationality.like(f"%{search}%")))
    total = query.count()

    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Leanings.leaning.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["leaning"]:
                name = "name"
            col = getattr(Exps, name)
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

    res = {
        "data": [
            {
                "id": exp.id,
                "nationality": exp.nationality,
            }
            for exp in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/professions_data")
@login_required
def professions_data():
    query = Profession.query

    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Profession.profession.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["profession", "background"]:
                name = "name"
            col = getattr(Exps, name)
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

    res = {
        "data": [
            {
                "id": exp.id,
                "profession": exp.profession,
                "background": exp.background,
            }
            for exp in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/educations_data")
@login_required
def educations_data():
    query = Education.query

    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Education.education_level.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["education_level"]:
                name = "name"
            col = getattr(Exps, name)
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

    res = {
        "data": [
            {
                "id": exp.id,
                "education_level": exp.education_level,
            }
            for exp in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/create_language")
@login_required
def create_language():
    check_privileges(current_user.username)

    language = request.args.get("language")

    lang = Languages(language=language)
    db.session.add(lang)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_leaning")
@login_required
def create_leaning():
    check_privileges(current_user.username)

    leaning = request.args.get("leaning")

    lean = Leanings(leaning=leaning)
    db.session.add(lean)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_nationality")
@login_required
def create_nationality():
    check_privileges(current_user.username)

    nationality = request.args.get("nationality")
    nat = Nationalities(nationality=nationality)

    db.session.add(nat)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_profession")
@login_required
def create_profession():
    check_privileges(current_user.username)

    profession = request.args.get("profession")
    background = request.args.get("background")

    prof = Profession(profession=profession, background=background)
    db.session.add(prof)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_education")
@login_required
def create_education():
    check_privileges(current_user.username)

    education_level = request.args.get("education_level")

    ed = Education(education_level=education_level)
    db.session.add(ed)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/upload_rss_feeds/<int:exp_id>", methods=["POST"])
@login_required
def upload_rss_feeds(exp_id):
    check_privileges(current_user.username)
    
    experiment = Exps.query.filter_by(idexp=exp_id).first()
    if not experiment:
        flash("Experiment not found")
        return redirect(request.referrer)
    
    if experiment.platform_type != "forum":
        flash("RSS feeds are only supported for forum experiments")
        return redirect(request.referrer)
    
    rss_feeds_file = request.files.get("rss_feeds")
    if not rss_feeds_file or rss_feeds_file.filename == "":
        flash("Please select an RSS feeds file")
        return redirect(request.referrer)
    
    if not rss_feeds_file.filename.lower().endswith('.json'):
        flash("RSS feeds file must be a JSON file")
        return redirect(request.referrer)
    
    try:
        # Validate JSON format
        rss_content = rss_feeds_file.read()
        rss_data = json.loads(rss_content.decode('utf-8'))
        
        # Save the RSS file to experiment directory
        exp_dir = f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}"
        with open(f"{exp_dir}{os.sep}rss_feeds.json", "w") as f:
            json.dump(rss_data, f, indent=2)
            
        flash(f"RSS feeds file uploaded successfully with {len(rss_data)} feeds")
        
    except json.JSONDecodeError:
        flash("Invalid JSON format in RSS feeds file")
    except Exception as e:
        flash(f"Error processing RSS feeds file: {str(e)}")
    
    return redirect(request.referrer)


@experiments.route("/admin/download_rss_feeds/<int:exp_id>", methods=["GET"])
@login_required
def download_rss_feeds(exp_id):
    check_privileges(current_user.username)
    
    experiment = Exps.query.filter_by(idexp=exp_id).first()
    if not experiment:
        if request.headers.get('Accept') == 'application/json':
            return {"error": "Experiment not found"}, 404
        flash("Experiment not found")
        return redirect(request.referrer)
    
    exp_dir = f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}"
    rss_file_path = f"{exp_dir}{os.sep}rss_feeds.json"
    
    if not os.path.exists(rss_file_path):
        if request.headers.get('Accept') == 'application/json':
            return {"error": "No RSS feeds file found"}, 404
        flash("No RSS feeds file found for this experiment")
        return redirect(request.referrer)
    
    # If this is an AJAX request (JSON), return the data
    if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
        try:
            with open(rss_file_path, 'r') as f:
                rss_data = json.load(f)
            return rss_data
        except Exception as e:
            return {"error": f"Error reading RSS file: {str(e)}"}, 500
    
    # Otherwise, return the file for download
    return send_file(
        f"experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}rss_feeds.json",
        as_attachment=True,
        download_name=f"{experiment.exp_name}_rss_feeds.json"
    )
