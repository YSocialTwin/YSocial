"""
Tutorial wizard routes.

Provides routes for the guided tutorial wizard that helps new admin/researcher
users create their first simulation by guiding them through:
1. Population Creation
2. Experiment Creation
3. Client Creation
"""

import json
import os
import pathlib
import shutil
import uuid
from urllib.parse import urlparse

import faker
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

from y_web import db
from y_web.models import (
    ActivityProfile,
    Admin_users,
    AgeClass,
    Agent,
    Agent_Population,
    Client,
    Content_Recsys,
    Education,
    Exp_stats,
    Exp_Topic,
    Exps,
    Follow_Recsys,
    Jupyter_instances,
    Leanings,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Profession,
    Topic_List,
    Toxicity_Levels,
)
from y_web.routes_admin.experiments_routes import get_suggested_port
from y_web.utils import generate_population
from y_web.utils.miscellanea import check_privileges
from y_web.utils.path_utils import get_resource_path, get_writable_path

tutorial = Blueprint("tutorial", __name__)


@tutorial.route("/admin/tutorial/check_status")
@login_required
def check_tutorial_status():
    """
    Check if the current user should see the tutorial.

    Returns:
        JSON with show_tutorial boolean and user role
    """
    user = Admin_users.query.filter_by(username=current_user.username).first()

    if not user or user.role not in ["admin", "researcher"]:
        return jsonify({"show_tutorial": False, "role": None})

    return jsonify({"show_tutorial": not user.tutorial_shown, "role": user.role})


@tutorial.route("/admin/tutorial/dismiss", methods=["POST"])
@login_required
def dismiss_tutorial():
    """
    Mark the tutorial as shown for the current user.

    Returns:
        JSON response with success status
    """
    user = Admin_users.query.filter_by(username=current_user.username).first()

    if not user or user.role not in ["admin", "researcher"]:
        return jsonify({"success": False, "message": "Access denied"}), 403

    user.tutorial_shown = True
    db.session.commit()

    return jsonify({"success": True})


@tutorial.route("/admin/tutorial/reset", methods=["POST"])
@login_required
def reset_tutorial():
    """
    Reset the tutorial flag to allow showing it again.

    Returns:
        JSON response with success status
    """
    user = Admin_users.query.filter_by(username=current_user.username).first()

    if not user or user.role not in ["admin", "researcher"]:
        return jsonify({"success": False, "message": "Access denied"}), 403

    user.tutorial_shown = False
    db.session.commit()

    return jsonify({"success": True})


@tutorial.route("/admin/tutorial/data")
@login_required
def get_tutorial_data():
    """
    Get all data needed for the tutorial wizard forms.

    Returns:
        JSON with education levels, political leanings, activity profiles,
        recommendation systems, and Ollama status
    """
    from y_web.utils.external_processes import get_ollama_models, is_ollama_running

    check_privileges(current_user.username)

    education_levels = Education.query.all()
    leanings = Leanings.query.all()
    activity_profiles = ActivityProfile.query.all()
    crecsys = Content_Recsys.query.all()
    frecsys = Follow_Recsys.query.all()

    # Check if Ollama is running
    ollama_available = False
    ollama_models = []
    try:
        ollama_available = is_ollama_running()
        if ollama_available:
            ollama_models = get_ollama_models()
    except Exception:
        pass

    return jsonify(
        {
            "education_levels": [
                {"id": e.id, "name": e.education_level} for e in education_levels
            ],
            "political_leanings": [{"id": l.id, "name": l.leaning} for l in leanings],
            "activity_profiles": [
                {"id": a.id, "name": a.name, "hours": a.hours}
                for a in activity_profiles
            ],
            "content_recsys": [
                {"id": c.id, "name": c.name, "value": c.value} for c in crecsys
            ],
            "follow_recsys": [
                {"id": f.id, "name": f.name, "value": f.value} for f in frecsys
            ],
            "ollama_available": ollama_available,
            "ollama_models": ollama_models,
        }
    )


