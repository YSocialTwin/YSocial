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
import socket
import uuid
from collections import defaultdict

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

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
    ClientLogMetrics,
    Education,
    Exp_stats,
    Exp_Topic,
    ExperimentScheduleGroup,
    ExperimentScheduleItem,
    ExperimentScheduleLog,
    ExperimentScheduleStatus,
    Exps,
    Jupyter_instances,
    Languages,
    Leanings,
    LogFileOffset,
    LogSyncSettings,
    Nationalities,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    Profession,
    Rounds,
    ServerLogMetrics,
    Topic_List,
    Toxicity_Levels,
    User_Experiment,
    User_mgmt,
)
from y_web.utils import (
    start_client,
    start_server,
    terminate_client,
    terminate_process_on_port,
    terminate_server_process,
)
from y_web.utils.desktop_file_handler import send_file_desktop
from y_web.utils.jupyter_utils import stop_process
from y_web.utils.miscellanea import check_privileges, ollama_status, reload_current_user
from y_web.utils.path_utils import get_resource_path

experiments = Blueprint("experiments", __name__)


def get_suggested_port():
    """
    Find the first available port in the range 5000-6000.

    A port is considered available if:
    1. It is not assigned to any existing experiment (regardless of running status)
    2. It is currently free (not in use by any process)

    Returns:
        int: The first available port, or 5000 if none found
    """
    # Get all ports assigned to existing experiments
    assigned_ports = set()
    experiments = Exps.query.all()
    for exp in experiments:
        if exp.port:
            assigned_ports.add(exp.port)

    # Check each port in the range
    for port in range(5000, 6001):
        # Skip if already assigned to an experiment
        if port in assigned_ports:
            continue

        # Check if port is currently free
        if is_port_free(port):
            return port

    # Return None if no port is available
    return None


def is_port_free(port):
    """
    Check if a port is currently free.

    Args:
        port: Port number to check

    Returns:
        bool: True if port is free, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def is_port_valid(port):
    """
    Validate that a port is in the allowed range and not already assigned.

    Args:
        port: Port number to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    # Check range
    if port < 5000 or port > 6000:
        return False, "Port must be in the range 5000-6000"

    # Check if already assigned to an experiment
    existing_exp = Exps.query.filter_by(port=port).first()
    if existing_exp:
        return (
            False,
            f"Port {port} is already assigned to experiment '{existing_exp.exp_name}'",
        )

    return True, None


@experiments.route("/admin/experiments")
@login_required
def settings():
    """
    Display experiments settings and management page.

    Shows list of experiments, users, and database configuration.
    """
    # Get current user
    user = Admin_users.query.filter_by(username=current_user.username).first()

    # Filter experiments based on user role
    if user.role == "admin":
        # Admin sees all experiments (limit 5 for initial display)
        experiments = Exps.query.limit(5).all()
        # All experiments for copy dropdown (no limit)
        all_experiments = Exps.query.all()
    elif user.role == "researcher":
        # Researcher sees only experiments they own (limit 5 for initial display)
        experiments = Exps.query.filter_by(owner=user.username).limit(5).all()
        # All experiments owned by researcher for copy dropdown (no limit)
        all_experiments = Exps.query.filter_by(owner=user.username).all()
    else:
        # Regular users should not access this page
        flash("Access denied. Please use the experiment feed.")
        return redirect(url_for("auth.login"))

    users = Admin_users.query.all()

    # check if current db is the same of the active experiment
    exp = Exps.query.filter_by(status=1).first()
    if exp:
        active_db = current_app.config["SQLALCHEMY_BINDS"]["db_exp"]
        if exp.exp_name not in active_db:
            # change the active experiment
            db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})

    dbtype = current_app.config["SQLALCHEMY_DATABASE_URI"].split(":")[0]

    # Get suggested port for new experiment
    suggested_port = get_suggested_port()

    return render_template(
        "admin/settings.html",
        experiments=experiments,
        all_experiments=all_experiments,
        users=users,
        dbtype=dbtype,
        suggested_port=suggested_port,
        enable_notebook=current_app.config.get("ENABLE_NOTEBOOK", False),
    )


@experiments.route("/admin/join_simulation")
@login_required
def join_simulation():
    """
    Display menu of active experiments for user to join.

    If only one experiment is active, redirect directly.
    If multiple experiments are active, show selection menu.
    """
    # Get all active experiments
    active_exps = Exps.query.filter_by(status=1).all()

    if not active_exps:
        flash("No active experiment. Please activate an experiment first.")
        return redirect(request.referrer)

    # If only one active experiment, redirect directly
    if len(active_exps) == 1:
        exp = active_exps[0]
        return redirect(f"/admin/join_experiment/{exp.idexp}")

    # Multiple active experiments - show selection menu
    check_privileges(current_user.username)

    return render_template(
        "admin/select_experiment.html",
        experiments=active_exps,
    )


@experiments.route("/admin/join_experiment/<int:exp_id>")
@login_required
def join_experiment(exp_id):
    """
    Join a specific active experiment.

    Args:
        exp_id: ID of experiment to join

    Returns:
        Redirect to experiment feed
    """
    exp = Exps.query.filter_by(idexp=exp_id, status=1).first()
    if exp is None:
        flash("Experiment not found or not active.")
        return redirect("/admin/experiments")

    # Get user id - need to check in the experiment database
    from y_web.experiment_context import register_experiment_database

    bind_key = f"db_exp_{exp_id}"

    # Ensure the experiment database is registered
    if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
        register_experiment_database(current_app, exp_id, exp.db_name)

    # Temporarily switch to experiment database to get user
    old_bind = current_app.config["SQLALCHEMY_BINDS"]["db_exp"]
    current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
        "SQLALCHEMY_BINDS"
    ][bind_key]

    try:
        user = (
            db.session.query(User_mgmt)
            .filter_by(username=current_user.username)
            .first()
        )
        if not user:
            flash("User not found in experiment database.")
            return redirect("/admin/experiments")
        user_id = user.id
    finally:
        current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind

    # Route to the appropriate feed based on platform type
    if exp.platform_type == "microblogging":
        return redirect(f"/{exp_id}/feed/{user_id}/feed/rf/1")
    elif exp.platform_type == "forum":
        return redirect(f"/{exp_id}/rfeed/{user_id}/feed/rf/1")
    else:
        flash("Unknown platform type for this experiment.")
        return redirect("/admin/experiments")


@experiments.route("/admin/select_experiment/<int:exp_id>")
@login_required
def change_active_experiment(exp_id):
    """
    Activate or deactivate an experiment.

    Now supports multiple active experiments simultaneously.

    Args:
        exp_id: ID of experiment to toggle activation

    Returns:
        Redirect to settings page
    """
    check_privileges(current_user.username)
    uname = current_user.username

    exp = Exps.query.filter_by(idexp=exp_id).first()

    if not exp:
        flash("Experiment not found.")
        return redirect(request.referrer)

    # Toggle experiment status
    if exp.status == 1:
        # Deactivate the experiment
        exp.status = 0
        db.session.commit()
        flash(f"Experiment '{exp.exp_name}' deactivated.")
    else:
        # Activate the experiment
        exp.status = 1
        db.session.commit()

        # Register the experiment database dynamically
        from y_web.experiment_context import register_experiment_database

        register_experiment_database(current_app, exp_id, exp.db_name)

        # Ensure user exists in the experiment database
        # We need to switch to the correct bind temporarily
        bind_key = f"db_exp_{exp_id}"

        # Check if user exists in this experiment's database
        # Note: User_mgmt uses db_exp bind, so we need to query with bind
        with db.session.no_autoflush:
            # Temporarily set db_exp to this experiment
            old_bind = current_app.config["SQLALCHEMY_BINDS"]["db_exp"]
            current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
                "SQLALCHEMY_BINDS"
            ][bind_key]

            try:
                user = (
                    db.session.query(User_mgmt)
                    .filter_by(username=current_user.username)
                    .first()
                )

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
            finally:
                # Restore old bind
                current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind

        # Add user to experiment if not present
        user_exp = (
            db.session.query(User_Experiment)
            .filter_by(user_id=current_user.id, exp_id=exp_id)
            .first()
        )
        if user_exp is None:
            user_exp = User_Experiment(user_id=current_user.id, exp_id=exp_id)
            db.session.add(user_exp)
            db.session.commit()

        flash(f"Experiment '{exp.exp_name}' activated.")

    reload_current_user(uname)

    return redirect("/admin/dashboard")


