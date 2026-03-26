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
from ._data import experiment_details
from ._helpers import *  # noqa: F401,F403
from ._helpers import (
    _current_admin_user_or_none,
    _experiment_configuration_update_required,
)


def _external_repo_availability():
    """Detect which simulator repositories are available under external/."""
    repo_root = pathlib.Path(__file__).resolve().parents[5]
    external_dir = repo_root / "external"

    def present(name):
        path = external_dir / name
        return path.exists() and path.is_dir()

    microblogging = present("YServer") and present("YClient")
    hpc = present("YSimulator")
    forum = present("YServerReddit") and present("YClientReddit")

    return {
        "microblogging": microblogging,
        "hpc": hpc,
        "forum": forum,
    }
from ._notifications import _enqueue_user_notification, _resolve_bulk_experiment_ids
from ._schedule import _get_clients_to_start


@experiments.route("/admin/experiments")
@login_required
def settings():
    """
    Display experiments settings and management page.

    Shows list of experiments, users, and database configuration.
    """
    # Get current user
    user = Admin_users.query.filter_by(username=current_user.username).first()

    # Filter experiments based on role + visibility grants
    if user.role in ("admin", "researcher"):
        visible_query = get_visible_experiment_query(user)
        experiments = visible_query.limit(5).all()
        all_experiments = visible_query.all()
        active_experiments = visible_query.filter_by(status=1).all()
    else:
        # Regular users should not access this page
        flash("Access denied. Please use the experiment feed.")
        return redirect(url_for("auth.login"))

    users = Admin_users.query.all()

    # Check and update status for stopped experiments that are actually completed
    # Get all stopped experiments
    stopped_experiments = Exps.query.filter_by(exp_status="stopped").all()
    for exp in stopped_experiments:
        # Use existing helper function to check if all clients completed
        all_clients_completed, _ = _get_clients_to_start(exp)
        if all_clients_completed:
            # Update status to completed
            exp.exp_status = "completed"
            db.session.commit()

    # Check which experiments have infinite clients
    exp_has_infinite = {}
    for exp in experiments:
        clients = Client.query.filter_by(id_exp=exp.idexp).all()
        exp_has_infinite[exp.idexp] = any(client.days == -1 for client in clients)

    dbtype = current_app.config["SQLALCHEMY_DATABASE_URI"].split(":")[0]

    # Get suggested port for new experiment
    suggested_port = get_suggested_port()

    # Get unique experiment groups
    exp_groups = (
        db.session.query(Exps.exp_group)
        .filter(Exps.exp_group != "")
        .filter(Exps.exp_group.isnot(None))
        .distinct()
        .all()
    )
    exp_groups = [group[0] for group in exp_groups]  # Extract from tuples
    repo_availability = _external_repo_availability()

    return render_template(
        "admin/settings.html",
        experiments=experiments,
        all_experiments=all_experiments,
        users=users,
        dbtype=dbtype,
        suggested_port=suggested_port,
        enable_notebook=current_app.config.get("ENABLE_NOTEBOOK", False),
        exp_has_infinite=exp_has_infinite,
        exp_groups=exp_groups,
        active_experiments=active_experiments,
        repo_availability=repo_availability,
    )


@experiments.route("/admin/visibility_settings", methods=["GET"])
@login_required
def visibility_settings():
    """Configure experiment/group visibility for researcher users."""
    check_privileges(current_user.username)
    user = _current_admin_user_or_none()
    role = (user.role or "").strip().lower() if user else ""
    is_admin = role == "admin"
    is_researcher = role == "researcher"
    if not user or (not is_admin and not is_researcher):
        flash("Access denied.", "error")
        return redirect(url_for("admin.dashboard"))

    if is_admin:
        manageable_experiments = Exps.query.order_by(Exps.exp_name.asc()).all()
    else:
        manageable_experiments = (
            Exps.query.filter_by(owner=user.username)
            .order_by(Exps.exp_name.asc())
            .all()
        )

    researcher_users = (
        Admin_users.query.filter_by(role="researcher")
        .order_by(Admin_users.username.asc())
        .all()
    )

    group_names = sorted(
        {
            exp.exp_group.strip()
            for exp in manageable_experiments
            if exp.exp_group and exp.exp_group.strip()
        }
    )

    shared_rows = (
        db.session.query(User_Experiment, Admin_users, Exps)
        .join(Admin_users, Admin_users.id == User_Experiment.user_id)
        .join(Exps, Exps.idexp == User_Experiment.exp_id)
        .filter(Admin_users.role == "researcher")
    )
    if not is_admin:
        shared_rows = shared_rows.filter(Exps.owner == user.username)
    shared_rows = shared_rows.order_by(
        Exps.exp_name.asc(), Admin_users.username.asc()
    ).all()
    shared_visibility_rows = [
        {
            "exp_id": row[2].idexp,
            "experiment_name": row[2].exp_name,
            "experiment_url": url_for(
                "experiments.experiment_details", uid=row[2].idexp
            ),
            "group_name": row[2].exp_group if row[2].exp_group else "-",
            "researcher_id": row[1].id,
            "researcher_name": row[1].username,
        }
        for row in shared_rows
    ]

    return render_template(
        "admin/visibility_settings.html",
        manageable_experiments=manageable_experiments,
        researcher_users=researcher_users,
        group_names=group_names,
        shared_rows=shared_rows,
        shared_visibility_rows=shared_visibility_rows,
        current_admin_user=user,
    )


def _get_selected_researcher_ids():
    """Parse and validate selected researcher IDs from form payload."""
    selected_ids = []
    for uid in request.form.getlist("researcher_ids"):
        try:
            selected_ids.append(int(uid))
        except (TypeError, ValueError):
            continue
    if not selected_ids:
        return []

    valid_users = (
        Admin_users.query.filter(Admin_users.id.in_(selected_ids))
        .filter(Admin_users.role == "researcher")
        .all()
    )
    return [u.id for u in valid_users]


