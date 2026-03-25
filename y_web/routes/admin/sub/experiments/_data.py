"""
Experiment management routes.

Administrative routes for creating, configuring, launching, and managing
social media simulation experiments including database setup, population
assignment, and experiment lifecycle control.
"""

import json
import os
import pathlib
import random
import re
import shutil
import socket
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

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
from flask_login import current_user, login_required, login_user

from y_web import db  # , app
from y_web.src.content.avatars import normalize_forum_avatar_mode
from y_web.src.experiment.access import (
    get_visible_experiment_query,
    user_can_manage_experiment,
    user_can_view_experiment,
)
from y_web.src.hpc.population_backup import restore_population_for_hpc_client
from y_web.src.models import (
    ActivityProfile,
    Admin_users,
    AgeClass,
    Agent,
    Agent_Population,
    Agent_Profile,
    Client,
    Client_Execution,
    ClientLogMetrics,
    DownloadNotification,
    Education,
    Exp_stats,
    Exp_Topic,
    ExperimentScheduleGroup,
    ExperimentScheduleItem,
    ExperimentScheduleLog,
    ExperimentScheduleStatus,
    Exps,
    HpcMonitorSettings,
    Jupyter_instances,
    Languages,
    Leanings,
    LogFileOffset,
    Nationalities,
    Ollama_Pull,
    OpinionDistribution,
    OpinionEvolutionCache,
    OpinionEvolutionSampledAgents,
    OpinionGroup,
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
from y_web.src.simulation.execution_backend import (
    start_client_for_experiment,
    start_server_for_experiment,
    stop_client_for_experiment,
    stop_server_for_experiment,
)
from y_web.src.system.desktop_file_handler import send_file_desktop
from y_web.src.system.jupyter_utils import stop_process
from y_web.src.system.miscellanea import (
    check_privileges,
    llm_backend_status,
    ollama_status,
    reload_current_user,
)
from y_web.src.system.path_utils import get_resource_path

from ._blueprint import (
    _EXP_IDS_MARKER_RE,
    DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS,
    DEFAULT_FEED_LIMITS,
    DEFAULT_FORUM_AVATAR_SETTINGS,
    DEFAULT_FORUM_EMBEDDING_SETTINGS,
    FORUM_FEED_REQUEST_HEADERS,
    MAX_HPC_PER_GROUP,
    OPINION_CACHE_EXPIRY_MINUTES,
    _schedule_check_lock,
    experiments,
)
from ._helpers import *  # noqa: F401,F403
from ._helpers import (
    _current_admin_user_or_none,
    _experiment_configuration_box_present,
    _experiment_configuration_update_required,
    _experiment_has_started_once,
    _get_database_type,
    _get_experiment_folder,
    _normalize_embedding_host,
    _normalize_embedding_service,
    _normalize_forum_embedding_host,
    _normalize_forum_embedding_service,
    _read_forum_feed_health,
)


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

    # Filter experiments based on role + visibility grants
    if user.role in ("admin", "researcher"):
        query = get_visible_experiment_query(user)
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
    # Track experiments with infinite clients
    exp_has_infinite = {}
    for exp in res:
        # Check if any client has infinite duration (days = -1)
        clients = Client.query.filter_by(id_exp=exp.idexp).all()
        exp_has_infinite[exp.idexp] = any(client.days == -1 for client in clients)

        if exp.running == 1 or exp.exp_status == "active":
            # Get all clients for this experiment
            if clients:
                total_progress = 0
                count = 0
                for client in clients:
                    client_exec = Client_Execution.query.filter_by(
                        client_id=client.id
                    ).first()
                    if client_exec and client_exec.expected_duration_rounds > 0:
                        progress = min(
                            100,
                            max(
                                0,
                                int(
                                    client_exec.elapsed_time
                                    / client_exec.expected_duration_rounds
                                    * 100
                                ),
                            ),
                        )
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
                "has_infinite_client": exp_has_infinite.get(exp.idexp, False),
                "exp_group": exp.exp_group if exp.exp_group else "No group",
                "simulator_type": getattr(exp, "simulator_type", "Standard"),
                "is_remote": getattr(exp, "is_remote", 0),
                "can_manage": user_can_manage_experiment(user, exp),
            }
            for exp in res
        ],
        "total": total,
    }