@experiments.route("/admin/upload_experiment", methods=["POST"])
@login_required
def upload_experiment():
    """Upload experiment."""
    check_privileges(current_user.username)

    experiment = request.files["experiment"]
    # Get experiment name from form, fallback to name from config if not provided
    exp_name_override = request.form.get("exp_name", "").strip()
    uid = str(uuid.uuid4()).replace("-", "_")

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    pathlib.Path(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    experiment.save(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}exp.zip"
    )
    # unzip the file
    shutil.unpack_archive(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}exp.zip",
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
    )
    # remove the zip file
    os.remove(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}exp.zip")

    # Handle ZIP files with nested directory structure
    # If config_server.json is not at the expected location, look for it in subdirectories
    exp_dir = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"
    expected_config = os.path.join(exp_dir, "config_server.json")

    if not os.path.exists(expected_config):
        # Look for config_server.json in subdirectories
        for item in os.listdir(exp_dir):
            subdir = os.path.join(exp_dir, item)
            if os.path.isdir(subdir):
                nested_config = os.path.join(subdir, "config_server.json")
                if os.path.exists(nested_config):
                    # Found config_server.json in a subdirectory - move all files up
                    for nested_item in os.listdir(subdir):
                        src = os.path.join(subdir, nested_item)
                        dst = os.path.join(exp_dir, nested_item)
                        # Skip if destination already exists to avoid conflicts
                        if not os.path.exists(dst):
                            shutil.move(src, dst)
                    # Remove the subdirectory (will fail if not empty, which is ok)
                    shutil.rmtree(subdir, ignore_errors=True)
                    break

    # Determine database type
    db_type = "sqlite"
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        db_type = "postgresql"

    # Get suggested port for new experiment
    suggested_port = get_suggested_port()
    if not suggested_port:
        flash(
            "Error: No available port found in range 5000-6000. Cannot upload experiment."
        )
        shutil.rmtree(
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
            ignore_errors=True,
        )
        return redirect(request.referrer)

    # create the experiment in the database from the config_server.json file
    try:
        # list the files in the directory
        files = os.listdir(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}")
        config_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json"

        with open(config_path, "r") as f:
            experiment_config = json.load(f)

        # Use override name if provided, otherwise use name from config
        name = exp_name_override if exp_name_override else experiment_config["name"]

        # check if the experiment already exists
        exp = Exps.query.filter_by(exp_name=name).first()

        if exp:
            flash(
                "The experiment already exists. Please check the experiment name and try again."
            )
            shutil.rmtree(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
                ignore_errors=True,
            )
            return settings()

        # Check client configuration files for llm_agents setting
        # Default to enabled (1) unless we find [null] in any client config
        llm_agents_enabled = 1
        client_files = [
            f
            for f in os.listdir(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"
            )
            if f.endswith(".json") and f.startswith("client")
        ]

        for client_file in client_files:
            try:
                client_config_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}{client_file}"
                with open(client_config_path, "r") as f:
                    client_config = json.load(f)

                # Check if agents.llm_agents exists and equals [null]
                if (
                    "agents" in client_config
                    and "llm_agents" in client_config["agents"]
                ):
                    llm_agents_value = client_config["agents"]["llm_agents"]
                    # Check if it's a list with a single null value
                    if (
                        isinstance(llm_agents_value, list)
                        and len(llm_agents_value) == 1
                        and llm_agents_value[0] is None
                    ):
                        llm_agents_enabled = 0
                        break  # If any client has [null], disable for entire experiment
            except Exception as e:
                # If we can't read a client config, log but continue
                current_app.logger.warning(
                    f"Could not check llm_agents in {client_file}: {str(e)}"
                )

        # Prepare database URI and name based on db_type
        db_name = ""
        db_uri = ""

        if db_type == "sqlite":
            db_name = f"experiments{os.sep}{uid}{os.sep}database_server.db"
            db_uri = os.path.abspath(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db"
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

            # New database name - sanitize to ensure PostgreSQL compatibility
            dbname = f"experiments_{uid}"
            # Validate database name (only alphanumeric and underscore)
            if not dbname.replace("_", "").isalnum():
                raise ValueError(f"Invalid database name: {dbname}")
            db_name = dbname
            db_uri = f"postgresql://{user}:{password}@{host}:{port_db}/{dbname}"

            # Connect to the default 'postgres' DB to check/create the new one
            admin_engine = create_engine(
                f"postgresql://{user}:{password}@{host}:{port_db}/postgres"
            )

            # Check and create database if needed
            with admin_engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": dbname},
                )
                db_exists = result.scalar() is not None

            if not db_exists:
                # CREATE DATABASE must run in AUTOCOMMIT mode
                # Note: Database names are validated above to prevent SQL injection
                with admin_engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as conn:
                    conn.execute(text(f'CREATE DATABASE "{dbname}"'))

                # Connect to the newly created database
                experiment_engine = create_engine(db_uri)
                with experiment_engine.connect() as dummy_conn:
                    # Load and execute schema
                    schema_path = get_resource_path(
                        os.path.join("data_schema", "postgre_server.sql")
                    )
                    try:
                        with open(schema_path, "r") as schema_file:
                            schema_sql = schema_file.read()
                            dummy_conn.execute(text(schema_sql))
                    except Exception as e:
                        # If schema execution fails, log and re-raise
                        current_app.logger.error(
                            f"Failed to execute schema for database {dbname}: {str(e)}"
                        )
                        raise

                    # Insert initial admin user
                    hashed_pw = generate_password_hash("admin", method="pbkdf2:sha256")

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
                            "username": "Admin",
                            "email": "admin@y-not.social",
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

        # Update config_server.json with new port, name, and database_uri
        experiment_config["name"] = name
        experiment_config["port"] = suggested_port
        experiment_config["database_uri"] = db_uri

        with open(config_path, "w") as f:
            json.dump(experiment_config, f, indent=4)

        # Update all client configuration files with new port
        for item in os.listdir(
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"
        ):
            if item.startswith("client") and item.endswith(".json"):
                client_config_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}{item}"
                try:
                    with open(client_config_path, "r") as f:
                        client_config = json.load(f)
                except json.JSONDecodeError as e:
                    flash(f"Warning: Failed to parse client config {item}: {str(e)}")
                    continue
                except IOError as e:
                    flash(f"Warning: Failed to read client config {item}: {str(e)}")
                    continue

                # Update the API endpoint in servers section
                if "servers" in client_config and "api" in client_config["servers"]:
                    try:
                        # Update the port in the API URL
                        import re

                        old_api = client_config["servers"]["api"]
                        # Replace port in URL - handles both with and without trailing slash
                        # Pattern matches :port/ or :port at end of string
                        new_api = re.sub(
                            r":(\d+)(/|$)", f":{suggested_port}\\2", old_api
                        )
                        client_config["servers"]["api"] = new_api

                        with open(client_config_path, "w") as f:
                            json.dump(client_config, f, indent=4)
                    except IOError as e:
                        flash(
                            f"Warning: Failed to write updated client config {item}: {str(e)}"
                        )
                    except Exception as e:
                        flash(
                            f"Warning: Failed to update port in client config {item}: {str(e)}"
                        )

        exp = Exps(
            exp_name=name,
            db_name=db_name,
            owner=current_user.username,
            exp_descr="",
            status=0,
            port=suggested_port,
            server=experiment_config.get("host", "127.0.0.1"),
            platform_type=experiment_config.get("platform_type", "microblogging"),
            llm_agents_enabled=llm_agents_enabled,
        )

        db.session.add(exp)
        db.session.commit()

        exp_stats = Exp_stats(
            exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0
        )
        db.session.add(exp_stats)
        db.session.commit()

        # Create Jupyter instance record
        jupyter_instance = Jupyter_instances(
            port=-1, notebook_dir="", exp_id=exp.idexp, status="stopped"
        )
        db.session.add(jupyter_instance)
        db.session.commit()

        # Reconstruct exp_topic entries from config_server.json
        # If no topics in config, add a generic "Topic 1"
        topics = experiment_config.get("topics", [])
        if not topics:
            topics = ["Topic 1"]

        for topic_name in topics:
            topic_name = topic_name.strip()
            if topic_name:
                # Check if topic already exists in Topic_List
                existing_topic = Topic_List.query.filter_by(name=topic_name).first()
                if not existing_topic:
                    existing_topic = Topic_List(name=topic_name)
                    db.session.add(existing_topic)
                    db.session.commit()

                # Add topic to experiment
                exp_topic = Exp_Topic(exp_id=exp.idexp, topic_id=existing_topic.id)
                db.session.add(exp_topic)
                db.session.commit()

    except Exception as e:
        flash(f"There was an error loading the experiment files: {str(e)}")
        # remove the directory containing the files
        shutil.rmtree(
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
            ignore_errors=True,
        )
        return redirect(request.referrer)

    # get the json files that do not start with "client"
    populations = [
        f
        for f in os.listdir(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}")
        if f.endswith(".json")
        and not f.startswith("client")
        and f != "config_server.json"
        and f != "prompts.json"
    ]

    for population_file in populations:
        original_name = population_file.split(".")[0]
        pop = json.load(
            open(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}{population_file}"
            )
        )

        # check if the population already exists
        existing_population = Population.query.filter_by(name=original_name).first()
        population_created_or_reused = None  # Track if we need to create agents

        if existing_population:
            # Population exists - need to check if agents are the same
            # Get agent names from uploaded config
            uploaded_agent_names = set()
            for agent in pop["agents"]:
                uploaded_agent_names.add(agent["name"])

            # Get agent names from existing population
            existing_agent_names = set()
            # Get agents linked to this population
            agent_pop_links = Agent_Population.query.filter_by(
                population_id=existing_population.id
            ).all()
            for link in agent_pop_links:
                agent = Agent.query.get(link.agent_id)
                if agent:
                    existing_agent_names.add(agent.name)

            # Get pages linked to this population
            page_pop_links = Page_Population.query.filter_by(
                population_id=existing_population.id
            ).all()
            for link in page_pop_links:
                page = Page.query.get(link.page_id)
                if page:
                    existing_agent_names.add(page.name)

            # Check if agents are the same
            if uploaded_agent_names == existing_agent_names:
                # Agents are the same - just link existing population to experiment
                population = existing_population
                pop_exp = Population_Experiment(
                    id_exp=exp.idexp, id_population=population.id
                )
                db.session.add(pop_exp)
                db.session.commit()

                # Skip agent creation - use existing agents
                population_created_or_reused = population
            else:
                # Agents are different - create new population with modified name
                # Find a unique name by appending a counter
                counter = 1
                new_name = f"{original_name}_{counter}"
                while Population.query.filter_by(name=new_name).first():
                    counter += 1
                    new_name = f"{original_name}_{counter}"

                # Rename population and client JSON files to match the new population name
                exp_folder = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"

                # Rename population JSON file
                old_pop_file = os.path.join(exp_folder, f"{original_name}.json")
                new_pop_file = os.path.join(exp_folder, f"{new_name}.json")
                if os.path.exists(old_pop_file):
                    os.rename(old_pop_file, new_pop_file)

                # Rename client JSON file(s) that contain the original population name
                # Client files follow the pattern: client_{client_name}-{population_name}.json
                for f in os.listdir(exp_folder):
                    if f.startswith("client") and f.endswith(".json"):
                        # Check if the filename ends with -{original_name}.json
                        expected_suffix = f"-{original_name}.json"
                        if f.endswith(expected_suffix):
                            old_client_file = os.path.join(exp_folder, f)
                            # Replace only the population name at the end
                            new_client_filename = (
                                f[: -len(expected_suffix)] + f"-{new_name}.json"
                            )
                            new_client_file = os.path.join(
                                exp_folder, new_client_filename
                            )
                            os.rename(old_client_file, new_client_file)

                # Create new population with unique name
                population = Population(name=new_name, descr="")
                db.session.add(population)
                db.session.commit()

                pop_exp = Population_Experiment(
                    id_exp=exp.idexp, id_population=population.id
                )
                db.session.add(pop_exp)
                db.session.commit()

                # Mark that we need to create agents for this new population
                population_created_or_reused = None
        else:
            # Create new population and its agents
            population = Population(name=original_name, descr="")
            db.session.add(population)
            db.session.commit()

            pop_exp = Population_Experiment(
                id_exp=exp.idexp, id_population=population.id
            )
            db.session.add(pop_exp)
            db.session.commit()

            # Mark that we need to create agents for this new population
            population_created_or_reused = None

        # Only create agents if this is a new population or agents are different
        if population_created_or_reused is None:
            for agent in pop["agents"]:
                if agent["is_page"] == 1:
                    # check if the page already exists
                    page = Page.query.filter_by(name=agent["name"]).first()

                    if page:
                        # add page to the population
                        ap = Page_Population(
                            page_id=page.id, population_id=population.id
                        )
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
                        ap = Page_Population(
                            page_id=page.id, population_id=population.id
                        )
                        db.session.add(ap)
                        db.session.commit()

                # add agent to the database
                else:
                    # Handle activity_profile - look up by name or create default
                    activity_profile_id = None
                    activity_profile_name = agent.get("activity_profile", "default")
                    if activity_profile_name:
                        existing_profile = ActivityProfile.query.filter_by(
                            name=activity_profile_name
                        ).first()
                        if existing_profile:
                            activity_profile_id = existing_profile.id
                        else:
                            # Create a default activity profile if it doesn't exist
                            # Default hours: 9am-5pm working hours
                            new_profile = ActivityProfile(
                                name=activity_profile_name,
                                hours="9,10,11,12,13,14,15,16,17",
                            )
                            db.session.add(new_profile)
                            db.session.commit()
                            activity_profile_id = new_profile.id

                    ag = Agent(
                        name=agent["name"],
                        age=agent["age"],
                        ag_type=agent["type"],
                        leaning=agent["leaning"],
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
                        activity_profile=activity_profile_id,
                    )
                    db.session.add(ag)
                    db.session.commit()

                    if "prompts" in agent and agent["prompts"] is not None:
                        ag_profile = Agent_Profile(
                            agent_id=ag.id, profile=agent["prompts"]
                        )
                        db.session.add(ag_profile)
                        db.session.commit()

                    # add agent to population
                    ap = Agent_Population(agent_id=ag.id, population_id=population.id)
                    db.session.add(ap)
                    db.session.commit()

        # get the json file that start with "client" and contains "population"
        client = [
            f
            for f in os.listdir(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"
            )
            if f.endswith(".json") and f.startswith("client") and original_name in f
        ]
        if len(client) == 0:
            flash("No client file found for the population")
            shutil.rmtree(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
                ignore_errors=True,
            )
            return redirect(request.referrer)

        client = json.load(
            open(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}{client[0]}"
            )
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
            last_active_hour=-1,
            last_active_day=-1,
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

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    database = request.files["sqlite_filename"]
    config = request.files["yserver_filename"]
    uid = uuid.uuid4()
    pathlib.Path(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    database.save(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db"
    )
    config.save(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json"
    )

    try:
        experiment = json.load(
            open(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json"
            )
        )
        experiment = experiment["name"]

        # check if the experiment already exists
        exp = Exps.query.filter_by(exp_name=experiment).first()

        if exp:
            flash(
                "The experiment already exists. Please check the experiment name and try again."
            )
            shutil.rmtree(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
                ignore_errors=True,
            )
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
        shutil.rmtree(
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
            ignore_errors=True,
        )

    return settings()


@experiments.route("/admin/create_experiment", methods=["POST", "GET"])
@login_required
def create_experiment():
    """Create experiment."""
    check_privileges(current_user.username)

    exp_name = request.form.get("exp_name")
    exp_descr = request.form.get("exp_descr")
    platform_type = request.form.get("platform_type")

    # Use fixed host value
    host = "127.0.0.1"

    # Use suggested port (first available in range 5000-6000)
    port = get_suggested_port()

    # Use current logged-in user as owner
    owner = current_user.username

    # Get LLM agents setting (convert to integer for database compatibility)
    llm_agents_enabled = 1 if request.form.get("llm_agents_enabled") == "true" else 0

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

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    uid = str(uuid.uuid4()).replace("-", "_")
    pathlib.Path(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    db_uri = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db"

    # copy the clean database to the experiments folder
    if platform_type == "microblogging" or platform_type == "forum":
        if db_type == "sqlite":
            clean_db_source = get_resource_path(
                os.path.join("data_schema", "database_clean_server.db")
            )
            shutil.copyfile(
                clean_db_source,
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db",
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
                    schema_path = get_resource_path(
                        os.path.join("data_schema", "postgre_server.sql")
                    )
                    with open(schema_path, "r") as schema_file:
                        schema_sql = schema_file.read()
                        dummy_conn.execute(text(schema_sql))

                    # Insert initial admin user
                    hashed_pw = generate_password_hash("admin", method="pbkdf2:sha256")

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
                            "username": "Admin",
                            "email": "admin@y-not.social",
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
        "database_uri": db_uri,
        "topics": [t.strip() for t in topics if t.strip()],
    }

    with open(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json",
        "w",
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
        owner=owner,
        exp_descr=exp_descr,
        status=0,
        port=int(port),
        server=host,
        annotations=annotations,
        llm_agents_enabled=llm_agents_enabled,
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

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)
    telemetry.log_event(
        {
            "action": "create_experiment",
            "data": {
                "platform_type": exp.platform_type,
                "annotations": exp.annotations,
                "llm_agents_enabled": exp.llm_agents_enabled,
            },
        },
    )

    # Redirect to the newly created experiment's details page
    return redirect(url_for("experiments.experiment_details", uid=exp.idexp))


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
            from y_web.utils.path_utils import get_writable_path

            BASE_DIR = get_writable_path()
            shutil.rmtree(
                os.path.join(
                    BASE_DIR,
                    f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}",
                ),
                ignore_errors=True,
            )
        elif current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("postgresql"):
            # Remove experiment folder
            from y_web.utils.path_utils import get_writable_path

            BASE_DIR = get_writable_path()
            shutil.rmtree(
                os.path.join(
                    BASE_DIR,
                    f"y_web{os.sep}experiments{os.sep}{exp.db_name.removeprefix('experiments_')}",
                ),
                ignore_errors=True,
            )

            # Drop the PostgreSQL database
            try:
                from urllib.parse import urlparse

                from sqlalchemy import create_engine, text

                current_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
                parsed_uri = urlparse(current_uri)

                user = parsed_uri.username or "postgres"
                password = parsed_uri.password or "password"
                host = parsed_uri.hostname or "localhost"
                port_db = parsed_uri.port or 5432

                # Connect to postgres database
                admin_engine = create_engine(
                    f"postgresql://{user}:{password}@{host}:{port_db}/postgres"
                )

                # Drop the database if it exists
                with admin_engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as conn:
                    # Terminate existing connections to the database
                    conn.execute(
                        text(
                            f"""
                            SELECT pg_terminate_backend(pg_stat_activity.pid)
                            FROM pg_stat_activity
                            WHERE pg_stat_activity.datname = :dbname
                            AND pid <> pg_backend_pid()
                            """
                        ),
                        {"dbname": exp.db_name},
                    )
                    # Drop the database
                    conn.execute(text(f'DROP DATABASE IF EXISTS "{exp.db_name}"'))

                admin_engine.dispose()
            except Exception as e:
                # Log error but continue with deletion
                current_app.logger.error(
                    f"Error dropping PostgreSQL database: {str(e)}", exc_info=True
                )

        # delete the experiment
        db.session.delete(exp)
        db.session.commit()

        # Delete log metrics and offsets (should cascade but we do it explicitly for safety)
        db.session.query(LogFileOffset).filter_by(exp_id=exp_id).delete()
        db.session.query(ServerLogMetrics).filter_by(exp_id=exp_id).delete()
        db.session.query(ClientLogMetrics).filter_by(exp_id=exp_id).delete()
        db.session.commit()

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

            db.session.query(Client).filter_by(id=cid).delete()
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

    Query params:
        exp_status: Filter by experiment status ('active', 'completed', 'stopped', 'scheduled')

    Returns:
        Rendered experiments list template
    """
    # Get current user
    user = Admin_users.query.filter_by(username=current_user.username).first()

    # Filter experiments based on user role
    if user.role == "admin":
        query = Exps.query
    elif user.role == "researcher":
        # Researcher sees only experiments they own
        query = Exps.query.filter_by(owner=user.username)
    else:
        # Regular users should not access this endpoint
        return {"data": [], "total": 0}

    # Filter by exp_status if provided
    exp_status_filter = request.args.get("exp_status")
    if exp_status_filter:
        if exp_status_filter == "stopped_scheduled":
            # Include both 'stopped' and 'scheduled' statuses
            query = query.filter(Exps.exp_status.in_(["stopped", "scheduled"]))
        else:
            query = query.filter(Exps.exp_status == exp_status_filter)

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
            "exp_status": "exp_status",
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

    # Calculate average progress for running experiments
    exp_progress = {}
    for exp in res:
        if exp.running == 1 or exp.exp_status == "active":
            # Get all clients for this experiment
            clients = Client.query.filter_by(id_exp=exp.idexp).all()
            if clients:
                total_progress = 0
                count = 0
                for client in clients:
                    client_exec = Client_Execution.query.filter_by(client_id=client.id).first()
                    if client_exec and client_exec.expected_duration_rounds > 0:
                        progress = min(100, max(0, int(
                            client_exec.elapsed_time / client_exec.expected_duration_rounds * 100
                        )))
                        total_progress += progress
                        count += 1
                if count > 0:
                    exp_progress[exp.idexp] = int(total_progress / count)
                else:
                    exp_progress[exp.idexp] = 0
            else:
                exp_progress[exp.idexp] = 0

    return {
        "data": [
            {
                "idexp": exp.idexp,
                "exp_name": exp.exp_name,
                "platform_type": exp.platform_type,
                "owner": exp.owner,
                "web": "Loaded" if exp.status == 1 else "Not loaded",
                "running": "Running" if exp.running == 1 else "Stopped",
                "exp_status": getattr(exp, "exp_status", "stopped"),
                "jupyter_status": (
                    "Active" if jupyter_status.get(exp.idexp, False) else "Inactive"
                ),
                "annotations": exp.annotations if exp.annotations else "",
                "progress": exp_progress.get(exp.idexp, 0),
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

    # get client execution data to check if clients have been run
    client_executions = {}
    for client in clients:
        execution = Client_Execution.query.filter_by(client_id=client.id).first()
        # Client has been run at least once if execution exists and elapsed_time > 0
        client_executions[client.id] = execution and execution.elapsed_time > 0

    # check database type
    dbtype = None
    if current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("sqlite"):
        dbtype = "sqlite"
    elif current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("postgresql"):
        dbtype = "postgresql"

    # get jupyter instance for this experiment if exists

    jupyter_instance = Jupyter_instances.query.filter_by(exp_id=uid).first()

    # Pass telemetry flag independently to avoid issues with current_user object
    # User is already authenticated due to @login_required decorator
    telemetry_enabled = getattr(current_user, "telemetry_enabled", True)

    return render_template(
        "admin/experiment_details.html",
        experiment=experiment,
        clients=clients,
        client_executions=client_executions,
        users=users,
        len=len,
        dbtype=dbtype,
        jupyter_instance=jupyter_instance,
        notebooks=current_app.config["ENABLE_NOTEBOOK"],
        telemetry_enabled=telemetry_enabled,
    )


@experiments.route("/admin/submit_experiment_logs/<int:exp_id>", methods=["POST"])
@login_required
def submit_experiment_logs(exp_id):
    """Submit experiment logs to telemetry server for troubleshooting."""
    check_privileges(current_user.username)

    from y_web.telemetry import Telemetry
    from y_web.utils.path_utils import get_writable_path

    # Get experiment details
    experiment = Exps.query.filter_by(idexp=exp_id).first()
    if not experiment:
        return jsonify({"success": False, "message": "Experiment not found"}), 404

    # Check if telemetry is enabled for current user
    if not current_user.telemetry_enabled:
        return jsonify(
            {
                "success": False,
                "message": "Telemetry is disabled. Please enable it in your user settings to submit logs.",
            }
        )

    # Get problem description from request body
    problem_description = None
    if request.is_json:
        data = request.get_json()
        problem_description = data.get("problem_description", "").strip()
        if not problem_description:
            problem_description = None

    # Get experiment folder path
    BASE_DIR = get_writable_path()

    # Extract experiment folder name from db_name
    # db_name format: "experiments{sep}{folder}{sep}database_server.db"
    db_name_parts = experiment.db_name.split(os.sep)
    if len(db_name_parts) < 2:
        return jsonify(
            {"success": False, "message": "Invalid experiment database path format."}
        )

    experiment_folder_name = db_name_parts[1]
    experiment_folder = (
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{experiment_folder_name}"
    )

    # Initialize telemetry and submit logs with problem description
    telemetry = Telemetry(user=current_user)
    success, message = telemetry.submit_experiment_logs(
        exp_id, experiment_folder, problem_description=problem_description
    )

    return jsonify({"success": success, "message": message})


@experiments.route("/admin/experiment_logs/<int:exp_id>")
@login_required
def experiment_logs(exp_id):
    """Get experiment server logs analysis using database-backed metrics."""
    try:
        check_privileges(current_user.username)

        # Get experiment details
        experiment = Exps.query.filter_by(idexp=exp_id).first()
        if not experiment:
            return jsonify({"error": "Experiment not found"}), 404

        from y_web.utils.log_metrics import (
            has_server_log_files,
            update_server_log_metrics,
        )
        from y_web.utils.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Construct path to _server.log
        # db_name format: "experiments/uid/database_server.db" or "experiments_uid" for postgresql
        db_name = experiment.db_name
        if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
            # Extract the UUID folder
            parts = db_name.split(os.sep)
            if len(parts) >= 2:
                exp_folder = os.path.join(
                    BASE_DIR, f"y_web{os.sep}experiments{os.sep}{parts[1]}"
                )
            else:
                return jsonify({"error": "Invalid experiment path"}), 400
        elif db_name.startswith("experiments_"):
            # PostgreSQL format - UUID is after the underscore
            uid = db_name.replace("experiments_", "")
            exp_folder = os.path.join(
                BASE_DIR, f"y_web{os.sep}experiments{os.sep}{uid}"
            )
        else:
            return jsonify({"error": "Invalid experiment path format"}), 400

        log_file = os.path.join(exp_folder, "_server.log")

        # Check if any log files exist (main or rotated)
        if not has_server_log_files(log_file):
            return jsonify(
                {"call_volume": {}, "mean_duration": {}, "error": "Log file not found"}
            )

        # Update metrics incrementally from log file
        try:
            update_server_log_metrics(exp_id, log_file)
        except Exception as e:
            # Log the error but continue with existing data
            current_app.logger.error(
                f"Error updating server log metrics: {e}", exc_info=True
            )
            # Ensure session is in clean state after error
            try:
                db.session.rollback()
            except Exception:
                pass

        # Retrieve aggregated metrics from database (daily aggregation for overview)
        try:
            metrics = ServerLogMetrics.query.filter_by(
                exp_id=exp_id, aggregation_level="daily"
            ).all()
        except Exception as e:
            # Handle PendingRollbackError by rolling back and retrying
            current_app.logger.warning(
                f"Session error during metrics query, retrying: {e}"
            )
            db.session.rollback()
            metrics = ServerLogMetrics.query.filter_by(
                exp_id=exp_id, aggregation_level="daily"
            ).all()

        # Aggregate by path across all days
        path_counts = defaultdict(int)
        path_total_durations = defaultdict(float)

        for metric in metrics:
            path_counts[metric.path] += metric.call_count
            path_total_durations[metric.path] += metric.total_duration

        # Calculate mean durations
        mean_durations = {}
        for path in path_counts.keys():
            if path_counts[path] > 0:
                mean_durations[path] = path_total_durations[path] / path_counts[path]
            else:
                mean_durations[path] = 0

        return jsonify(
            {"call_volume": dict(path_counts), "mean_duration": mean_durations}
        )

    except Exception as e:
        # Catch any unhandled exceptions and return JSON error
        current_app.logger.error(
            f"Error in experiment_logs endpoint: {e}", exc_info=True
        )
        return (
            jsonify(
                {
                    "error": f"Internal server error: {str(e)}",
                    "call_volume": {},
                    "mean_duration": {},
                }
            ),
            500,
        )


@experiments.route("/admin/experiment_trends/<int:exp_id>")
@login_required
def experiment_trends(exp_id):
    """Get experiment server trends analysis using database-backed metrics."""
    try:
        check_privileges(current_user.username)

        # Get experiment details
        experiment = Exps.query.filter_by(idexp=exp_id).first()
        if not experiment:
            return jsonify({"error": "Experiment not found"}), 404

        from y_web.utils.log_metrics import (
            has_server_log_files,
            update_client_log_metrics,
            update_server_log_metrics,
        )
        from y_web.utils.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Construct path to _server.log
        db_name = experiment.db_name
        if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
            parts = db_name.split(os.sep)
            if len(parts) >= 2:
                exp_folder = os.path.join(
                    BASE_DIR, f"y_web{os.sep}experiments{os.sep}{parts[1]}"
                )
            else:
                return jsonify({"error": "Invalid experiment path"}), 400
        elif db_name.startswith("experiments_"):
            uid = db_name.replace("experiments_", "")
            exp_folder = os.path.join(
                BASE_DIR, f"y_web{os.sep}experiments{os.sep}{uid}"
            )
        else:
            return jsonify({"error": "Invalid experiment path format"}), 400

        log_file = os.path.join(exp_folder, "_server.log")

        # Check if any log files exist (main or rotated)
        if not has_server_log_files(log_file):
            return jsonify(
                {
                    "daily_compute": {},
                    "daily_simulation": {},
                    "hourly_compute": {},
                    "hourly_simulation": {},
                    "error": "Log file not found",
                }
            )

        # Update server metrics incrementally
        try:
            update_server_log_metrics(exp_id, log_file)
        except Exception as e:
            current_app.logger.error(
                f"Error updating server log metrics: {e}", exc_info=True
            )

        # Retrieve aggregated metrics from database
        # Get daily metrics
        daily_metrics = ServerLogMetrics.query.filter_by(
            exp_id=exp_id, aggregation_level="daily"
        ).all()

        daily_durations = defaultdict(float)
        daily_simulation = {}

        for metric in daily_metrics:
            daily_durations[metric.day] += metric.total_duration
            # Calculate simulation time from min_time and max_time
            if metric.min_time and metric.max_time:
                sim_time = (metric.max_time - metric.min_time).total_seconds()
                if metric.day in daily_simulation:
                    daily_simulation[metric.day] = max(
                        daily_simulation[metric.day], sim_time
                    )
                else:
                    daily_simulation[metric.day] = sim_time

        # Get hourly metrics
        hourly_metrics = ServerLogMetrics.query.filter_by(
            exp_id=exp_id, aggregation_level="hourly"
        ).all()

        hourly_durations = defaultdict(float)
        hourly_simulation = {}

        for metric in hourly_metrics:
            key = f"{metric.day}-{metric.hour}"
            hourly_durations[key] += metric.total_duration
            # Calculate simulation time from min_time and max_time
            if metric.min_time and metric.max_time:
                sim_time = (metric.max_time - metric.min_time).total_seconds()
                if key in hourly_simulation:
                    hourly_simulation[key] = max(hourly_simulation[key], sim_time)
                else:
                    hourly_simulation[key] = sim_time

        # Get total expected duration from client_execution table
        clients = Client.query.filter_by(id_exp=exp_id).all()
        client_ids = [c.id for c in clients]

        max_expected_rounds = 0
        max_remaining_rounds = 0
        client_progress = {}

        if client_ids:
            client_executions = Client_Execution.query.filter(
                Client_Execution.client_id.in_(client_ids)
            ).all()
            if client_executions:
                max_expected_rounds = max(
                    ce.expected_duration_rounds for ce in client_executions
                )

                # Calculate remaining rounds for each client
                for ce in client_executions:
                    current_round = ce.last_active_day * 24 + ce.last_active_hour
                    remaining = ce.expected_duration_rounds - current_round
                    client_progress[ce.client_id] = {
                        "expected_rounds": ce.expected_duration_rounds,
                        "current_round": current_round,
                        "remaining_rounds": max(0, remaining),
                    }
                    max_remaining_rounds = max(max_remaining_rounds, remaining)

        # Convert rounds to days
        total_days = max_expected_rounds / 24 if max_expected_rounds > 0 else 0
        max_remaining_days = (
            max_remaining_rounds / 24 if max_remaining_rounds > 0 else 0
        )

        # Update and retrieve client log metrics
        client_daily_compute = {}
        client_hourly_compute = {}

        for client in clients:
            client_log_file = os.path.join(exp_folder, f"{client.name}_client.log")

            # Update client metrics if log file exists
            if os.path.exists(client_log_file):
                try:
                    update_client_log_metrics(exp_id, client.id, client_log_file)
                except Exception as e:
                    current_app.logger.error(
                        f"Error updating client {client.id} log metrics: {e}",
                        exc_info=True,
                    )

            # Retrieve aggregated client metrics from database
            client_daily_metrics = ClientLogMetrics.query.filter_by(
                exp_id=exp_id, client_id=client.id, aggregation_level="daily"
            ).all()

            client_hourly_metrics = ClientLogMetrics.query.filter_by(
                exp_id=exp_id, client_id=client.id, aggregation_level="hourly"
            ).all()

            # Aggregate by day
            if client_daily_metrics:
                client_daily = defaultdict(float)
                for metric in client_daily_metrics:
                    client_daily[metric.day] += metric.total_execution_time
                client_daily_compute[client.name] = dict(client_daily)

            # Aggregate by hour
            if client_hourly_metrics:
                client_hourly = defaultdict(float)
                for metric in client_hourly_metrics:
                    key = f"{metric.day}-{metric.hour}"
                    client_hourly[key] += metric.total_execution_time
                client_hourly_compute[client.name] = dict(client_hourly)

        return jsonify(
            {
                "daily_compute": dict(daily_durations),
                "daily_simulation": daily_simulation,
                "hourly_compute": dict(hourly_durations),
                "hourly_simulation": hourly_simulation,
                "total_expected_days": total_days,
                "total_expected_rounds": max_expected_rounds,
                "max_remaining_rounds": max(0, max_remaining_rounds),
                "max_remaining_days": max_remaining_days,
                "client_daily_compute": client_daily_compute,
                "client_hourly_compute": client_hourly_compute,
                "client_progress": client_progress,
            }
        )

    except Exception as e:
        # Catch any unhandled exceptions and return JSON error
        current_app.logger.error(
            f"Error in experiment_trends endpoint: {e}", exc_info=True
        )
        return (
            jsonify(
                {
                    "error": f"Internal server error: {str(e)}",
                    "daily_compute": {},
                    "daily_simulation": {},
                    "hourly_compute": {},
                    "hourly_simulation": {},
                    "total_expected_days": 0,
                    "total_expected_rounds": 0,
                    "max_remaining_rounds": 0,
                    "max_remaining_days": 0,
                    "client_daily_compute": {},
                    "client_hourly_compute": {},
                    "client_progress": {},
                }
            ),
            500,
        )


@experiments.route("/admin/client_logs/<int:client_id>")
@login_required
def client_logs(client_id):
    """Get client logs analysis for a specific client."""
    try:
        check_privileges(current_user.username)

        # Get client details
        client = Client.query.filter_by(id=client_id).first()
        if not client:
            return jsonify({"error": "Client not found"}), 404

        # Get experiment details
        experiment = Exps.query.filter_by(idexp=client.id_exp).first()
        if not experiment:
            return jsonify({"error": "Experiment not found"}), 404

        from y_web.utils.log_metrics import update_client_log_metrics
        from y_web.utils.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Construct path to client log file
        db_name = experiment.db_name
        if db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
            # Extract the UUID folder
            parts = db_name.split(os.sep)
            if len(parts) >= 2:
                exp_folder = os.path.join(
                    BASE_DIR, f"y_web{os.sep}experiments{os.sep}{parts[1]}"
                )
            else:
                return jsonify({"error": "Invalid experiment path"}), 400
        elif db_name.startswith("experiments_"):
            # PostgreSQL format - UUID is after the underscore
            uid = db_name.replace("experiments_", "")
            exp_folder = os.path.join(
                BASE_DIR, f"y_web{os.sep}experiments{os.sep}{uid}"
            )
        else:
            return jsonify({"error": "Invalid experiment path format"}), 400

        # Client log file name format: {client_name}_client.log
        log_file = os.path.join(exp_folder, f"{client.name}_client.log")

        # Check if log file exists
        if not os.path.exists(log_file):
            return jsonify(
                {
                    "call_volume": {},
                    "mean_execution_time": {},
                    "error": "Log file not found",
                }
            )

        # Update client metrics incrementally
        try:
            update_client_log_metrics(experiment.idexp, client_id, log_file)
        except Exception as e:
            current_app.logger.error(
                f"Error updating client log metrics: {e}", exc_info=True
            )

        # Retrieve aggregated metrics from database (daily aggregation for overview)
        metrics = ClientLogMetrics.query.filter_by(
            exp_id=experiment.idexp, client_id=client_id, aggregation_level="daily"
        ).all()

        # Aggregate by method across all days
        method_counts = defaultdict(int)
        method_total_times = defaultdict(float)

        for metric in metrics:
            method_counts[metric.method_name] += metric.call_count
            method_total_times[metric.method_name] += metric.total_execution_time

        # Calculate mean execution times
        mean_execution_times = {}
        for method in method_counts.keys():
            if method_counts[method] > 0:
                mean_execution_times[method] = (
                    method_total_times[method] / method_counts[method]
                )
            else:
                mean_execution_times[method] = 0

        return jsonify(
            {
                "call_volume": dict(method_counts),
                "mean_execution_time": mean_execution_times,
            }
        )

    except Exception as e:
        # Catch any unhandled exceptions and return JSON error
        current_app.logger.error(f"Error in client_logs endpoint: {e}", exc_info=True)
        return (
            jsonify(
                {
                    "error": f"Internal server error: {str(e)}",
                    "call_volume": {},
                    "mean_execution_time": {},
                }
            ),
            500,
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
    db.session.query(Exps).filter_by(idexp=uid).update(
        {Exps.running: 1, Exps.exp_status: "active"}
    )
    db.session.commit()

    # start the yserver
    start_server(exp)

    return experiment_details(uid)


@experiments.route("/admin/stop_experiment/<int:uid>")
@login_required
def stop_experiment(uid):
    """Handle stop experiment operation.

    Stops the experiment by first terminating all client processes, then stopping
    the server. This order prevents clients from trying to communicate with a dead server.

    Shutdown sequence:
    1. Terminate all client processes
    2. Update client execution status in database
    3. Stop the server process
    4. Update server execution status in database
    """
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return experiment_details(uid)

    # Step 1 & 2: Stop all running clients attached to this experiment first
    # This prevents clients from trying to communicate with a dead server
    clients = Client.query.filter_by(id_exp=uid).all()
    for client in clients:
        # Only terminate clients that are marked as running (status=1)
        if client.status == 1:
            # Terminate the client process if it has a PID
            if client.pid:
                print(
                    f"Stopping client {client.name} (ID: {client.id}, PID: {client.pid}) for experiment {uid}"
                )
                terminate_client(client, pause=False)

            # Update client status in database
            client.status = 0
            db.session.commit()

    # Step 3: Now stop the yserver after all clients are terminated
    # Try the new subprocess-based termination first
    # If that fails or no process is tracked, fall back to port-based termination
    terminated = terminate_server_process(uid)
    if not terminated:
        # Fallback to port-based termination for backward compatibility
        terminate_process_on_port(exp.port)

    # Step 4: Update the experiment status in database
    db.session.query(Exps).filter_by(idexp=uid).update(
        {Exps.running: 0, Exps.exp_status: "stopped"}
    )
    db.session.commit()

    return experiment_details(uid)


@experiments.route("/admin/prompts/<int:uid>")
@login_required
def prompts(uid):
    """Handle prompts operation."""
    check_privileges(current_user.username)

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()
    # get the prompts file for the experiment
    prompts = os.path.join(
        BASE_DIR,
        f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

    # read the prompts file
    prompts = json.load(open(prompts))

    return render_template("admin/prompts.html", experiment=experiment, prompts=prompts)


@experiments.route("/admin/update_prompts/<int:uid>", methods=["POST"])
@login_required
def update_prompts(uid):
    """Update prompts."""
    check_privileges(current_user.username)

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()
    # get the prompts file for the experiment
    prompts_filename = os.path.join(
        BASE_DIR,
        f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

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
    """Download experiment file.

    For SQLite: Downloads experiment folder as-is with the database file.
    For PostgreSQL: Creates an SQLite copy of the PostgreSQL database first,
    then downloads the experiment folder with the SQLite copy.
    """
    check_privileges(current_user.username)

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=eid).first()

    # Determine database type
    db_type = "sqlite"
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        db_type = "postgresql"

    # Get folder path based on database type
    if db_type == "sqlite":
        folder = os.path.join(
            BASE_DIR,
            f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}",
        )
    else:
        # PostgreSQL: extract UUID from db_name (format: experiments_uuid)
        folder = os.path.join(
            BASE_DIR,
            f"y_web{os.sep}experiments{os.sep}{experiment.db_name.removeprefix('experiments_')}",
        )

    # For PostgreSQL, create an SQLite copy of the database
    if db_type == "postgresql":
        try:
            import sqlite3
            from urllib.parse import urlparse

            from sqlalchemy import create_engine, inspect

            # Connect to PostgreSQL database
            current_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
            parsed_uri = urlparse(current_uri)

            user = parsed_uri.username or "postgres"
            password = parsed_uri.password or "password"
            host = parsed_uri.hostname or "localhost"
            port_db = parsed_uri.port or 5432

            pg_uri = (
                f"postgresql://{user}:{password}@{host}:{port_db}/{experiment.db_name}"
            )
            pg_engine = create_engine(pg_uri)

            # Create SQLite database in the experiment folder
            sqlite_path = os.path.join(folder, "database_server.db")
            sqlite_uri = f"sqlite:///{sqlite_path}"
            sqlite_engine = create_engine(sqlite_uri)

            # Get inspector for PostgreSQL database
            inspector = inspect(pg_engine)

            # Copy all tables from PostgreSQL to SQLite
            # Use raw connection for SQLite to handle parameter binding correctly
            with pg_engine.connect() as pg_conn:
                from sqlalchemy import text

                # Get all table names
                table_names = inspector.get_table_names()

                # Get raw SQLite connection
                sqlite_raw_conn = sqlite3.connect(sqlite_path)
                sqlite_cursor = sqlite_raw_conn.cursor()

                for table_name in table_names:
                    # Read from PostgreSQL using text()
                    result = pg_conn.execute(text(f"SELECT * FROM {table_name}"))
                    rows = result.fetchall()
                    columns = result.keys()

                    if rows:
                        # Create table in SQLite if it doesn't exist
                        # Get column definitions from PostgreSQL
                        pg_columns = inspector.get_columns(table_name)
                        col_defs = []
                        for col in pg_columns:
                            col_type = str(col["type"])
                            # Map PostgreSQL types to SQLite types
                            if "INTEGER" in col_type or "SERIAL" in col_type:
                                sqlite_type = "INTEGER"
                            elif (
                                "REAL" in col_type
                                or "DOUBLE" in col_type
                                or "FLOAT" in col_type
                            ):
                                sqlite_type = "REAL"
                            elif (
                                "TEXT" in col_type
                                or "VARCHAR" in col_type
                                or "CHAR" in col_type
                            ):
                                sqlite_type = "TEXT"
                            else:
                                sqlite_type = "TEXT"

                            col_defs.append(f"{col['name']} {sqlite_type}")

                        create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_defs)})"
                        sqlite_cursor.execute(create_table_sql)

                        # Insert data into SQLite using raw connection
                        placeholders = ", ".join(["?" for _ in columns])
                        insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

                        for row in rows:
                            sqlite_cursor.execute(insert_sql, tuple(row))

                sqlite_raw_conn.commit()
                sqlite_raw_conn.close()

            pg_engine.dispose()
            sqlite_engine.dispose()

        except Exception as e:
            current_app.logger.error(
                f"Error creating SQLite copy of PostgreSQL database: {str(e)}",
                exc_info=True,
            )
            flash(f"Error creating database copy: {str(e)}")
            return redirect(url_for("experiments.experiment_details", uid=eid))

    # compress the folder and send the file
    shutil.make_archive(folder, "zip", folder)

    # Ensure temp_data directory exists
    temp_data_dir = os.path.join(BASE_DIR, f"y_web{os.sep}experiments{os.sep}temp_data")
    os.makedirs(temp_data_dir, exist_ok=True)

    # move the file to the temp_data folder
    temp_data_path = os.path.join(temp_data_dir, f"{folder.split(os.sep)[-1]}.zip")
    shutil.move(
        f"{folder}.zip",
        temp_data_path,
    )
    # return the file
    return send_file_desktop(
        temp_data_path,
        as_attachment=True,
    )


@experiments.route("/admin/miscellanea/", methods=["GET"])
@login_required
def miscellanea():
    """
    Display miscellaneous settings page (admin only).

    Returns:
        Rendered miscellaneous settings template
    """
    # Check if user is admin (researchers should not access this page)
    user = Admin_users.query.filter_by(username=current_user.username).first()
    if user.role != "admin":
        flash("Access denied. This page is only accessible to administrators.", "error")
        return redirect(url_for("admin.dashboard"))

    check_privileges(current_user.username)

    # Get telemetry and watchdog settings for the current admin user
    telemetry_enabled = getattr(user, "telemetry_enabled", True)
    watchdog_interval = 15  # Default watchdog interval

    # Try to get watchdog interval from the watchdog status
    try:
        from y_web.utils.process_watchdog import get_watchdog_status

        status = get_watchdog_status()
        watchdog_interval = status.get("run_interval_minutes", 15)
    except ImportError:
        # process_watchdog module not available
        pass
    except (KeyError, TypeError, AttributeError):
        # Status returned unexpected format
        pass

    return render_template(
        "admin/miscellanea.html",
        telemetry_enabled=telemetry_enabled,
        watchdog_interval=watchdog_interval,
    )


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
                name = "language"
            col = getattr(Languages, name)
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
                name = "leaning"
            col = getattr(Leanings, name)
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

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["nationality"]:
                name = "nationality"
            col = getattr(Nationalities, name)
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
                name = "profession"
            col = getattr(Profession, name)
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
                name = "education_level"
            col = getattr(Education, name)
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
                name = "toxicity_level"
            col = getattr(Toxicity_Levels, name)
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


@experiments.route("/admin/copy_experiment", methods=["POST"])
@login_required
def copy_experiment():
    """
    Copy an existing experiment with a new name.

    Creates a complete copy of an experiment including:
    - New unique folder with UUID
    - All configuration files (server, populations, clients, prompts)
    - Database tables (for both SQLite and PostgreSQL)
    - All related records (populations, clients, topics, etc.)

    The copy is ready to start without needing a reset.
    Supports creating multiple copies with incremental naming (name_1, name_2, etc.)
    """
    check_privileges(current_user.username)

    # Get form data
    new_exp_name = request.form.get("new_exp_name")
    source_exp_id = request.form.get("source_exp_id")
    num_copies = request.form.get("num_copies", "1")

    # Validate inputs
    if not new_exp_name or not source_exp_id:
        flash("Both experiment name and source experiment are required.")
        return redirect(url_for("experiments.settings"))

    # Parse and validate num_copies
    try:
        num_copies = int(num_copies)
        if num_copies < 1:
            num_copies = 1
        elif num_copies > 20:
            num_copies = 20
    except (ValueError, TypeError):
        num_copies = 1

    # Get source experiment
    source_exp = Exps.query.filter_by(idexp=source_exp_id).first()
    if not source_exp:
        flash("Source experiment not found.")
        return redirect(url_for("experiments.settings"))

    # Generate list of experiment names to create
    exp_names_to_create = []
    if num_copies == 1:
        exp_names_to_create = [new_exp_name]
    else:
        for i in range(1, num_copies + 1):
            exp_names_to_create.append(f"{new_exp_name}_{i}")

    # Validate that none of the names already exist
    for name in exp_names_to_create:
        existing_exp = Exps.query.filter_by(exp_name=name).first()
        if existing_exp:
            flash(f"An experiment with name '{name}' already exists.")
            return redirect(url_for("experiments.settings"))

    # Create each copy
    created_count = 0
    for copy_name in exp_names_to_create:
        try:
            success = _create_single_experiment_copy(source_exp, copy_name)
            if success:
                created_count += 1
        except Exception as e:
            current_app.logger.error(f"Error copying experiment to '{copy_name}': {str(e)}", exc_info=True)
            flash(f"Error creating copy '{copy_name}': {str(e)}")

    if created_count > 0:
        if created_count == 1:
            flash(f"Experiment '{exp_names_to_create[0]}' successfully created as a copy of '{source_exp.exp_name}'.")
        else:
            flash(f"{created_count} experiment copies successfully created from '{source_exp.exp_name}'.")

    return redirect(url_for("experiments.settings"))


def _create_single_experiment_copy(source_exp, new_exp_name):
    """
    Helper function to create a single experiment copy.
    
    Args:
        source_exp: Source experiment object
        new_exp_name: Name for the new experiment
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Create new unique ID for the folder
    new_uid = str(uuid.uuid4()).replace("-", "_")

    # Determine database type
    db_type = "sqlite"
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        db_type = "postgresql"

    # Extract source experiment folder
    if db_type == "sqlite":
        # Source: experiments/old_uid/database_server.db -> old_uid
        source_parts = source_exp.db_name.split(os.sep)
        if len(source_parts) >= 2:
            source_uid = source_parts[1]
        else:
            return False
    else:
        # PostgreSQL: experiments_old_uid -> old_uid
        source_uid = source_exp.db_name.replace("experiments_", "")

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    source_folder = os.path.join(
        BASE_DIR, f"y_web{os.sep}experiments{os.sep}{source_uid}"
    )
    new_folder = os.path.join(
        BASE_DIR, f"y_web{os.sep}experiments{os.sep}{new_uid}"
    )

    # Check if source folder exists
    if not os.path.exists(source_folder):
        return False

    # Create new experiment folder and copy all files
    pathlib.Path(new_folder).mkdir(parents=True, exist_ok=True)

    # Copy all files from source to new folder, excluding log files
    import re

    log_pattern = re.compile(
        r"\.log(\.\d+)?$"
    )  # Matches .log, .log.1, .log.2, etc.

    for item in os.listdir(source_folder):
        # Skip log files (server logs and client logs) including rotated logs
        if log_pattern.search(item):
            continue

        source_item = os.path.join(source_folder, item)
        dest_item = os.path.join(new_folder, item)

        if os.path.isfile(source_item):
            shutil.copy2(source_item, dest_item)
        elif os.path.isdir(source_item):
            shutil.copytree(source_item, dest_item)

    # Get suggested port for new experiment
    suggested_port = get_suggested_port()
    if not suggested_port:
        # Cleanup and return
        current_app.logger.warning(f"No available port found for experiment copy: {new_exp_name}")
        shutil.rmtree(new_folder, ignore_errors=True)
        return False

    # Handle database copying first to get the correct db_uri
    new_db_name = ""
    new_db_uri = ""

    if db_type == "sqlite":
        # Create a fresh SQLite database with clean schema (no data from source)
        new_db_path = os.path.join(new_folder, "database_server.db")

        # Copy the clean database schema instead of the source database
        clean_db_path = get_resource_path(
            os.path.join("data_schema", "database_clean_server.db")
        )
        if os.path.exists(clean_db_path):
            shutil.copy2(clean_db_path, new_db_path)
        else:
            # Create an empty database file
            import sqlite3

            conn = sqlite3.connect(new_db_path)
            conn.close()

        new_db_name = f"experiments{os.sep}{new_uid}{os.sep}database_server.db"

        # Build absolute path for database_uri
        # Use the absolute path of the new_db_path
        new_db_uri = os.path.abspath(new_db_path)

    elif db_type == "postgresql":
        # Create new PostgreSQL database with clean schema (no data from source)
        from urllib.parse import urlparse

        from sqlalchemy import create_engine, text
        from werkzeug.security import generate_password_hash

        current_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
        parsed_uri = urlparse(current_uri)

        user = parsed_uri.username or "postgres"
        password = parsed_uri.password or "password"
        host = parsed_uri.hostname or "localhost"
        port_db = parsed_uri.port or 5432

        new_dbname = f"experiments_{new_uid}"
        new_db_name = new_dbname
        new_db_uri = f"postgresql://{user}:{password}@{host}:{port_db}/{new_dbname}"

        # Connect to postgres database
        admin_engine = create_engine(
            f"postgresql://{user}:{password}@{host}:{port_db}/postgres"
        )

        # Check if database already exists
        with admin_engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": new_dbname},
            )
            db_exists = result.scalar() is not None

        if not db_exists:
            # Create new empty database
            with admin_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                conn.execute(text(f'CREATE DATABASE "{new_dbname}"'))

            # Connect to the newly created database and apply schema
            experiment_engine = create_engine(new_db_uri)
            with experiment_engine.connect() as conn:
                # Load schema from SQL file
                schema_path = get_resource_path(
                    os.path.join("data_schema", "postgre_server.sql")
                )
                with open(schema_path, "r") as schema_file:
                    schema_sql = schema_file.read()
                    conn.execute(text(schema_sql))

                # Insert initial admin user
                hashed_pw = generate_password_hash("admin", method="pbkdf2:sha256")

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

                conn.execute(
                    stmt,
                    {
                        "username": "Admin",
                        "email": "admin@y-not.social",
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

    # Update config_server.json with new name, port, and database_uri
    config_path = os.path.join(new_folder, "config_server.json")
    if not os.path.exists(config_path):
        # Cleanup and return
        if os.path.exists(new_folder):
            shutil.rmtree(new_folder, ignore_errors=True)
        return False

    with open(config_path, "r") as f:
        config = json.load(f)

    # Update all necessary fields
    config["name"] = new_exp_name
    config["port"] = suggested_port
    config["database_uri"] = new_db_uri

    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

    # Verify the config was written correctly
    with open(config_path, "r") as f:
        verify_config = json.load(f)

    if (
        verify_config.get("port") != suggested_port
        or verify_config.get("database_uri") != new_db_uri
    ):
        # Cleanup and return
        if os.path.exists(new_folder):
            shutil.rmtree(new_folder, ignore_errors=True)
        return False

    # Update all client configuration files with new port
    # Client configs have the format: client_*.json
    for item in os.listdir(new_folder):
        if item.startswith("client") and item.endswith(".json"):
            client_config_path = os.path.join(new_folder, item)
            try:
                with open(client_config_path, "r") as f:
                    client_config = json.load(f)

                # Update the API endpoint in servers section
                if "servers" in client_config and "api" in client_config["servers"]:
                    # Update the port in the API URL
                    old_api = client_config["servers"]["api"]
                    # Replace port in URL - handles both with and without trailing slash
                    # Pattern matches :port/ or :port at end of string
                    import re

                    new_api = re.sub(
                        r":(\d+)(/|$)", f":{suggested_port}\\2", old_api
                    )
                    client_config["servers"]["api"] = new_api

                    with open(client_config_path, "w") as f:
                        json.dump(client_config, f, indent=4)
            except Exception as e:
                # Continue anyway - this is not critical enough to fail the entire copy
                current_app.logger.warning(f"Failed to update client config {item}: {str(e)}")

    # Create new experiment record in admin database
    new_exp = Exps(
        exp_name=new_exp_name,
        platform_type=source_exp.platform_type,
        db_name=new_db_name,
        owner=current_user.username,
        exp_descr=source_exp.exp_descr,
        status=0,  # Not loaded
        running=0,  # Not running
        port=suggested_port,
        server=source_exp.server,
        annotations=source_exp.annotations,
        llm_agents_enabled=source_exp.llm_agents_enabled,
    )
    db.session.add(new_exp)
    db.session.commit()

    # Copy Exp_stats
    source_stats = Exp_stats.query.filter_by(exp_id=source_exp.idexp).first()
    if source_stats:
        new_stats = Exp_stats(
            exp_id=new_exp.idexp,
            rounds=0,  # Reset to 0 for new experiment
            agents=source_stats.agents,
            posts=0,  # Reset to 0
            reactions=0,  # Reset to 0
            mentions=0,  # Reset to 0
        )
        db.session.add(new_stats)
        db.session.commit()

    # Copy Exp_Topic relationships
    source_topics = Exp_Topic.query.filter_by(exp_id=source_exp.idexp).all()
    for topic in source_topics:
        new_topic = Exp_Topic(exp_id=new_exp.idexp, topic_id=topic.topic_id)
        db.session.add(new_topic)
    db.session.commit()

    # Copy Population_Experiment relationships
    source_pop_exps = Population_Experiment.query.filter_by(
        id_exp=source_exp.idexp
    ).all()
    for pop_exp in source_pop_exps:
        new_pop_exp = Population_Experiment(
            id_exp=new_exp.idexp, id_population=pop_exp.id_population
        )
        db.session.add(new_pop_exp)
    db.session.commit()

    # Copy Client records
    source_clients = Client.query.filter_by(id_exp=source_exp.idexp).all()
    for source_client in source_clients:
        new_client = Client(
            name=source_client.name,
            descr=source_client.descr,
            days=source_client.days,
            percentage_new_agents_iteration=source_client.percentage_new_agents_iteration,
            percentage_removed_agents_iteration=source_client.percentage_removed_agents_iteration,
            max_length_thread_reading=source_client.max_length_thread_reading,
            reading_from_follower_ratio=source_client.reading_from_follower_ratio,
            probability_of_daily_follow=source_client.probability_of_daily_follow,
            attention_window=source_client.attention_window,
            visibility_rounds=source_client.visibility_rounds,
            post=source_client.post,
            share=source_client.share,
            image=source_client.image,
            comment=source_client.comment,
            read=source_client.read,
            news=source_client.news,
            search=source_client.search,
            vote=source_client.vote,
            share_link=source_client.share_link,
            llm=source_client.llm,
            llm_api_key=source_client.llm_api_key,
            llm_max_tokens=source_client.llm_max_tokens,
            llm_temperature=source_client.llm_temperature,
            llm_v_agent=source_client.llm_v_agent,
            llm_v=source_client.llm_v,
            llm_v_api_key=source_client.llm_v_api_key,
            llm_v_max_tokens=source_client.llm_v_max_tokens,
            llm_v_temperature=source_client.llm_v_temperature,
            status=0,  # Not running
            id_exp=new_exp.idexp,
            probability_of_secondary_follow=source_client.probability_of_secondary_follow,
            population_id=source_client.population_id,
            network_type=source_client.network_type,
            crecsys=source_client.crecsys,
            frecsys=source_client.frecsys,
            pid=None,  # No process ID yet
        )
        db.session.add(new_client)
        db.session.commit()

    # Note: Client_Execution entries are NOT copied - they will be created
    # when the client is first started, ensuring fresh execution state

    # Note: Rounds table is in the experiment database (db_exp)
    # The clean database template already has the initial round (day=0, hour=0)

    # Create Jupyter instance record
    jupyter_instance = Jupyter_instances(
        port=-1, notebook_dir="", exp_id=new_exp.idexp, status="stopped"
    )
    db.session.add(jupyter_instance)
    db.session.commit()

    return True


@experiments.route("/admin/log_sync_settings", methods=["GET"])
@login_required
def get_log_sync_settings():
    """
    Get current log sync settings.

    Returns:
        JSON with log sync settings
    """
    check_privileges(current_user.username)

    # Get or create default settings
    settings = LogSyncSettings.query.first()
    if not settings:
        settings = LogSyncSettings(enabled=True, sync_interval_minutes=10)
        db.session.add(settings)
        db.session.commit()

    return jsonify(
        {
            "enabled": settings.enabled,
            "sync_interval_minutes": settings.sync_interval_minutes,
            "last_sync": (
                settings.last_sync.isoformat() + "Z" if settings.last_sync else None
            ),
        }
    )


@experiments.route("/admin/log_sync_settings", methods=["POST"])
@login_required
def update_log_sync_settings():
    """
    Update log sync settings.

    Expects JSON body with:
    - enabled (bool): Whether automatic log sync is enabled
    - sync_interval_minutes (int): Sync frequency in minutes (1-1440)

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    # Get or create settings
    settings = LogSyncSettings.query.first()
    if not settings:
        settings = LogSyncSettings(enabled=True, sync_interval_minutes=10)
        db.session.add(settings)

    # Update enabled if provided
    if "enabled" in data:
        settings.enabled = bool(data["enabled"])

    # Update sync interval if provided
    if "sync_interval_minutes" in data:
        try:
            interval = int(data["sync_interval_minutes"])
            # Validate range: 1 minute to 24 hours
            if interval < 1 or interval > 1440:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Sync interval must be between 1 and 1440 minutes",
                        }
                    ),
                    400,
                )
            settings.sync_interval_minutes = interval
        except (ValueError, TypeError):
            return (
                jsonify({"success": False, "message": "Invalid sync interval value"}),
                400,
            )

    db.session.commit()

    return jsonify(
        {
            "success": True,
            "enabled": settings.enabled,
            "sync_interval_minutes": settings.sync_interval_minutes,
        }
    )


@experiments.route("/admin/log_sync_trigger", methods=["POST"])
@login_required
def trigger_log_sync():
    """
    Manually trigger a log sync for all running experiments.

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    try:
        from y_web.utils.log_sync_scheduler import get_scheduler

        scheduler = get_scheduler()
        if scheduler:
            success = scheduler.trigger_sync()
            if success:
                return jsonify(
                    {"success": True, "message": "Log sync triggered successfully"}
                )
            else:
                return (
                    jsonify({"success": False, "message": "Log sync failed"}),
                    500,
                )
        else:
            return (
                jsonify(
                    {"success": False, "message": "Log sync scheduler not running"}
                ),
                503,
            )
    except Exception as e:
        current_app.logger.error(f"Error triggering log sync: {e}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 500


# =====================================================
# Experiment Schedule Routes
# =====================================================


@experiments.route("/admin/schedule/groups", methods=["GET"])
@login_required
def get_schedule_groups():
    """
    Get all experiment schedule groups with their experiments.

    Returns:
        JSON with groups and their associated experiments
    """
    check_privileges(current_user.username)

    # Only show non-completed groups
    groups = (
        ExperimentScheduleGroup.query.filter(
            (ExperimentScheduleGroup.is_completed == 0)
            | (ExperimentScheduleGroup.is_completed == None)
        )
        .order_by(ExperimentScheduleGroup.order_index)
        .all()
    )

    result = []
    for group in groups:
        items = (
            ExperimentScheduleItem.query.filter_by(group_id=group.id)
            .order_by(ExperimentScheduleItem.order_index)
            .all()
        )
        experiments_list = []
        for item in items:
            exp = Exps.query.get(item.experiment_id)
            if exp:
                experiments_list.append(
                    {
                        "id": exp.idexp,
                        "name": exp.exp_name,
                        "owner": exp.owner,
                        "exp_status": exp.exp_status,
                        "item_id": item.id,
                    }
                )
        result.append(
            {
                "id": group.id,
                "name": group.name,
                "order_index": group.order_index,
                "is_completed": group.is_completed or 0,
                "experiments": experiments_list,
            }
        )

    return jsonify({"success": True, "groups": result})


@experiments.route("/admin/schedule/groups", methods=["POST"])
@login_required
def create_schedule_group():
    """
    Create a new experiment schedule group.

    Expects JSON body with:
    - name: Group name

    Returns:
        JSON with created group details
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"success": False, "message": "Name is required"}), 400

    # Get max order index
    max_order = (
        db.session.query(db.func.max(ExperimentScheduleGroup.order_index)).scalar() or 0
    )

    group = ExperimentScheduleGroup(name=data["name"], order_index=max_order + 1)
    db.session.add(group)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "group": {
                "id": group.id,
                "name": group.name,
                "order_index": group.order_index,
                "experiments": [],
            },
        }
    )


@experiments.route("/admin/schedule/groups/<int:group_id>", methods=["DELETE"])
@login_required
def delete_schedule_group(group_id):
    """
    Delete an experiment schedule group.

    Args:
        group_id: ID of the group to delete

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    group = ExperimentScheduleGroup.query.get(group_id)
    if not group:
        return jsonify({"success": False, "message": "Group not found"}), 404

    # Check if the group is currently running
    status = ExperimentScheduleStatus.query.first()
    if status and status.is_running and status.current_group_id == group_id:
        return jsonify(
            {"success": False, "message": "Cannot delete a running group"}
        ), 400

    # Delete all items in the group first
    ExperimentScheduleItem.query.filter_by(group_id=group_id).delete()
    db.session.delete(group)
    db.session.commit()

    return jsonify({"success": True})


@experiments.route("/admin/schedule/groups/<int:group_id>/experiments", methods=["POST"])
@login_required
def add_experiment_to_group(group_id):
    """
    Add an experiment to a schedule group.

    Args:
        group_id: ID of the group

    Expects JSON body with:
    - experiment_id: ID of the experiment to add

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data or "experiment_id" not in data:
        return jsonify({"success": False, "message": "experiment_id is required"}), 400

    group = ExperimentScheduleGroup.query.get(group_id)
    if not group:
        return jsonify({"success": False, "message": "Group not found"}), 404

    exp = Exps.query.get(data["experiment_id"])
    if not exp:
        return jsonify({"success": False, "message": "Experiment not found"}), 404

    # Check if already in this group
    existing = ExperimentScheduleItem.query.filter_by(
        group_id=group_id, experiment_id=data["experiment_id"]
    ).first()
    if existing:
        return jsonify({"success": False, "message": "Experiment already in group"}), 400

    # Get max order index for this group
    max_order = (
        db.session.query(db.func.max(ExperimentScheduleItem.order_index))
        .filter(ExperimentScheduleItem.group_id == group_id)
        .scalar()
        or 0
    )

    item = ExperimentScheduleItem(
        group_id=group_id, experiment_id=data["experiment_id"], order_index=max_order + 1
    )
    db.session.add(item)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "item": {
                "id": item.id,
                "experiment_id": exp.idexp,
                "name": exp.exp_name,
            },
        }
    )


@experiments.route("/admin/schedule/items/<int:item_id>", methods=["DELETE"])
@login_required
def remove_experiment_from_group(item_id):
    """
    Remove an experiment from a schedule group.

    Args:
        item_id: ID of the schedule item to remove

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    item = ExperimentScheduleItem.query.get(item_id)
    if not item:
        return jsonify({"success": False, "message": "Item not found"}), 404

    # Check if the group is currently running
    status = ExperimentScheduleStatus.query.first()
    if status and status.is_running and status.current_group_id == item.group_id:
        return jsonify(
            {"success": False, "message": "Cannot remove experiments from a running group"}
        ), 400

    db.session.delete(item)
    db.session.commit()

    return jsonify({"success": True})


@experiments.route("/admin/schedule/groups/reorder", methods=["POST"])
@login_required
def reorder_schedule_groups():
    """
    Reorder schedule groups.

    Expects JSON body with:
    - group_ids: List of group IDs in new order

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data or "group_ids" not in data:
        return jsonify({"success": False, "message": "group_ids is required"}), 400

    for index, group_id in enumerate(data["group_ids"]):
        group = ExperimentScheduleGroup.query.get(group_id)
        if group:
            group.order_index = index
    db.session.commit()

    return jsonify({"success": True})


@experiments.route("/admin/schedule/status", methods=["GET"])
@login_required
def get_schedule_status():
    """
    Get current schedule execution status.

    Returns:
        JSON with schedule status
    """
    check_privileges(current_user.username)

    status = ExperimentScheduleStatus.query.first()
    if not status:
        status = ExperimentScheduleStatus(is_running=0)
        db.session.add(status)
        db.session.commit()

    return jsonify(
        {
            "success": True,
            "is_running": bool(status.is_running),
            "current_group_id": status.current_group_id,
            "started_at": status.started_at.isoformat() if status.started_at else None,
        }
    )


def _get_clients_to_start(exp):
    """
    Check which clients in an experiment need to be started.
    
    Args:
        exp: Experiment object
        
    Returns:
        tuple: (all_clients_completed, clients_to_start)
            - all_clients_completed: True if all clients have finished
            - clients_to_start: List of Client objects that still need to run
    """
    clients = Client.query.filter_by(id_exp=exp.idexp).all()
    all_clients_completed = True
    clients_to_start = []
    
    for client in clients:
        # Check if client has completed
        client_exec = Client_Execution.query.filter_by(client_id=client.id).first()
        if client_exec:
            if client_exec.elapsed_time < client_exec.expected_duration_rounds:
                all_clients_completed = False
                clients_to_start.append(client)
        else:
            # No execution record means client hasn't run yet
            all_clients_completed = False
            clients_to_start.append(client)
    
    # If no clients exist, consider it not completed (nothing to run)
    if len(clients) == 0:
        all_clients_completed = False
    
    return all_clients_completed, clients_to_start


@experiments.route("/admin/schedule/start", methods=["POST"])
@login_required
def start_schedule():
    """
    Start executing the experiment schedule.

    Starts all experiments in the first group and monitors for completion.

    Returns:
        JSON with success status and execution logs
    """
    import time
    check_privileges(current_user.username)

    # Check if already running
    status = ExperimentScheduleStatus.query.first()
    if not status:
        status = ExperimentScheduleStatus(is_running=0)
        db.session.add(status)
        db.session.commit()

    if status.is_running:
        return jsonify({"success": False, "message": "Schedule already running"}), 400

    # Clear old logs when starting a new schedule
    ExperimentScheduleLog.query.delete()
    db.session.commit()

    # Get first non-completed group
    first_group = (
        ExperimentScheduleGroup.query.filter(
            (ExperimentScheduleGroup.is_completed == 0)
            | (ExperimentScheduleGroup.is_completed == None)
        )
        .order_by(ExperimentScheduleGroup.order_index)
        .first()
    )
    if not first_group:
        return jsonify({"success": False, "message": "No groups defined or all groups completed"}), 400

    # Start all experiments in first group
    items = ExperimentScheduleItem.query.filter_by(group_id=first_group.id).all()
    if not items:
        return jsonify({"success": False, "message": "First group has no experiments"}), 400

    from datetime import datetime

    # Add persistent log
    log_entry = ExperimentScheduleLog(
        message=f"Schedule started - beginning with group '{first_group.name}'",
        log_type="info",
        created_at=datetime.utcnow(),
    )
    db.session.add(log_entry)
    db.session.commit()

    # Update status
    status.is_running = 1
    status.current_group_id = first_group.id
    status.started_at = datetime.utcnow()
    db.session.commit()

    # Collect execution logs
    logs = []

    # Start each experiment in the group
    started_count = 0
    for item in items:
        exp = Exps.query.get(item.experiment_id)
        if exp and exp.running == 0:
            # Check if all clients have already completed before starting the server
            all_clients_completed, clients_to_start = _get_clients_to_start(exp)
            
            # If all clients have completed, mark experiment as completed and skip
            if all_clients_completed:
                msg = f"Experiment '{exp.exp_name}' already completed - skipping"
                logs.append(msg)
                db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
                exp.exp_status = "completed"
                db.session.commit()
                continue
            
            # If no clients to start, skip
            if len(clients_to_start) == 0:
                msg = f"No clients to start for '{exp.exp_name}' - skipping"
                logs.append(msg)
                db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
                continue
            
            msg = f"Starting server for '{exp.exp_name}'..."
            logs.append(msg)
            db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))

            # Update experiment status
            exp.running = 1
            exp.exp_status = "active"
            db.session.commit()

            # Start the server
            start_server(exp)
            started_count += 1

            # Wait for server to be ready
            msg = f"Waiting for server '{exp.exp_name}' to be ready..."
            logs.append(msg)
            time.sleep(3)  # Give server time to start

            # Start only clients that haven't completed
            for client in clients_to_start:
                if client.status == 0:
                    msg = f"Starting client '{client.name}' for '{exp.exp_name}'..."
                    logs.append(msg)
                    db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
                    # Get population for client
                    population = Population.query.filter_by(id=client.population_id).first()
                    if population:
                        start_client(exp, client, population, resume=True)
                        # Mark client as running
                        client.status = 1
                        db.session.commit()
                        msg = f"Client '{client.name}' started successfully"
                        logs.append(msg)
                    else:
                        msg = f"Warning: No population found for client '{client.name}'"
                        logs.append(msg)
                        db.session.add(ExperimentScheduleLog(message=msg, log_type="warning"))

            msg = f"Experiment '{exp.exp_name}' started successfully"
            logs.append(msg)
            db.session.add(ExperimentScheduleLog(message=msg, log_type="success"))
            db.session.commit()

    msg = f"Group '{first_group.name}' started with {started_count} experiment(s)"
    logs.append(msg)
    db.session.add(ExperimentScheduleLog(message=msg, log_type="success"))
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": f"Started {started_count} experiments in group '{first_group.name}'",
            "current_group": first_group.name,
            "current_group_id": first_group.id,
            "logs": logs,
        }
    )


@experiments.route("/admin/schedule/stop", methods=["POST"])
@login_required
def stop_schedule():
    """
    Stop the experiment schedule.

    Stops all running experiments and resets schedule status.

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    status = ExperimentScheduleStatus.query.first()
    if not status or not status.is_running:
        return jsonify({"success": False, "message": "Schedule not running"}), 400

    # Stop all experiments in current group
    if status.current_group_id:
        items = ExperimentScheduleItem.query.filter_by(
            group_id=status.current_group_id
        ).all()
        for item in items:
            exp = Exps.query.get(item.experiment_id)
            if exp and exp.running == 1:
                # Stop all clients first
                clients = Client.query.filter_by(id_exp=exp.idexp).all()
                for client in clients:
                    if client.status == 1:
                        if client.pid:
                            terminate_client(client, pause=False)
                        client.status = 0
                        db.session.commit()

                # Stop server
                terminated = terminate_server_process(exp.idexp)
                if not terminated:
                    terminate_process_on_port(exp.port)

                exp.running = 0
                exp.exp_status = "stopped"
                db.session.commit()

    # Reset status
    status.is_running = 0
    status.current_group_id = None
    status.started_at = None
    db.session.commit()

    return jsonify({"success": True, "message": "Schedule stopped"})


@experiments.route("/admin/schedule/check_progress", methods=["POST"])
@login_required
def check_schedule_progress():
    """
    Check progress of scheduled experiments and advance to next group if needed.

    Called periodically to check if current group is complete and start next group.

    Returns:
        JSON with progress status
    """
    import time
    check_privileges(current_user.username)

    status = ExperimentScheduleStatus.query.first()
    if not status or not status.is_running:
        return jsonify({"success": True, "is_running": False})

    if not status.current_group_id:
        return jsonify({"success": True, "is_running": False})

    # Check if all experiments in current group are completed
    items = ExperimentScheduleItem.query.filter_by(
        group_id=status.current_group_id
    ).all()
    all_completed = True

    for item in items:
        exp = Exps.query.get(item.experiment_id)
        if exp:
            # Check if experiment is completed
            if exp.exp_status != "completed":
                all_completed = False
                break

    if not all_completed:
        return jsonify(
            {
                "success": True,
                "is_running": True,
                "all_completed": False,
                "current_group_id": status.current_group_id,
            }
        )

    # All completed - stop current group experiments and move to next group
    logs = []
    current_group = ExperimentScheduleGroup.query.get(status.current_group_id)
    
    msg = f"Group '{current_group.name}' completed!"
    logs.append(msg)
    db.session.add(ExperimentScheduleLog(message=msg, log_type="success"))

    # Mark current group as completed
    current_group.is_completed = 1
    db.session.commit()

    for item in items:
        exp = Exps.query.get(item.experiment_id)
        if exp and exp.running == 1:
            msg = f"Stopping experiment '{exp.exp_name}'..."
            logs.append(msg)
            db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
            # Stop clients
            clients = Client.query.filter_by(id_exp=exp.idexp).all()
            for client in clients:
                if client.status == 1:
                    if client.pid:
                        terminate_client(client, pause=False)
                    client.status = 0
                    db.session.commit()

            # Stop server
            terminated = terminate_server_process(exp.idexp)
            if not terminated:
                terminate_process_on_port(exp.port)

            exp.running = 0
            db.session.commit()

    # Get next non-completed group
    next_group = (
        ExperimentScheduleGroup.query.filter(
            ExperimentScheduleGroup.order_index > current_group.order_index,
            (ExperimentScheduleGroup.is_completed == 0)
            | (ExperimentScheduleGroup.is_completed == None),
        )
        .order_by(ExperimentScheduleGroup.order_index)
        .first()
    )

    if not next_group:
        # Schedule complete
        status.is_running = 0
        status.current_group_id = None
        db.session.commit()
        msg = "All groups completed! Schedule finished."
        logs.append(msg)
        db.session.add(ExperimentScheduleLog(message=msg, log_type="success"))
        db.session.commit()
        
        # Clear all schedule logs after successful completion
        ExperimentScheduleLog.query.delete()
        db.session.commit()
        
        return jsonify(
            {
                "success": True,
                "is_running": False,
                "all_completed": True,
                "schedule_complete": True,
                "logs": logs,
            }
        )

    # Start next group
    msg = f"Starting next group: '{next_group.name}'..."
    logs.append(msg)
    db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
    status.current_group_id = next_group.id
    db.session.commit()

    next_items = ExperimentScheduleItem.query.filter_by(group_id=next_group.id).all()
    for item in next_items:
        exp = Exps.query.get(item.experiment_id)
        if exp and exp.running == 0:
            # Check if all clients have already completed before starting the server
            all_clients_completed, clients_to_start = _get_clients_to_start(exp)
            
            # If all clients have completed, mark experiment as completed and skip
            if all_clients_completed:
                msg = f"Experiment '{exp.exp_name}' already completed - skipping"
                logs.append(msg)
                db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
                exp.exp_status = "completed"
                db.session.commit()
                continue
            
            # If no clients to start, skip
            if len(clients_to_start) == 0:
                msg = f"No clients to start for '{exp.exp_name}' - skipping"
                logs.append(msg)
                db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
                continue
            
            logs.append(f"Starting server for '{exp.exp_name}'...")
            db.session.add(ExperimentScheduleLog(message=f"Starting server for '{exp.exp_name}'...", log_type="info"))
            exp.running = 1
            exp.exp_status = "active"
            db.session.commit()
            start_server(exp)

            # Wait for server to be ready
            logs.append(f"Waiting for server '{exp.exp_name}' to be ready...")
            time.sleep(3)

            # Start only clients that haven't completed
            for client in clients_to_start:
                if client.status == 0:
                    logs.append(f"Starting client '{client.name}'...")
                    db.session.add(ExperimentScheduleLog(message=f"Starting client '{client.name}'...", log_type="info"))
                    population = Population.query.filter_by(id=client.population_id).first()
                    if population:
                        start_client(exp, client, population, resume=True)
                        client.status = 1
                        db.session.commit()

            logs.append(f"Experiment '{exp.exp_name}' started successfully")
            db.session.add(ExperimentScheduleLog(message=f"Experiment '{exp.exp_name}' started successfully", log_type="success"))
            db.session.commit()

    logs.append(f"Group '{next_group.name}' started!")
    db.session.add(ExperimentScheduleLog(message=f"Group '{next_group.name}' started!", log_type="success"))
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "is_running": True,
            "all_completed": True,
            "next_group": next_group.name,
            "next_group_id": next_group.id,
            "logs": logs,
        }
    )


@experiments.route("/admin/schedule/available_experiments", methods=["GET"])
@login_required
def get_available_experiments_for_schedule():
    """
    Get experiments that can be added to schedule groups.

    Returns experiments that are stopped and not already in any group.

    Returns:
        JSON with available experiments
    """
    check_privileges(current_user.username)

    # Get current user
    user = Admin_users.query.filter_by(username=current_user.username).first()

    # Get experiments based on role
    if user.role == "admin":
        experiments_query = Exps.query
    else:
        experiments_query = Exps.query.filter_by(owner=user.username)

    # Get experiments that are stopped
    experiments_list = experiments_query.filter(
        Exps.exp_status.in_(["stopped", "scheduled"])
    ).all()

    # Get experiments already in groups
    scheduled_exp_ids = set(
        item.experiment_id for item in ExperimentScheduleItem.query.all()
    )

    result = []
    for exp in experiments_list:
        if exp.idexp not in scheduled_exp_ids:
            result.append(
                {
                    "id": exp.idexp,
                    "name": exp.exp_name,
                    "owner": exp.owner,
                    "exp_status": exp.exp_status,
                }
            )

    return jsonify({"success": True, "experiments": result})


def add_schedule_log(message, log_type="info"):
    """Helper function to add a log message to the database."""
    from datetime import datetime

    log = ExperimentScheduleLog(
        message=message, log_type=log_type, created_at=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()
    return log


@experiments.route("/admin/schedule/logs", methods=["GET"])
@login_required
def get_schedule_logs():
    """
    Get persistent schedule execution logs.

    Returns:
        JSON with log entries
    """
    check_privileges(current_user.username)

    # Get last 100 logs, ordered by most recent first
    logs = (
        ExperimentScheduleLog.query.order_by(ExperimentScheduleLog.created_at.desc())
        .limit(100)
        .all()
    )

    # Reverse to show oldest first in UI
    logs = list(reversed(logs))

    return jsonify(
        {
            "success": True,
            "logs": [
                {
                    "id": log.id,
                    "message": log.message,
                    "log_type": log.log_type,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
        }
    )


@experiments.route("/admin/schedule/logs/clear", methods=["POST"])
@login_required
def clear_schedule_logs():
    """
    Clear all schedule execution logs.

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    ExperimentScheduleLog.query.delete()
    db.session.commit()

    return jsonify({"success": True})


@experiments.route("/admin/schedule/auto_create_groups", methods=["POST"])
@login_required
def auto_create_groups():
    """
    Automatically create groups and assign available experiments.

    Expects JSON body with:
    - experiments_per_group: Number of experiments per group

    Returns:
        JSON with created groups
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data or "experiments_per_group" not in data:
        return (
            jsonify({"success": False, "message": "experiments_per_group is required"}),
            400,
        )

    try:
        experiments_per_group = int(data["experiments_per_group"])
        if experiments_per_group < 1:
            raise ValueError("Must be at least 1")
    except (ValueError, TypeError):
        return (
            jsonify({"success": False, "message": "Invalid experiments_per_group value"}),
            400,
        )

    # Get current user
    user = Admin_users.query.filter_by(username=current_user.username).first()

    # Get available experiments (stopped, not in any group)
    if user.role == "admin":
        experiments_query = Exps.query
    else:
        experiments_query = Exps.query.filter_by(owner=user.username)

    experiments_list = experiments_query.filter(
        Exps.exp_status.in_(["stopped", "scheduled"])
    ).all()

    # Filter out experiments already in groups
    scheduled_exp_ids = set(
        item.experiment_id for item in ExperimentScheduleItem.query.all()
    )
    available_exps = [exp for exp in experiments_list if exp.idexp not in scheduled_exp_ids]

    if not available_exps:
        return jsonify({"success": False, "message": "No available experiments to assign"}), 400

    # Get current max order index
    max_order = (
        db.session.query(db.func.max(ExperimentScheduleGroup.order_index)).scalar() or 0
    )

    # Create groups and assign experiments
    created_groups = []
    group_num = 1

    for i in range(0, len(available_exps), experiments_per_group):
        group_exps = available_exps[i : i + experiments_per_group]

        # Create group
        group = ExperimentScheduleGroup(
            name=f"Auto Group {max_order + group_num}",
            order_index=max_order + group_num,
            is_completed=0,
        )
        db.session.add(group)
        db.session.commit()

        # Add experiments to group
        for idx, exp in enumerate(group_exps):
            item = ExperimentScheduleItem(
                group_id=group.id, experiment_id=exp.idexp, order_index=idx
            )
            db.session.add(item)

        db.session.commit()

        created_groups.append(
            {
                "id": group.id,
                "name": group.name,
                "experiment_count": len(group_exps),
            }
        )
        group_num += 1

    add_schedule_log(
        f"Auto-created {len(created_groups)} group(s) with {len(available_exps)} experiment(s)",
        "info",
    )

    return jsonify(
        {
            "success": True,
            "message": f"Created {len(created_groups)} groups",
            "groups": created_groups,
        }
    )


@experiments.route("/admin/schedule/cleanup_completed", methods=["POST"])
@login_required
def cleanup_completed_groups():
    """
    Remove all completed groups from the schedule.

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    # Find and delete completed groups
    completed_groups = ExperimentScheduleGroup.query.filter_by(is_completed=1).all()
    count = len(completed_groups)

    for group in completed_groups:
        # Delete items first
        ExperimentScheduleItem.query.filter_by(group_id=group.id).delete()
        db.session.delete(group)

    db.session.commit()

    if count > 0:
        add_schedule_log(f"Cleaned up {count} completed group(s)", "info")

    return jsonify({"success": True, "removed_count": count})