@experiments.route("/admin/visibility_settings/experiment", methods=["POST"])
@login_required
def visibility_settings_add_experiment():
    """Grant or revoke visibility/management for a single experiment to selected researchers."""
    check_privileges(current_user.username)
    user = _current_admin_user_or_none()
    if not user:
        flash("Invalid user session.", "error")
        return redirect(url_for("experiments.visibility_settings"))
    is_admin = (user.role or "").strip().lower() == "admin"

    exp_id = request.form.get("exp_id", type=int)
    experiment = Exps.query.filter_by(idexp=exp_id).first()
    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.visibility_settings"))

    if not is_admin and experiment.owner != user.username:
        flash("You can only share experiments you own.", "error")
        return redirect(url_for("experiments.visibility_settings"))

    action = (request.form.get("action") or "grant").strip().lower()
    if action not in ("grant", "revoke"):
        action = "grant"

    researcher_ids = _get_selected_researcher_ids()
    if not researcher_ids:
        flash("Select at least one researcher user.", "warning")
        return redirect(url_for("experiments.visibility_settings"))

    changed = 0
    if action == "grant":
        newly_granted_user_ids = []
        for researcher_id in researcher_ids:
            existing = User_Experiment.query.filter_by(
                user_id=researcher_id, exp_id=experiment.idexp
            ).first()
            if existing:
                continue
            db.session.add(
                User_Experiment(user_id=researcher_id, exp_id=experiment.idexp)
            )
            changed += 1
            newly_granted_user_ids.append(researcher_id)

        for researcher_id in newly_granted_user_ids:
            _enqueue_user_notification(
                researcher_id,
                title=f"Experiment shared: {experiment.exp_name}",
                message=f"{user.username} granted you visibility to experiment '{experiment.exp_name}'.",
                status="ready",
                related_exp_ids=[experiment.idexp],
            )
        success_msg = f"Granted access to {changed} researcher(s) for experiment '{experiment.exp_name}'."
    else:
        deleted_count = (
            User_Experiment.query.filter(User_Experiment.exp_id == experiment.idexp)
            .filter(User_Experiment.user_id.in_(researcher_ids))
            .delete(synchronize_session=False)
        )
        changed = int(deleted_count or 0)
        success_msg = f"Revoked access for {changed} researcher(s) from experiment '{experiment.exp_name}'."

    db.session.commit()
    flash(success_msg, "success")
    return redirect(url_for("experiments.visibility_settings"))


@experiments.route("/admin/visibility_settings/group", methods=["POST"])
@login_required
def visibility_settings_add_group():
    """Grant or revoke visibility/management for all experiments in a group to selected researchers."""
    check_privileges(current_user.username)
    user = _current_admin_user_or_none()
    if not user:
        flash("Invalid user session.", "error")
        return redirect(url_for("experiments.visibility_settings"))
    is_admin = (user.role or "").strip().lower() == "admin"

    group_name = (request.form.get("group_name") or "").strip()
    if not group_name:
        flash("Select a valid group.", "warning")
        return redirect(url_for("experiments.visibility_settings"))

    experiments_query = Exps.query.filter(Exps.exp_group == group_name)
    if not is_admin:
        experiments_query = experiments_query.filter(Exps.owner == user.username)
    group_experiments = experiments_query.all()

    if not group_experiments:
        flash("No experiments found in the selected group.", "warning")
        return redirect(url_for("experiments.visibility_settings"))

    action = (request.form.get("action") or "grant").strip().lower()
    if action not in ("grant", "revoke"):
        action = "grant"

    researcher_ids = _get_selected_researcher_ids()
    if not researcher_ids:
        flash("Select at least one researcher user.", "warning")
        return redirect(url_for("experiments.visibility_settings"))

    changed = 0
    if action == "grant":
        newly_granted_group_users = set()
        for researcher_id in researcher_ids:
            user_got_new_visibility = False
            for exp in group_experiments:
                existing = User_Experiment.query.filter_by(
                    user_id=researcher_id, exp_id=exp.idexp
                ).first()
                if existing:
                    continue
                db.session.add(User_Experiment(user_id=researcher_id, exp_id=exp.idexp))
                changed += 1
                user_got_new_visibility = True
            if user_got_new_visibility:
                newly_granted_group_users.add(researcher_id)

        for researcher_id in newly_granted_group_users:
            _enqueue_user_notification(
                researcher_id,
                title=f"Experiment group shared: {group_name}",
                message=f"{user.username} granted you visibility to group '{group_name}'.",
                status="ready",
            )
        success_msg = f"Granted group '{group_name}' visibility to selected researchers ({changed} new assignment(s))."
    else:
        group_exp_ids = [exp.idexp for exp in group_experiments]
        deleted_count = (
            User_Experiment.query.filter(User_Experiment.exp_id.in_(group_exp_ids))
            .filter(User_Experiment.user_id.in_(researcher_ids))
            .delete(synchronize_session=False)
        )
        changed = int(deleted_count or 0)
        success_msg = f"Revoked group '{group_name}' visibility from selected researchers ({changed} assignment(s) removed)."

    db.session.commit()
    flash(success_msg, "success")
    return redirect(url_for("experiments.visibility_settings"))


@experiments.route("/admin/visibility_settings/revoke_assignment", methods=["POST"])
@login_required
def visibility_settings_revoke_assignment():
    """Revoke visibility for one specific experiment/researcher assignment."""
    check_privileges(current_user.username)
    user = _current_admin_user_or_none()
    if not user:
        flash("Invalid user session.", "error")
        return redirect(url_for("experiments.visibility_settings"))
    is_admin = (user.role or "").strip().lower() == "admin"

    exp_id = request.form.get("exp_id", type=int)
    researcher_id = request.form.get("researcher_id", type=int)
    if not exp_id or not researcher_id:
        flash("Invalid revoke request.", "error")
        return redirect(url_for("experiments.visibility_settings"))

    experiment = Exps.query.filter_by(idexp=exp_id).first()
    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.visibility_settings"))
    if not is_admin and experiment.owner != user.username:
        flash("You can only revoke visibility for experiments you own.", "error")
        return redirect(url_for("experiments.visibility_settings"))

    deleted_count = User_Experiment.query.filter_by(
        user_id=researcher_id, exp_id=exp_id
    ).delete(synchronize_session=False)
    db.session.commit()
    if deleted_count:
        flash("Visibility assignment revoked.", "success")
    else:
        flash("No matching visibility assignment found.", "warning")
    return redirect(url_for("experiments.visibility_settings"))


