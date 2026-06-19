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
from y_web.migrations.add_hpc_monitor_settings import (
    ensure_hpc_monitor_settings_schema,
)
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
        return (
            jsonify({"success": False, "message": "Cannot delete a running group"}),
            400,
        )

    # Delete all items in the group first
    ExperimentScheduleItem.query.filter_by(group_id=group_id).delete()
    db.session.delete(group)
    db.session.commit()

    return jsonify({"success": True})


@experiments.route(
    "/admin/schedule/groups/<int:group_id>/experiments", methods=["POST"]
)
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
    ensure_hpc_monitor_settings_schema()
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
        return (
            jsonify({"success": False, "message": "Experiment already in group"}),
            400,
        )

    # HPC experiment validation: keep HPC and Standard experiments separate.
    is_hpc = exp.simulator_type == "HPC"
    hpc_settings = HpcMonitorSettings.query.first()
    max_hpc_per_group = (
        getattr(hpc_settings, "max_hpc_per_group", 4) if hpc_settings else 4
    )

    if is_hpc:
        # Check if there are any non-HPC (Standard) experiments in this group
        standard_count = (
            db.session.query(ExperimentScheduleItem)
            .join(Exps, ExperimentScheduleItem.experiment_id == Exps.idexp)
            .filter(
                ExperimentScheduleItem.group_id == group_id,
                Exps.simulator_type != "HPC",
            )
            .count()
        )
        if standard_count > 0:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Cannot mix HPC experiments with Standard experiments in the same group.",
                    }
                ),
                400,
            )
        if max_hpc_per_group is not None:
            hpc_count = (
                db.session.query(ExperimentScheduleItem)
                .join(Exps, ExperimentScheduleItem.experiment_id == Exps.idexp)
                .filter(
                    ExperimentScheduleItem.group_id == group_id,
                    Exps.simulator_type == "HPC",
                )
                .count()
            )
            if hpc_count >= max_hpc_per_group:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": (
                                f"Maximum {max_hpc_per_group} HPC experiments allowed per group. "
                                f"This group already has {hpc_count} HPC experiments."
                            ),
                        }
                    ),
                    400,
                )
    else:
        # Check if group already contains an HPC experiment (use join for efficiency)
        hpc_in_group = (
            db.session.query(ExperimentScheduleItem)
            .join(Exps, ExperimentScheduleItem.experiment_id == Exps.idexp)
            .filter(
                ExperimentScheduleItem.group_id == group_id,
                Exps.simulator_type == "HPC",
            )
            .first()
        )
        if hpc_in_group:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Cannot mix Standard experiments with HPC experiments in the same group.",
                    }
                ),
                400,
            )

    # Get max order index for this group
    max_order = (
        db.session.query(db.func.max(ExperimentScheduleItem.order_index))
        .filter(ExperimentScheduleItem.group_id == group_id)
        .scalar()
        or 0
    )

    item = ExperimentScheduleItem(
        group_id=group_id,
        experiment_id=data["experiment_id"],
        order_index=max_order + 1,
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
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Cannot remove experiments from a running group",
                }
            ),
            400,
        )

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
            "started_at": (
                status.started_at.isoformat() + "Z" if status.started_at else None
            ),
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
            # Infinite clients (expected_duration_rounds = -1) are never considered completed
            if client_exec.expected_duration_rounds == -1:
                all_clients_completed = False
                clients_to_start.append(client)
            elif client_exec.elapsed_time < client_exec.expected_duration_rounds:
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
        return (
            jsonify(
                {
                    "success": False,
                    "message": "No groups defined or all groups completed",
                }
            ),
            400,
        )

    # Start all experiments in first group
    items = ExperimentScheduleItem.query.filter_by(group_id=first_group.id).all()
    if not items:
        return (
            jsonify({"success": False, "message": "First group has no experiments"}),
            400,
        )

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

            # Start the server (use appropriate function for HPC vs Standard)
            start_server_for_experiment(exp)
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
                    population = Population.query.filter_by(
                        id=client.population_id
                    ).first()
                    if population:
                        start_client_for_experiment(
                            exp, client, population, resume=True
                        )
                        # Mark client as running
                        client.status = 1
                        db.session.commit()
                        msg = f"Client '{client.name}' started successfully"
                        logs.append(msg)
                    else:
                        msg = f"Warning: No population found for client '{client.name}'"
                        logs.append(msg)
                        db.session.add(
                            ExperimentScheduleLog(message=msg, log_type="warning")
                        )

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
                        stop_result = True
                        if client.pid or exp.simulator_type == "HPC":
                            stop_result = stop_client_for_experiment(
                                exp, client, pause=False
                            )
                        if exp.simulator_type == "HPC" and stop_result is False:
                            client.status = 1
                        else:
                            client.status = 0
                        db.session.commit()

                # Stop server
                stop_server_for_experiment(exp)

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
    check_privileges(current_user.username)
    return jsonify(_do_check_schedule_progress())


