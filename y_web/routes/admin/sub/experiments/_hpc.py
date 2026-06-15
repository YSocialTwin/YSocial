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
from y_web.migrations.add_hpc_monitor_settings import (
    ensure_hpc_monitor_settings_schema,
)


@experiments.route("/admin/test_remote_server/<int:exp_id>", methods=["POST"])
@login_required
def test_remote_server(exp_id):
    """Test connection to remote experiment server."""
    check_privileges(current_user.username)

    try:
        data = request.get_json()
        host = data.get("host", "").strip()
        port = data.get("port")

        if not host or not port:
            return jsonify({"success": False, "message": "Host and port are required"})

        # Try to connect to the server
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)  # 5 second timeout

        try:
            result = sock.connect_ex((host, int(port)))
            sock.close()

            if result == 0:
                return jsonify(
                    {
                        "success": True,
                        "message": f"Successfully connected to {host}:{port}",
                    }
                )
            else:
                return jsonify(
                    {
                        "success": False,
                        "message": f"Cannot connect to {host}:{port} - Connection refused",
                    }
                )
        except socket.gaierror:
            return jsonify({"success": False, "message": f"Invalid hostname: {host}"})
        except socket.timeout:
            return jsonify(
                {"success": False, "message": f"Connection timeout to {host}:{port}"}
            )
        except Exception as e:
            return jsonify({"success": False, "message": f"Connection error: {str(e)}"})

    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})


@experiments.route("/admin/update_remote_server/<int:exp_id>", methods=["POST"])
@login_required
def update_remote_server(exp_id):
    """Update remote experiment server host and port."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

    try:
        data = request.get_json()
        host = data.get("host", "").strip()
        port = data.get("port")

        if not host:
            return jsonify({"success": False, "message": "Host address is required"})

        # Validate hostname/IP format
        if not re.match(r"^[a-zA-Z0-9\.\-\:]+$", host):
            return jsonify({"success": False, "message": "Invalid host format"})

        # Validate port
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                return jsonify(
                    {"success": False, "message": "Port must be between 1 and 65535"}
                )
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Invalid port number"})

        # Get experiment
        exp = Exps.query.filter_by(idexp=exp_id).first()
        if not exp:
            return jsonify({"success": False, "message": "Experiment not found"})

        if exp.is_remote != 1:
            return jsonify(
                {"success": False, "message": "This is not a remote experiment"}
            )

        # Update database
        db.session.query(Exps).filter_by(idexp=exp_id).update(
            {Exps.server: host, Exps.port: port}
        )
        db.session.commit()

        # Update config files
        BASE_DIR = get_writable_path()
        db_name_parts = exp.db_name.split(os.sep)
        if len(db_name_parts) >= 2:
            experiment_folder_name = db_name_parts[1]
            experiment_folder = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{experiment_folder_name}"

            # Update config_server.json (Standard) or server_config.json (HPC)
            if exp.simulator_type == "HPC":
                config_file = os.path.join(experiment_folder, "server_config.json")
            else:
                config_file = os.path.join(experiment_folder, "config_server.json")

            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    config = json.load(f)

                config["host"] = host
                config["port"] = port

                with open(config_file, "w") as f:
                    json.dump(config, f, indent=4)

            # Update all client configuration files
            clients = Client.query.filter_by(id_exp=exp_id).all()
            for client in clients:
                if exp.simulator_type == "HPC":
                    # HPC client config format: "server": {"address": null, "port": null}
                    client_config_file = os.path.join(
                        experiment_folder, f"{client.name}_config.json"
                    )
                    if os.path.exists(client_config_file):
                        with open(client_config_file, "r") as f:
                            client_config = json.load(f)

                        if "server" not in client_config:
                            client_config["server"] = {}
                        client_config["server"]["address"] = host
                        client_config["server"]["port"] = port

                        with open(client_config_file, "w") as f:
                            json.dump(client_config, f, indent=4)
                else:
                    # Standard client config format: "servers": {"api": "http://{host}:{port}/"}
                    client_config_file = os.path.join(
                        experiment_folder, f"{client.name}_config.json"
                    )
                    if os.path.exists(client_config_file):
                        with open(client_config_file, "r") as f:
                            client_config = json.load(f)

                        if "servers" in client_config:
                            client_config["servers"]["api"] = f"http://{host}:{port}/"

                        with open(client_config_file, "w") as f:
                            json.dump(client_config, f, indent=4)

        return jsonify(
            {"success": True, "message": "Server settings updated successfully"}
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error updating server: {str(e)}"}
        )


@experiments.route("/admin/hpc_monitor_settings", methods=["GET"])
@login_required
def get_hpc_monitor_settings():
    """
    Get current HPC monitor settings.

    Returns:
        JSON with HPC monitor settings
    """
    check_privileges(current_user.username)

    ensure_hpc_monitor_settings_schema()

    # Get or create default settings
    settings = HpcMonitorSettings.query.first()
    if not settings:
        settings = HpcMonitorSettings(
            enabled=True, check_interval_seconds=5, max_hpc_per_group=4
        )
        db.session.add(settings)
        db.session.commit()

    return jsonify(
        {
            "enabled": settings.enabled,
            "check_interval_seconds": settings.check_interval_seconds,
            "max_hpc_per_group": settings.max_hpc_per_group,
            "last_check": (
                settings.last_check.isoformat() + "Z" if settings.last_check else None
            ),
        }
    )


@experiments.route("/admin/hpc_monitor_settings", methods=["POST"])
@login_required
def update_hpc_monitor_settings():
    """
    Update HPC monitor settings.

    Expects JSON body with:
    - enabled (bool): Whether HPC monitoring is enabled
    - check_interval_seconds (int): Check frequency in seconds (1-300)
    - max_hpc_per_group (int|null): Maximum HPC experiments per group, or null for unlimited

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    ensure_hpc_monitor_settings_schema()

    # Get or create settings
    settings = HpcMonitorSettings.query.first()
    if not settings:
        settings = HpcMonitorSettings(
            enabled=True, check_interval_seconds=5, max_hpc_per_group=4
        )
        db.session.add(settings)

    # Update enabled if provided
    if "enabled" in data:
        settings.enabled = bool(data["enabled"])

    # Update check interval if provided
    if "check_interval_seconds" in data:
        try:
            interval = int(data["check_interval_seconds"])
            # Validate range: 1 second to 5 minutes (300 seconds)
            if interval < 1 or interval > 300:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Check interval must be between 1 and 300 seconds",
                        }
                    ),
                    400,
                )
            settings.check_interval_seconds = interval
        except (ValueError, TypeError):
            return (
                jsonify({"success": False, "message": "Invalid check interval value"}),
                400,
            )

    if "max_hpc_per_group" in data:
        raw_value = data["max_hpc_per_group"]
        if raw_value in ("", None):
            settings.max_hpc_per_group = None
        else:
            try:
                max_value = int(raw_value)
            except (ValueError, TypeError):
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Invalid max HPC group value",
                        }
                    ),
                    400,
                )
            if max_value < 1:
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Max HPC experiments per group must be at least 1, or choose unlimited",
                        }
                    ),
                    400,
                )
            settings.max_hpc_per_group = max_value

    db.session.commit()

    return jsonify(
        {
            "success": True,
            "enabled": settings.enabled,
            "check_interval_seconds": settings.check_interval_seconds,
        }
    )


# =====================================================
# Experiment Schedule Routes
# =====================================================