@experiments.route("/admin/experiment_clients/<int:exp_id>")
@login_required
def experiment_clients(exp_id):
    """Get client information for an experiment including progress data.

    Returns:
        JSON with client details and progress information
    """
    try:
        # Get experiment
        experiment = Exps.query.filter_by(idexp=exp_id).first()
        if not experiment:
            return jsonify({"error": "Experiment not found"}), 404

        # Check user permissions
        user = Admin_users.query.filter_by(username=current_user.username).first()
        if not user_can_view_experiment(user, experiment):
            return jsonify({"error": "Access denied"}), 403

        # Import log metrics function and path utilities
        from y_web.src.hpc.log_metrics import update_client_log_metrics
        from y_web.src.system.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Get experiment folder path
        uid = get_experiment_uid_from_db_name(experiment.db_name)
        if uid is None:
            return jsonify({"error": "Invalid experiment path format"}), 400

        exp_folder = os.path.join(BASE_DIR, "y_web", "experiments", uid)

        # Get clients for this experiment
        clients = Client.query.filter_by(id_exp=exp_id).all()

        client_data = []
        for client in clients:
            # Update client log metrics before reading execution data
            # This ensures we have the latest progress information
            client_log_file = os.path.join(exp_folder, f"{client.name}_client.log")
            if os.path.exists(client_log_file):
                try:
                    # Pass is_hpc flag for HPC experiments to use correct log format
                    is_hpc = experiment.simulator_type == "HPC"
                    current_app.logger.info(
                        f"Updating metrics for client {client.id} ({client.name}), "
                        f"is_hpc={is_hpc}, log_file={client_log_file}"
                    )
                    update_client_log_metrics(
                        exp_id, client.id, client_log_file, is_hpc=is_hpc
                    )
                except Exception as e:
                    current_app.logger.error(
                        f"Error updating client {client.id} log metrics: {e}",
                        exc_info=True,
                    )
            else:
                current_app.logger.warning(
                    f"Log file not found for client {client.id} ({client.name}): {client_log_file}"
                )

            # Get client execution data (now updated with latest info)
            client_exec = Client_Execution.query.filter_by(client_id=client.id).first()

            if client_exec:
                current_app.logger.info(
                    f"Client_Execution for client {client.id}: elapsed_time={client_exec.elapsed_time}, "
                    f"expected={client_exec.expected_duration_rounds}, "
                    f"last_day={client_exec.last_active_day}, last_hour={client_exec.last_active_hour}"
                )
            else:
                current_app.logger.warning(
                    f"No Client_Execution record found for client {client.id} ({client.name})"
                )

            client_info = {
                "id": client.id,
                "name": client.name,
                "status": client.status,
                "days": client.days,
                "progress": 0,
                "infinite": client.days == -1,
            }

            if client_exec:
                # Calculate progress for finite clients
                if (
                    client_exec.expected_duration_rounds
                    and client_exec.expected_duration_rounds > 0
                ):
                    progress = min(
                        100,
                        max(
                            0,
                            int(
                                client_exec.elapsed_time
                                / client_exec.expected_duration_rounds
                                * 100
                            ),
                        ),
                    )
                    client_info["progress"] = progress
                    client_info["elapsed_time"] = client_exec.elapsed_time
                    client_info["expected_duration_rounds"] = (
                        client_exec.expected_duration_rounds
                    )
                elif client_exec.expected_duration_rounds == -1:
                    # Infinite client
                    client_info["infinite"] = True
                    client_info["elapsed_time"] = client_exec.elapsed_time
                    client_info["elapsed_days"] = client_exec.elapsed_time // 24
                    client_info["elapsed_hours"] = client_exec.elapsed_time % 24

            client_data.append(client_info)

        return jsonify({"clients": client_data})

    except Exception as e:
        current_app.logger.error(
            f"Error fetching experiment clients: {e}", exc_info=True
        )
        return jsonify({"error": str(e)}), 500


