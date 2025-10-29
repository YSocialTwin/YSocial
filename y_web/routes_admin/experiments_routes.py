"""
Experiment management routes.

Administrative routes for creating, configuring, launching, and managing
social media simulation experiments including database setup, population
assignment, and experiment lifecycle control.
"""

import json
import os
import pathlib
import shutil
import uuid

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
)
from flask_login import current_user, login_required
from traitlets import Instance

from y_web import db  # , app
from y_web.models import (
    ActivityProfile,
    Admin_users,
    AgeClass,
    Agent,
    Agent_Population,
    Agent_Profile,
    Client,
    Client_Execution,
    Education,
    Exp_stats,
    Exp_Topic,
    Exps,
    Jupyter_instances,
    Languages,
    Leanings,
    Nationalities,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    Profession,
    Rounds,
    Topic_List,
    Toxicity_Levels,
    User_Experiment,
    User_mgmt,
)
from y_web.utils import (
    start_server,
    terminate_process_on_port,
    terminate_server_process,
)
from y_web.utils.jupyter_utils import stop_process
from y_web.utils.miscellanea import check_privileges, ollama_status, reload_current_user

experiments = Blueprint("experiments", __name__)


@experiments.route("/admin/experiments")
@login_required
def settings():
    """
    Display experiments settings and management page.

    Shows list of experiments, users, and database configuration.
    """
    check_privileges(current_user.username)

    # load all experiments
    experiments = Exps.query.limit(5).all()
    users = Admin_users.query.all()

    # check if current db is the same of the active experiment
    exp = Exps.query.filter_by(status=1).first()
    if exp:
        active_db = current_app.config["SQLALCHEMY_BINDS"]["db_exp"]
        if exp.exp_name not in active_db:
            # change the active experiment
            db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})

    ollamas = ollama_status()

    dbtype = current_app.config["SQLALCHEMY_DATABASE_URI"].split(":")[0]

    return render_template(
        "admin/settings.html",
        experiments=experiments,
        users=users,
        ollamas=ollamas,
        dbtype=dbtype,
        enable_notebook=current_app.config.get("ENABLE_NOTEBOOK", False),
    )