def _do_check_schedule_progress():
    """
    Core logic for checking schedule progress and advancing to next group.

    Can be called from the HTTP endpoint or the background monitor.

    Returns:
        dict suitable for jsonify
    """

    with _schedule_check_lock:
        status = ExperimentScheduleStatus.query.first()
        if not status or not status.is_running:
            return {"success": True, "is_running": False}

        if not status.current_group_id:
            return {"success": True, "is_running": False}

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
            return {
                "success": True,
                "is_running": True,
                "all_completed": False,
                "current_group_id": status.current_group_id,
            }

        # All completed - stop current group experiments and move to next group
        logs = []
        current_group = ExperimentScheduleGroup.query.get(status.current_group_id)

        msg = f"Group '{current_group.name}' completed!"
        logs.append(msg)
        db.session.add(ExperimentScheduleLog(message=msg, log_type="success"))

        # Mark current group as completed (don't delete yet - will clean up at end of schedule)
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
                        stop_result = True
                        if client.pid or exp.simulator_type == "HPC":
                            stop_result = stop_client_for_experiment(
                                exp, client, pause=False
                            )
                        if exp.simulator_type == "HPC" and stop_result is False:
                            client.status = 1
                        else:
                            client.status = 0
                        db.session.commit()

                # Stop server
                stop_server_for_experiment(exp)

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

            # Clean up all completed groups from the database
            completed_groups = ExperimentScheduleGroup.query.filter_by(
                is_completed=1
            ).all()
            for group in completed_groups:
                ExperimentScheduleItem.query.filter_by(group_id=group.id).delete()
                db.session.delete(group)
            db.session.commit()

            # Clear all schedule logs after successful completion
            ExperimentScheduleLog.query.delete()
            db.session.commit()

            return {
                "success": True,
                "is_running": False,
                "all_completed": True,
                "schedule_complete": True,
                "logs": logs,
            }

        # Start next group
        msg = f"Starting next group: '{next_group.name}'..."
        logs.append(msg)
        db.session.add(ExperimentScheduleLog(message=msg, log_type="info"))
        status.current_group_id = next_group.id
        db.session.commit()

        next_items = ExperimentScheduleItem.query.filter_by(
            group_id=next_group.id
        ).all()
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
                db.session.add(
                    ExperimentScheduleLog(
                        message=f"Starting server for '{exp.exp_name}'...",
                        log_type="info",
                    )
                )
                exp.running = 1
                exp.exp_status = "active"
                db.session.commit()

                # Start the server (use appropriate function for HPC vs Standard)
                start_server_for_experiment(exp)

                # Wait for server to be ready
                logs.append(f"Waiting for server '{exp.exp_name}' to be ready...")
                time.sleep(3)

                # Start only clients that haven't completed
                for client in clients_to_start:
                    if client.status == 0:
                        logs.append(f"Starting client '{client.name}'...")
                        db.session.add(
                            ExperimentScheduleLog(
                                message=f"Starting client '{client.name}'...",
                                log_type="info",
                            )
                        )
                        population = Population.query.filter_by(
                            id=client.population_id
                        ).first()
                        if population:
                            start_client_for_experiment(
                                exp, client, population, resume=True
                            )
                            client.status = 1
                            db.session.commit()

                logs.append(f"Experiment '{exp.exp_name}' started successfully")
                db.session.add(
                    ExperimentScheduleLog(
                        message=f"Experiment '{exp.exp_name}' started successfully",
                        log_type="success",
                    )
                )
                db.session.commit()

        logs.append(f"Group '{next_group.name}' started!")
        db.session.add(
            ExperimentScheduleLog(
                message=f"Group '{next_group.name}' started!", log_type="success"
            )
        )
        db.session.commit()

        return {
            "success": True,
            "is_running": True,
            "all_completed": True,
            "next_group": next_group.name,
            "next_group_id": next_group.id,
            "logs": logs,
        }