@experiments.route("/admin/join_simulation")
@login_required
def join_simulation():
    """
    Display menu of active experiments for user to join.

    If only one experiment is active, redirect directly.
    If multiple experiments are active, show selection menu.
    """
    admin_user = _current_admin_user_or_none()
    if not admin_user:
        flash("Unable to resolve current user.")
        return redirect(url_for("experiments.settings"))

    # Get visible active experiments
    active_exps = get_visible_experiment_query(admin_user).filter_by(status=1).all()

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

    admin_user = _current_admin_user_or_none()
    if not user_can_view_experiment(admin_user, exp):
        flash("You are not allowed to access this experiment.", "error")
        return redirect("/admin/experiments")

    # Get user id - need to check in the experiment database
    from y_web.src.experiment.context import register_experiment_database

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

    admin_user = _current_admin_user_or_none()
    if not user_can_view_experiment(admin_user, exp):
        flash("You are not allowed to access this experiment.", "error")
        return redirect(url_for("experiments.settings"))

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
        from y_web.src.experiment.context import register_experiment_database

        register_experiment_database(current_app, exp_id, exp.db_name)

        # Ensure user exists in the experiment database
        # For HPC experiments with SQLite: database is created by server on first startup
        # We skip user registration if database doesn't exist yet
        # We need to switch to the correct bind temporarily
        bind_key = f"db_exp_{exp_id}"

        # For HPC experiments with SQLite, check if database exists
        skip_user_registration = False
        if exp.simulator_type == "HPC":
            # Check database type
            if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
                # Check if the SQLite database file exists
                from y_web.src.system.path_utils import get_writable_path

                db_path = get_writable_path(os.path.join("y_web", exp.db_name))
                if not os.path.exists(db_path):
                    skip_user_registration = True
                    current_app.logger.info(
                        f"HPC experiment database doesn't exist yet for experiment {exp_id}. "
                        f"User will be added when server creates database on first startup."
                    )

        if not skip_user_registration:
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
                        # For HPC experiments, we need to use UUID strings as IDs
                        # Standard experiments use integer IDs with auto-increment
                        if exp.simulator_type == "HPC":
                            # Generate a UUID string for HPC user ID
                            user_id = str(uuid.uuid4())
                            current_app.logger.info(
                                f"Assigning HPC user UUID {user_id} to {current_user.username} for experiment {exp_id}"
                            )
                        else:
                            # For Standard experiments, use the admin user's ID (auto-increment behavior)
                            user_id = current_user.id

                        try:
                            # Set recsys_type based on experiment type
                            # HPC experiments use rchrono, Standard use default
                            content_recsys = (
                                "rchrono" if exp.simulator_type == "HPC" else "default"
                            )

                            new_user = User_mgmt(
                                id=user_id,
                                email=current_user.email,
                                username=current_user.username,
                                password=current_user.password,
                                user_type="user",
                                leaning="neutral",
                                age=0,
                                recsys_type=content_recsys,
                                language="en",
                                frecsys_type="default",
                                round_actions=1,
                                toxicity="no",
                                joined_on=int(time.time()),
                            )
                            db.session.add(new_user)
                            db.session.commit()
                        except Exception as e:
                            db.session.rollback()
                            # If IntegrityError due to duplicate ID, log and re-raise
                            current_app.logger.error(
                                f"Error adding user {current_user.username} to experiment {exp_id}: {e}"
                            )
                            flash(
                                f"Error activating experiment: {str(e)}. Please try again."
                            )
                            raise
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

    # Reload user session from admin database (not experiment database)
    # Use Admin_users which is in the main database
    admin_user = Admin_users.query.filter_by(username=uname).first()
    if admin_user:
        login_user(admin_user, remember=True, force=True)

    return redirect("/admin/dashboard")


@experiments.route("/admin/upload_experiment", methods=["POST"])
@login_required
def upload_experiment():
    """Upload experiment."""
    check_privileges(current_user.username)

    experiment = request.files["experiment"]
    # Get experiment name from form, fallback to name from config if not provided
    exp_name_override = request.form.get("exp_name", "").strip()
    exp_group = request.form.get("exp_group", "").strip()  # Get experiment group
    uid = str(uuid.uuid4()).replace("-", "_")

    from y_web.src.system.path_utils import get_writable_path

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

        # Detect simulator type by checking which config file exists
        # Standard experiments use config_server.json, HPC use server_config.json
        config_path_standard = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json"
        config_path_hpc = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}server_config.json"

        is_hpc_experiment = False
        if os.path.exists(config_path_hpc):
            config_path = config_path_hpc
            is_hpc_experiment = True
        elif os.path.exists(config_path_standard):
            config_path = config_path_standard
            is_hpc_experiment = False
        else:
            raise FileNotFoundError(
                "No server configuration file found (config_server.json or server_config.json)"
            )

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
                    stmt = text("""
                        INSERT INTO user_mgmt (username, email, password, user_type, leaning, age,
                                               language, owner, joined_on, frecsys_type,
                                               round_actions, toxicity, is_page, daily_activity_level)
                        VALUES (:username, :email, :password, :user_type, :leaning, :age,
                                :language, :owner, :joined_on, :frecsys_type,
                                :round_actions, :toxicity, :is_page, :daily_activity_level)
                        """)

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

        from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

        if db_type == "sqlite":
            ensure_experiment_schema_for_uri(f"sqlite:///{db_uri}")
        elif db_type == "postgresql":
            ensure_experiment_schema_for_uri(db_uri)

        # Update config_server.json with new port, name, database_uri, and data_path
        experiment_config["name"] = name
        experiment_config["port"] = suggested_port
        experiment_config["database_uri"] = db_uri
        # Add data_path so YServer knows where to write logs (e.g., _server.log)
        exp_data_path = os.path.join(BASE_DIR, "y_web", "experiments", uid) + os.sep
        experiment_config["data_path"] = exp_data_path

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
            simulator_type="HPC" if is_hpc_experiment else "Standard",
            exp_group=exp_group,
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
    # Also exclude server_config.json for HPC experiments
    populations = [
        f
        for f in os.listdir(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}")
        if f.endswith(".json")
        and not f.startswith("client")
        and f != "config_server.json"
        and f != "server_config.json"  # Exclude HPC server config
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

        # Get client configuration file for this population
        # For Standard: client_*.json files containing population name
        # For HPC: client_{name}-{population}.json files
        client = [
            f
            for f in os.listdir(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"
            )
            if f.endswith(".json") and f.startswith("client") and original_name in f
        ]

        # Handle missing client configs
        if len(client) == 0:
            if not is_hpc_experiment:
                # Standard experiments REQUIRE client config
                flash("No client file found for the population")
                shutil.rmtree(
                    f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}",
                    ignore_errors=True,
                )
                return redirect(request.referrer)
            else:
                # HPC experiments: Auto-create default client if config missing
                # This ensures Client records exist for scheduler tracking
                print(
                    f"No client config found for HPC population {original_name}, creating default client"
                )

                # Create default Client record for HPC
                default_client_name = f"client_{original_name}"
                cl = Client(
                    id_exp=exp.idexp,
                    population_id=population.id,
                    status=0,
                    name=default_client_name,
                    descr=f"Auto-created client for {original_name}",
                    days=7,  # Default 7 days
                    percentage_new_agents_iteration=0,
                    percentage_removed_agents_iteration=0,
                    max_length_thread_reading=10,
                    reading_from_follower_ratio=0.5,
                    probability_of_daily_follow=0.1,
                    attention_window=24,
                    visibility_rounds=36,
                    post=0.3,
                    share=0.2,
                    image=0.1,
                    comment=0.2,
                    read=0.8,
                    news=0.1,
                    search=0.1,
                    vote=0.1,
                    llm="",
                    llm_api_key="",
                    llm_max_tokens=100,
                    llm_temperature=0.7,
                    llm_v_agent=0,
                    llm_v="",
                    llm_v_api_key="",
                    llm_v_max_tokens=100,
                    llm_v_temperature=0.7,
                )
                db.session.add(cl)
                db.session.commit()

                # Create Client_Execution for progress tracking
                expected_rounds = cl.days * 24  # HPC uses 24 hourly slots
                client_exec = Client_Execution(
                    client_id=cl.id,
                    elapsed_time=0,
                    expected_duration_rounds=expected_rounds,
                    last_active_hour=-1,
                    last_active_day=-1,
                )
                db.session.add(client_exec)
                db.session.commit()

                print(
                    f"Created default HPC client '{default_client_name}' for population {original_name}"
                )
                continue  # Skip to next population

        client_config = json.load(
            open(
                f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}{client[0]}"
            )
        )

        # Parse client configuration based on experiment type
        if is_hpc_experiment:
            # HPC client config has simpler structure
            # Extract basic information
            client_name = client_config.get("name", "hpc_client")
            client_days = client_config.get("simulation", {}).get("days", 7)

            # Create minimal Client record for HPC
            # Many fields will use defaults since HPC config is simpler
            cl = Client(
                id_exp=exp.idexp,
                population_id=population.id,
                status=0,
                name=client_name,
                descr="",
                days=client_days,
                percentage_new_agents_iteration=0,
                percentage_removed_agents_iteration=0,
                max_length_thread_reading=10,
                reading_from_follower_ratio=0.5,
                probability_of_daily_follow=0.1,
                attention_window=24,
                visibility_rounds=36,
                post=0.3,
                share=0.2,
                image=0.1,
                comment=0.2,
                read=0.8,
                news=0.1,
                search=0.1,
                vote=0.1,
                llm="",
                llm_api_key="",
                llm_max_tokens=100,
                llm_temperature=0.7,
                llm_v_agent=0,
                llm_v="",
                llm_v_api_key="",
                llm_v_max_tokens=100,
                llm_v_temperature=0.7,
            )
        else:
            # Standard client config - use existing parsing logic
            cl = Client(
                id_exp=exp.idexp,
                population_id=population.id,
                status=0,
                name=client_config["simulation"]["name"],
                descr="",
                days=client_config["simulation"]["days"],
                percentage_new_agents_iteration=client_config["simulation"][
                    "percentage_new_agents_iteration"
                ],
                percentage_removed_agents_iteration=client_config["simulation"][
                    "percentage_removed_agents_iteration"
                ],
                max_length_thread_reading=client_config["agents"][
                    "max_length_thread_reading"
                ],
                reading_from_follower_ratio=client_config["agents"][
                    "reading_from_follower_ratio"
                ],
                probability_of_daily_follow=client_config["agents"][
                    "probability_of_daily_follow"
                ],
                attention_window=client_config["agents"]["attention_window"],
                visibility_rounds=client_config["posts"]["visibility_rounds"],
                post=client_config["simulation"]["actions_likelihood"]["post"],
                share=client_config["simulation"]["actions_likelihood"]["share"],
                image=client_config["simulation"]["actions_likelihood"]["image"],
                comment=client_config["simulation"]["actions_likelihood"]["comment"],
                read=client_config["simulation"]["actions_likelihood"]["read"],
                news=client_config["simulation"]["actions_likelihood"]["news"],
                search=client_config["simulation"]["actions_likelihood"]["search"],
                vote=client_config["simulation"]["actions_likelihood"]["cast"],
                llm=client_config["servers"]["llm"],
                llm_api_key=client_config["servers"]["llm_api_key"],
                llm_max_tokens=client_config["servers"]["llm_max_tokens"],
                llm_temperature=client_config["servers"]["llm_temperature"],
                llm_v_agent=client_config["agents"]["llm_v_agent"],
                llm_v=client_config["servers"]["llm_v"],
                llm_v_api_key=client_config["servers"]["llm_v_api_key"],
                llm_v_max_tokens=client_config["servers"]["llm_v_max_tokens"],
                llm_v_temperature=client_config["servers"]["llm_v_temperature"],
            )
        db.session.add(cl)
        db.session.commit()

        # For infinite clients (days = -1), set expected_duration_rounds to -1
        # For HPC, slots default to 24 (one per hour)
        if is_hpc_experiment:
            slots = 24  # HPC uses hourly slots
        else:
            slots = client_config.get("simulation", {}).get("slots", 24)

        expected_rounds = -1 if cl.days == -1 else cl.days * slots
        client_exec = Client_Execution(
            client_id=cl.id,
            last_active_hour=-1,
            last_active_day=-1,
            expected_duration_rounds=expected_rounds,
        )
        db.session.add(client_exec)
        db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/upload_database", methods=["POST"])