@experiments.route("/admin/join_simulation")
@login_required
def join_simulation():
    # get user id for the current user logged in
    """Handle join simulation operation."""
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
    """
    Change the currently active experiment.

    Args:
        exp_id: ID of experiment to activate

    Returns:
        Redirect to settings page
    """
    check_privileges(current_user.username)
    uname = current_user.username

    exp = Exps.query.filter_by(idexp=exp_id).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    # check the database type in the URI
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        new_db = "/".join(
            current_app.config["SQLALCHEMY_DATABASE_URI"].rsplit("/", 1)[:-1]
            + [exp.db_name]
        )
        # if postgresql, set the bind to the postgresql database
        current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = new_db
    elif current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        current_app.config["SQLALCHEMY_BINDS"][
            "db_exp"
        ] = f"sqlite:///{BASE_DIR}/{exp.db_name}"

    else:
        flash("Unsupported database type. Please use SQLite or PostgreSQL.")
        return redirect(request.referrer)

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
    """Upload experiment."""
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
            platform_type=experiment["platform_type"],
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
    """Upload database."""
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
    """Create experiment."""
    check_privileges(current_user.username)

    exp_name = request.form.get("exp_name")
    exp_descr = request.form.get("exp_descr")
    owner = request.form.get("owner")
    platform_type = request.form.get("platform_type")
    host = request.form.get("host")
    port = int(request.form.get("port"))

    # Get annotation settings
    toxicity_annotation = request.form.get("toxicity_annotation") == "true"
    perspective_api = (
        request.form.get("perspective_api") if toxicity_annotation else None
    )
    sentiment_annotation = request.form.get("sentiment_annotation") == "true"
    emotion_annotation = request.form.get("emotion_annotation") == "true"

    topics = request.form.get("tags").split(",")

    # identify db type
    db_type = "sqlite"
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        db_type = "postgresql"

    uid = str(uuid.uuid4()).replace("-", "_")
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    # copy the clean database to the experiments folder
    if platform_type == "microblogging" or platform_type == "forum":
        if db_type == "sqlite":
            shutil.copyfile(
                f"data_schema{os.sep}database_clean_server.db",
                f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db",
            )
        elif db_type == "postgresql":
            from urllib.parse import urlparse

            from sqlalchemy import create_engine, text
            from werkzeug.security import generate_password_hash

            # Get current URI and parse it
            current_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
            parsed_uri = urlparse(current_uri)

            # Extract components
            user = parsed_uri.username or "postgres"
            password = parsed_uri.password or "password"
            host = parsed_uri.hostname or "localhost"
            port_db = parsed_uri.port or 5432

            # New database name
            dbname = f"experiments_{uid}".replace("-", "_")  # PostgreSQL-safe
            db_uri = f"postgresql://{user}:{password}@{host}:{port_db}/{dbname}"

            # Connect to the default 'postgres' DB to check/create the new one
            admin_engine = create_engine(
                f"postgresql://{user}:{password}@{host}:{port_db}/postgres"
            )

            # --- Check and create dummy DB if needed ---
            with admin_engine.connect() as conn:
                result = conn.execute(
                    text(f"SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": dbname},
                )
                db_exists = result.scalar() is not None

            if not db_exists:
                # CREATE DATABASE must run in AUTOCOMMIT mode
                with admin_engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as conn:
                    conn.execute(
                        text(f'CREATE DATABASE "{dbname}"')
                    )  # quoted for safety

                # ✅ Now connect to the *newly created* database
                experiment_engine = create_engine(db_uri)
                with experiment_engine.connect() as dummy_conn:
                    # Load schema
                    schema_path = os.path.join("data_schema", "postgre_server.sql")
                    with open(schema_path, "r") as schema_file:
                        schema_sql = schema_file.read()
                        dummy_conn.execute(text(schema_sql))

                    # Insert initial admin user
                    hashed_pw = generate_password_hash("test", method="pbkdf2:sha256")

                    stmt = text(
                        """
                                INSERT INTO user_mgmt (username, email, password, user_type, leaning, age,
                                                       language, owner, joined_on, frecsys_type,
                                                       round_actions, toxicity, is_page, daily_activity_level)
                                VALUES (:username, :email, :password, :user_type, :leaning, :age,
                                        :language, :owner, :joined_on, :frecsys_type,
                                        :round_actions, :toxicity, :is_page, :daily_activity_level)
                                """
                    )

                    dummy_conn.execute(
                        stmt,
                        {
                            "username": "admin",
                            "email": "admin@ysocial.com",
                            "password": hashed_pw,
                            "user_type": "user",
                            "leaning": "none",
                            "age": 0,
                            "language": "en",
                            "owner": "admin",
                            "joined_on": 0,
                            "frecsys_type": "default",
                            "round_actions": 3,
                            "toxicity": "none",
                            "is_page": 0,
                            "daily_activity_level": 1,
                        },
                    )

                experiment_engine.dispose()

            admin_engine.dispose()

        else:
            raise NotImplementedError(f"Unsupported dbms {db_type}")
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
        "perspective_api": (
            perspective_api if perspective_api and len(perspective_api) > 0 else None
        ),
        "sentiment_annotation": sentiment_annotation,
        "emotion_annotation": emotion_annotation,
    }

    with open(
        f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json", "w"
    ) as f:
        json.dump(config, f, indent=4)

    # add the experiment to the database

    annotations = ""
    if toxicity_annotation:
        annotations += "toxicity,"
    if sentiment_annotation:
        annotations += "sentiment,"
    if emotion_annotation:
        annotations += "emotion,"
    # remove trailing comma
    annotations = annotations.rstrip(",")

    exp = Exps(
        exp_name=exp_name,
        platform_type=platform_type,
        db_name=(
            f"experiments{os.sep}{uid}{os.sep}database_server.db"
            if db_type == "sqlite"
            else f"experiments_{uid}"
        ),
        owner=db.session.query(Admin_users).filter_by(id=owner).first().username,
        exp_descr=exp_descr,
        status=0,
        port=int(port),
        server=host,
        annotations=annotations,
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

    for topic in topics:
        # check if the topic already exists in Topics
        topic = topic.strip()
        if topic:
            existing_topic = Topic_List.query.filter_by(name=topic).first()
            if not existing_topic:
                existing_topic = Topic_List(name=topic)
                db.session.add(existing_topic)
                db.session.commit()

            # add the topic to the experiment
            exp_topic = Exp_Topic(exp_id=exp.idexp, topic_id=existing_topic.id)
            db.session.add(exp_topic)
            db.session.commit()

    jn_instance = Jupyter_instances(
        port=-1, notebook_dir="", exp_id=exp.idexp, status="stopped"
    )
    db.session.add(jn_instance)
    db.session.commit()

    return settings()


@experiments.route("/admin/delete_simulation/<int:exp_id>")
@login_required
def delete_simulation(exp_id):
    # get the experiment
    """Delete simulation."""
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if exp:
        # remove the experiment folder
        # check database type
        if current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("sqlite"):
            shutil.rmtree(
                f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}",
                ignore_errors=True,
            )
        elif current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("postgresql"):
            shutil.rmtree(
                f"y_web{os.sep}experiments{os.sep}{exp.db_name.removeprefix('experiments_')}",
                ignore_errors=True,
            )

        # delete the experiment
        db.session.delete(exp)
        db.session.commit()

        # check database type
        if current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("sqlite"):
            # remove the experiment folder
            shutil.rmtree(
                f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[0]}{os.sep}{exp.db_name.split(os.sep)[1]}",
                ignore_errors=True,
            )
        elif current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("postgresql"):
            # remove the experiment folder
            shutil.rmtree(
                f"y_web{os.sep}experiments{os.sep}{exp.db_name.removeprefix('experiments_')}",
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

        # delete experiment topics
        db.session.query(Exp_Topic).filter_by(exp_id=exp_id).delete()
        db.session.commit()

        # delete jupyter instances
        instances = db.session.query(Jupyter_instances).filter_by(exp_id=exp_id).all()
        try:
            stop_process(instances.process, instances.exp_id)
        except Exception:
            pass
        db.session.query(Jupyter_instances).filter_by(exp_id=exp_id).delete()
        db.session.commit()

    return settings()


@experiments.route("/admin/experiments_data")
@login_required
def experiments_data():
    """
    Display paginated list of experiments.

    Returns:
        Rendered experiments list template
    """
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
        # Map column IDs to actual database field names
        column_mapping = {
            "exp_name": "exp_name",
            "owner": "owner",
            "platform_type": "platform_type",
            "exp_descr": "exp_descr",
            "annotations": "annotations",
            "running": "running",
            "web": "status",  # web interface status
        }
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            # Only sort by columns that have database fields
            if name in column_mapping:
                db_field = column_mapping[name]
                col = getattr(Exps, db_field)
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

    # Get JupyterLab status for each experiment
    import psutil

    jupyter_status = {}
    jupyter_instances = Jupyter_instances.query.all()
    for jupyter in jupyter_instances:
        is_running = False
        if jupyter.process is not None:
            try:
                proc = psutil.Process(int(jupyter.process))
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    is_running = True
            except (psutil.NoSuchProcess, ValueError, TypeError):
                pass
        jupyter_status[jupyter.exp_id] = is_running

    return {
        "data": [
            {
                "idexp": exp.idexp,
                "exp_name": exp.exp_name,
                "platform_type": exp.platform_type,
                "owner": exp.owner,
                "web": "Loaded" if exp.status == 1 else "Not loaded",
                "running": "Running" if exp.running == 1 else "Stopped",
                "jupyter_status": (
                    "Active" if jupyter_status.get(exp.idexp, False) else "Inactive"
                ),
                "annotations": exp.annotations if exp.annotations else "",
            }
            for exp in res
        ],
        "total": total,
    }


@experiments.route("/admin/experiment_details/<int:uid>")
@login_required
def experiment_details(uid):
    """Handle experiment details operation."""
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

    # check database type
    dbtype = None
    if current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("sqlite"):
        dbtype = "sqlite"
    elif current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("postgresql"):
        dbtype = "postgresql"

    # get jupyter instance for this experiment if exists

    jupyter_instance = Jupyter_instances.query.filter_by(exp_id=uid).first()

    return render_template(
        "admin/experiment_details.html",
        experiment=experiment,
        clients=clients,
        users=users,
        len=len,
        ollamas=ollamas,
        dbtype=dbtype,
        jupyter_instance=jupyter_instance,
        notebooks=current_app.config["ENABLE_NOTEBOOK"],
    )


@experiments.route("/admin/start_experiment/<int:uid>")
@login_required
def start_experiment(uid):
    """Handle start experiment operation."""
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

    return experiment_details(uid)


@experiments.route("/admin/stop_experiment/<int:uid>")
@login_required
def stop_experiment(uid):
    """Handle stop experiment operation."""
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return experiment_details(uid)

    # stop the yserver - try the new subprocess-based termination first
    # If that fails or no process is tracked, fall back to port-based termination
    terminated = terminate_server_process(uid)
    if not terminated:
        # Fallback to port-based termination for backward compatibility
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

    return experiment_details(uid)


@experiments.route("/admin/prompts/<int:uid>")
@login_required
def prompts(uid):
    """Handle prompts operation."""
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
    """Update prompts."""
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
    """Download experiment file."""
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
    """
    Display miscellaneous settings page (languages, leanings, etc.).

    Returns:
        Rendered miscellaneous settings template
    """
    check_privileges(current_user.username)

    ollamas = ollama_status()

    return render_template("admin/miscellanea.html", ollamas=ollamas)


@experiments.route("/admin/languages_data")
@login_required
def languages_data():
    """Display languages data page."""
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
    """Display leanings data page."""
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
    """Display nationalities data page."""
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
    """Display professions data page."""
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
    """Display educations data page."""
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


@experiments.route("/admin/create_language", methods=["POST"])
@login_required
def create_language():
    """Create language."""
    check_privileges(current_user.username)

    language = request.form.get("language")

    lang = Languages(language=language)
    db.session.add(lang)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_leaning", methods=["POST"])
@login_required
def create_leaning():
    """Create leaning."""
    check_privileges(current_user.username)

    leaning = request.form.get("leaning")

    lean = Leanings(leaning=leaning)
    db.session.add(lean)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_nationality", methods=["POST"])
@login_required
def create_nationality():
    """Create nationality."""
    check_privileges(current_user.username)

    nationality = request.form.get("nationality")
    nat = Nationalities(nationality=nationality)

    db.session.add(nat)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_profession", methods=["POST"])
@login_required
def create_profession():
    """Create profession."""
    check_privileges(current_user.username)

    profession = request.form.get("profession")
    background = request.form.get("background")

    prof = Profession(profession=profession, background=background)
    db.session.add(prof)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_education", methods=["POST"])
@login_required
def create_education():
    """Create education."""
    check_privileges(current_user.username)

    education_level = request.form.get("education_level")

    ed = Education(education_level=education_level)
    db.session.add(ed)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/create_topic", methods=["POST"])
@login_required
def create_topic():
    """Create topic."""
    check_privileges(current_user.username)

    topic = request.form.get("topic")

    # check if the topic already exists
    existing_topic = Topic_List.query.filter_by(name=topic).first()
    if existing_topic:
        flash("The topic already exists.")
        return redirect(request.referrer)

    new_topic = Topic_List(name=topic)
    db.session.add(new_topic)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/topic_data")
@login_required
def topic_data():
    """Display topic data page."""
    query = Topic_List.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Topic_List.name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name"]:
                name = "name"
            col = getattr(Topic_List, name)
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
                "id": exp.id,
                "name": exp.name,
            }
            for exp in res
        ],
        "total": total,
    }