@experiments.route("/admin/schedule/available_experiments", methods=["GET"])
@login_required
def get_available_experiments_for_schedule():
    """
    Get experiments that can be added to schedule groups.

    Returns experiments that are stopped, not already in any group,
    and do not have any infinite-duration clients.

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

    experiments_list = _get_schedulable_experiments(experiments_query)

    # Get experiments already in groups
    scheduled_exp_ids = set(
        item.experiment_id for item in ExperimentScheduleItem.query.all()
    )

    # Get experiment IDs that have infinite clients (clients with days = -1)
    # Use a single query instead of nested loops for efficiency.
    # These experiments remain visible in the picker so they can be inspected
    # or manually scheduled; auto-grouping still keeps the stricter rule below.
    exp_ids = [exp.idexp for exp in experiments_list]
    infinite_clients = (
        (
            Client.query.filter(Client.days == -1, Client.id_exp.in_(exp_ids))
            .with_entities(Client.id_exp)
            .distinct()
            .all()
        )
        if exp_ids
        else []
    )
    experiments_with_infinite_clients = set(c.id_exp for c in infinite_clients)

    result = _build_available_schedule_experiments(
        experiments_list, scheduled_exp_ids, experiments_with_infinite_clients
    )

    return jsonify({"success": True, "experiments": result})


def _build_available_schedule_experiments(
    experiments_list, scheduled_exp_ids, experiments_with_infinite_clients
):
    """Convert schedule-eligible experiments into the payload shown in the picker."""
    result = []
    for exp in experiments_list:
        if exp.idexp in scheduled_exp_ids:
            continue

        result.append(
            {
                "id": exp.idexp,
                "name": exp.exp_name,
                "owner": exp.owner,
                "exp_status": exp.exp_status,
                "has_infinite_client": exp.idexp in experiments_with_infinite_clients,
            }
        )

    return result


def _get_schedulable_experiments(experiments_query):
    """Return schedule-eligible experiments in a deterministic order.

    Fresh clones should be selectable as long as they are not running.
    Older copied experiments can also have a NULL, empty, or stale exp_status,
    so we do not require a specific status value here.
    """
    experiments = experiments_query.all()
    result = []
    for exp in experiments:
        if getattr(exp, "running", 0) != 0:
            continue
        if exp.exp_status == "active":
            continue
        if exp.exp_status == "completed" and getattr(exp, "status", 0) == 1:
            continue
        result.append(exp)

    return sorted(result, key=lambda exp: (exp.idexp or 0, exp.exp_name or ""))


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
                    "created_at": (
                        log.created_at.isoformat() + "Z" if log.created_at else None
                    ),
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
    - group_filter: Optional list of experiment group names to filter by

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
            jsonify(
                {"success": False, "message": "Invalid experiments_per_group value"}
            ),
            400,
        )

    # Get optional group filter
    group_filter = data.get("group_filter", None)

    # Get current user
    user = Admin_users.query.filter_by(username=current_user.username).first()

    if user.role == "admin":
        experiments_query = Exps.query
    else:
        experiments_query = Exps.query.filter_by(owner=user.username)

    experiments_list = _get_schedulable_experiments(experiments_query)

    # Apply group filter if specified
    if group_filter:
        experiments_list = [
            exp for exp in experiments_list if exp.exp_group in group_filter
        ]

    # Filter out experiments already in groups
    scheduled_exp_ids = set(
        item.experiment_id for item in ExperimentScheduleItem.query.all()
    )

    # Filter out experiments with infinite clients (days = -1)
    exp_ids = [exp.idexp for exp in experiments_list]
    infinite_clients = (
        (
            Client.query.filter(Client.days == -1, Client.id_exp.in_(exp_ids))
            .with_entities(Client.id_exp)
            .distinct()
            .all()
        )
        if exp_ids
        else []
    )
    experiments_with_infinite_clients = set(c.id_exp for c in infinite_clients)

    available_exps = [
        exp
        for exp in experiments_list
        if exp.idexp not in scheduled_exp_ids
        and exp.idexp not in experiments_with_infinite_clients
    ]

    if not available_exps:
        return (
            jsonify(
                {"success": False, "message": "No available experiments to assign"}
            ),
            400,
        )

    ensure_hpc_monitor_settings_schema()
    hpc_settings = HpcMonitorSettings.query.first()
    max_hpc_per_group = (
        getattr(hpc_settings, "max_hpc_per_group", 4) if hpc_settings else 4
    )

    # Separate HPC and Standard experiments
    hpc_exps = [exp for exp in available_exps if exp.simulator_type == "HPC"]
    standard_exps = [exp for exp in available_exps if exp.simulator_type != "HPC"]

    # Get current max order index
    max_order = (
        db.session.query(db.func.max(ExperimentScheduleGroup.order_index)).scalar() or 0
    )

    # Create groups and assign experiments
    created_groups = []
    group_num = 1

    # Use the configured HPC grouping size when limited; otherwise honor user input.
    hpc_per_group = (
        max(1, min(max_hpc_per_group, experiments_per_group))
        if max_hpc_per_group is not None
        else max(1, experiments_per_group)
    )

    # First, create groups for HPC experiments using the requested group size
    for i in range(0, len(hpc_exps), hpc_per_group):
        group_hpc_exps = hpc_exps[i : i + hpc_per_group]

        group = ExperimentScheduleGroup(
            name=f"Auto Group {max_order + group_num} (HPC)",
            order_index=max_order + group_num,
            is_completed=0,
        )
        db.session.add(group)
        db.session.commit()

        # Add HPC experiments to the group
        for idx, exp in enumerate(group_hpc_exps):
            item = ExperimentScheduleItem(
                group_id=group.id, experiment_id=exp.idexp, order_index=idx
            )
            db.session.add(item)
        db.session.commit()

        created_groups.append(
            {
                "id": group.id,
                "name": group.name,
                "experiment_count": len(group_hpc_exps),
            }
        )
        group_num += 1

    # Then, create groups for Standard experiments
    for i in range(0, len(standard_exps), experiments_per_group):
        group_exps = standard_exps[i : i + experiments_per_group]

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


# ========================================
# Opinion Dynamics Routes
# ========================================