@login_required
def upload_database():
    """Upload database."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

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
            simulator_type="Standard",  # Default to Standard
            exp_group="",  # Default empty group for legacy upload_database route
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


def generate_standard_config(
    platform_type,
    exp_name,
    host,
    port,
    perspective_api,
    sentiment_annotation,
    emotion_annotation,
    db_uri,
    topics,
    data_path,
    opinion_dynamics_enabled=None,
    is_remote=False,
    opinions_enabled=None,
):
    """Generate config file for Standard simulator type."""
    if opinion_dynamics_enabled is None:
        opinion_dynamics_enabled = bool(opinions_enabled)

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
        "opinion_dynamics_enabled": opinion_dynamics_enabled,
        "database_uri": db_uri,
        "topics": [t.strip() for t in topics if t.strip()],
        "data_path": data_path,
        "is_remote": is_remote,
        "experiment_configuration_confirmed": False,
        "memory": {"enabled": False},
    }

    return config


def generate_hpc_config(
    exp_name,
    platform_type,
    db_type,
    db_uri,
    redis_enabled,
    redis_host,
    redis_port,
    redis_password,
    redis_sliding_window_days,
    perspective_api,
    sentiment_annotation,
    emotion_annotation,
    topics,
    data_path,
    opinion_dynamics_enabled=None,
    db_config_dict=None,
    is_remote=False,
    opinions_enabled=None,
):
    """Generate config file for HPC simulator type."""
    if opinion_dynamics_enabled is None:
        opinion_dynamics_enabled = bool(opinions_enabled)

    # Build database configuration section
    database_config = {
        "type": db_type,
    }

    if db_type == "sqlite":
        database_config["sqlite"] = {"filename": "simulation.db"}
    elif db_type == "postgresql":
        if db_config_dict:
            database_config["postgresql"] = db_config_dict
        else:
            # Fallback defaults
            database_config["postgresql"] = {
                "host": "localhost",
                "port": 5432,
                "database": "ysimulator",
                "username": "postgres",
                "password": "password",
            }

    config = {
        "server_name": exp_name,
        "namespace": exp_name,
        "address": "auto",
        "port": None,
        "database": database_config,
        "min_to_start": 1,
        "timeout_seconds": 180,
        "redis": {
            "enabled": redis_enabled,
            "host": redis_host,
            "port": redis_port,
            "db": 0,
            "password": redis_password,
            "sliding_window_days": redis_sliding_window_days,
        },
        "posts": {"visibility_rounds": 36},
        "experiment_configuration_confirmed": False,
        # Server-side fallback. Client-specific recommendation limits are set
        # in each HPC client config at client creation time.
        "recommendations": {"default_limit": 5},
        "simulation": {
            "agent_archetypes": {
                "enabled": True,
                "distribution": {
                    "validator": 0.33,
                    "broadcaster": 0.33,
                    "explorer": 0.34,
                },
                "transitions": {
                    "validator": {
                        "validator": 0.85,
                        "broadcaster": 0.1,
                        "explorer": 0.05,
                    },
                    "broadcaster": {
                        "validator": 0.1,
                        "broadcaster": 0.8,
                        "explorer": 0.1,
                    },
                    "explorer": {
                        "validator": 0.05,
                        "broadcaster": 0.1,
                        "explorer": 0.85,
                    },
                },
            }
        },
        "logging": {
            "enable_server_log": True,
            "enable_actor_log": True,
            "enable_request_log": True,
            "enable_console_log": True,
        },
        "platform_type": platform_type,
        "perspective_api": perspective_api,
        "sentiment_annotation": sentiment_annotation,
        "emotion_annotation": emotion_annotation,
        "opinion_dynamics_enabled": opinion_dynamics_enabled,
        "database_uri": db_uri,
        "topics": [t.strip() for t in topics if t.strip()],
        "data_path": data_path,
        "is_remote": is_remote,
    }

    return config


@experiments.route("/admin/create_experiment", methods=["POST", "GET"])
@login_required
def create_experiment():
    """Create experiment."""
    check_privileges(current_user.username)

    exp_name = request.form.get("exp_name")
    exp_descr = request.form.get("exp_descr")
    platform_type = request.form.get("platform_type")
    simulator_type = request.form.get(
        "simulator_type", "Standard"
    )  # Default to Standard
    exp_group = request.form.get("exp_group", "").strip()  # Get experiment group
    repo_availability = _external_repo_availability()

    if platform_type == "forum" and not repo_availability["forum"]:
        flash("Forum experiments are unavailable because YServerReddit and YClientReddit are not both present.", "error")
        return redirect(url_for("experiments.settings"))

    if platform_type == "microblogging":
        if simulator_type == "HPC":
            if not repo_availability["hpc"]:
                if repo_availability["microblogging"]:
                    simulator_type = "Standard"
                else:
                    flash("HPC microblogging experiments are unavailable because YSimulator is not present.", "error")
                    return redirect(url_for("experiments.settings"))
        else:
            if not repo_availability["microblogging"]:
                if repo_availability["hpc"]:
                    simulator_type = "HPC"
                else:
                    flash("Microblogging experiments are unavailable because neither YServer/YClient nor YSimulator is present.", "error")
                    return redirect(url_for("experiments.settings"))

    if platform_type == "forum":
        simulator_type = "Standard"
    elif simulator_type != "HPC":
        simulator_type = "Standard"

    # Remote experiment configuration
    is_remote = 1 if request.form.get("is_remote") == "true" else 0

    # Validate remote configuration if remote experiment is selected
    if is_remote:
        # For remote experiments, use the provided host and port
        host = request.form.get("remote_host", "").strip()
        if not host:
            flash("Remote host address is required for remote experiments.")
            return redirect(url_for("experiments.settings"))

        # Basic validation for hostname/IP format
        # Allow: IP addresses (IPv4), domain names, and localhost
        # This is a basic check - actual connectivity validation happens at runtime
        import re

        # Pattern allows: alphanumeric, dots, hyphens, and colons (for IPv6)
        if not re.match(r"^[a-zA-Z0-9\.\-\:]+$", host):
            flash("Invalid remote host format. Use IP address or domain name.")
            return redirect(url_for("experiments.settings"))

        # Validate and parse remote_port
        remote_port_str = request.form.get("remote_port", "").strip()
        if not remote_port_str:
            flash("Remote port is required for remote experiments.")
            return redirect(url_for("experiments.settings"))

        try:
            port = int(remote_port_str)
            # Validate port range
            if not (1 <= port <= 65535):
                flash("Invalid remote port. Port must be between 1 and 65535.")
                return redirect(url_for("experiments.settings"))
        except ValueError:
            flash("Invalid remote port. Please enter a valid number.")
            return redirect(url_for("experiments.settings"))
    else:
        # For local experiments, use default local settings
        host = "127.0.0.1"
        # Use suggested port (first available in range 5000-6000)
        port = get_suggested_port()

    # Redis configuration parameters for HPC simulator
    redis_enabled = request.form.get("redis_enabled") == "true"
    redis_host = request.form.get("redis_host", "localhost")
    redis_port = (
        int(request.form.get("redis_port", "6379"))
        if request.form.get("redis_port")
        else 6379
    )
    redis_password = (
        request.form.get("redis_password")
        if request.form.get("redis_password")
        else None
    )
    redis_sliding_window_days = (
        int(request.form.get("redis_sliding_window_days", "2"))
        if request.form.get("redis_sliding_window_days")
        else 2
    )

    # Use current logged-in user as owner
    owner = current_user.username

    # Get LLM agents setting (convert to integer for database compatibility)
    llm_agents_enabled = 1 if request.form.get("llm_agents_enabled") == "true" else 0
    opinion_dynamics_enabled = request.form.get("opinion_annotation") == "true"

    # Get annotation settings
    toxicity_annotation = request.form.get("toxicity_annotation") == "true"
    perspective_api = (
        request.form.get("perspective_api") if toxicity_annotation else None
    )
    sentiment_annotation = request.form.get("sentiment_annotation") == "true"
    emotion_annotation = request.form.get("emotion_annotation") == "true"

    if platform_type == "forum":
        opinion_dynamics_enabled = False
        toxicity_annotation = False
        perspective_api = None
        sentiment_annotation = False
        emotion_annotation = False

    topics = request.form.get("tags").split(",")

    # identify db type
    db_type = "sqlite"
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        db_type = "postgresql"

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    uid = str(uuid.uuid4()).replace("-", "_")
    pathlib.Path(f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    db_uri = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db"

    # copy the clean database to the experiments folder
    if platform_type == "microblogging" or platform_type == "forum":
        if db_type == "sqlite":
            # Only Standard experiments get a pre-created database
            # HPC experiments: database is created automatically by the server on first startup
            if simulator_type == "Standard":
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

                    stmt = text("""
                                INSERT INTO user_mgmt (username, email, password, user_type, leaning, age,
                                                       language, owner, joined_on, frecsys_type,
                                                       round_actions, toxicity, is_page, daily_activity_level)
                                VALUES (:username, :email, :password, :user_type, :leaning, :age,
                                        :language, :owner, :joined_on, :frecsys_type,
                                        :round_actions, :toxicity, :is_page, :daily_activity_level)
                                """)

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

        from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

        if db_type == "sqlite" and simulator_type == "Standard":
            ensure_experiment_schema_for_uri(f"sqlite:///{db_uri}")
        elif db_type == "sqlite" and simulator_type == "HPC":
            pass  # HPC experiments: database is created automatically by the server on first startup
        elif db_type == "postgresql":
            ensure_experiment_schema_for_uri(db_uri)
        else:
            raise NotImplementedError(f"Unsupported dbms {db_type}")
    else:
        raise NotImplementedError(f"Unsupported platform {platform_type}")

    # Generate data_path
    data_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"

    # Generate config based on simulator type
    if simulator_type == "HPC":
        # For HPC, extract PostgreSQL connection details if using postgresql
        db_config_dict = None
        if db_type == "postgresql":
            from urllib.parse import urlparse

            parsed_uri = urlparse(current_app.config["SQLALCHEMY_DATABASE_URI"])
            db_config_dict = {
                "host": parsed_uri.hostname or "localhost",
                "port": parsed_uri.port or 5432,
                "database": f"experiments_{uid}".replace("-", "_"),
                "username": parsed_uri.username or "postgres",
                "password": parsed_uri.password or "password",
            }

        config = generate_hpc_config(
            exp_name=exp_name,
            platform_type=platform_type,
            db_type=db_type,
            db_uri=db_uri,
            redis_enabled=redis_enabled,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_password=redis_password,
            redis_sliding_window_days=redis_sliding_window_days,
            perspective_api=(
                perspective_api
                if perspective_api and len(perspective_api) > 0
                else None
            ),
            sentiment_annotation=sentiment_annotation,
            emotion_annotation=emotion_annotation,
            opinion_dynamics_enabled=opinion_dynamics_enabled,
            topics=topics,
            data_path=data_path,
            db_config_dict=db_config_dict,
            is_remote=is_remote,
        )
    else:
        # Standard simulator
        config = generate_standard_config(
            platform_type=platform_type,
            exp_name=exp_name,
            host=host,
            port=port,
            perspective_api=(
                perspective_api
                if perspective_api and len(perspective_api) > 0
                else None
            ),
            sentiment_annotation=sentiment_annotation,
            emotion_annotation=emotion_annotation,
            opinion_dynamics_enabled=opinion_dynamics_enabled,
            db_uri=db_uri,
            topics=topics,
            data_path=data_path,
            is_remote=is_remote,
        )

    if simulator_type == "HPC":
        with open(
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}server_config.json",
            "w",
        ) as f:
            json.dump(config, f, indent=4)
    else:
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
    if opinion_dynamics_enabled:
        annotations += "opinions,"
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
        simulator_type=simulator_type,
        is_remote=is_remote,
        exp_group=exp_group,
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

    from y_web.src.telemetry import Telemetry

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
    """Delete a single simulation."""
    check_privileges(current_user.username)
    admin_user = _current_admin_user_or_none()
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if exp and not user_can_manage_experiment(admin_user, exp):
        flash("You do not have permission to delete this experiment.", "error")
        return settings()

    deleted, error_message = _delete_simulation_internal(exp_id)
    if not deleted and error_message:
        flash(error_message, "warning")

    return settings()


def _delete_simulation_internal(exp_id):
    """
    Delete an experiment and related artifacts/records.

    Returns:
        tuple(bool, str|None): (deleted, error_message)
    """
    # get the experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if exp:
        # remove the experiment folder
        # check database type
        if current_app.config["SQLALCHEMY_BINDS"]["db_exp"].startswith("sqlite"):
            from y_web.src.system.path_utils import get_writable_path

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
            from y_web.src.system.path_utils import get_writable_path

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
                        text(f"""
                            SELECT pg_terminate_backend(pg_stat_activity.pid)
                            FROM pg_stat_activity
                            WHERE pg_stat_activity.datname = :dbname
                            AND pid <> pg_backend_pid()
                            """),
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
        for instance in instances:
            try:
                if getattr(instance, "process", None):
                    stop_process(instance.process, instance.exp_id)
            except Exception:
                pass
        db.session.query(Jupyter_instances).filter_by(exp_id=exp_id).delete()
        db.session.commit()

        return True, None

    return False, f"Experiment with id {exp_id} was not found."


@experiments.route("/admin/delete_simulations_bulk", methods=["POST"])
@login_required
def delete_simulations_bulk():
    """Delete multiple experiments selected from the experiment boxes."""
    check_privileges(current_user.username)

    exp_ids_json = request.form.get("exp_ids", "[]")
    try:
        exp_ids = json.loads(exp_ids_json)
    except json.JSONDecodeError:
        flash("Invalid experiment IDs provided.", "error")
        return redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user_or_none()
    normalized_ids = _resolve_bulk_experiment_ids(exp_ids, admin_user=admin_user)

    if not normalized_ids:
        flash("No experiments selected for deletion.", "warning")
        return redirect(url_for("experiments.settings"))

    deleted_count = 0
    failed_ids = []

    for eid in normalized_ids:
        exp = Exps.query.filter_by(idexp=eid).first()
        if exp and not user_can_manage_experiment(admin_user, exp):
            failed_ids.append(eid)
            continue
        deleted, _ = _delete_simulation_internal(eid)
        if deleted:
            deleted_count += 1
        else:
            failed_ids.append(eid)

    if deleted_count:
        flash(f"Deleted {deleted_count} experiment(s).", "success")
    if failed_ids:
        flash(
            f"Failed to delete {len(failed_ids)} experiment(s): {', '.join(map(str, failed_ids[:10]))}",
            "warning",
        )

    return redirect(url_for("experiments.settings"))


@experiments.route("/admin/start_experiment/<int:uid>")
@login_required
def start_experiment(uid):
    """Handle start experiment operation."""
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=uid).first()
    admin_user = _current_admin_user_or_none()
    if not user_can_view_experiment(admin_user, exp):
        flash("You are not allowed to start this experiment.", "error")
        return redirect(url_for("experiments.settings"))

    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before starting the server or creating clients.",
            "warning",
        )
        return experiment_details(uid)

    # check if the experiment is already running
    if exp.running == 1:
        return experiment_details(uid)

    # update the experiment status
    db.session.query(Exps).filter_by(idexp=uid).update(
        {Exps.running: 1, Exps.exp_status: "active"}
    )
    db.session.commit()

    start_server_for_experiment(exp)

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
    admin_user = _current_admin_user_or_none()
    if not user_can_manage_experiment(admin_user, exp):
        flash("You do not have permission to stop this experiment.", "error")
        return redirect(url_for("experiments.settings"))

    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before changing server or client execution state.",
            "warning",
        )
        return experiment_details(uid)

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
                stop_client_for_experiment(exp, client, pause=False)

            # Update client status in database
            client.status = 0
            db.session.commit()

    # Step 3: Now stop the yserver after all clients are terminated
    # Try the new subprocess-based termination first
    # If that fails or no process is tracked, fall back to port-based termination
    stop_server_for_experiment(exp)

    # Step 4: Check if all clients have completed to determine final status
    all_clients_completed, _ = _get_clients_to_start(exp)
    final_status = "completed" if all_clients_completed else "stopped"

    # Update the experiment status in database
    db.session.query(Exps).filter_by(idexp=uid).update(
        {Exps.running: 0, Exps.exp_status: final_status}
    )
    db.session.commit()

    # Step 5: Handle scheduled experiments - remove from running group to unblock schedule
    # Check if there's an active schedule and if this experiment is part of it
    schedule_status = ExperimentScheduleStatus.query.first()
    if (
        schedule_status
        and schedule_status.is_running
        and schedule_status.current_group_id
    ):
        # Check if this experiment is in the current running group
        schedule_item = ExperimentScheduleItem.query.filter_by(
            experiment_id=uid, group_id=schedule_status.current_group_id
        ).first()

        if schedule_item:
            # This experiment is part of the running schedule group
            # Remove it from the schedule to unblock subsequent groups
            group = ExperimentScheduleGroup.query.get(schedule_status.current_group_id)
            group_name = group.name if group else "Unknown"

            # Log the removal
            log_msg = f"Experiment '{exp.exp_name}' was manually stopped and removed from schedule group '{group_name}'"
            db.session.add(ExperimentScheduleLog(message=log_msg, log_type="warning"))

            # Remove the schedule item
            db.session.delete(schedule_item)
            db.session.commit()

            print(
                f"Removed stopped experiment {exp.exp_name} (ID: {uid}) from schedule group {group_name}"
            )

    return experiment_details(uid)


@experiments.route("/admin/prompts/<int:uid>")
@login_required
def prompts(uid):
    """Handle prompts operation."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()

    # Route to the configuration page matching the experiment type.
    if experiment.simulator_type == "HPC":
        return redirect(url_for("experiments.prompts_hpc", uid=uid))
    if experiment.platform_type == "forum":
        return redirect(url_for("experiments.prompts_forum", uid=uid))

    # get the prompts file for the experiment
    prompts = os.path.join(
        BASE_DIR,
        f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

    # read the prompts file
    prompts = json.load(open(prompts))

    return render_template("admin/prompts.html", experiment=experiment, prompts=prompts)


@experiments.route("/admin/prompts_forum/<int:uid>")
@login_required
def prompts_forum(uid):
    """Handle forum prompts operation."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    experiment = Exps.query.filter_by(idexp=uid).first()

    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    if experiment.simulator_type == "HPC":
        return redirect(url_for("experiments.prompts_hpc", uid=uid))
    if experiment.platform_type != "forum":
        return redirect(url_for("experiments.prompts", uid=uid))

    prompts_path = os.path.join(
        BASE_DIR,
        f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

    with open(prompts_path) as f:
        prompts = json.load(f)

    return render_template(
        "admin/prompts_forum.html", experiment=experiment, prompts=prompts
    )


@experiments.route("/admin/prompts_hpc/<int:uid>")
@login_required
def prompts_hpc(uid):
    """Handle HPC prompts operation."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()

    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    # Ensure this is an HPC experiment
    if experiment.simulator_type != "HPC":
        flash(
            "This page is only for HPC experiments. Redirecting to standard prompts page.",
            "warning",
        )
        return redirect(url_for("experiments.prompts", uid=uid))

    # get the prompts file for the experiment
    prompts_path = os.path.join(
        BASE_DIR,
        f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

    # read the prompts file
    with open(prompts_path) as f:
        prompts = json.load(f)

    return render_template(
        "admin/prompts_hpc.html", experiment=experiment, prompts=prompts
    )


@experiments.route("/admin/update_prompts/<int:uid>", methods=["POST"])
@login_required
def update_prompts(uid):
    """Update prompts."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

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


@experiments.route("/admin/update_prompts_hpc/<int:uid>", methods=["POST"])
@login_required
def update_prompts_hpc(uid):
    """Update HPC prompts."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()

    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    # Ensure this is an HPC experiment
    if experiment.simulator_type != "HPC":
        flash("This update is only for HPC experiments.", "error")
        return redirect(request.referrer)

    # get the prompts file for the experiment
    prompts_filename = os.path.join(
        BASE_DIR,
        f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

    # read the prompts file
    with open(prompts_filename) as f:
        prompts = json.load(f)

    # Update prompts based on form data
    # Handle persona_template
    if "persona_template" in request.form:
        prompts["persona_template"] = request.form["persona_template"]

    # Handle personas (archetypes)
    if "personas" not in prompts:
        prompts["personas"] = {}
    if "personas_0" in request.form:
        prompts["personas"]["0"] = request.form["personas_0"]
    if "personas_1" in request.form:
        prompts["personas"]["1"] = request.form["personas_1"]
    if "personas_2" in request.form:
        prompts["personas"]["2"] = request.form["personas_2"]

    # Handle all action prompts (system_template and user_template pairs)
    action_types = [
        "generate_post",
        "decide_reaction",
        "generate_comment",
        "generate_read_reaction",
        "decide_search_action",
        "generate_news_commentary",
        "decide_follow",
        "decide_secondary_follow",
        "extract_article_topics",
        "extract_emotions",
        "describe_image",
        "generate_image_commentary",
        "infer_article_opinion",
        "evaluate_opinion",
        "generate_share_commentary",
    ]

    for action in action_types:
        if action not in prompts:
            prompts[action] = {}

        system_key = f"{action}_system_template"
        user_key = f"{action}_user_template"

        if system_key in request.form:
            prompts[action]["system_template"] = request.form[system_key]
        if user_key in request.form:
            prompts[action]["user_template"] = request.form[user_key]

    # write the updated prompts
    with open(prompts_filename, "w") as f:
        json.dump(prompts, f, indent=2)

    flash("HPC prompts updated successfully!", "success")

    return redirect(request.referrer)


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
    from y_web.src.telemetry import Telemetry

    # Get form data
    new_exp_name = request.form.get("new_exp_name")
    source_exp_id = request.form.get("source_exp_id")
    num_copies = request.form.get("num_copies", "1")
    exp_group = request.form.get("exp_group", "").strip()  # Get experiment group

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
            success = _create_single_experiment_copy(source_exp, copy_name, exp_group)
            if success:
                created_count += 1

                telemetry = Telemetry(user=current_user)
                telemetry.log_event(
                    {
                        "action": "create_experiment",
                        "data": {
                            "platform_type": source_exp.platform_type,
                            "annotations": source_exp.annotations,
                            "llm_agents_enabled": source_exp.llm_agents_enabled,
                            "copy_experiment": "True",
                        },
                    },
                )
        except Exception as e:
            current_app.logger.error(
                f"Error copying experiment to '{copy_name}': {str(e)}", exc_info=True
            )
            flash(f"Error creating copy '{copy_name}': {str(e)}")

    if created_count > 0:
        if created_count == 1:
            flash(
                f"Experiment '{exp_names_to_create[0]}' successfully created as a copy of '{source_exp.exp_name}'."
            )
        else:
            flash(
                f"{created_count} experiment copies successfully created from '{source_exp.exp_name}'."
            )

    return redirect(url_for("experiments.settings"))


def _create_single_experiment_copy(source_exp, new_exp_name, exp_group=""):
    """
    Helper function to create a single experiment copy.

    Args:
        source_exp: Source experiment object
        new_exp_name: Name for the new experiment
        exp_group: Group name for the experiment (optional)

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

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    source_folder = os.path.join(
        BASE_DIR, f"y_web{os.sep}experiments{os.sep}{source_uid}"
    )
    new_folder = os.path.join(BASE_DIR, f"y_web{os.sep}experiments{os.sep}{new_uid}")

    # Check if source folder exists
    if not os.path.exists(source_folder):
        return False

    # Create new experiment folder and copy all files
    pathlib.Path(new_folder).mkdir(parents=True, exist_ok=True)

    # Detect if this is an HPC or Standard experiment BEFORE copying files
    # This is critical: HPC experiments have different file handling requirements
    is_hpc = os.path.exists(os.path.join(source_folder, "server_config.json"))

    # Copy all files from source to new folder, excluding log files and HPC-specific files
    import re

    log_pattern = re.compile(r"\.log(\.\d+)?$")  # Matches .log, .log.1, .log.2, etc.

    for item in os.listdir(source_folder):
        # Skip log files (server logs and client logs) including rotated logs
        if log_pattern.search(item):
            continue

        # For HPC experiments, skip additional files:
        # - database files (HPC generates its own on server startup)
        # - ray_config.temp (temporary Ray configuration file)
        if is_hpc:
            if (
                item == "database_server.db"
                or item.startswith("database_")
                and item.endswith(".db")
            ):
                continue
            if item == "ray_config.temp":
                continue

        source_item = os.path.join(source_folder, item)
        dest_item = os.path.join(new_folder, item)

        if os.path.isfile(source_item):
            shutil.copy2(source_item, dest_item)
        elif os.path.isdir(source_item):
            # Special handling for logs directory: create empty directory without copying contents
            if item == "logs":
                os.makedirs(dest_item, exist_ok=True)
            else:
                shutil.copytree(source_item, dest_item)

    # Get suggested port for new experiment
    suggested_port = get_suggested_port()
    if not suggested_port:
        # Cleanup and return
        current_app.logger.warning(
            f"No available port found for experiment copy: {new_exp_name}"
        )
        shutil.rmtree(new_folder, ignore_errors=True)
        return False

    # Handle database copying first to get the correct db_uri
    new_db_name = ""
    new_db_uri = ""

    if db_type == "sqlite":
        # Create database path
        new_db_path = os.path.join(new_folder, "database_server.db")

        # Only Standard experiments get a pre-created database
        # HPC experiments: database is created automatically by the server on first startup
        if not is_hpc:
            # Copy the clean database schema for Standard experiments
            clean_db_path = get_resource_path(
                os.path.join("data_schema", "database_clean_server.db")
            )
            if os.path.exists(clean_db_path):
                shutil.copy2(clean_db_path, new_db_path)
            else:
                # If clean DB doesn't exist, create an empty database file
                import sqlite3

                conn = sqlite3.connect(new_db_path)
                conn.close()
        # For HPC: Do NOT create any database file - the HPC server will create it on startup

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

                stmt = text("""
                    INSERT INTO user_mgmt (username, email, password, user_type, leaning, age,
                                           language, owner, joined_on, frecsys_type,
                                           round_actions, toxicity, is_page, daily_activity_level)
                    VALUES (:username, :email, :password, :user_type, :leaning, :age,
                            :language, :owner, :joined_on, :frecsys_type,
                            :round_actions, :toxicity, :is_page, :daily_activity_level)
                    """)
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

    from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

    if db_type == "sqlite" and not is_hpc:
        ensure_experiment_schema_for_uri(f"sqlite:///{new_db_uri}")
    elif db_type == "postgresql":
        ensure_experiment_schema_for_uri(new_db_uri)

    # Update configuration file with new name, port, and database_uri
    # is_hpc was already detected earlier (before database copying)
    # Just need to determine the correct config path
    if is_hpc:
        config_path = os.path.join(new_folder, "server_config.json")
    else:
        config_path = os.path.join(new_folder, "config_server.json")

    if not os.path.exists(config_path):
        # Config file doesn't exist - cleanup and return
        if os.path.exists(new_folder):
            shutil.rmtree(new_folder, ignore_errors=True)
        return False

    with open(config_path, "r") as f:
        config = json.load(f)

    # Update configuration fields based on experiment type
    if is_hpc:
        # HPC experiment configuration structure
        config["experiment_name"] = new_exp_name
        if "server" in config:
            config["server"]["port"] = suggested_port
        else:
            config["server"] = {"port": suggested_port}
        config["database_uri"] = new_db_uri
    else:
        # Standard experiment configuration structure
        config["name"] = new_exp_name
        config["port"] = suggested_port
        config["database_uri"] = new_db_uri
        # Add data_path so YServer knows where to write logs (e.g., _server.log)
        config["data_path"] = new_folder + os.sep

    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

    # Verify the config was written correctly
    with open(config_path, "r") as f:
        verify_config = json.load(f)

    # Verify based on experiment type
    if is_hpc:
        if (
            verify_config.get("experiment_name") != new_exp_name
            or verify_config.get("server", {}).get("port") != suggested_port
            or verify_config.get("database_uri") != new_db_uri
        ):
            # Cleanup and return
            if os.path.exists(new_folder):
                shutil.rmtree(new_folder, ignore_errors=True)
            return False
    else:
        if (
            verify_config.get("port") != suggested_port
            or verify_config.get("database_uri") != new_db_uri
        ):
            # Cleanup and return
            if os.path.exists(new_folder):
                shutil.rmtree(new_folder, ignore_errors=True)
            return False

    # Update all client configuration files with new port
    # Standard: client_*.json, HPC: {client_name}_config.json
    # The is_hpc flag determines which config structure to update, not the filename pattern

    for item in os.listdir(new_folder):
        # Match Standard (client_*.json) OR HPC (*_config.json excluding server_config.json)
        is_standard_client = item.startswith("client") and item.endswith(".json")
        is_hpc_client = item.endswith("_config.json") and not item.startswith("server")

        if is_standard_client or is_hpc_client:
            client_config_path = os.path.join(new_folder, item)
            try:
                with open(client_config_path, "r") as f:
                    client_config = json.load(f)

                # Update port based on experiment type
                if is_hpc:
                    # HPC client config format: "server": {"address": null, "port": null}
                    if "server" in client_config:
                        client_config["server"]["port"] = suggested_port
                else:
                    # Standard client config: "servers": {"api": "http://..."}
                    if "servers" in client_config and "api" in client_config["servers"]:
                        # Update the port in the API URL
                        old_api = client_config["servers"]["api"]
                        # Replace port in URL - handles both with and without trailing slash
                        # Pattern matches :port/ or :port at end of string
                        new_api = re.sub(
                            r":(\d+)(/|$)", f":{suggested_port}\\2", old_api
                        )
                        client_config["servers"]["api"] = new_api

                with open(client_config_path, "w") as f:
                    json.dump(client_config, f, indent=4)
            except Exception as e:
                # Continue anyway - this is not critical enough to fail the entire copy
                current_app.logger.warning(
                    f"Failed to update client config {item}: {str(e)}"
                )

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
        simulator_type=source_exp.simulator_type,
        exp_group=exp_group,
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