@experiments.route("/admin/experiment_details/<int:uid>")
@login_required
def experiment_details(uid):
    """Handle experiment details operation."""
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()
    admin_user = _current_admin_user_or_none()
    if not user_can_view_experiment(admin_user, experiment):
        flash("You are not allowed to view this experiment.", "error")
        return redirect(url_for("experiments.settings"))

    # get experiment populations along with population names and ids
    experiment_populations = (
        db.session.query(Population_Experiment, Population)
        .join(Population)
        .filter(Population_Experiment.id_exp == uid)
        .all()
    )
    experiment_topics = (
        db.session.query(Exp_Topic, Topic_List)
        .join(Topic_List, Exp_Topic.topic_id == Topic_List.id)
        .filter(Exp_Topic.exp_id == uid)
        .all()
    )
    experiment_topics = [topic.name for _, topic in experiment_topics]

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

    # HPC reset availability: only stopped experiments that already started once.
    has_started_once = _experiment_has_started_once(experiment, clients=clients)
    hpc_reset_available = (
        experiment.simulator_type == "HPC"
        and experiment.running == 0
        and has_started_once
    )

    # Check if any client has infinite duration (days = -1)
    has_infinite_client = any(client.days == -1 for client in clients)

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

    # Resolve current toggle values from persisted server config.
    current_perspective_api = ""
    embedding_settings = dict(DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS)
    forum_embedding_settings = dict(DEFAULT_FORUM_EMBEDDING_SETTINGS)
    forum_avatar_settings = dict(DEFAULT_FORUM_AVATAR_SETTINGS)
    forum_feed_health = None
    memory_module_enabled = False
    memory_configuration_supported = bool(
        experiment.simulator_type != "HPC"
        and bool(getattr(experiment, "llm_agents_enabled", 0))
    )
    toxicity_annotation_enabled = bool(
        experiment.annotations and "toxicity" in experiment.annotations
    )
    sentiment_annotation_enabled = bool(
        experiment.annotations and "sentiment" in experiment.annotations
    )
    emotion_annotation_enabled = bool(
        experiment.annotations and "emotion" in experiment.annotations
    )
    opinion_dynamics_enabled = bool(
        experiment.annotations and "opinions" in experiment.annotations
    )
    configuration_update_required = _experiment_configuration_update_required(
        experiment
    )
    configuration_box_present = _experiment_configuration_box_present(experiment)
    try:
        from y_web.src.system.path_utils import get_writable_path

        base_dir = get_writable_path()
        exp_folder = _get_experiment_folder(base_dir, experiment, _get_database_type())
        cfg_name = (
            "server_config.json"
            if experiment.simulator_type == "HPC"
            else "config_server.json"
        )
        cfg_path = os.path.join(exp_folder, cfg_name)
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                config = json.load(f)
            config_topics = config.get("topics")
            if isinstance(config_topics, list):
                experiment_topics = [
                    str(topic).strip()[:50]
                    for topic in config_topics
                    if str(topic).strip()
                ]
            current_perspective_api = (config.get("perspective_api") or "").strip()
            toxicity_annotation_enabled = bool(
                config.get("toxicity_annotation", toxicity_annotation_enabled)
            ) or bool(config.get("perspective_api"))
            sentiment_annotation_enabled = bool(
                config.get("sentiment_annotation", sentiment_annotation_enabled)
            )
            emotion_annotation_enabled = bool(
                config.get("emotion_annotation", emotion_annotation_enabled)
            )
            opinion_dynamics_enabled = bool(
                config.get(
                    "opinion_dynamics_enabled",
                    config.get("opinions_enabled", opinion_dynamics_enabled),
                )
            )
            configuration_update_required = configuration_box_present and not bool(
                config.get("experiment_configuration_confirmed")
            )
            memory_cfg = config.get("memory")
            if isinstance(memory_cfg, dict):
                memory_module_enabled = bool(memory_cfg.get("enabled"))
            if experiment.platform_type in {"forum", "microblogging"}:
                persisted_embedding = config.get("memory_embeddings")
                if isinstance(persisted_embedding, dict):
                    embedding_settings = {
                        "service": _normalize_embedding_service(
                            persisted_embedding.get("service")
                        ),
                        "host": _normalize_embedding_host(
                            persisted_embedding.get("host")
                        ),
                        "model": str(persisted_embedding.get("model") or "").strip(),
                    }
            if experiment.platform_type == "forum":
                persisted_embedding = config.get("memory_embeddings")
                if isinstance(persisted_embedding, dict):
                    forum_embedding_settings = {
                        "service": _normalize_forum_embedding_service(
                            persisted_embedding.get("service")
                        ),
                        "host": _normalize_forum_embedding_host(
                            persisted_embedding.get("host")
                        ),
                        "model": str(persisted_embedding.get("model") or "").strip(),
                    }
                forum_avatar_settings["mode"] = normalize_forum_avatar_mode(
                    config.get("avatar_mode")
                )
    except Exception:
        current_perspective_api = ""

    if experiment.platform_type == "forum":
        try:
            from y_web.src.system.path_utils import get_writable_path

            base_dir = get_writable_path()
            exp_folder = _get_experiment_folder(
                base_dir, experiment, _get_database_type()
            )
            forum_feed_health = _read_forum_feed_health(experiment, exp_folder)
        except Exception:
            forum_feed_health = None

    template_name = (
        "admin/experiment_details_forum.html"
        if experiment.platform_type == "forum"
        else "admin/experiment_details.html"
    )

    return render_template(
        template_name,
        experiment=experiment,
        clients=clients,
        client_executions=client_executions,
        has_infinite_client=has_infinite_client,
        users=users,
        experiment_topics=experiment_topics,
        len=len,
        dbtype=dbtype,
        jupyter_instance=jupyter_instance,
        notebooks=current_app.config["ENABLE_NOTEBOOK"],
        telemetry_enabled=telemetry_enabled,
        can_manage_experiment=user_can_manage_experiment(admin_user, experiment),
        current_perspective_api=current_perspective_api,
        toxicity_annotation_enabled=toxicity_annotation_enabled,
        sentiment_annotation_enabled=sentiment_annotation_enabled,
        emotion_annotation_enabled=emotion_annotation_enabled,
        opinion_dynamics_enabled=opinion_dynamics_enabled,
        configuration_box_present=configuration_box_present,
        configuration_update_required=configuration_update_required,
        memory_configuration_supported=memory_configuration_supported,
        memory_module_enabled=memory_module_enabled,
        embedding_settings=embedding_settings,
        forum_embedding_settings=forum_embedding_settings,
        forum_avatar_settings=forum_avatar_settings,
        forum_feed_health=forum_feed_health,
        hpc_reset_available=hpc_reset_available,
    )