@experiments.route("/admin/delete_topic/<int:topic_id>", methods=["DELETE"])
@login_required
def delete_topic(topic_id):
    """Delete topic."""
    check_privileges(current_user.username)

    topic = Topic_List.query.filter_by(id=topic_id).first()
    if not topic:
        flash("Topic not found.")
        return miscellanea()
    db.session.delete(topic)
    db.session.commit()
    return miscellanea()


@experiments.route("/admin/delete_language/<int:language_id>", methods=["DELETE"])
@login_required
def delete_language(language_id):
    """Delete language."""
    check_privileges(current_user.username)

    language = Languages.query.filter_by(id=language_id).first()
    if not language:
        flash("Language not found.")
        return miscellanea()
    db.session.delete(language)
    db.session.commit()
    return miscellanea()


@experiments.route("/admin/delete_leaning/<int:leaning_id>", methods=["DELETE"])
@login_required
def delete_leaning(leaning_id):
    """Delete leaning."""
    check_privileges(current_user.username)

    leaning = Leanings.query.filter_by(id=leaning_id).first()
    if not leaning:
        flash("Leaning not found.")
        return miscellanea()
    db.session.delete(leaning)
    db.session.commit()
    return miscellanea()


@experiments.route("/admin/delete_nationality/<int:nationality_id>", methods=["DELETE"])
@login_required
def delete_nationality(nationality_id):
    """Delete nationality."""
    check_privileges(current_user.username)

    nationality = Nationalities.query.filter_by(id=nationality_id).first()
    if not nationality:
        flash("Nationality not found.")
        return miscellanea()
    db.session.delete(nationality)
    db.session.commit()
    return miscellanea()