@tutorial.route("/admin/tutorial/create_all", methods=["POST"])
@login_required
def create_tutorial_experiment():
    """
    Create population, experiment, and client in one step from the tutorial wizard.

    This endpoint handles all three steps of the tutorial and returns the
    experiment ID for redirection.

    Expects JSON body with:
    - population_name: Name for the population
    - population_size: Size of population (10-100)
    - education_levels: List of education level IDs
    - political_leanings: List of political leaning IDs
    - toxicity_levels: List of toxicity level IDs
    - experiment_name: Name for the experiment
    - client_name: Name for the client
    - simulation_days: Number of days to run (1-30)
    - post_probability: Probability of posting (0-1)
    - share_probability: Probability of sharing (0-1)
    - comment_probability: Probability of commenting (0-1)
    - read_probability: Probability of reading (0-1)
    - content_recsys: Content recommendation system name
    - follow_recsys: Follow recommendation system name

    Returns:
        JSON with success status and experiment_id
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    try:
        # Extract population data
        population_name = data.get("population_name", "").strip()
        population_size = int(data.get("population_size", 50))
        education_levels = data.get("education_levels", [])
        political_leanings = data.get("political_leanings", [])
        activity_profiles_data = data.get(
            "activity_profiles_data", []
        )  # List of {id, name, percentage}

        # Extract experiment data
        experiment_name = data.get("experiment_name", "").strip()
        llm_enabled = data.get("llm_enabled", False)
        topics = data.get("topics", [])

        # Extract client data
        client_name = data.get("client_name", "").strip()
        simulation_days = int(data.get("simulation_days", 7))
        post_probability = float(data.get("post_probability", 0.3))
        share_probability = float(data.get("share_probability", 0.2))
        comment_probability = float(data.get("comment_probability", 0.3))
        read_probability = float(data.get("read_probability", 0.2))
        content_recsys = data.get("content_recsys", "reverse_chronological")
        follow_recsys = data.get("follow_recsys", "preferential_attachment")
        llm_model = data.get("llm_model", "")

        # Validate required fields
        if not population_name:
            return (
                jsonify({"success": False, "message": "Population name is required"}),
                400,
            )
        if not experiment_name:
            return (
                jsonify({"success": False, "message": "Experiment name is required"}),
                400,
            )
        if not client_name:
            return (
                jsonify({"success": False, "message": "Client name is required"}),
                400,
            )

        # Validate size constraints
        if population_size < 10 or population_size > 100:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Population size must be between 10 and 100",
                    }
                ),
                400,
            )
        if simulation_days < 1 or simulation_days > 30:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Simulation length must be between 1 and 30 days",
                    }
                ),
                400,
            )

        # Check for existing names
        if Population.query.filter_by(name=population_name).first():
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Population '{population_name}' already exists",
                    }
                ),
                400,
            )
        if Exps.query.filter_by(exp_name=experiment_name).first():
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Experiment '{experiment_name}' already exists",
                    }
                ),
                400,
            )

        # ============== STEP 1: Create Population ==============

        # Convert IDs to comma-separated strings
        education_str = ",".join(str(e) for e in education_levels)
        political_str = ",".join(str(p) for p in political_leanings)

        # Default toxicity to "None" (ID 1 typically)
        none_toxicity = Toxicity_Levels.query.filter_by(toxicity_level="None").first()
        toxicity_str = str(none_toxicity.id) if none_toxicity else "1"

        # Build percentages dict with equal distribution
        def build_percentages(items):
            if not items:
                return {}
            pct = 100.0 / len(items)
            return {str(i): pct for i in items}

        # Build age class percentages with default values matching the population form
        # Default percentages based on typical age distribution
        default_age_percentages = {
            "Youth": 35.0,
            "Adults": 42.0,
            "Middle-aged": 18.0,
            "Elderly": 5.0,
        }

        # Query all age classes from database and build percentages
        all_age_classes = AgeClass.query.all()
        age_class_percentages = {}
        for age_class in all_age_classes:
            # Use default percentage if available, otherwise distribute evenly
            pct = default_age_percentages.get(age_class.name, 25.0)
            age_class_percentages[str(age_class.id)] = pct

        # Normalize to ensure they sum to 100
        if age_class_percentages:
            total = sum(age_class_percentages.values())
            if total > 0:
                age_class_percentages = {
                    k: (v / total) * 100 for k, v in age_class_percentages.items()
                }

        # Build toxicity percentages (default to None only)
        toxicity_percentages = {toxicity_str: 100.0}

        percentages = {
            "education": build_percentages(education_levels),
            "political_leanings": build_percentages(political_leanings),
            "toxicity_levels": toxicity_percentages,
            "age_classes": age_class_percentages,
            "gender": {"male": 50, "female": 50},
        }

        # Create population record
        pop = Population(
            name=population_name,
            descr="Created via tutorial wizard",
            size=population_size,
            llm=None,  # LLM agents disabled
            age_min=None,
            age_max=None,
            education=education_str,
            leanings=political_str,
            nationalities="American",
            languages="English",
            interests="",
            toxicity=toxicity_str,
            llm_url=None,
        )

        db.session.add(pop)
        db.session.commit()

        # Assign activity profiles with their percentages
        if activity_profiles_data:
            for profile_data in activity_profiles_data:
                profile_id = profile_data.get("id")
                percentage = float(profile_data.get("percentage", 0))
                if profile_id and percentage > 0:
                    profile = ActivityProfile.query.filter_by(id=profile_id).first()
                    if profile:
                        profile_assoc = PopulationActivityProfile(
                            population=pop.id,
                            activity_profile=profile.id,
                            percentage=percentage,
                        )
                        db.session.add(profile_assoc)
            db.session.commit()
        else:
            # Default to "Always On" at 100% if no profiles specified
            selected_profile = ActivityProfile.query.filter_by(name="Always On").first()
            if selected_profile:
                profile_assoc = PopulationActivityProfile(
                    population=pop.id,
                    activity_profile=selected_profile.id,
                    percentage=100.0,
                )
                db.session.add(profile_assoc)
                db.session.commit()

        # Get all profession backgrounds for population generation
        all_backgrounds = db.session.query(Profession.background).distinct().all()
        profession_backgrounds = [bg[0] for bg in all_backgrounds]

        # Actions configuration for population generation
        actions_config = {
            "min": "1",
            "max": "5",
            "distribution": "Uniform",
            "Poisson": "0.88",
            "Geometric": "0.6667",
            "Zipf": "2.5",
        }

        # Generate the population agents
        generate_population(
            population_name, percentages, actions_config, profession_backgrounds
        )

        # ============== STEP 2: Create Experiment ==============

        BASE_DIR = get_writable_path()

        # Determine database type
        db_type = "sqlite"
        if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
            db_type = "postgresql"

        uid = str(uuid.uuid4()).replace("-", "_")
        pathlib.Path(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}").mkdir(
            parents=True, exist_ok=True
        )

        # Get suggested port
        port = get_suggested_port()
        if not port:
            return (
                jsonify({"success": False, "message": "No available port found"}),
                500,
            )

        # Create experiment database
        if db_type == "sqlite":
            db_uri = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db"
            clean_db_source = get_resource_path(
                os.path.join("data_schema", "database_clean_server.db")
            )
            shutil.copyfile(
                clean_db_source,
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db",
            )
            db_name = f"experiments{os.sep}{uid}{os.sep}database_server.db"
        else:
            # PostgreSQL setup
            current_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
            parsed_uri = urlparse(current_uri)

            user = parsed_uri.username or "postgres"
            password = parsed_uri.password or "password"
            host = parsed_uri.hostname or "localhost"
            port_db = parsed_uri.port or 5432

            dbname = f"experiments_{uid}"
            db_uri = f"postgresql://{user}:{password}@{host}:{port_db}/{dbname}"
            db_name = dbname

            admin_engine = create_engine(
                f"postgresql://{user}:{password}@{host}:{port_db}/postgres"
            )

            with admin_engine.connect() as conn:
                result = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": dbname},
                )
                db_exists = result.scalar() is not None

            if not db_exists:
                with admin_engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as conn:
                    conn.execute(text(f'CREATE DATABASE "{dbname}"'))

                experiment_engine = create_engine(db_uri)
                with experiment_engine.connect() as dummy_conn:
                    schema_path = get_resource_path(
                        os.path.join("data_schema", "postgre_server.sql")
                    )
                    with open(schema_path, "r") as schema_file:
                        schema_sql = schema_file.read()
                        dummy_conn.execute(text(schema_sql))

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

        # Determine topics list (use provided topics if LLM enabled, otherwise "General")
        experiment_topics = topics if llm_enabled and topics else ["General"]

        # Create experiment config file
        config = {
            "platform_type": "microblogging",
            "name": experiment_name,
            "host": "127.0.0.1",
            "port": port,
            "debug": "False",
            "reset_db": "False",
            "modules": ["news", "voting", "image"],
            "perspective_api": None,
            "sentiment_annotation": False,
            "emotion_annotation": False,
            "database_uri": db_uri,
            "topics": experiment_topics,
        }

        config_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        # Create experiment record
        exp = Exps(
            exp_name=experiment_name,
            platform_type="microblogging",
            db_name=db_name,
            owner=current_user.username,
            exp_descr="Created via tutorial wizard",
            status=0,
            port=int(port),
            server="127.0.0.1",
            annotations="",
            llm_agents_enabled=1 if llm_enabled else 0,
        )

        db.session.add(exp)
        db.session.commit()

        # Create experiment stats
        exp_stats = Exp_stats(
            exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0
        )
        db.session.add(exp_stats)
        db.session.commit()

        # Create topics for the experiment
        for topic_name in experiment_topics:
            existing_topic = Topic_List.query.filter_by(name=topic_name).first()
            if not existing_topic:
                existing_topic = Topic_List(name=topic_name)
                db.session.add(existing_topic)
                db.session.commit()

            exp_topic = Exp_Topic(exp_id=exp.idexp, topic_id=existing_topic.id)
            db.session.add(exp_topic)
            db.session.commit()

        # Create Jupyter instance record
        jupyter_instance = Jupyter_instances(
            port=-1, notebook_dir="", exp_id=exp.idexp, status="stopped"
        )
        db.session.add(jupyter_instance)
        db.session.commit()

        # ============== STEP 3: Create Client ==============

        # Associate population with experiment
        pop_exp = Population_Experiment(id_population=pop.id, id_exp=exp.idexp)
        db.session.add(pop_exp)
        db.session.commit()

        # Get activity profiles for the population
        activity_profiles = (
            db.session.query(PopulationActivityProfile)
            .filter(PopulationActivityProfile.population == pop.id)
            .all()
        )
        activity_profiles_ids = [a.activity_profile for a in activity_profiles]

        all_activity_profiles = (
            db.session.query(ActivityProfile)
            .filter(ActivityProfile.id.in_(activity_profiles_ids))
            .all()
        )
        profiles = {ap.name: ap.hours for ap in all_activity_profiles}

        # Default hourly activity pattern
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

        # Create client record with LLM model if enabled
        client = Client(
            name=client_name,
            descr="Created via tutorial wizard",
            id_exp=exp.idexp,
            population_id=pop.id,
            days=simulation_days,
            percentage_new_agents_iteration=0.0,
            percentage_removed_agents_iteration=0.0,
            max_length_thread_reading=5,
            reading_from_follower_ratio=0.5,
            probability_of_daily_follow=0.1,
            attention_window=10,
            visibility_rounds=48,
            post=post_probability,
            share=share_probability,
            image=0.0,
            comment=comment_probability,
            read=read_probability,
            news=0.0,
            search=0.0,
            vote=0.0,
            share_link=0.0,
            llm="http://127.0.0.1:11434/v1",
            llm_api_key="NULL",
            llm_max_tokens=-1,
            llm_temperature=1.5,
            llm_v_agent="",
            llm_v="",
            llm_v_api_key="NULL",
            llm_v_max_tokens=300,
            llm_v_temperature=0.5,
            probability_of_secondary_follow=0.0,
            crecsys=content_recsys,
            frecsys=follow_recsys,
            status=0,
            # user_type=llm_model if llm_enabled and llm_model else None,
        )

        db.session.add(client)
        db.session.commit()

        # Create client config file
        # Get agents in the population
        agents = Agent_Population.query.filter_by(population_id=pop.id).all()
        agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

        # Build agent population file
        res = {"agents": []}
        fake = faker.Faker()
        agent_topics = experiment_topics  # Use the experiment topics

        for a in agents:
            if a is None:
                continue

            interests = list(
                set(
                    fake.random_elements(
                        elements=set(agent_topics),
                        length=fake.random_int(min=1, max=min(5, len(agent_topics))),
                    )
                )
            )

            activity_profile_obj = (
                db.session.query(ActivityProfile)
                .filter_by(id=a.activity_profile)
                .first()
            )
            activity_profile_name = (
                activity_profile_obj.name if activity_profile_obj else "Always On"
            )

            # Set agent type based on LLM model if enabled
            agent_type = llm_model if llm_enabled and llm_model else ""

            res["agents"].append(
                {
                    "name": a.name,
                    "email": f"{a.name}@ysocial.it",
                    "password": f"{a.name}",
                    "age": a.age,
                    "type": agent_type,
                    "leaning": a.leaning,
                    "interests": [interests, len(interests)],
                    "oe": a.oe,
                    "co": a.co,
                    "ex": a.ex,
                    "ag": a.ag,
                    "ne": a.ne,
                    "rec_sys": content_recsys,
                    "frec_sys": follow_recsys,
                    "language": a.language,
                    "owner": exp.owner,
                    "education_level": a.education_level,
                    "round_actions": int(a.round_actions) if a.round_actions else 3,
                    "gender": a.gender,
                    "nationality": a.nationality,
                    "toxicity": a.toxicity,
                    "is_page": 0,
                    "prompts": None,
                    "daily_activity_level": a.daily_activity_level,
                    "profession": a.profession,
                    "activity_profile": activity_profile_name,
                }
            )

        # Save agent population file
        pop_filename = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}{population_name.replace(' ', '')}.json"
        with open(pop_filename, "w") as f:
            json.dump(res, f, indent=4)

        # Create client config
        client_config = {
            "servers": {
                "llm": "http://127.0.0.1:11434/v1",
                "llm_api_key": "NULL",
                "llm_max_tokens": -1,
                "llm_temperature": 1.5,
                "llm_v": "http://127.0.0.1:11434/v1",
                "llm_v_api_key": "NULL",
                "llm_v_max_tokens": 300,
                "llm_v_temperature": 0.5,
                "api": f"http://127.0.0.1:{port}/",
            },
            "simulation": {
                "name": client_name,
                "population": population_name,
                "client": "YClientWeb",
                "days": simulation_days,
                "slots": 24,
                "percentage_new_agents_iteration": 0.0,
                "percentage_removed_agents_iteration": 0.0,
                "activity_profiles": profiles,
                "hourly_activity": default_hourly_activity,
                "actions_likelihood": {
                    "post": post_probability,
                    "image": 0.0,
                    "news": 0.0,
                    "comment": comment_probability,
                    "read": read_probability,
                    "share": share_probability,
                    "search": 0.0,
                    "cast": 0.0,
                    "share_link": 0.0,
                },
                "emotion_annotation": False,
            },
            "posts": {
                "visibility_rounds": 48,
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
                "reading_from_follower_ratio": 0.5,
                "max_length_thread_reading": 5,
                "attention_window": 10,
                "probability_of_daily_follow": 0.1,
                "probability_of_secondary_follow": 0.0,
                "age": {"min": 18, "max": 65},
                "political_leaning": [],
                "toxicity_levels": [],
                "languages": [],
                "llm_agents": [None],  # Disabled
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

        client_config_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{client_name}-{population_name}.json"
        with open(client_config_path, "w") as f:
            json.dump(client_config, f, indent=4)

        # Copy prompts file
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
        shutil.copy(
            prompts_src,
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}prompts.json",
        )

        # Note: Don't create Client_Execution here - let the client runner create it
        # on first run so that first_run detection works correctly

        # Mark tutorial as shown
        user = Admin_users.query.filter_by(username=current_user.username).first()
        if user:
            user.tutorial_shown = True
            db.session.commit()

        # Log telemetry
        try:
            from y_web.telemetry import Telemetry

            telemetry = Telemetry(user=current_user)
            telemetry.log_event(
                {
                    "action": "tutorial_complete",
                    "data": {
                        "population_size": population_size,
                        "simulation_days": simulation_days,
                    },
                }
            )
        except Exception as telemetry_error:
            current_app.logger.debug(
                f"Telemetry logging skipped: {str(telemetry_error)}"
            )

        return jsonify(
            {
                "success": True,
                "experiment_id": exp.idexp,
                "client_id": client.id,
                "message": "Experiment created successfully!",
            }
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Tutorial wizard error: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@tutorial.route("/admin/tutorial/run_simulation", methods=["POST"])
@login_required
def run_tutorial_simulation():
    """
    Start the experiment server and client for a tutorial-created experiment.

    This is an async-friendly JSON API endpoint that starts both the server
    and client, waiting for the server to be ready before starting the client.

    Expects JSON body with:
    - experiment_id: ID of the experiment to start
    - client_id: ID of the client to run

    Returns:
        JSON with success status
    """
    from y_web.utils import start_client
    from y_web.utils.external_processes import start_server

    check_privileges(current_user.username)

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    experiment_id = data.get("experiment_id")
    client_id = data.get("client_id")

    if not experiment_id or not client_id:
        return (
            jsonify(
                {"success": False, "message": "Missing experiment_id or client_id"}
            ),
            400,
        )

    try:
        # Get the experiment
        exp = Exps.query.filter_by(idexp=experiment_id).first()
        if not exp:
            return jsonify({"success": False, "message": "Experiment not found"}), 404

        # Get the client
        client = Client.query.filter_by(id=client_id).first()
        if not client:
            return jsonify({"success": False, "message": "Client not found"}), 404

        # Get the population
        population = Population.query.filter_by(id=client.population_id).first()
        if not population:
            return jsonify({"success": False, "message": "Population not found"}), 404

        # Start the experiment server if not already running
        if exp.running == 0:
            # Update experiment status
            db.session.query(Exps).filter_by(idexp=experiment_id).update(
                {Exps.running: 1, Exps.exp_status: "active"}
            )
            db.session.commit()

            # Start the server
            start_server(exp)

            # Wait a bit for the server to start
            import time

            time.sleep(2)

        # Start the client
        start_client(exp, client, population, resume=True)

        # Update client status
        db.session.query(Client).filter_by(id=client_id).update({Client.status: 1})
        db.session.commit()

        return jsonify({"success": True, "message": "Simulation started successfully!"})

    except Exception as e:
        current_app.logger.error(
            f"Error starting tutorial simulation: {str(e)}", exc_info=True
        )
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500