@experiments.route("/admin/update_experiment_descr/<int:uid>", methods=["POST"])
@login_required
def update_experiment_descr(uid):
    """Update a forum experiment description shown to forum agents."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=uid).first()
    if not exp:
        return jsonify({"success": False, "message": "Experiment not found"}), 404

    admin_user = _current_admin_user_or_none()
    if not user_can_manage_experiment(admin_user, exp):
        return jsonify({"success": False, "message": "Forbidden"}), 403

    data = request.get_json(silent=True) or {}
    exp_descr = (data.get("exp_descr") or request.form.get("exp_descr") or "").strip()
    exp_descr = exp_descr[:200]

    try:
        exp.exp_descr = exp_descr
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            "Failed to update experiment description for exp %s: %s",
            uid,
            e,
            exc_info=True,
        )
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Failed to update experiment description: {e}",
                }
            ),
            500,
        )

    return jsonify({"success": True, "exp_descr": exp_descr}), 200


@experiments.route("/admin/update_experiment_config/<int:uid>", methods=["POST"])
@login_required
def update_experiment_config(uid):
    """Update experiment config toggles and persist changes in server/client JSON files."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=uid).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user_or_none()
    if not user_can_manage_experiment(admin_user, exp):
        flash("You do not have permission to update this experiment.", "error")
        return redirect(url_for("experiments.experiment_details", uid=uid))

    def _is_checked(field_name):
        return str(request.form.get(field_name, "")).strip().lower() in (
            "on",
            "true",
            "1",
            "yes",
        )

    toxicity_enabled = _is_checked("toxicity_annotation")
    emotion_enabled = _is_checked("emotion_annotation")
    sentiment_enabled = _is_checked("sentiment_annotation")
    opinion_dynamics_enabled = _is_checked("opinion_dynamics_enabled")
    memory_enabled = None
    perspective_api = (request.form.get("perspective_api") or "").strip()

    if not bool(getattr(exp, "llm_agents_enabled", 0)):
        toxicity_enabled = False
        emotion_enabled = False
        sentiment_enabled = False
        perspective_api = ""

    if getattr(exp, "platform_type", "") == "forum":
        toxicity_enabled = False
        emotion_enabled = False
        sentiment_enabled = False
        opinion_dynamics_enabled = False
        perspective_api = ""

    memory_configuration_supported = bool(
        exp.simulator_type != "HPC"
        and bool(getattr(exp, "llm_agents_enabled", 0))
    )
    if memory_configuration_supported:
        memory_enabled = _is_checked("memory_enabled")
    else:
        memory_enabled = False

    existing = [a.strip() for a in (exp.annotations or "").split(",") if a.strip()]
    annotation_set = set(existing)
    for key, enabled in (
        ("toxicity", toxicity_enabled),
        ("emotion", emotion_enabled),
        ("sentiment", sentiment_enabled),
        ("opinions", opinion_dynamics_enabled),
    ):
        if enabled:
            annotation_set.add(key)
        else:
            annotation_set.discard(key)
    exp.annotations = ",".join(sorted(annotation_set))

    try:
        from y_web.src.system.path_utils import get_writable_path

        base_dir = get_writable_path()
        exp_folder = _get_experiment_folder(base_dir, exp, _get_database_type())
        cfg_name = (
            "server_config.json"
            if exp.simulator_type == "HPC"
            else "config_server.json"
        )
        cfg_path = os.path.join(exp_folder, cfg_name)
        if not os.path.exists(cfg_path):
            flash(f"Configuration file not found: {cfg_name}", "error")
            return redirect(url_for("experiments.experiment_details", uid=uid))

        with open(cfg_path, "r") as f:
            config = json.load(f)

        config["emotion_annotation"] = emotion_enabled
        config["sentiment_annotation"] = sentiment_enabled
        config["opinion_dynamics_enabled"] = opinion_dynamics_enabled
        config["perspective_api"] = perspective_api if toxicity_enabled else None
        config["experiment_configuration_confirmed"] = True
        memory_config = config.get("memory")
        if not isinstance(memory_config, dict):
            memory_config = {}
        if memory_enabled is not None:
            memory_config["enabled"] = bool(memory_enabled)
        else:
            memory_config["enabled"] = bool(memory_config.get("enabled"))
        config["memory"] = memory_config

        with open(cfg_path, "w") as f:
            json.dump(config, f, indent=4)

        clients = Client.query.filter_by(id_exp=uid).all()
        for client in clients:
            population = Population.query.filter_by(id=client.population_id).first()
            if not population:
                continue
            pop_name = population.name
            pop_name_compact = population.name.replace(" ", "")
            client_config_candidates = [
                os.path.join(exp_folder, f"client_{client.name}-{pop_name}.json"),
                os.path.join(
                    exp_folder, f"client_{client.name}-{pop_name_compact}.json"
                ),
                os.path.join(exp_folder, f"{client.name}_config.json"),
            ]
            client_config_file = None
            for candidate in client_config_candidates:
                if os.path.exists(candidate):
                    client_config_file = candidate
                    break
            if not client_config_file:
                continue

            try:
                with open(client_config_file, "r") as f:
                    client_config = json.load(f)

                if exp.simulator_type == "HPC":
                    if not isinstance(client_config.get("simulation"), dict):
                        client_config["simulation"] = {}
                    client_config["simulation"]["enable_sentiment"] = sentiment_enabled
                    client_config["simulation"]["emotion_annotation"] = emotion_enabled
                    client_config["simulation"]["enable_toxicity"] = toxicity_enabled
                    client_config["simulation"]["perspective_api_key"] = (
                        perspective_api if toxicity_enabled else None
                    )

                    if not isinstance(client_config.get("opinion_dynamics"), dict):
                        client_config["opinion_dynamics"] = {}
                    client_config["opinion_dynamics"][
                        "enabled"
                    ] = opinion_dynamics_enabled
                else:
                    if not isinstance(client_config.get("simulation"), dict):
                        client_config["simulation"] = {}
                    if not isinstance(
                        client_config["simulation"].get("opinion_dynamics"), dict
                    ):
                        client_config["simulation"]["opinion_dynamics"] = {}
                    client_config["simulation"]["opinion_dynamics"][
                        "enabled"
                    ] = opinion_dynamics_enabled

                with open(client_config_file, "w") as f:
                    json.dump(client_config, f, indent=4)
            except Exception:
                current_app.logger.warning(
                    f"Failed to align client config: {client_config_file}",
                    exc_info=True,
                )

        db.session.commit()
        flash("Experiment configuration updated.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to update configuration: {str(exc)}", "error")

    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/update_experiment_topics/<int:uid>", methods=["POST"])