@experiments.route(
    "/admin/delete_education/<int:education_level_id>", methods=["DELETE"]
)
@login_required
def delete_education_level(education_level_id):
    """Delete education level."""
    check_privileges(current_user.username)

    education_level = Education.query.filter_by(id=education_level_id).first()
    if not education_level:
        flash("Education level not found.")
        return miscellanea()
    db.session.delete(education_level)
    db.session.commit()
    return miscellanea()


@experiments.route("/admin/delete_profession/<int:profession_id>", methods=["DELETE"])
@login_required
def delete_profession(profession_id):
    """Delete profession."""
    check_privileges(current_user.username)

    profession = Profession.query.filter_by(id=profession_id).first()
    if not profession:
        flash("Profession not found.")
        return miscellanea()
    db.session.delete(profession)
    db.session.commit()
    return miscellanea()


@experiments.route("/admin/toxicity_levels_data")
@login_required
def toxicity_levels_data():
    """Display toxicity levels data page."""
    query = Toxicity_Levels.query

    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Toxicity_Levels.toxicity_level.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["toxicity_level"]:
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
                "toxicity_level": exp.toxicity_level,
            }
            for exp in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/create_toxicity_level", methods=["POST"])
@login_required
def create_toxicity_level():
    """Create toxicity level."""
    check_privileges(current_user.username)

    toxicity_level = request.form.get("toxicity_level")

    tox = Toxicity_Levels(toxicity_level=toxicity_level)
    db.session.add(tox)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route(
    "/admin/delete_toxicity_level/<int:toxicity_level_id>", methods=["DELETE"]
)
@login_required
def delete_toxicity_level(toxicity_level_id):
    """Delete toxicity level."""
    check_privileges(current_user.username)

    toxicity_level = Toxicity_Levels.query.filter_by(id=toxicity_level_id).first()
    if not toxicity_level:
        flash("Toxicity level not found.")
        return miscellanea()
    db.session.delete(toxicity_level)
    db.session.commit()
    return miscellanea()


@experiments.route("/admin/age_classes_data", methods=["GET", "POST"])
@login_required
def age_classes_data():
    """Display age classes data page and handle inline edits."""
    if request.method == "POST":
        # Handle inline edit
        data = request.get_json()
        age_class_id = data.get("id")
        age_class = AgeClass.query.filter_by(id=age_class_id).first()
        if age_class:
            try:
                if "name" in data:
                    age_class.name = data["name"]
                if "age_start" in data:
                    age_class.age_start = int(data["age_start"])
                if "age_end" in data:
                    age_class.age_end = int(data["age_end"])
                db.session.commit()
            except (ValueError, TypeError):
                return {"success": False, "error": "Invalid value provided"}, 400
        return {"success": True}

    # GET request - return data for grid
    query = AgeClass.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(AgeClass.name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name", "age_start", "age_end"]:
                name = "name"
            col = getattr(AgeClass, name)
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
                "id": ac.id,
                "name": ac.name,
                "age_start": ac.age_start,
                "age_end": ac.age_end,
            }
            for ac in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/create_age_class", methods=["POST"])
@login_required
def create_age_class():
    """Create age class."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    try:
        age_start = int(request.form.get("age_start", 0))
        age_end = int(request.form.get("age_end", 100))
    except (ValueError, TypeError):
        flash("Invalid age value provided.")
        return miscellanea()

    age_class = AgeClass(
        name=name,
        age_start=age_start,
        age_end=age_end,
    )
    db.session.add(age_class)
    db.session.commit()

    return miscellanea()


@experiments.route("/admin/delete_age_class/<int:age_class_id>", methods=["DELETE"])
@login_required
def delete_age_class(age_class_id):
    """Delete age class."""
    check_privileges(current_user.username)

    age_class = AgeClass.query.filter_by(id=age_class_id).first()
    if not age_class:
        flash("Age class not found.")
        return miscellanea()
    db.session.delete(age_class)
    db.session.commit()
    return miscellanea()


@experiments.route("/admin/activity_profiles_data", methods=["GET", "POST"])
@login_required
def activity_profiles_data():
    """Display activity profiles data page and handle inline edits."""
    if request.method == "POST":
        # Handle inline edit
        data = request.get_json()
        profile_id = data.get("id")
        profile = ActivityProfile.query.filter_by(id=profile_id).first()
        if profile:
            if "name" in data:
                profile.name = data["name"]
            db.session.commit()
        return {"success": True}

    query = ActivityProfile.query

    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(ActivityProfile.name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name"]:
                name = "name"
            col = getattr(ActivityProfile, name)
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
                "id": profile.id,
                "name": profile.name,
                "hours": profile.hours,
            }
            for profile in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/create_activity_profile", methods=["POST"])
@login_required
def create_activity_profile():
    """Create activity profile."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    hours = request.form.get("hours")

    if not name or not hours:
        flash("Name and hours are required.")
        return redirect(request.referrer)

    # Check if the profile already exists
    existing_profile = ActivityProfile.query.filter_by(name=name).first()
    if existing_profile:
        flash("An activity profile with this name already exists.")
        return redirect(request.referrer)

    profile = ActivityProfile(name=name, hours=hours)
    db.session.add(profile)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route(
    "/admin/delete_activity_profile/<int:profile_id>", methods=["DELETE"]
)
@login_required
def delete_activity_profile(profile_id):
    """Delete activity profile."""
    check_privileges(current_user.username)

    profile = ActivityProfile.query.filter_by(id=profile_id).first()
    if not profile:
        flash("Activity profile not found.")
        return miscellanea()
    db.session.delete(profile)
    db.session.commit()
    return miscellanea()