@login_required
def update_experiment_topics(uid):
    """Update experiment topics in admin DB and persisted server config."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=uid).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user_or_none()
    if not user_can_manage_experiment(admin_user, exp):
        flash("You do not have permission to update experiment topics.", "error")
        return redirect(url_for("experiments.experiment_details", uid=uid))

    raw_topics = (request.form.get("topics") or "").split(",")
    topics = []
    seen = set()
    for raw_topic in raw_topics:
        topic = str(raw_topic or "").strip()[:50]
        if not topic:
            continue
        key = topic.lower()
        if key in seen:
            continue
        seen.add(key)
        topics.append(topic)

    if not topics:
        flash("Please provide at least one simulation topic.", "warning")
        return redirect(url_for("experiments.experiment_details", uid=uid))

    try:
        db.session.query(Exp_Topic).filter_by(exp_id=uid).delete()
        for topic in topics:
            existing_topic = Topic_List.query.filter_by(name=topic).first()
            if existing_topic is None:
                existing_topic = Topic_List(name=topic)
                db.session.add(existing_topic)
                db.session.flush()
            db.session.add(Exp_Topic(exp_id=uid, topic_id=existing_topic.id))

        from y_web.src.system.path_utils import get_writable_path

        base_dir = get_writable_path()
        exp_folder = _get_experiment_folder(base_dir, exp, _get_database_type())
        cfg_name = (
            "server_config.json"
            if exp.simulator_type == "HPC"
            else "config_server.json"
        )
        cfg_path = os.path.join(exp_folder, cfg_name)
        if os.path.exists(cfg_path):
            with open(cfg_path, "r") as f:
                config = json.load(f)
            config["topics"] = topics
            with open(cfg_path, "w") as f:
                json.dump(config, f, indent=4)

        db.session.commit()
        flash("Experiment topics updated.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to update experiment topics: {str(exc)}", "error")

    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/reset_hpc_experiment/<int:uid>", methods=["POST"])
@login_required
def reset_hpc_experiment(uid):
    """Reset stopped HPC experiment state to initial conditions."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=uid).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))
    if exp.simulator_type != "HPC":
        flash("Reset is available only for HPC experiments.", "warning")
        return redirect(url_for("experiments.experiment_details", uid=uid))
    if exp.running == 1:
        flash("HPC reset is available only when the experiment is stopped.", "warning")
        return redirect(url_for("experiments.experiment_details", uid=uid))

    clients = Client.query.filter_by(id_exp=uid).all()
    has_started_once = _experiment_has_started_once(exp, clients=clients)
    if not has_started_once:
        flash(
            "HPC reset is available only for experiments that have been started at least once.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=uid))

    admin_user = _current_admin_user_or_none()
    if not user_can_manage_experiment(admin_user, exp):
        flash("You do not have permission to reset this experiment.", "error")
        return redirect(url_for("experiments.experiment_details", uid=uid))

    try:
        for client in clients:
            if client.status == 1 and client.pid:
                try:
                    stop_client_for_experiment(exp, client, pause=False)
                except Exception:
                    current_app.logger.warning(
                        f"Failed to stop HPC client {client.id} during reset.",
                        exc_info=True,
                    )
            client.status = 0
            client.pid = None

        restored_count = 0
        for client in clients:
            population = Population.query.filter_by(id=client.population_id).first()
            if restore_population_for_hpc_client(exp, client, population):
                restored_count += 1

        from y_web.src.system.path_utils import get_writable_path

        base_dir = get_writable_path()
        exp_folder = _get_experiment_folder(base_dir, exp, _get_database_type())

        for log_dir in [os.path.join(exp_folder, "logs"), exp_folder]:
            if not os.path.isdir(log_dir):
                continue
            for root, _, files in os.walk(log_dir):
                for filename in files:
                    if (
                        log_dir.endswith("logs")
                        or filename.endswith(".log")
                        or filename.endswith(".gz")
                        or filename.endswith(".jsonl")
                    ):
                        try:
                            os.remove(os.path.join(root, filename))
                        except OSError:
                            current_app.logger.warning(
                                f"Could not delete log file {os.path.join(root, filename)}"
                            )

        for db_filename in ("database_server.db", "simulation.db"):
            db_path = os.path.join(exp_folder, db_filename)
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except OSError:
                    current_app.logger.warning(
                        f"Could not delete db file during reset: {db_path}"
                    )

        for client in clients:
            expected_rounds = -1 if client.days == -1 else max(int(client.days), 0) * 24
            client_exec = Client_Execution.query.filter_by(client_id=client.id).first()
            if client_exec:
                client_exec.elapsed_time = 0
                client_exec.last_active_day = -1
                client_exec.last_active_hour = -1
                client_exec.expected_duration_rounds = expected_rounds
            else:
                db.session.add(
                    Client_Execution(
                        client_id=client.id,
                        elapsed_time=0,
                        last_active_day=-1,
                        last_active_hour=-1,
                        expected_duration_rounds=expected_rounds,
                    )
                )

        exp.running = 0
        exp.status = 0
        exp.exp_status = "stopped"

        exp_stats = Exp_stats.query.filter_by(exp_id=uid).first()
        if not exp_stats:
            exp_stats = Exp_stats(
                exp_id=uid, rounds=0, agents=0, posts=0, reactions=0, mentions=0
            )
            db.session.add(exp_stats)
        else:
            exp_stats.rounds = 0
            exp_stats.agents = 0
            exp_stats.posts = 0
            exp_stats.reactions = 0
            exp_stats.mentions = 0

        db.session.query(LogFileOffset).filter_by(exp_id=uid).delete()
        db.session.query(ServerLogMetrics).filter_by(exp_id=uid).delete()
        db.session.query(ClientLogMetrics).filter_by(exp_id=uid).delete()
        db.session.query(OpinionEvolutionCache).filter_by(exp_id=uid).delete()
        db.session.query(OpinionEvolutionSampledAgents).filter_by(exp_id=uid).delete()

        db.session.commit()
        flash(
            f"HPC experiment reset completed. Restored {restored_count} population backup file(s).",
            "success",
        )
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to reset HPC experiment: {str(exc)}", "error")

    return redirect(url_for("experiments.experiment_details", uid=uid))


@experiments.route("/admin/submit_experiment_logs/<int:exp_id>", methods=["POST"])
@login_required
def submit_experiment_logs(exp_id):
    """Submit experiment logs to telemetry server for troubleshooting."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path
    from y_web.src.telemetry import Telemetry

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

        from y_web.src.hpc.log_metrics import update_server_log_metrics
        from y_web.src.hpc.log_parser import has_server_log_files
        from y_web.src.system.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Construct path to _server.log
        # Use helper function to extract UID regardless of path separator
        uid = get_experiment_uid_from_db_name(experiment.db_name)
        if uid is None:
            return jsonify({"error": "Invalid experiment path format"}), 400

        exp_folder = os.path.join(BASE_DIR, "y_web", "experiments", uid)
        # For HPC experiments, logs are stored in /logs subfolder
        if experiment.simulator_type == "HPC":
            exp_folder = os.path.join(exp_folder, "logs")
        log_file = os.path.join(exp_folder, "_server.log")

        # Check if any log files exist (main or rotated)
        if not has_server_log_files(log_file):
            return jsonify(
                {"call_volume": {}, "mean_duration": {}, "error": "Log file not found"}
            )

        # Update metrics incrementally from log file
        try:
            # Pass is_hpc flag for HPC experiments to use correct log format
            is_hpc = experiment.simulator_type == "HPC"
            update_server_log_metrics(exp_id, log_file, is_hpc=is_hpc)
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

        from y_web.src.hpc.log_metrics import (
            update_client_log_metrics,
            update_server_log_metrics,
        )
        from y_web.src.hpc.log_parser import has_server_log_files
        from y_web.src.system.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Construct path to _server.log
        # Use helper function to extract UID regardless of path separator
        uid = get_experiment_uid_from_db_name(experiment.db_name)
        if uid is None:
            return jsonify({"error": "Invalid experiment path format"}), 400

        exp_folder = os.path.join(BASE_DIR, "y_web", "experiments", uid)
        # For HPC experiments, logs are stored in /logs subfolder
        if experiment.simulator_type == "HPC":
            exp_folder = os.path.join(exp_folder, "logs")
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
            # Pass is_hpc flag for HPC experiments to use correct log format
            is_hpc = experiment.simulator_type == "HPC"
            update_server_log_metrics(exp_id, log_file, is_hpc=is_hpc)
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
                # Filter out infinite clients (-1) and get max from finite ones
                finite_expected = [
                    ce.expected_duration_rounds
                    for ce in client_executions
                    if ce.expected_duration_rounds > 0
                ]
                max_expected_rounds = max(finite_expected) if finite_expected else 0

                # Calculate remaining rounds for each client
                for ce in client_executions:
                    # Handle None values for last_active_day and last_active_hour
                    last_day = (
                        ce.last_active_day if ce.last_active_day is not None else -1
                    )
                    last_hour = (
                        ce.last_active_hour if ce.last_active_hour is not None else -1
                    )

                    # Calculate current round
                    # Note: days and hours are 0-indexed, but rounds are 1-indexed
                    # (day 0, hour 0 = round 1), so we add 1
                    if last_day >= 0 and last_hour >= 0:
                        current_round = last_day * 24 + last_hour + 1
                    else:
                        current_round = 0

                    # Calculate remaining rounds (handle infinite clients)
                    if ce.expected_duration_rounds > 0:
                        remaining = ce.expected_duration_rounds - current_round
                    else:
                        remaining = -1  # Infinite client

                    client_progress[ce.client_id] = {
                        "expected_rounds": ce.expected_duration_rounds,
                        "current_round": current_round,
                        "remaining_rounds": remaining if remaining >= 0 else -1,
                    }
                    if remaining > 0:  # Only consider finite positive remaining
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
                    # Pass is_hpc flag for HPC experiments to use correct log format
                    is_hpc = experiment.simulator_type == "HPC"
                    update_client_log_metrics(
                        exp_id, client.id, client_log_file, is_hpc=is_hpc
                    )
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

        result_data = {
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

        # Log data for debugging HPC plots
        if experiment.simulator_type == "HPC":
            result_data["debug_info"] = {
                "daily_compute_count": len(result_data["daily_compute"]),
                "daily_compute_keys": list(result_data["daily_compute"].keys()),
                "daily_compute_sample": {
                    k: result_data["daily_compute"][k]
                    for k in list(result_data["daily_compute"].keys())[:3]
                },
                "hourly_compute_count": len(result_data["hourly_compute"]),
                "hourly_compute_keys": list(result_data["hourly_compute"].keys())[:5],
                "daily_simulation_count": len(result_data["daily_simulation"]),
                "hourly_simulation_count": len(result_data["hourly_simulation"]),
                "log_file_path": log_file,
                "log_file_exists": os.path.exists(log_file),
            }

        return jsonify(result_data)

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

        from y_web.src.hpc.log_metrics import update_client_log_metrics
        from y_web.src.system.path_utils import get_writable_path

        BASE_DIR = get_writable_path()

        # Construct path to client log file
        # Use helper function to extract UID regardless of path separator
        uid = get_experiment_uid_from_db_name(experiment.db_name)
        if uid is None:
            return jsonify({"error": "Invalid experiment path format"}), 400

        exp_folder = os.path.join(BASE_DIR, "y_web", "experiments", uid)
        # For HPC experiments, logs are stored in /logs subfolder
        if experiment.simulator_type == "HPC":
            exp_folder = os.path.join(exp_folder, "logs")

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
            # Pass is_hpc flag for HPC experiments to use correct log format
            is_hpc = experiment.simulator_type == "HPC"
            update_client_log_metrics(
                experiment.idexp, client_id, log_file, is_hpc=is_hpc
            )
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


@experiments.route("/admin/miscellanea/", methods=["GET"])
@login_required
def miscellanea():
    """
    Display miscellaneous settings page (admin only).

    Returns:
        Rendered miscellaneous settings template
    """
    from y_web.src.llm.vllm_manager import get_llm_models

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
        from y_web.src.simulation.watchdog import get_watchdog_status

        status = get_watchdog_status()
        watchdog_interval = status.get("run_interval_minutes", 15)
    except ImportError:
        # process_watchdog module not available
        pass
    except (KeyError, TypeError, AttributeError):
        # Status returned unexpected format
        pass

    # Get LLM backend status for the LLM Management tab
    llm_backend = llm_backend_status()

    # Get installed LLM models
    models = []
    try:
        models = get_llm_models()
    except Exception:
        pass

    # Get active Ollama pulls
    ollama_pulls = Ollama_Pull.query.all()
    ollama_pulls = [(pull.model_name, float(pull.status)) for pull in ollama_pulls]

    return render_template(
        "admin/miscellanea.html",
        telemetry_enabled=telemetry_enabled,
        watchdog_interval=watchdog_interval,
        llm_backend=llm_backend,
        models=models,
        active_pulls=ollama_pulls,
        len=len,
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
