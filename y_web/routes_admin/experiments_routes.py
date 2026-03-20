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
from y_web.utils.avatars import normalize_forum_avatar_mode
from y_web.utils.desktop_file_handler import send_file_desktop
from y_web.utils.execution_backend import (
    start_client_for_experiment,
    start_server_for_experiment,
    stop_client_for_experiment,
    stop_server_for_experiment,
)
from y_web.utils.experiment_access import (
    get_visible_experiment_query,
    user_can_manage_experiment,
    user_can_view_experiment,
)
from y_web.utils.hpc_population_backup import restore_population_for_hpc_client
from y_web.utils.jupyter_utils import stop_process
from y_web.utils.miscellanea import (
    check_privileges,
    llm_backend_status,
    ollama_status,
    reload_current_user,
)
from y_web.utils.path_utils import get_resource_path

experiments = Blueprint("experiments", __name__)

# Configuration constants
OPINION_CACHE_EXPIRY_MINUTES = 5  # Cache expiry time for opinion evolution statistics
MAX_HPC_PER_GROUP = 4  # Maximum number of HPC experiments allowed per schedule group
DEFAULT_FEED_LIMITS = {
    "rss_entries_per_feed": 100,
    "reddit_entries_per_feed": 200,
    "reddit_pages": 2,
    "reddit_rate_limit_seconds": 2,
    "db_fallback_limit": 50,
    "image_entries_per_feed": 100,
}
DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS = {
    "service": "",
    "host": "",
    "model": "",
}
DEFAULT_FORUM_EMBEDDING_SETTINGS = dict(DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS)
DEFAULT_FORUM_AVATAR_SETTINGS = {
    "mode": "placeholder",
}

FORUM_FEED_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}

# Lock to prevent concurrent schedule advancement (from HTTP endpoint and background monitor)
_schedule_check_lock = threading.Lock()
_EXP_IDS_MARKER_RE = re.compile(r"\[exp_ids:([0-9,\s]+)\]")


def _normalize_rss_feed_item(item):
    """Normalize a forum RSS feed definition."""
    if not isinstance(item, dict):
        return None

    feed_url = str(item.get("feed_url", "")).strip()
    parsed_url = urlparse(feed_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return None

    return {
        "name": str(item.get("name") or parsed_url.netloc).strip()[:255],
        "url_site": str(item.get("url_site") or parsed_url.netloc).strip()[:255],
        "feed_url": feed_url,
        "description": str(item.get("description") or "").strip()[:2000],
    }


def _normalize_rss_feeds_payload(feeds):
    """Validate and sanitize the stored forum RSS feeds payload."""
    if not isinstance(feeds, list):
        raise ValueError("RSS feeds payload must be a JSON array.")

    normalized_feeds = []
    seen_urls = set()
    for item in feeds:
        normalized = _normalize_rss_feed_item(item)
        if normalized is None:
            continue
        feed_url = normalized["feed_url"]
        if feed_url in seen_urls:
            continue
        seen_urls.add(feed_url)
        normalized_feeds.append(normalized)

    return normalized_feeds


def _normalize_image_feed_item(item):
    """Normalize a forum image feed definition."""
    if not isinstance(item, dict):
        return None

    subreddit = str(item.get("subreddit", "")).strip().lower()
    subreddit = subreddit[2:] if subreddit.startswith("r/") else subreddit
    if not subreddit:
        return None

    interests = item.get("interests") or []
    if not isinstance(interests, list):
        interests = [interests]

    cleaned_interests = []
    seen_interests = set()
    for interest in interests:
        label = str(interest).strip()
        if not label or label in seen_interests:
            continue
        seen_interests.add(label)
        cleaned_interests.append(label)

    return {"subreddit": subreddit, "interests": cleaned_interests}


def _normalize_image_feeds_payload(feeds):
    """Validate and sanitize the stored forum image feeds payload."""
    if not isinstance(feeds, list):
        raise ValueError("Image feeds payload must be a JSON array.")

    normalized_feeds = []
    seen_subreddits = set()
    for item in feeds:
        normalized = _normalize_image_feed_item(item)
        if normalized is None:
            continue
        subreddit = normalized["subreddit"]
        if subreddit in seen_subreddits:
            continue
        seen_subreddits.add(subreddit)
        normalized_feeds.append(normalized)

    return normalized_feeds


def _read_feed_with_headers(feed_url):
    """Fetch a forum feed with explicit headers to avoid upstream blocks."""
    request_obj = Request(feed_url, headers=FORUM_FEED_REQUEST_HEADERS)
    with urlopen(request_obj, timeout=15) as response:
        return response.read()


def _parse_required_feed_limit(form_key, cast, label, minimum=None):
    """Parse and validate a numeric feed limit field."""
    raw_value = str(request.form.get(form_key, "")).strip()
    if not raw_value:
        raise ValueError(f"{label} is required.")

    try:
        value = cast(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid number.") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be greater than or equal to {minimum}.")

    return value


def get_experiment_uid_from_db_name(db_name):
    """
    Extract the experiment UID from the db_name field.

    This function handles both SQLite and PostgreSQL formats, and correctly
    parses paths regardless of which path separator was used when storing.

    Args:
        db_name: The db_name field from an experiment record
                 SQLite format: "experiments/uid/database_server.db" or "experiments\\uid\\database_server.db"
                 PostgreSQL format: "experiments_uid"

    Returns:
        str: The experiment UID, or None if unable to extract
    """
    if db_name.startswith("experiments_"):
        # PostgreSQL format - UUID is after the underscore
        return db_name.replace("experiments_", "")
    elif db_name.startswith("experiments/") or db_name.startswith("experiments\\"):
        # SQLite format - split using both possible separators
        # Use regex to split on either forward slash or backslash
        parts = re.split(r"[/\\]", db_name)
        if len(parts) >= 2:
            return parts[1]
    return None


def _sanitize_filename(name, fallback):
    """Return a filesystem-safe filename stem."""
    safe_name = "".join(c for c in (name or "") if c.isalnum() or c in (" ", "-", "_"))
    safe_name = safe_name.strip()
    return safe_name or fallback


def _current_admin_user():
    """Resolve current authenticated admin user record."""
    return Admin_users.query.filter_by(username=current_user.username).first()


def _current_admin_user_or_none():
    """Resolve current admin user or None if unavailable."""
    try:
        return _current_admin_user()
    except Exception:
        return None


def _notifications_temp_data_dir():
    """Return temp_data directory used for async archive output."""
    from y_web.utils.path_utils import get_writable_path

    base_dir = get_writable_path()
    return os.path.join(base_dir, f"y_web{os.sep}experiments{os.sep}temp_data")


def _experiment_has_started_once(experiment, clients=None):
    """Best-effort started-once detection that also works for legacy experiments."""
    if not experiment:
        return False

    if int(getattr(experiment, "running", 0) or 0) == 1:
        return True
    if int(getattr(experiment, "status", 0) or 0) > 0:
        return True
    if str(getattr(experiment, "exp_status", "") or "").lower() in (
        "active",
        "completed",
    ):
        return True

    if clients is None:
        clients = Client.query.filter_by(id_exp=experiment.idexp).all()

    for client in clients:
        ce = Client_Execution.query.filter_by(client_id=client.id).first()
        if not ce:
            continue
        if (ce.elapsed_time or 0) > 0:
            return True
        if (ce.last_active_day is not None and ce.last_active_day >= 0) or (
            ce.last_active_hour is not None and ce.last_active_hour >= 0
        ):
            return True

    if ServerLogMetrics.query.filter_by(exp_id=experiment.idexp).first() is not None:
        return True
    if ClientLogMetrics.query.filter_by(exp_id=experiment.idexp).first() is not None:
        return True

    stats = Exp_stats.query.filter_by(exp_id=experiment.idexp).first()
    if stats and any(
        int(getattr(stats, field, 0) or 0) > 0
        for field in ("rounds", "posts", "reactions", "mentions")
    ):
        return True

    # File-based fallback for experiments where metrics rows were never materialized.
    try:
        from y_web.utils.path_utils import get_writable_path

        base_dir = get_writable_path()
        exp_folder = _get_experiment_folder(base_dir, experiment, _get_database_type())
        candidate_logs = [
            os.path.join(exp_folder, "_server.log"),
            os.path.join(exp_folder, "logs", "_server.log"),
        ]
        for log_path in candidate_logs:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
                return True
    except Exception:
        pass

    return False


def _is_path_in_temp_data(path):
    """Ensure file path is inside temp_data to prevent arbitrary deletions."""
    if not path:
        return False
    temp_dir = os.path.realpath(_notifications_temp_data_dir())
    real_path = os.path.realpath(path)
    return real_path.startswith(temp_dir + os.sep) or real_path == temp_dir


def _load_forum_experiment_context(uid, require_manage=True):
    """Load a forum experiment and its writable directory."""
    check_privileges(current_user.username)

    experiment = Exps.query.filter_by(idexp=uid).first()
    if not experiment:
        flash("Experiment not found", "error")
        return None, None, redirect(url_for("experiments.settings"))

    if experiment.platform_type != "forum":
        flash("This page is only available for forum experiments.", "warning")
        return (
            None,
            None,
            redirect(url_for("experiments.experiment_details", uid=uid)),
        )

    admin_user = _current_admin_user_or_none()
    if require_manage and not user_can_manage_experiment(admin_user, experiment):
        flash("You do not have permission to manage this experiment.", "error")
        return (
            None,
            None,
            redirect(url_for("experiments.experiment_details", uid=uid)),
        )

    from y_web.utils.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return None, None, redirect(url_for("experiments.settings"))

    experiment_dir = os.path.join(base_dir, "y_web", "experiments", exp_folder)
    os.makedirs(experiment_dir, exist_ok=True)
    return experiment, experiment_dir, None


def _load_memory_capable_experiment_context(uid, require_manage=True):
    """Load a standard/forum experiment and its writable directory."""
    check_privileges(current_user.username)

    experiment = Exps.query.filter_by(idexp=uid).first()
    if not experiment:
        flash("Experiment not found", "error")
        return None, None, redirect(url_for("experiments.settings"))

    if getattr(experiment, "simulator_type", "Standard") == "HPC":
        flash(
            "This page is only available for Standard and Forum experiments.",
            "warning",
        )
        return (
            None,
            None,
            redirect(url_for("experiments.experiment_details", uid=uid)),
        )

    admin_user = _current_admin_user_or_none()
    if require_manage and not user_can_manage_experiment(admin_user, experiment):
        flash("You do not have permission to manage this experiment.", "error")
        return (
            None,
            None,
            redirect(url_for("experiments.experiment_details", uid=uid)),
        )

    from y_web.utils.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return None, None, redirect(url_for("experiments.settings"))

    experiment_dir = os.path.join(base_dir, "y_web", "experiments", exp_folder)
    os.makedirs(experiment_dir, exist_ok=True)
    return experiment, experiment_dir, None


def _normalize_forum_embedding_service(value):
    """Normalize forum memory embedding provider name."""
    service = str(value or "").strip().lower()
    if service in {"ollama"}:
        return service
    return ""


def _normalize_forum_embedding_host(value):
    """Normalize forum memory embedding host input."""
    host = str(value or "").strip()
    if not host:
        return ""
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    host = host.rstrip("/")
    if host.endswith("/v1"):
        host = host[:-3].rstrip("/")
    return host


def _normalize_embedding_service(value):
    return _normalize_forum_embedding_service(value)


def _normalize_embedding_host(value):
    return _normalize_forum_embedding_host(value)


def _read_forum_feed_health(experiment, experiment_dir):
    """Return configured and loaded forum feed counts for the experiment."""
    health = {
        "rss_feed_count": 0,
        "image_feed_count": 0,
        "article_count": 0,
        "image_post_count": 0,
        "rss_post_count": 0,
        "image_share_post_count": 0,
    }

    rss_path = os.path.join(experiment_dir, "rss_feeds.json")
    image_path = os.path.join(experiment_dir, "image_feeds.json")

    try:
        if os.path.exists(rss_path):
            with open(rss_path, "r") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                health["rss_feed_count"] = len(data)
    except Exception:
        pass

    try:
        if os.path.exists(image_path):
            with open(image_path, "r") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                health["image_feed_count"] = len(data)
    except Exception:
        pass

    try:
        if _get_database_type() == "sqlite":
            import sqlite3

            db_path = os.path.join(experiment_dir, "database_server.db")
            if not os.path.exists(db_path):
                return health
            conn = sqlite3.connect(db_path)
            try:
                health["article_count"] = int(
                    conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
                )
                health["image_post_count"] = int(
                    conn.execute("SELECT COUNT(*) FROM image_posts").fetchone()[0]
                )
                health["rss_post_count"] = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM post WHERE news_id IS NOT NULL AND news_id NOT IN (-1, 0)"
                    ).fetchone()[0]
                )
                health["image_share_post_count"] = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM post WHERE image_post_id IS NOT NULL AND image_post_id NOT IN (-1, 0)"
                    ).fetchone()[0]
                )
            finally:
                conn.close()
        else:
            from sqlalchemy import create_engine, text

            admin_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
            db_name = str(experiment.db_name or "").strip()
            if not db_name:
                return health
            db_uri = admin_uri.rsplit("/", 1)[0] + "/" + db_name
            engine = create_engine(db_uri)
            try:
                with engine.connect() as conn:
                    health["article_count"] = int(conn.execute(text("SELECT COUNT(*) FROM articles")).scalar() or 0)
                    health["image_post_count"] = int(conn.execute(text("SELECT COUNT(*) FROM image_posts")).scalar() or 0)
                    health["rss_post_count"] = int(
                        conn.execute(text("SELECT COUNT(*) FROM post WHERE news_id IS NOT NULL AND news_id NOT IN (-1, 0)")).scalar()
                        or 0
                    )
                    health["image_share_post_count"] = int(
                        conn.execute(text("SELECT COUNT(*) FROM post WHERE image_post_id IS NOT NULL AND image_post_id NOT IN (-1, 0)")).scalar()
                        or 0
                    )
            finally:
                engine.dispose()
    except Exception:
        pass

    return health


def _read_forum_embedding_settings(experiment_dir):
    """Load persisted forum memory embedding settings from config_server.json."""
    config_path = os.path.join(experiment_dir, "config_server.json")
    settings = dict(DEFAULT_FORUM_EMBEDDING_SETTINGS)
    if not os.path.exists(config_path):
        return settings
    try:
        with open(config_path, "r") as handle:
            config = json.load(handle)
    except (json.JSONDecodeError, IOError):
        return settings

    persisted = config.get("memory_embeddings")
    if not isinstance(persisted, dict):
        return settings

    settings["service"] = _normalize_forum_embedding_service(persisted.get("service"))
    settings["host"] = _normalize_forum_embedding_host(persisted.get("host"))
    settings["model"] = str(persisted.get("model") or "").strip()
    return settings


def _read_experiment_embedding_settings(experiment_dir):
    """Load persisted memory embedding settings from config_server.json."""
    config_path = os.path.join(experiment_dir, "config_server.json")
    settings = dict(DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS)
    if not os.path.exists(config_path):
        return settings
    try:
        with open(config_path, "r") as handle:
            config = json.load(handle)
    except (json.JSONDecodeError, IOError):
        return settings

    persisted = config.get("memory_embeddings")
    if not isinstance(persisted, dict):
        return settings

    settings["service"] = _normalize_embedding_service(persisted.get("service"))
    settings["host"] = _normalize_embedding_host(persisted.get("host"))
    settings["model"] = str(persisted.get("model") or "").strip()
    return settings


def _read_forum_avatar_settings(experiment_dir):
    """Load persisted forum avatar settings from config_server.json."""
    from y_web.utils.avatars import normalize_forum_avatar_mode

    config_path = os.path.join(experiment_dir, "config_server.json")
    settings = dict(DEFAULT_FORUM_AVATAR_SETTINGS)
    if not os.path.exists(config_path):
        return settings
    try:
        with open(config_path, "r") as handle:
            config = json.load(handle)
    except (json.JSONDecodeError, IOError):
        return settings

    settings["mode"] = normalize_forum_avatar_mode(config.get("avatar_mode"))
    return settings


def _serialize_download_notification(notification):
    """Convert notification model to JSON-safe structure."""
    clean_message, related_exp_ids = _extract_related_experiment_ids(
        notification.message
    )
    related_experiments = []
    if related_exp_ids:
        experiments = Exps.query.filter(Exps.idexp.in_(related_exp_ids)).all()
        exp_map = {exp.idexp: exp for exp in experiments}
        for exp_id in related_exp_ids:
            exp = exp_map.get(exp_id)
            if exp:
                related_experiments.append(
                    {
                        "id": exp.idexp,
                        "name": exp.exp_name,
                        "url": url_for("experiments.experiment_details", uid=exp.idexp),
                    }
                )

    action_url = (
        url_for(
            "experiments.download_notification_resource",
            notification_id=notification.id,
        )
        if notification.status == "ready" and notification.resource_path
        else None
    )
    return {
        "id": notification.id,
        "title": notification.title,
        "message": clean_message,
        "status": notification.status,
        "resource_name": notification.resource_name,
        "is_read": bool(notification.is_read),
        "created_at": (
            notification.created_at.isoformat() if notification.created_at else None
        ),
        "updated_at": (
            notification.updated_at.isoformat() if notification.updated_at else None
        ),
        "action_url": action_url,
        "download_url": action_url,
        "related_experiments": related_experiments,
    }


def _inject_related_experiment_ids(message, exp_ids):
    """Attach experiment IDs marker to message for link rendering without schema changes."""
    if not exp_ids:
        return message
    normalized = []
    seen = set()
    for exp_id in exp_ids:
        try:
            eid = int(exp_id)
        except (TypeError, ValueError):
            continue
        if eid not in seen:
            normalized.append(eid)
            seen.add(eid)
    if not normalized:
        return message
    return f"{(message or '').strip()} [exp_ids:{','.join(str(eid) for eid in normalized)}]"


def _extract_related_experiment_ids(message):
    """Extract encoded related experiment IDs from message."""
    text = message or ""
    exp_ids = []
    seen = set()
    for match in _EXP_IDS_MARKER_RE.finditer(text):
        ids_raw = match.group(1)
        for token in ids_raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                eid = int(token)
            except ValueError:
                continue
            if eid not in seen:
                exp_ids.append(eid)
                seen.add(eid)

    clean_message = _EXP_IDS_MARKER_RE.sub("", text)
    clean_message = re.sub(r"\s{2,}", " ", clean_message).strip()
    return clean_message, exp_ids


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

    return render_template(
        "admin/visibility_settings.html",
        manageable_experiments=manageable_experiments,
        researcher_users=researcher_users,
        group_names=group_names,
        shared_rows=shared_rows,
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
        from y_web.experiment_context import register_experiment_database

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
                from y_web.utils.path_utils import get_writable_path

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

        from y_web.utils.experiment_schema import ensure_experiment_schema_for_uri

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
    opinions_enabled,
    db_uri,
    topics,
    data_path,
    is_remote=False,
):
    """Generate config file for Standard simulator type."""
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
        "opinions_enabled": opinions_enabled,
        "database_uri": db_uri,
        "topics": [t.strip() for t in topics if t.strip()],
        "data_path": data_path,
        "is_remote": is_remote,
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
    db_config_dict=None,
    is_remote=False,
):
    """Generate config file for HPC simulator type."""
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
    opinions_enabled = request.form.get("opinion_annotation") == "true"

    # Get annotation settings
    toxicity_annotation = request.form.get("toxicity_annotation") == "true"
    perspective_api = (
        request.form.get("perspective_api") if toxicity_annotation else None
    )
    sentiment_annotation = request.form.get("sentiment_annotation") == "true"
    emotion_annotation = request.form.get("emotion_annotation") == "true"

    if platform_type == "forum":
        opinions_enabled = False
        toxicity_annotation = False
        perspective_api = None
        sentiment_annotation = False
        emotion_annotation = False

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

        from y_web.utils.experiment_schema import ensure_experiment_schema_for_uri

        if db_type == "sqlite" and simulator_type == "Standard":
            ensure_experiment_schema_for_uri(f"sqlite:///{db_uri}")
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
            opinions_enabled=opinions_enabled,
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
    if opinions_enabled:
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

    normalized_ids = _resolve_bulk_experiment_ids(exp_ids)

    if not normalized_ids:
        flash("No experiments selected for deletion.", "warning")
        return redirect(url_for("experiments.settings"))

    deleted_count = 0
    failed_ids = []
    admin_user = _current_admin_user_or_none()

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
        from y_web.utils.log_metrics import update_client_log_metrics
        from y_web.utils.path_utils import get_writable_path

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
    try:
        from y_web.utils.path_utils import get_writable_path

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
            from y_web.utils.path_utils import get_writable_path

            base_dir = get_writable_path()
            exp_folder = _get_experiment_folder(base_dir, experiment, _get_database_type())
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
    memory_enabled = _is_checked("memory_enabled")
    perspective_api = (request.form.get("perspective_api") or "").strip()

    if not bool(getattr(exp, "llm_agents_enabled", 0)):
        toxicity_enabled = False
        emotion_enabled = False
        sentiment_enabled = False
        perspective_api = ""

    opinions_enabled = opinion_dynamics_enabled

    existing = [a.strip() for a in (exp.annotations or "").split(",") if a.strip()]
    annotation_set = set(existing)
    for key, enabled in (
        ("toxicity", toxicity_enabled),
        ("emotion", emotion_enabled),
        ("sentiment", sentiment_enabled),
        ("opinions", opinions_enabled),
    ):
        if enabled:
            annotation_set.add(key)
        else:
            annotation_set.discard(key)
    exp.annotations = ",".join(sorted(annotation_set))

    try:
        from y_web.utils.path_utils import get_writable_path

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
        config["opinions_enabled"] = opinions_enabled
        config["opinion_dynamics_enabled"] = opinion_dynamics_enabled
        config["perspective_api"] = perspective_api if toxicity_enabled else None
        memory_config = config.get("memory")
        if not isinstance(memory_config, dict):
            memory_config = {}
        memory_config["enabled"] = bool(memory_enabled)
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

        from y_web.utils.path_utils import get_writable_path

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

    from y_web.utils.path_utils import get_writable_path

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

        from y_web.utils.log_metrics import (
            has_server_log_files,
            update_client_log_metrics,
            update_server_log_metrics,
        )
        from y_web.utils.path_utils import get_writable_path

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

        from y_web.utils.log_metrics import update_client_log_metrics
        from y_web.utils.path_utils import get_writable_path

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

    from y_web.utils.path_utils import get_writable_path

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

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    experiment = Exps.query.filter_by(idexp=uid).first()

    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.experiments"))

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

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()

    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.experiments"))

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


@experiments.route("/admin/update_prompts_hpc/<int:uid>", methods=["POST"])
@login_required
def update_prompts_hpc(uid):
    """Update HPC prompts."""
    check_privileges(current_user.username)

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()

    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.experiments"))

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


@experiments.route("/admin/rss_feeds/<int:uid>")
@login_required
def rss_feeds(uid):
    """Display and edit forum RSS and URL feeds."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")

    rss_feeds_data = []
    if os.path.exists(rss_feeds_path):
        try:
            with open(rss_feeds_path, "r") as handle:
                rss_feeds_data = json.load(handle)
        except (json.JSONDecodeError, IOError):
            rss_feeds_data = []

    url_feeds_data = []
    if os.path.exists(url_feeds_path):
        try:
            with open(url_feeds_path, "r") as handle:
                url_feeds_data = [line.strip() for line in handle if line.strip()]
        except IOError:
            url_feeds_data = []

    return render_template(
        "admin/rss_feeds.html",
        experiment=experiment,
        rss_feeds=rss_feeds_data,
        url_feeds=url_feeds_data,
    )


@experiments.route("/admin/update_rss_feeds/<int:uid>", methods=["POST"])
@login_required
def update_rss_feeds(uid):
    """Persist forum RSS feeds configuration."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    feeds_json = request.form.get("rss_feeds_json", "[]")

    try:
        feeds = _normalize_rss_feeds_payload(json.loads(feeds_json))
    except json.JSONDecodeError:
        flash("Invalid RSS feeds payload; changes were not saved.", "error")
        return redirect(request.referrer or url_for("experiments.rss_feeds", uid=uid))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("experiments.rss_feeds", uid=uid))

    with open(rss_feeds_path, "w") as handle:
        json.dump(feeds, handle, indent=2)

    flash("RSS feeds updated successfully.", "success")
    return redirect(request.referrer or url_for("experiments.rss_feeds", uid=uid))


@experiments.route("/admin/update_url_feeds/<int:uid>", methods=["POST"])
@login_required
def update_url_feeds(uid):
    """Persist forum URL feeds configuration."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")
    urls_text = request.form.get("url_feeds_text", "")
    urls = [line.strip() for line in urls_text.splitlines() if line.strip()]

    with open(url_feeds_path, "w") as handle:
        handle.write("\n".join(urls))

    flash("URL feeds updated successfully.", "success")
    return redirect(request.referrer or url_for("experiments.rss_feeds", uid=uid))


@experiments.route("/admin/api/parse_rss_feed", methods=["POST"])
@login_required
def parse_rss_feed():
    """Parse an RSS URL and return basic feed metadata."""
    check_privileges(current_user.username)

    import feedparser

    payload = request.get_json(silent=True) or {}
    feed_url = str(payload.get("feed_url", "")).strip()
    if not feed_url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        feed_content = _read_feed_with_headers(feed_url)
        feed = feedparser.parse(feed_content)
        if feed.bozo and not feed.entries:
            return jsonify({"error": "Invalid RSS feed URL"}), 400
        parsed_url = urlparse(feed_url)
        return jsonify(
            {
                "name": feed.feed.get("title", parsed_url.netloc or feed_url),
                "feed_url": feed_url,
                "url_site": parsed_url.netloc,
                "description": feed.feed.get("description", ""),
                "entries_count": len(feed.entries),
            }
        )
    except HTTPError as exc:
        return jsonify({"error": f"Feed source returned HTTP {exc.code}."}), 400
    except URLError:
        return jsonify({"error": "Feed source could not be reached."}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/upload_rss_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_rss_feeds(uid):
    """Bulk upload RSS feeds from JSON."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    rss_feeds_path = os.path.join(experiment_dir, "rss_feeds.json")
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = upload.read().decode("utf-8")
        new_feeds = _normalize_rss_feeds_payload(json.loads(content))

        mode = request.form.get("mode", "replace")
        if mode == "merge" and os.path.exists(rss_feeds_path):
            with open(rss_feeds_path, "r") as handle:
                existing_feeds = _normalize_rss_feeds_payload(json.load(handle))
            new_feeds = _normalize_rss_feeds_payload(existing_feeds + new_feeds)

        with open(rss_feeds_path, "w") as handle:
            json.dump(new_feeds, handle, indent=2)
        return jsonify({"success": True, "count": len(new_feeds)})
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format"}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/upload_url_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_url_feeds(uid):
    """Bulk upload URL feeds from text or JSON."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    url_feeds_path = os.path.join(experiment_dir, "url_feeds.txt")
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = upload.read().decode("utf-8")
        try:
            urls = json.loads(content)
            if isinstance(urls, list):
                urls = [str(item).strip() for item in urls if str(item).strip()]
            else:
                urls = [line.strip() for line in content.splitlines() if line.strip()]
        except json.JSONDecodeError:
            urls = [line.strip() for line in content.splitlines() if line.strip()]

        mode = request.form.get("mode", "replace")
        if mode == "merge" and os.path.exists(url_feeds_path):
            with open(url_feeds_path, "r") as handle:
                existing_urls = {line.strip() for line in handle if line.strip()}
            urls = sorted(existing_urls | set(urls))

        with open(url_feeds_path, "w") as handle:
            handle.write("\n".join(urls))
        return jsonify({"success": True, "count": len(urls)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/image_feeds/<int:uid>")
@login_required
def image_feeds(uid):
    """Display and edit forum image feeds."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    image_feeds_data = []
    if os.path.exists(image_feeds_path):
        try:
            with open(image_feeds_path, "r") as handle:
                image_feeds_data = json.load(handle)
        except (json.JSONDecodeError, IOError):
            image_feeds_data = []

    available_interests = sorted(
        [
            "animals",
            "art",
            "books",
            "celebrities",
            "cooking",
            "creative",
            "cute",
            "design",
            "education",
            "entertainment",
            "fitness",
            "food",
            "fun",
            "gaming",
            "general",
            "geek",
            "history",
            "humor",
            "memes",
            "movies",
            "music",
            "nature",
            "news",
            "pets",
            "photography",
            "politics",
            "science",
            "sports",
            "technology",
            "travel",
            "tv",
            "wholesome",
        ]
    )

    return render_template(
        "admin/image_feeds.html",
        experiment=experiment,
        image_feeds=image_feeds_data,
        available_interests=available_interests,
    )


@experiments.route("/admin/update_image_feeds/<int:uid>", methods=["POST"])
@login_required
def update_image_feeds(uid):
    """Persist forum image feeds configuration."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    feeds_json = request.form.get("image_feeds_json", "[]")
    try:
        feeds = _normalize_image_feeds_payload(json.loads(feeds_json))
    except json.JSONDecodeError:
        flash("Invalid image feeds payload; changes were not saved.", "error")
        return redirect(request.referrer or url_for("experiments.image_feeds", uid=uid))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("experiments.image_feeds", uid=uid))

    with open(image_feeds_path, "w") as handle:
        json.dump(feeds, handle, indent=2)

    flash("Image feeds updated successfully.", "success")
    return redirect(request.referrer or url_for("experiments.image_feeds", uid=uid))


@experiments.route("/admin/upload_image_feeds/<int:uid>", methods=["POST"])
@login_required
def upload_image_feeds(uid):
    """Bulk upload image feeds from JSON."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    image_feeds_path = os.path.join(experiment_dir, "image_feeds.json")
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    upload = request.files["file"]
    if upload.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        content = upload.read().decode("utf-8")
        normalized_feeds = _normalize_image_feeds_payload(json.loads(content))

        mode = request.form.get("mode", "replace")
        if mode == "merge" and os.path.exists(image_feeds_path):
            with open(image_feeds_path, "r") as handle:
                existing_feeds = _normalize_image_feeds_payload(json.load(handle))

            merged = []
            by_subreddit = {}
            for feed in existing_feeds:
                if not isinstance(feed, dict):
                    continue
                subreddit = str(feed.get("subreddit", "")).strip().lower()
                if not subreddit:
                    continue
                merged_feed = {
                    "subreddit": subreddit,
                    "interests": list(feed.get("interests") or []),
                }
                merged.append(merged_feed)
                by_subreddit[subreddit] = merged_feed

            for feed in normalized_feeds:
                subreddit = feed["subreddit"]
                if subreddit in by_subreddit:
                    combined = []
                    seen = set()
                    for label in list(
                        by_subreddit[subreddit].get("interests") or []
                    ) + list(feed.get("interests") or []):
                        label = str(label).strip()
                        if not label or label in seen:
                            continue
                        seen.add(label)
                        combined.append(label)
                    by_subreddit[subreddit]["interests"] = combined
                else:
                    merged.append(feed)
                    by_subreddit[subreddit] = feed
            normalized_feeds = merged

        with open(image_feeds_path, "w") as handle:
            json.dump(normalized_feeds, handle, indent=2)
        return jsonify({"success": True, "count": len(normalized_feeds)})
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON format"}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/api/parse_image_feed", methods=["POST"])
@login_required
def parse_image_feed():
    """Parse a subreddit RSS feed and extract sample image URLs."""
    check_privileges(current_user.username)

    import re

    import feedparser

    payload = request.get_json(silent=True) or {}
    subreddit = str(payload.get("subreddit", "")).strip().lower()
    if not subreddit:
        return jsonify({"error": "No subreddit provided"}), 400

    subreddit = subreddit[2:] if subreddit.startswith("r/") else subreddit
    feed_url = f"https://www.reddit.com/r/{quote(subreddit)}.rss"

    try:
        feed_content = _read_feed_with_headers(feed_url)
        feed = feedparser.parse(feed_content)
        if feed.bozo and not feed.entries:
            return jsonify({"error": f"Could not parse r/{subreddit}."}), 400
        if not feed.entries:
            return jsonify({"error": f"No posts found in r/{subreddit}"}), 400

        image_pattern = re.compile(r"\.(jpg|jpeg|png|gif|webp)(\?.*)?$", re.IGNORECASE)
        image_hosts = ["i.redd.it", "i.imgur.com", "preview.redd.it"]
        images = []
        nsfw_count = 0

        for entry in feed.entries[:50]:
            is_nsfw = False
            if getattr(entry, "over_18", False):
                is_nsfw = True
            elif "[nsfw]" in entry.get("title", "").lower():
                is_nsfw = True
            elif hasattr(entry, "tags"):
                for tag in entry.tags:
                    if tag.get("term", "").lower() == "nsfw":
                        is_nsfw = True
                        break

            if is_nsfw:
                nsfw_count += 1
                continue

            image_url = None
            link = entry.get("link", "")
            if image_pattern.search(link) or any(host in link for host in image_hosts):
                image_url = link

            if not image_url and hasattr(entry, "media_content"):
                for media in entry.media_content:
                    media_url = media.get("url", "")
                    if image_pattern.search(media_url) or any(
                        host in media_url for host in image_hosts
                    ):
                        image_url = media_url
                        break

            if not image_url and hasattr(entry, "media_thumbnail"):
                for thumb in entry.media_thumbnail:
                    media_url = thumb.get("url", "")
                    if media_url:
                        image_url = media_url
                        break

            if image_url:
                images.append(image_url)

        return jsonify(
            {
                "subreddit": subreddit,
                "feed_url": feed_url,
                "image_count": len(images),
                "nsfw_filtered": nsfw_count,
                "sample_images": images[:5],
            }
        )
    except HTTPError as exc:
        if exc.code == 404:
            return jsonify({"error": f"r/{subreddit} does not exist."}), 400
        return (
            jsonify(
                {
                    "error": (
                        f"Reddit returned HTTP {exc.code} while loading r/{subreddit}. "
                        "Retry later."
                    )
                }
            ),
            400,
        )
    except URLError:
        return jsonify({"error": "Reddit could not be reached. Retry later."}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@experiments.route("/admin/feed_limits/<int:uid>", methods=["GET"])
@login_required
def feed_limits(uid):
    """Display and edit feed retrieval limits for a forum experiment."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    config_path = os.path.join(experiment_dir, "config_server.json")
    feed_limits_data = dict(DEFAULT_FEED_LIMITS)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as handle:
                config = json.load(handle)
            if isinstance(config.get("feed_limits"), dict):
                feed_limits_data.update(config["feed_limits"])
        except (json.JSONDecodeError, IOError):
            pass

    return render_template(
        "admin/feed_limits.html",
        experiment=experiment,
        feed_limits=feed_limits_data,
    )


@experiments.route("/admin/embedding_settings/<int:uid>", methods=["GET"])
@login_required
def embedding_settings(uid):
    """Display and edit memory embedding backend settings for standard/forum experiments."""
    experiment, experiment_dir, error_response = _load_memory_capable_experiment_context(
        uid
    )
    if error_response is not None:
        return error_response

    return render_template(
        "admin/embedding_settings.html",
        experiment=experiment,
        embedding_settings=_read_experiment_embedding_settings(experiment_dir),
        platform_label=(
            "Forum" if experiment.platform_type == "forum" else "Microblogging"
        ),
        server_label=(
            "YServerReddit" if experiment.platform_type == "forum" else "YServer"
        ),
    )


@experiments.route("/admin/update_embedding_settings/<int:uid>", methods=["POST"])
@login_required
def update_embedding_settings(uid):
    """Persist memory embedding backend settings to config_server.json."""
    experiment, experiment_dir, error_response = _load_memory_capable_experiment_context(
        uid
    )
    if error_response is not None:
        return error_response

    config_path = os.path.join(experiment_dir, "config_server.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as handle:
                config = json.load(handle)
        except (json.JSONDecodeError, IOError):
            config = {}

    service = _normalize_embedding_service(request.form.get("embedding_service"))
    host = _normalize_embedding_host(request.form.get("embedding_host"))
    model = str(request.form.get("embedding_model") or "").strip()

    if service == "ollama":
        if not host:
            flash(
                "An Ollama host is required when memory embeddings are enabled.",
                "error",
            )
            return redirect(
                request.referrer or url_for("experiments.embedding_settings", uid=uid)
            )
        if not model:
            flash("Select an embedding model before saving the configuration.", "error")
            return redirect(
                request.referrer or url_for("experiments.embedding_settings", uid=uid)
            )
        config["memory_embeddings"] = {
            "service": service,
            "host": host,
            "model": model,
        }
    else:
        config["memory_embeddings"] = dict(DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS)

    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    flash("Embedding settings updated successfully.", "success")
    return redirect(
        request.referrer or url_for("experiments.embedding_settings", uid=uid)
    )


@experiments.route("/admin/update_forum_avatar_mode/<int:uid>", methods=["POST"])
@login_required
def update_forum_avatar_mode(uid):
    """Persist forum avatar mode to config_server.json."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    config_path = os.path.join(experiment_dir, "config_server.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as handle:
                config = json.load(handle)
        except (json.JSONDecodeError, IOError):
            config = {}

    enabled_flag = (
        str(request.form.get("use_actual_profile_pics") or "").strip().lower()
    )
    requested_mode = request.form.get("avatar_mode")
    mode = normalize_forum_avatar_mode(requested_mode)
    if enabled_flag in {"1", "true", "on", "yes"}:
        mode = "actual"

    config["avatar_mode"] = mode

    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    flash("Forum avatar mode updated successfully.", "success")
    return redirect(
        request.referrer or url_for("experiments.experiment_details", uid=uid)
    )


@experiments.route("/admin/update_feed_limits/<int:uid>", methods=["POST"])
@login_required
def update_feed_limits(uid):
    """Update feed retrieval limits for a forum experiment."""
    experiment, experiment_dir, error_response = _load_forum_experiment_context(uid)
    if error_response is not None:
        return error_response

    config_path = os.path.join(experiment_dir, "config_server.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as handle:
                config = json.load(handle)
        except (json.JSONDecodeError, IOError):
            config = {}

    try:
        config["feed_limits"] = {
            "rss_entries_per_feed": _parse_required_feed_limit(
                "rss_entries_per_feed", int, "RSS entries per feed", minimum=1
            ),
            "reddit_entries_per_feed": _parse_required_feed_limit(
                "reddit_entries_per_feed", int, "Reddit entries per feed", minimum=1
            ),
            "reddit_pages": _parse_required_feed_limit(
                "reddit_pages", int, "Reddit pages", minimum=1
            ),
            "reddit_rate_limit_seconds": _parse_required_feed_limit(
                "reddit_rate_limit_seconds",
                float,
                "Reddit rate limit seconds",
                minimum=0,
            ),
            "db_fallback_limit": _parse_required_feed_limit(
                "db_fallback_limit", int, "Database fallback limit", minimum=1
            ),
            "image_entries_per_feed": _parse_required_feed_limit(
                "image_entries_per_feed", int, "Image entries per feed", minimum=1
            ),
        }
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("experiments.feed_limits", uid=uid))

    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    flash("Feed limits updated successfully.", "success")
    return redirect(request.referrer or url_for("experiments.feed_limits", uid=uid))


def _get_database_type():
    """Get active admin database backend type."""
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        return "postgresql"
    return "sqlite"


def _get_experiment_folder(base_dir, experiment, db_type):
    """Resolve experiment folder path for sqlite/postgresql layouts."""
    if db_type == "sqlite":
        return os.path.join(
            base_dir,
            f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}",
        )

    return os.path.join(
        base_dir,
        f"y_web{os.sep}experiments{os.sep}{experiment.db_name.removeprefix('experiments_')}",
    )


def _create_sqlite_copy_for_postgresql(experiment, folder):
    """Create SQLite mirror DB file for PostgreSQL experiment export."""
    import sqlite3
    from urllib.parse import urlparse

    from sqlalchemy import create_engine, inspect, text

    current_uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    parsed_uri = urlparse(current_uri)

    user = parsed_uri.username or "postgres"
    password = parsed_uri.password or "password"
    host = parsed_uri.hostname or "localhost"
    port_db = parsed_uri.port or 5432

    pg_uri = f"postgresql://{user}:{password}@{host}:{port_db}/{experiment.db_name}"
    pg_engine = create_engine(pg_uri)

    sqlite_path = os.path.join(folder, "database_server.db")
    sqlite_uri = f"sqlite:///{sqlite_path}"
    sqlite_engine = create_engine(sqlite_uri)

    inspector = inspect(pg_engine)

    with pg_engine.connect() as pg_conn:
        table_names = inspector.get_table_names()
        sqlite_raw_conn = sqlite3.connect(sqlite_path)
        sqlite_cursor = sqlite_raw_conn.cursor()

        for table_name in table_names:
            result = pg_conn.execute(text(f"SELECT * FROM {table_name}"))
            rows = result.fetchall()
            columns = result.keys()

            if not rows:
                continue

            pg_columns = inspector.get_columns(table_name)
            col_defs = []
            for col in pg_columns:
                col_type = str(col["type"])
                if "INTEGER" in col_type or "SERIAL" in col_type:
                    sqlite_type = "INTEGER"
                elif "REAL" in col_type or "DOUBLE" in col_type or "FLOAT" in col_type:
                    sqlite_type = "REAL"
                elif "TEXT" in col_type or "VARCHAR" in col_type or "CHAR" in col_type:
                    sqlite_type = "TEXT"
                else:
                    sqlite_type = "TEXT"
                col_defs.append(f"{col['name']} {sqlite_type}")

            create_table_sql = (
                f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(col_defs)})"
            )
            sqlite_cursor.execute(create_table_sql)

            placeholders = ", ".join(["?" for _ in columns])
            insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
            for row in rows:
                sqlite_cursor.execute(insert_sql, tuple(row))

        sqlite_raw_conn.commit()
        sqlite_raw_conn.close()

    pg_engine.dispose()
    sqlite_engine.dispose()


def _build_single_experiment_zip(eid, output_zip_path):
    """Build a single experiment zip file and return user-facing name."""
    from y_web.utils.path_utils import get_writable_path

    base_dir = get_writable_path()
    experiment = Exps.query.filter_by(idexp=eid).first()
    if not experiment:
        raise ValueError(f"Experiment {eid} not found")

    db_type = _get_database_type()
    folder = _get_experiment_folder(base_dir, experiment, db_type)
    if not os.path.exists(folder):
        raise FileNotFoundError(f"Experiment folder not found: {folder}")

    if db_type == "postgresql":
        _create_sqlite_copy_for_postgresql(experiment, folder)

    output_base = (
        output_zip_path[:-4] if output_zip_path.endswith(".zip") else output_zip_path
    )
    if os.path.exists(f"{output_base}.zip"):
        os.remove(f"{output_base}.zip")
    shutil.make_archive(output_base, "zip", folder)

    safe_exp_name = _sanitize_filename(experiment.exp_name, f"experiment_{eid}")
    return f"{safe_exp_name}.zip"


def _build_bulk_experiments_zip(exp_ids, output_zip_path):
    """Build a bulk zip containing one zip per experiment."""
    from y_web.utils.path_utils import get_writable_path

    base_dir = get_writable_path()
    db_type = _get_database_type()
    bulk_download_dir = os.path.join(
        base_dir, f"y_web{os.sep}experiments{os.sep}temp_bulk_{uuid.uuid4().hex}"
    )
    os.makedirs(bulk_download_dir, exist_ok=True)

    used_names = set()
    try:
        for eid in exp_ids:
            experiment = Exps.query.filter_by(idexp=eid).first()
            if not experiment:
                continue

            folder = _get_experiment_folder(base_dir, experiment, db_type)
            if not os.path.exists(folder):
                continue

            if db_type == "postgresql":
                try:
                    _create_sqlite_copy_for_postgresql(experiment, folder)
                except Exception as exc:
                    current_app.logger.error(
                        f"Error creating SQLite copy for {experiment.exp_name}: {exc}",
                        exc_info=True,
                    )
                    continue

            safe_exp_name = _sanitize_filename(experiment.exp_name, f"experiment_{eid}")
            if safe_exp_name in used_names:
                safe_exp_name = f"{safe_exp_name}_{eid}"
            used_names.add(safe_exp_name)

            exp_zip_path = os.path.join(bulk_download_dir, safe_exp_name)
            shutil.make_archive(exp_zip_path, "zip", folder)

        output_base = (
            output_zip_path[:-4]
            if output_zip_path.endswith(".zip")
            else output_zip_path
        )
        if os.path.exists(f"{output_base}.zip"):
            os.remove(f"{output_base}.zip")
        shutil.make_archive(output_base, "zip", bulk_download_dir)
    finally:
        shutil.rmtree(bulk_download_dir, ignore_errors=True)

    return "experiments.zip"


def _create_download_notification(user_id, title, message):
    """Create a processing notification entry."""
    notification = DownloadNotification(
        user_id=user_id,
        title=title,
        message=message,
        status="processing",
        is_read=False,
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def _enqueue_user_notification(
    user_id, title, message, status="ready", related_exp_ids=None
):
    """Queue a generic user notification record in current transaction."""
    if related_exp_ids:
        message = _inject_related_experiment_ids(message, related_exp_ids)
    notification = DownloadNotification(
        user_id=user_id,
        title=title,
        message=message,
        status=status,
        is_read=False,
    )
    db.session.add(notification)
    return notification


def _run_single_download_job(app, notification_id, eid):
    """Background worker for single experiment export."""
    with app.app_context():
        notification = DownloadNotification.query.get(notification_id)
        if not notification:
            return

        try:
            temp_data_dir = _notifications_temp_data_dir()
            os.makedirs(temp_data_dir, exist_ok=True)
            file_base = f"exp_{eid}_{notification_id}_{uuid.uuid4().hex[:8]}"
            output_zip_path = os.path.join(temp_data_dir, f"{file_base}.zip")
            download_name = _build_single_experiment_zip(eid, output_zip_path)

            notification = DownloadNotification.query.get(notification_id)
            if not notification:
                return
            if notification.status == "cancelled":
                if os.path.exists(output_zip_path) and _is_path_in_temp_data(
                    output_zip_path
                ):
                    os.remove(output_zip_path)
                return

            notification.status = "ready"
            notification.resource_path = output_zip_path
            notification.resource_name = download_name
            notification.message = _inject_related_experiment_ids(
                "Your experiment archive is ready to download.", [eid]
            )
            notification.error_message = None
            db.session.commit()
        except Exception as exc:
            current_app.logger.error(
                f"Error generating async experiment archive (eid={eid}): {exc}",
                exc_info=True,
            )
            notification = DownloadNotification.query.get(notification_id)
            if notification and notification.status != "cancelled":
                notification.status = "failed"
                notification.message = "Archive generation failed."
                notification.error_message = str(exc)[:500]
                db.session.commit()
        finally:
            db.session.remove()


def _run_bulk_download_job(app, notification_id, exp_ids):
    """Background worker for bulk experiments export."""
    with app.app_context():
        notification = DownloadNotification.query.get(notification_id)
        if not notification:
            return

        try:
            temp_data_dir = _notifications_temp_data_dir()
            os.makedirs(temp_data_dir, exist_ok=True)
            file_base = f"bulk_{notification_id}_{uuid.uuid4().hex[:8]}"
            output_zip_path = os.path.join(temp_data_dir, f"{file_base}.zip")
            download_name = _build_bulk_experiments_zip(exp_ids, output_zip_path)

            notification = DownloadNotification.query.get(notification_id)
            if not notification:
                return
            if notification.status == "cancelled":
                if os.path.exists(output_zip_path) and _is_path_in_temp_data(
                    output_zip_path
                ):
                    os.remove(output_zip_path)
                return

            notification.status = "ready"
            notification.resource_path = output_zip_path
            notification.resource_name = download_name
            notification.message = _inject_related_experiment_ids(
                "Your bulk experiments archive is ready to download.", exp_ids
            )
            notification.error_message = None
            db.session.commit()
        except Exception as exc:
            current_app.logger.error(
                f"Error generating async bulk archive: {exc}", exc_info=True
            )
            notification = DownloadNotification.query.get(notification_id)
            if notification and notification.status != "cancelled":
                notification.status = "failed"
                notification.message = "Bulk archive generation failed."
                notification.error_message = str(exc)[:500]
                db.session.commit()
        finally:
            db.session.remove()


def _resolve_bulk_experiment_ids(exp_ids_payload):
    """Resolve incoming payload to a deduplicated integer experiment ID list."""
    if exp_ids_payload == "all":
        completed_experiments = Exps.query.filter_by(exp_status="completed").all()
        return [exp.idexp for exp in completed_experiments]

    if isinstance(exp_ids_payload, dict) and exp_ids_payload.get("all"):
        status_filter = str(exp_ids_payload.get("status", "")).strip()
        query = Exps.query
        if status_filter:
            if status_filter == "stopped_scheduled":
                query = query.filter(Exps.exp_status.in_(["stopped", "scheduled"]))
            else:
                query = query.filter(Exps.exp_status == status_filter)
        return [exp.idexp for exp in query.all()]

    if isinstance(exp_ids_payload, dict) and exp_ids_payload.get("group"):
        group_name = str(exp_ids_payload.get("group")).strip()
        status_filter = str(exp_ids_payload.get("status", "")).strip()
        query = Exps.query.filter(Exps.exp_group == group_name)
        if status_filter:
            if status_filter == "stopped_scheduled":
                query = query.filter(Exps.exp_status.in_(["stopped", "scheduled"]))
            else:
                query = query.filter(Exps.exp_status == status_filter)
        return [exp.idexp for exp in query.all()]

    if not isinstance(exp_ids_payload, list):
        return []

    normalized_ids = []
    seen = set()
    for eid in exp_ids_payload:
        try:
            eid_int = int(eid)
        except (TypeError, ValueError):
            continue
        if eid_int not in seen:
            normalized_ids.append(eid_int)
            seen.add(eid_int)
    return normalized_ids


@experiments.route("/admin/download_experiment/<int:eid>", methods=["POST", "GET"])
@login_required
def download_experiment_file(eid):
    """Queue asynchronous experiment archive generation and notify when ready."""
    check_privileges(current_user.username)

    experiment = Exps.query.filter_by(idexp=eid).first()
    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user()
    if not admin_user:
        flash("Unable to resolve current admin user.", "error")
        return redirect(url_for("experiments.settings"))

    notification = _create_download_notification(
        admin_user.id,
        title=f"Export {experiment.exp_name}",
        message=_inject_related_experiment_ids(
            "Preparing experiment archive in background...", [eid]
        ),
    )
    app_obj = current_app._get_current_object()
    threading.Thread(
        target=_run_single_download_job,
        args=(app_obj, notification.id, eid),
        daemon=True,
    ).start()

    flash(
        "Archive generation started. You will be notified when the file is ready.",
        "info",
    )
    return redirect(
        request.referrer or url_for("experiments.experiment_details", uid=eid)
    )


@experiments.route("/admin/download_experiments_bulk", methods=["POST"])
@login_required
def download_experiments_bulk():
    """Queue asynchronous bulk archive generation for selected experiments."""
    check_privileges(current_user.username)

    exp_ids_json = request.form.get("exp_ids", "[]")
    try:
        exp_ids_payload = json.loads(exp_ids_json)
    except json.JSONDecodeError:
        flash("Invalid experiment IDs provided.", "error")
        return redirect(url_for("experiments.settings"))

    exp_ids = _resolve_bulk_experiment_ids(exp_ids_payload)
    if not exp_ids:
        flash("No experiments selected for download.", "warning")
        return redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user()
    if not admin_user:
        flash("Unable to resolve current admin user.", "error")
        return redirect(url_for("experiments.settings"))

    notification = _create_download_notification(
        admin_user.id,
        title="Bulk export experiments",
        message=_inject_related_experiment_ids(
            f"Preparing archive for {len(exp_ids)} experiment(s) in background...",
            exp_ids,
        ),
    )
    app_obj = current_app._get_current_object()
    threading.Thread(
        target=_run_bulk_download_job,
        args=(app_obj, notification.id, exp_ids),
        daemon=True,
    ).start()

    flash(
        "Bulk archive generation started. You will be notified when the file is ready.",
        "info",
    )
    return redirect(request.referrer or url_for("experiments.settings"))


@experiments.route("/admin/notifications")
@experiments.route("/admin/download_notifications")
@login_required
def download_notifications_page():
    """Render all download notifications for current admin user."""
    check_privileges(current_user.username)
    admin_user = _current_admin_user()
    if not admin_user:
        flash("Unable to resolve current admin user.", "error")
        return redirect(url_for("experiments.settings"))

    notifications = (
        DownloadNotification.query.filter_by(user_id=admin_user.id)
        .order_by(
            DownloadNotification.created_at.desc(), DownloadNotification.id.desc()
        )
        .all()
    )
    return render_template(
        "admin/download_notifications.html",
        notifications=[
            _serialize_download_notification(item) for item in notifications
        ],
    )


@experiments.route("/admin/notifications/data")
@experiments.route("/admin/download_notifications/data")
@login_required
def download_notifications_data():
    """Return notifications for header dropdown and dedicated page."""
    check_privileges(current_user.username)
    admin_user = _current_admin_user()
    if not admin_user:
        return jsonify({"items": [], "unread_count": 0})

    limit = request.args.get("limit", default=5, type=int)
    if limit < 1:
        limit = 5
    if limit > 100:
        limit = 100

    query = DownloadNotification.query.filter_by(
        user_id=admin_user.id, is_read=False
    ).order_by(DownloadNotification.created_at.desc(), DownloadNotification.id.desc())
    notifications = query.limit(limit).all()
    unread_count = DownloadNotification.query.filter_by(
        user_id=admin_user.id, is_read=False
    ).count()
    return jsonify(
        {
            "items": [_serialize_download_notification(item) for item in notifications],
            "unread_count": unread_count,
        }
    )


@experiments.route("/admin/notifications/<int:notification_id>/read", methods=["POST"])
@experiments.route(
    "/admin/download_notifications/<int:notification_id>/read", methods=["POST"]
)
@login_required
def mark_download_notification_read(notification_id):
    """Mark a download notification as read."""
    check_privileges(current_user.username)
    admin_user = _current_admin_user()
    if not admin_user:
        return jsonify({"success": False, "error": "User not found"}), 404

    notification = DownloadNotification.query.filter_by(
        id=notification_id, user_id=admin_user.id
    ).first()
    if not notification:
        return jsonify({"success": False, "error": "Notification not found"}), 404

    notification.is_read = True
    db.session.commit()
    return jsonify({"success": True})


@experiments.route(
    "/admin/notifications/<int:notification_id>/cancel", methods=["POST"]
)
@experiments.route(
    "/admin/download_notifications/<int:notification_id>/cancel", methods=["POST"]
)
@login_required
def cancel_download_notification(notification_id):
    """Cancel notification and delete related zip from temp_data if present."""
    check_privileges(current_user.username)
    admin_user = _current_admin_user()
    if not admin_user:
        return jsonify({"success": False, "error": "User not found"}), 404

    notification = DownloadNotification.query.filter_by(
        id=notification_id, user_id=admin_user.id
    ).first()
    if not notification:
        return jsonify({"success": False, "error": "Notification not found"}), 404

    if (
        not notification.is_read
        and notification.resource_path
        and _is_path_in_temp_data(notification.resource_path)
        and os.path.exists(notification.resource_path)
    ):
        try:
            os.remove(notification.resource_path)
        except OSError as exc:
            current_app.logger.warning(
                f"Could not delete cancelled notification file: {exc}"
            )

    notification.resource_path = None
    notification.resource_name = None
    notification.status = "cancelled"
    notification.message = "Notification cancelled."
    notification.error_message = None
    db.session.commit()

    return jsonify({"success": True})


@experiments.route(
    "/admin/notifications/<int:notification_id>/delete", methods=["POST"]
)
@experiments.route(
    "/admin/download_notifications/<int:notification_id>/delete", methods=["POST"]
)
@login_required
def delete_notification(notification_id):
    """Delete a notification and remove attached file from temp_data if present."""
    check_privileges(current_user.username)
    admin_user = _current_admin_user()
    if not admin_user:
        return jsonify({"success": False, "error": "User not found"}), 404

    notification = DownloadNotification.query.filter_by(
        id=notification_id, user_id=admin_user.id
    ).first()
    if not notification:
        return jsonify({"success": False, "error": "Notification not found"}), 404

    file_path = notification.resource_path
    if file_path and _is_path_in_temp_data(file_path) and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as exc:
            current_app.logger.warning(f"Could not delete notification file: {exc}")

    db.session.delete(notification)
    db.session.commit()
    return jsonify({"success": True})


@experiments.route(
    "/admin/notifications/<int:notification_id>/download", methods=["GET"]
)
@experiments.route(
    "/admin/download_notifications/<int:notification_id>/download", methods=["GET"]
)
@login_required
def download_notification_resource(notification_id):
    """Download the generated archive for a ready notification."""
    check_privileges(current_user.username)
    admin_user = _current_admin_user()
    if not admin_user:
        flash("Unable to resolve current admin user.", "error")
        return redirect(url_for("experiments.download_notifications_page"))

    notification = DownloadNotification.query.filter_by(
        id=notification_id, user_id=admin_user.id
    ).first()
    if not notification:
        flash("Notification not found.", "error")
        return redirect(url_for("experiments.download_notifications_page"))

    if notification.status != "ready" or not notification.resource_path:
        flash("Requested file is not ready for download.", "warning")
        return redirect(url_for("experiments.download_notifications_page"))

    if not _is_path_in_temp_data(notification.resource_path):
        flash("Invalid download path.", "error")
        return redirect(url_for("experiments.download_notifications_page"))

    if not os.path.exists(notification.resource_path):
        notification.status = "failed"
        notification.message = "Download file is no longer available."
        notification.error_message = "Generated archive not found in temp_data."
        db.session.commit()
        flash("Download file is no longer available.", "error")
        return redirect(url_for("experiments.download_notifications_page"))

    notification.is_read = True
    db.session.commit()

    return send_file_desktop(
        notification.resource_path,
        as_attachment=True,
        download_name=notification.resource_name
        or os.path.basename(notification.resource_path),
    )


@experiments.route("/admin/miscellanea/", methods=["GET"])
@login_required
def miscellanea():
    """
    Display miscellaneous settings page (admin only).

    Returns:
        Rendered miscellaneous settings template
    """
    from y_web.utils.external_processes import get_llm_models

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
    from y_web.telemetry import Telemetry

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

    from y_web.utils.path_utils import get_writable_path

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

    from y_web.utils.experiment_schema import ensure_experiment_schema_for_uri

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


@experiments.route("/admin/hpc_monitor_settings", methods=["GET"])
@login_required
def get_hpc_monitor_settings():
    """
    Get current HPC monitor settings.

    Returns:
        JSON with HPC monitor settings
    """
    check_privileges(current_user.username)

    # Get or create default settings
    settings = HpcMonitorSettings.query.first()
    if not settings:
        settings = HpcMonitorSettings(enabled=True, check_interval_seconds=5)
        db.session.add(settings)
        db.session.commit()

    return jsonify(
        {
            "enabled": settings.enabled,
            "check_interval_seconds": settings.check_interval_seconds,
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

    Returns:
        JSON with success status
    """
    check_privileges(current_user.username)

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    # Get or create settings
    settings = HpcMonitorSettings.query.first()
    if not settings:
        settings = HpcMonitorSettings(enabled=True, check_interval_seconds=5)
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

    # HPC experiment validation: Allow up to 4 HPC experiments per group
    # Check if this is an HPC experiment or if the group already has experiments
    is_hpc = exp.simulator_type == "HPC"

    if is_hpc:
        # Check how many HPC experiments are already in this group
        hpc_count = (
            db.session.query(ExperimentScheduleItem)
            .join(Exps, ExperimentScheduleItem.experiment_id == Exps.idexp)
            .filter(
                ExperimentScheduleItem.group_id == group_id,
                Exps.simulator_type == "HPC",
            )
            .count()
        )
        if hpc_count >= MAX_HPC_PER_GROUP:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Maximum {MAX_HPC_PER_GROUP} HPC experiments allowed per group. This group already has {hpc_count} HPC experiments.",
                    }
                ),
                400,
            )

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
                        if client.pid:
                            stop_client_for_experiment(exp, client, pause=False)
                        client.status = 0
                        db.session.commit()

                # Stop server
                stop_server_for_experiment(exp)

                # Check if all clients have completed to determine final status
                all_clients_completed, _ = _get_clients_to_start(exp)
                final_status = "completed" if all_clients_completed else "stopped"

                exp.running = 0
                exp.exp_status = final_status
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
                        if client.pid:
                            stop_client_for_experiment(exp, client, pause=False)
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

    # Get experiments that are stopped
    experiments_list = experiments_query.filter(
        Exps.exp_status.in_(["stopped", "scheduled"])
    ).all()

    # Get experiments already in groups
    scheduled_exp_ids = set(
        item.experiment_id for item in ExperimentScheduleItem.query.all()
    )

    # Get experiment IDs that have infinite clients (clients with days = -1)
    # Use a single query instead of nested loops for efficiency
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

    result = []
    for exp in experiments_list:
        # Exclude experiments that are already scheduled or have infinite clients
        if (
            exp.idexp not in scheduled_exp_ids
            and exp.idexp not in experiments_with_infinite_clients
        ):
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

    # Get available experiments (stopped, not in any group)
    if user.role == "admin":
        experiments_query = Exps.query
    else:
        experiments_query = Exps.query.filter_by(owner=user.username)

    experiments_list = experiments_query.filter(
        Exps.exp_status.in_(["stopped", "scheduled"])
    ).all()

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

    # Separate HPC and Standard experiments
    # HPC experiments can be grouped up to 4 per group
    hpc_exps = [exp for exp in available_exps if exp.simulator_type == "HPC"]
    standard_exps = [exp for exp in available_exps if exp.simulator_type != "HPC"]

    # Get current max order index
    max_order = (
        db.session.query(db.func.max(ExperimentScheduleGroup.order_index)).scalar() or 0
    )

    # Create groups and assign experiments
    created_groups = []
    group_num = 1

    # Calculate HPC experiments per group: min of MAX_HPC_PER_GROUP and user-specified value
    hpc_per_group = min(MAX_HPC_PER_GROUP, experiments_per_group)

    # First, create groups for HPC experiments (respecting user input, capped at 4)
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


@experiments.route("/admin/opinion_groups_data")
@login_required
def opinion_groups_data():
    """Display opinion groups data page."""
    query = OpinionGroup.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(OpinionGroup.name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name", "lower_bound", "upper_bound"]:
                name = "name"
            col = getattr(OpinionGroup, name)
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
                "id": group.id,
                "name": group.name,
                "lower_bound": group.lower_bound,
                "upper_bound": group.upper_bound,
            }
            for group in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/opinion_groups_data", methods=["POST"])
@login_required
def update_opinion_group():
    """Update opinion group data (for inline editing)."""
    check_privileges(current_user.username)

    data = request.get_json()
    group_id = data.get("id")
    group = OpinionGroup.query.filter_by(id=group_id).first()

    if not group:
        return jsonify({"success": False, "message": "Opinion group not found"}), 404

    # Update fields if provided
    if "name" in data:
        group.name = data["name"]
    if "lower_bound" in data:
        try:
            lower_bound = float(data["lower_bound"])
            if not (0 <= lower_bound <= 1):
                return (
                    jsonify(
                        {"success": False, "message": "Lower bound must be in [0, 1]"}
                    ),
                    400,
                )
            group.lower_bound = lower_bound
        except ValueError:
            return (
                jsonify({"success": False, "message": "Invalid lower_bound value"}),
                400,
            )
    if "upper_bound" in data:
        try:
            upper_bound = float(data["upper_bound"])
            if not (0 <= upper_bound <= 1):
                return (
                    jsonify(
                        {"success": False, "message": "Upper bound must be in [0, 1]"}
                    ),
                    400,
                )
            group.upper_bound = upper_bound
        except ValueError:
            return (
                jsonify({"success": False, "message": "Invalid upper_bound value"}),
                400,
            )

    # Validate that lower_bound <= upper_bound
    if group.lower_bound > group.upper_bound:
        return (
            jsonify(
                {"success": False, "message": "Lower bound must be <= upper bound"}
            ),
            400,
        )

    # Check for overlaps with other existing groups
    existing_groups = OpinionGroup.query.filter(OpinionGroup.id != group_id).all()
    for existing in existing_groups:
        # Check if the updated group overlaps with any other existing group
        # Two ranges [a1, a2] and [b1, b2] overlap if: a1 < b2 AND b1 < a2
        if (
            group.lower_bound < existing.upper_bound
            and existing.lower_bound < group.upper_bound
        ):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Overlaps with '{existing.name}' [{existing.lower_bound}, {existing.upper_bound}]",
                    }
                ),
                400,
            )

    db.session.commit()
    return jsonify({"success": True})


@experiments.route("/admin/create_opinion_group", methods=["POST"])
@login_required
def create_opinion_group():
    """Create opinion group."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    lower_bound = request.form.get("lower_bound")
    upper_bound = request.form.get("upper_bound")

    try:
        lower_bound = float(lower_bound)
        upper_bound = float(upper_bound)
    except (ValueError, TypeError):
        flash("Invalid bound values. Must be numbers.", "error")
        return redirect(request.referrer)

    # Validate bounds are in [0, 1] and lower <= upper
    if not (0 <= lower_bound <= 1 and 0 <= upper_bound <= 1):
        flash("Bounds must be in the range [0, 1].", "error")
        return redirect(request.referrer)

    if lower_bound > upper_bound:
        flash("Lower bound must be less than or equal to upper bound.", "error")
        return redirect(request.referrer)

    # Check for overlaps with existing groups
    existing_groups = OpinionGroup.query.all()
    for existing in existing_groups:
        # Check if the new group overlaps with any existing group
        # Two ranges [a1, a2] and [b1, b2] overlap if: a1 < b2 AND b1 < a2
        if lower_bound < existing.upper_bound and existing.lower_bound < upper_bound:
            flash(
                f"Opinion group overlaps with existing group '{existing.name}' "
                f"[{existing.lower_bound}, {existing.upper_bound}]. "
                "Groups must not overlap.",
                "error",
            )
            return redirect(request.referrer)

    group = OpinionGroup(name=name, lower_bound=lower_bound, upper_bound=upper_bound)
    db.session.add(group)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/delete_opinion_group/<int:group_id>", methods=["DELETE"])
@login_required
def delete_opinion_group(group_id):
    """Delete opinion group."""
    check_privileges(current_user.username)

    group = OpinionGroup.query.filter_by(id=group_id).first()
    if not group:
        return jsonify({"success": False, "message": "Opinion group not found"}), 404

    db.session.delete(group)
    db.session.commit()
    return jsonify({"success": True})


@experiments.route("/admin/opinion_distributions_data")
@login_required
def opinion_distributions_data():
    """Display opinion distributions data page."""
    query = OpinionDistribution.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(
            db.or_(
                OpinionDistribution.name.like(f"%{search}%"),
                OpinionDistribution.distribution_type.like(f"%{search}%"),
            )
        )
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name", "distribution_type"]:
                name = "name"
            col = getattr(OpinionDistribution, name)
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
                "id": dist.id,
                "name": dist.name,
                "distribution_type": dist.distribution_type,
                "parameters": dist.parameters,
            }
            for dist in res
        ],
        "total": total,
    }

    return res


@experiments.route("/admin/opinion_distributions_data", methods=["POST"])
@login_required
def update_opinion_distribution():
    """Update opinion distribution data (for inline editing)."""
    check_privileges(current_user.username)

    data = request.get_json()
    dist_id = data.get("id")
    dist = OpinionDistribution.query.filter_by(id=dist_id).first()

    if not dist:
        return (
            jsonify({"success": False, "message": "Opinion distribution not found"}),
            404,
        )

    # Update fields if provided
    if "name" in data:
        dist.name = data["name"]

    db.session.commit()
    return jsonify({"success": True})


@experiments.route("/admin/create_opinion_distribution", methods=["POST"])
@login_required
def create_opinion_distribution():
    """Create opinion distribution."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    distribution_type = request.form.get("distribution_type")
    parameters = request.form.get("parameters")  # JSON string

    # Validate JSON parameters
    try:
        json.loads(parameters)
    except (json.JSONDecodeError, TypeError):
        flash("Invalid parameters format. Must be valid JSON.", "error")
        return redirect(request.referrer)

    dist = OpinionDistribution(
        name=name, distribution_type=distribution_type, parameters=parameters
    )
    db.session.add(dist)
    db.session.commit()

    return redirect(request.referrer)


@experiments.route(
    "/admin/delete_opinion_distribution/<int:dist_id>", methods=["DELETE"]
)
@login_required
def delete_opinion_distribution(dist_id):
    """Delete opinion distribution."""
    check_privileges(current_user.username)

    dist = OpinionDistribution.query.filter_by(id=dist_id).first()
    if not dist:
        return (
            jsonify({"success": False, "message": "Opinion distribution not found"}),
            404,
        )

    db.session.delete(dist)
    db.session.commit()
    return jsonify({"success": True})


def generate_group_trends_data(expid, filter_day, filter_hour, filter_topic_id):
    """
    Generate opinion group volume trends over time.

    For each timestamp up to (filter_day, filter_hour), calculates the percentage
    of agents in each opinion group.

    Args:
        expid: Experiment ID
        filter_day: Current day filter
        filter_hour: Current hour filter
        filter_topic_id: Topic ID filter (None for all topics)

    Returns:
        dict: Time series data with timestamps and group percentages
    """
    from sqlalchemy import and_, or_

    from y_web.models import Agent_Opinion, Rounds

    # Get opinion groups from dashboard database for binning
    opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()

    # Find all rounds up to the specified day/hour for x-axis display
    # We'll filter to hour==0 (day boundaries) for cleaner x-axis labels
    # But first check if ANY rounds exist
    all_rounds_check = (
        db.session.query(Rounds.id).filter(Rounds.day <= filter_day).limit(1).first()
    )

    if not all_rounds_check:
        return {"timestamps": [], "timestamp_mapping": {}, "groups": []}

    # Get rounds at day boundaries (hour==0) for x-axis display points
    rounds_up_to_time = (
        db.session.query(Rounds.id, Rounds.day, Rounds.hour)
        .filter(
            Rounds.hour == 0,  # Only day boundaries for display
            Rounds.day <= filter_day,  # Up to current day
        )
        .order_by(Rounds.day, Rounds.hour)
        .all()
    )

    # If no hour==0 rounds exist (e.g., HPC experiments with different hour values),
    # fall back to selecting one round per day (this is expected for HPC experiments)
    if not rounds_up_to_time:
        # Group by day and take the first round from each day
        from sqlalchemy import func

        subquery = (
            db.session.query(Rounds.day, func.min(Rounds.hour).label("min_hour"))
            .filter(Rounds.day <= filter_day)
            .group_by(Rounds.day)
            .subquery()
        )

        rounds_up_to_time = (
            db.session.query(Rounds.id, Rounds.day, Rounds.hour)
            .join(
                subquery,
                and_(Rounds.day == subquery.c.day, Rounds.hour == subquery.c.min_hour),
            )
            .order_by(Rounds.day, Rounds.hour)
            .all()
        )
        current_app.logger.info(
            f"Fallback found {len(rounds_up_to_time)} rounds for exp {expid}"
        )

    if not rounds_up_to_time:
        current_app.logger.error(
            f"No rounds found at all for exp {expid} - returning empty data"
        )
        return {"timestamps": [], "timestamp_mapping": {}, "groups": []}

    # Create list of timestamps (simulation days, since hour==0)
    simulation_days = [float(r.day) for r in rounds_up_to_time]

    # Create timestamp mapping for tooltip context
    timestamp_mapping = {}
    for r in rounds_up_to_time:
        sim_day = float(r.day)
        timestamp_mapping[sim_day] = {
            "day": r.day,
            "hour": r.hour,
            "absolute": r.day * 24 + r.hour,
        }

    # Query ALL opinions up to the maximum time (not just from hour==0 rounds)
    # We need all opinions to correctly identify the latest opinion per agent at each timestamp
    max_day = filter_day
    max_hour = 23  # Get all opinions up to end of the last day

    # Get all rounds up to the max time
    all_rounds_query = (
        db.session.query(Rounds.id, Rounds.day, Rounds.hour)
        .filter(
            or_(
                Rounds.day < max_day,
                and_(Rounds.day == max_day, Rounds.hour <= max_hour),
            )
        )
        .order_by(Rounds.day, Rounds.hour)
    )

    all_rounds_list = all_rounds_query.all()

    if not all_rounds_list:
        return {
            "timestamps": simulation_days,
            "timestamp_mapping": timestamp_mapping,
            "groups": [],
        }

    # Query all opinions with timestamp info for these rounds
    base_query = (
        db.session.query(
            Agent_Opinion.agent_id,
            Agent_Opinion.topic_id,
            Agent_Opinion.tid,
            Agent_Opinion.opinion,
            Rounds.day,
            Rounds.hour,
        )
        .join(Rounds, Agent_Opinion.tid == Rounds.id)
        .filter(Agent_Opinion.tid.in_([r.id for r in all_rounds_list]))
    )

    # Apply topic filter if specified
    if filter_topic_id is not None:
        base_query = base_query.filter(Agent_Opinion.topic_id == filter_topic_id)

    all_opinions = base_query.all()

    if not all_opinions:
        return {
            "timestamps": simulation_days,
            "timestamp_mapping": timestamp_mapping,
            "groups": [],
        }

    # Organize opinions by (day, hour) for incremental processing
    opinions_by_time = defaultdict(list)
    for agent_id, topic_id, tid, opinion, opinion_day, opinion_hour in all_opinions:
        opinions_by_time[(opinion_day, opinion_hour)].append(
            (agent_id, topic_id, opinion)
        )

    # Sort time keys chronologically
    sorted_times = sorted(opinions_by_time.keys())

    # For each timestamp we want to display, calculate group percentages
    # using incremental updates for efficiency
    group_trends = {group.name: [] for group in opinion_groups}
    latest_at_time = {}  # Running dictionary: (agent_id, topic_id) -> opinion
    current_time_index = 0  # Track which times we've processed

    for round_obj in rounds_up_to_time:
        target_day = round_obj.day
        target_hour = round_obj.hour

        # Process all opinions up to the target time (incrementally)
        while current_time_index < len(sorted_times):
            time_day, time_hour = sorted_times[current_time_index]

            # Stop if this time is beyond our target
            if time_day > target_day or (
                time_day == target_day and time_hour > target_hour
            ):
                break

            # Update latest_at_time with opinions from this time
            for agent_id, topic_id, opinion in opinions_by_time[(time_day, time_hour)]:
                key = (agent_id, topic_id)
                latest_at_time[key] = opinion

            current_time_index += 1

        # Bin the opinions at this timestamp
        binned_counts = {group.name: 0 for group in opinion_groups}

        for opinion_value in latest_at_time.values():
            matched = False
            for group in opinion_groups:
                if group.lower_bound <= opinion_value <= group.upper_bound:
                    binned_counts[group.name] += 1
                    matched = True
                    break

            if not matched:
                # Log warning for unmatched opinion value
                current_app.logger.warning(
                    f"Opinion value {opinion_value} does not match any opinion group in experiment {expid}"
                )

        # Calculate percentages using actual binned count (not total opinions)
        # This ensures percentages sum to 100% even if some opinions don't match groups
        total_binned = sum(binned_counts.values())

        for group in opinion_groups:
            percentage = (
                (binned_counts[group.name] / total_binned * 100)
                if total_binned > 0
                else 0
            )
            group_trends[group.name].append(percentage)

    # Prepare return data
    groups_data = []
    for group in opinion_groups:
        groups_data.append({"name": group.name, "data": group_trends[group.name]})

    return {
        "timestamps": simulation_days,
        "timestamp_mapping": timestamp_mapping,
        "groups": groups_data,
    }


def get_or_sample_agents(expid, topic_id, sample_percentage, all_agent_ids):
    """
    Get or create a stable sample of agents for visualization.

    This function ensures that the same set of agents is used across all
    animation frames for stability and performance.

    Args:
        expid: Experiment ID
        topic_id: Topic ID as string (None for all topics, supports int or UUID)
        sample_percentage: Percentage of agents to sample
        all_agent_ids: List of all available agent IDs

    Returns:
        List of sampled agent IDs
    """
    # Try to get existing sample
    sample_entry = OpinionEvolutionSampledAgents.query.filter_by(
        exp_id=expid, topic_id=topic_id, sample_percentage=sample_percentage
    ).first()

    # If sample exists and is recent (< 1 hour), use it
    if sample_entry and (datetime.now() - sample_entry.created_at) < timedelta(hours=1):
        return json.loads(sample_entry.sampled_agent_ids)

    # Sample agents deterministically using experiment ID as seed for reproducibility
    # This ensures the same sample is generated if we need to recreate it
    # Handle topic_id which can be None, integer string, or UUID string
    if topic_id is None:
        topic_seed = 0
    else:
        # topic_id is a string (either int converted to string or UUID)
        # Use hash for consistent seeding
        topic_seed = abs(hash(topic_id)) % 1000000

    random.seed(expid * 1000 + topic_seed + sample_percentage)
    num_agents_to_sample = max(1, int(len(all_agent_ids) * sample_percentage / 100.0))
    sampled_agent_ids = random.sample(
        all_agent_ids, min(num_agents_to_sample, len(all_agent_ids))
    )

    # Store in database
    if sample_entry:
        # Update existing entry
        sample_entry.sampled_agent_ids = json.dumps(sampled_agent_ids)
        sample_entry.created_at = datetime.now()
    else:
        # Create new entry
        sample_entry = OpinionEvolutionSampledAgents(
            exp_id=expid,
            topic_id=topic_id,
            sample_percentage=sample_percentage,
            sampled_agent_ids=json.dumps(sampled_agent_ids),
        )
        db.session.add(sample_entry)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error storing sampled agents: {str(e)}")
        # Continue with the sampled agents even if storage fails
        # This ensures the visualization still works

    return sampled_agent_ids


def generate_agent_timeseries_data(
    expid, filter_day, filter_hour, filter_topic_id, sample_percentage=50
):
    """
    Generate agent opinion time series data for visualization.

    Args:
        expid: Experiment ID
        filter_day: Current day filter
        filter_hour: Current hour filter
        filter_topic_id: Topic ID filter (None for all topics)
        sample_percentage: Percentage of agents to sample (10, 25, 50, 75, 100)

    Returns:
        dict: Time series data with timestamps, sampled agents, and their opinions
    """
    from sqlalchemy import and_, or_

    from y_web.models import Agent_Opinion, Rounds

    # Find all rounds up to the specified day/hour for x-axis display
    # We'll filter to hour==0 (day boundaries) for cleaner x-axis labels
    # But first check if ANY rounds exist
    all_rounds_check = (
        db.session.query(Rounds.id).filter(Rounds.day <= filter_day).limit(1).first()
    )

    if not all_rounds_check:
        current_app.logger.warning(
            f"No rounds found for exp {expid} in generate_agent_timeseries_data"
        )
        return {"timestamps": [], "agents": [], "sample_percentage": sample_percentage}

    # Get rounds at day boundaries (hour==0) for x-axis display points
    rounds_up_to_time = (
        db.session.query(Rounds.id, Rounds.day, Rounds.hour)
        .filter(
            Rounds.hour == 0,  # Only day boundaries for display
            Rounds.day <= filter_day,  # Up to current day
        )
        .order_by(Rounds.day, Rounds.hour)
        .all()
    )

    current_app.logger.info(
        f"Found {len(rounds_up_to_time)} hour==0 rounds for exp {expid} in generate_agent_timeseries_data"
    )

    # If no hour==0 rounds exist (e.g., HPC experiments with different hour values),
    # fall back to selecting one round per day (this is expected for HPC experiments)
    if not rounds_up_to_time:
        current_app.logger.info(
            f"No hour==0 rounds for exp {expid}, using fallback to first hour per day"
        )
        # Group by day and take the first round from each day
        from sqlalchemy import func

        subquery = (
            db.session.query(Rounds.day, func.min(Rounds.hour).label("min_hour"))
            .filter(Rounds.day <= filter_day)
            .group_by(Rounds.day)
            .subquery()
        )

        rounds_up_to_time = (
            db.session.query(Rounds.id, Rounds.day, Rounds.hour)
            .join(
                subquery,
                and_(Rounds.day == subquery.c.day, Rounds.hour == subquery.c.min_hour),
            )
            .order_by(Rounds.day, Rounds.hour)
            .all()
        )
        current_app.logger.info(
            f"Fallback found {len(rounds_up_to_time)} rounds for exp {expid}"
        )

    if not rounds_up_to_time:
        current_app.logger.error(
            f"No rounds found at all in generate_agent_timeseries_data for exp {expid}"
        )
        return {"timestamps": [], "agents": [], "sample_percentage": sample_percentage}

    # Create list of timestamps (simulation days)
    simulation_days = [float(r.day) for r in rounds_up_to_time]

    # Query ALL opinions up to the maximum time (not just from display rounds)
    # This ensures alignment with group trends which uses all opinions
    max_day = filter_day
    max_hour = 23  # Get all opinions up to end of the last day

    # Get all rounds up to the max time
    all_rounds_query = (
        db.session.query(Rounds.id, Rounds.day, Rounds.hour)
        .filter(
            or_(
                Rounds.day < max_day,
                and_(Rounds.day == max_day, Rounds.hour <= max_hour),
            )
        )
        .order_by(Rounds.day, Rounds.hour)
    )

    all_rounds_list = all_rounds_query.all()

    if not all_rounds_list:
        return {"timestamps": [], "agents": [], "sample_percentage": sample_percentage}

    # Query all opinions with timestamp info for these rounds
    base_query = (
        db.session.query(
            Agent_Opinion.agent_id,
            Agent_Opinion.topic_id,
            Agent_Opinion.tid,
            Agent_Opinion.opinion,
            Rounds.day,
            Rounds.hour,
        )
        .join(Rounds, Agent_Opinion.tid == Rounds.id)
        .filter(Agent_Opinion.tid.in_([r.id for r in all_rounds_list]))
    )

    # Apply topic filter if specified
    if filter_topic_id is not None:
        base_query = base_query.filter(Agent_Opinion.topic_id == filter_topic_id)

    all_opinions = base_query.all()

    if not all_opinions:
        return {"timestamps": [], "agents": [], "sample_percentage": sample_percentage}

    # Organize opinions by (day, hour) for incremental processing
    opinions_by_time = defaultdict(list)
    agent_first_opinion = {}  # Track first observed opinion for each agent

    for agent_id, topic_id, tid, opinion, opinion_day, opinion_hour in all_opinions:
        opinions_by_time[(opinion_day, opinion_hour)].append(
            (agent_id, topic_id, opinion)
        )
        # Track first observed opinion for color coding (chronologically)
        if agent_id not in agent_first_opinion:
            agent_first_opinion[agent_id] = opinion

    # Sort time keys chronologically
    sorted_times = sorted(opinions_by_time.keys())

    # Get all unique agents that appear in the data
    all_agent_ids = list(agent_first_opinion.keys())

    # Sample agents based on percentage - use stable sampling
    # Convert topic_id to string for consistency (supports both int and UUID)
    topic_id_str = str(filter_topic_id) if filter_topic_id is not None else None
    sampled_agent_ids = get_or_sample_agents(
        expid, topic_id_str, sample_percentage, all_agent_ids
    )

    # For each display timestamp, compute the latest opinion for each sampled agent
    # Structure: {agent_id: {day: opinion_value}}
    agent_data = {agent_id: {} for agent_id in sampled_agent_ids}

    # Track latest opinion for each agent incrementally
    latest_at_time = {}  # (agent_id, topic_id) -> opinion
    latest_by_agent = (
        {}
    )  # agent_id -> opinion (for faster lookup when topic_id is None)
    current_time_index = 0

    for round_obj in rounds_up_to_time:
        target_day = round_obj.day
        target_hour = round_obj.hour

        # Process all opinions up to the target time (incrementally)
        while current_time_index < len(sorted_times):
            time_day, time_hour = sorted_times[current_time_index]

            # Stop if this time is beyond our target
            if time_day > target_day or (
                time_day == target_day and time_hour > target_hour
            ):
                break

            # Update latest_at_time with opinions from this time
            for agent_id, topic_id, opinion in opinions_by_time[(time_day, time_hour)]:
                key = (agent_id, topic_id)
                latest_at_time[key] = opinion
                # Also maintain agent-only index for faster lookup
                latest_by_agent[agent_id] = opinion

            current_time_index += 1

        # Store the latest opinion for each sampled agent at this timestamp
        for agent_id in sampled_agent_ids:
            if filter_topic_id is not None:
                # Topic filter is specified - look up exact key
                key = (agent_id, filter_topic_id)
                if key in latest_at_time:
                    agent_data[agent_id][target_day] = latest_at_time[key]
            else:
                # No topic filter - use agent-only index for O(1) lookup
                if agent_id in latest_by_agent:
                    agent_data[agent_id][target_day] = latest_by_agent[agent_id]

    # Create mapping for tooltip display
    timestamp_mapping = {}  # Maps day to (day, hour) for tooltips

    for round_obj in rounds_up_to_time:
        sim_day = float(round_obj.day)
        timestamp_mapping[sim_day] = {
            "day": round_obj.day,
            "hour": round_obj.hour,
            "absolute": round_obj.day * 24 + round_obj.hour,
        }

    # Get opinion groups for color coding
    opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()

    # Define color palette matching the opinion distribution chart
    color_palette = [
        "rgba(239, 68, 68, 0.7)",  # Red - Strongly against
        "rgba(251, 146, 60, 0.7)",  # Orange - Against
        "rgba(250, 204, 21, 0.7)",  # Yellow - Neutral
        "rgba(74, 222, 128, 0.7)",  # Light Green - In favor
        "rgba(34, 197, 94, 0.7)",  # Green - Strongly in favor
    ]

    # Build agent time series with forward-fill
    agents_timeseries = []
    for agent_id in sampled_agent_ids:
        agent_opinions = agent_data[agent_id]

        # Forward-fill: replicate last observed value
        filled_data = []
        last_opinion = None

        for day in simulation_days:
            if day in agent_opinions:
                last_opinion = agent_opinions[day]

            if last_opinion is not None:
                filled_data.append(last_opinion)
            else:
                filled_data.append(None)  # No data yet for this agent

        # Determine initial opinion group for color coding
        first_opinion = agent_first_opinion.get(agent_id)
        initial_group = "Unknown"
        color = "rgba(156, 163, 175, 0.7)"  # Default gray

        if first_opinion is not None:
            for idx, group in enumerate(opinion_groups):
                if group.lower_bound <= first_opinion <= group.upper_bound:
                    initial_group = group.name
                    # Use color from palette if available
                    if idx < len(color_palette):
                        color = color_palette[idx]
                    else:
                        # Generate color if not in palette
                        hue = idx * 360 / len(opinion_groups)
                        color = f"hsla({hue}, 70%, 60%, 0.7)"
                    break

        agents_timeseries.append(
            {
                "agent_id": str(agent_id),
                "data": filled_data,
                "initial_group": initial_group,
                "color": color,
            }
        )

    return {
        "timestamps": simulation_days,  # Simulation days (integers: 0, 1, 2, ...)
        "timestamp_mapping": timestamp_mapping,  # Maps day to actual day/hour
        "agents": agents_timeseries,
        "sample_percentage": sample_percentage,
    }


def count_social_interactions(all_opinions):
    """
    Count social interactions from opinion data.

    Social interactions: Count opinions where id_interacted_with is valid (has a value).

    Args:
        all_opinions: List of tuples (agent_id, topic_id, tid, opinion, id_interacted_with, day, hour)

    Returns:
        Number of social interactions
    """
    social_interactions = 0

    for (
        agent_id,
        topic_id,
        tid,
        opinion,
        id_interacted_with,
        day,
        hour,
    ) in all_opinions:
        # Check if interaction is valid: not null, not zero, and if string, not empty
        if id_interacted_with is not None and id_interacted_with != 0:
            # Convert to string and check if non-empty
            id_str = str(id_interacted_with).strip()
            if len(id_str) > 0 and id_str != "0":
                social_interactions += 1

    return social_interactions


def get_or_compute_opinion_stats(expid, filter_day, filter_hour, filter_topic_id):
    """
    Get opinion statistics from cache or compute them incrementally.

    This function implements incremental caching: if a previous time point is cached,
    it queries only new opinions since that time and updates the cached state.
    Otherwise, it computes from scratch.

    Args:
        expid: Experiment ID
        filter_day: Day filter
        filter_hour: Hour filter
        filter_topic_id: Topic filter (None for all topics)

    Returns:
        Dict with statistics: {
            'total_opinions': int,
            'social_interactions': int,
            'unique_agents': int,
            'binned_data': dict
        }
    """
    from sqlalchemy import and_, or_
    from sqlalchemy.orm import defer

    from y_web.models import Agent_Opinion, Rounds

    # Check if incremental caching is supported (column exists)
    incremental_supported = hasattr(OpinionEvolutionCache, "latest_opinions_state")

    # Try to get exact cache match
    # If latest_opinions_state column doesn't exist, defer it from the query
    try:
        query = OpinionEvolutionCache.query
        if not incremental_supported:
            # Defer the missing column to avoid SELECT errors
            query = query.options(defer("latest_opinions_state"))

        cache_entry = query.filter_by(
            exp_id=expid, day=filter_day, hour=filter_hour, topic_id=filter_topic_id
        ).first()
    except Exception as e:
        # Handle any other database errors - log only critical errors, not on every request
        # to avoid performance degradation from excessive logging
        cache_entry = None

    # Cache hit - return cached data (no expiry, cache persists)
    if cache_entry:
        # Extract all needed data from cache_entry while session is still valid
        cached_result = {
            "total_opinions": cache_entry.total_opinions,
            "social_interactions": cache_entry.social_interactions,
            "unique_agents": cache_entry.unique_agents,
            "binned_data": json.loads(cache_entry.binned_data),
        }
        return cached_result

    # Cache miss - try incremental computation
    # Find the most recent cached entry before the requested time
    current_time_value = filter_day * 24 + filter_hour

    previous_cache = None
    if incremental_supported:
        try:
            previous_cache = (
                OpinionEvolutionCache.query.filter(
                    OpinionEvolutionCache.exp_id == expid,
                    OpinionEvolutionCache.topic_id == filter_topic_id,
                    or_(
                        OpinionEvolutionCache.day < filter_day,
                        and_(
                            OpinionEvolutionCache.day == filter_day,
                            OpinionEvolutionCache.hour < filter_hour,
                        ),
                    ),
                )
                .order_by(
                    OpinionEvolutionCache.day.desc(), OpinionEvolutionCache.hour.desc()
                )
                .first()
            )
        except Exception as e:
            # If query fails (e.g., column doesn't exist), fall back to full computation
            # Reduce logging to avoid performance impact
            previous_cache = None

    if (
        previous_cache
        and incremental_supported
        and hasattr(previous_cache, "latest_opinions_state")
        and previous_cache.latest_opinions_state
    ):
        # Incremental computation from previous cache
        prev_day = previous_cache.day
        prev_hour = previous_cache.hour

        # Load previous state
        latest_opinions = {}
        stored_state = json.loads(previous_cache.latest_opinions_state)
        # Convert stored state back to the format we need
        for agent_id_str, topics_dict in stored_state.items():
            # Handle both integer agent_ids (standard) and UUID strings (HPC)
            try:
                agent_id = int(agent_id_str)
            except ValueError:
                agent_id = agent_id_str  # Keep as string for UUID
            for topic_id_str, opinion_data in topics_dict.items():
                # Handle both int and UUID topic_ids
                if topic_id_str == "null":
                    topic_id = None
                else:
                    try:
                        topic_id = int(topic_id_str)
                    except ValueError:
                        topic_id = topic_id_str  # Keep as string for UUID
                key = (agent_id, topic_id)
                latest_opinions[key] = opinion_data

        # Start with previous social interactions count
        social_interactions = previous_cache.social_interactions

        # Query only new opinions since previous cache time
        rounds_in_range = (
            db.session.query(Rounds.id, Rounds.day, Rounds.hour)
            .filter(
                or_(
                    and_(Rounds.day == prev_day, Rounds.hour > prev_hour),
                    and_(Rounds.day > prev_day, Rounds.day < filter_day),
                    and_(Rounds.day == filter_day, Rounds.hour <= filter_hour),
                )
            )
            .all()
        )

        if rounds_in_range:
            round_time_map = {r.id: (r.day, r.hour) for r in rounds_in_range}
            round_ids = [r.id for r in rounds_in_range]

            # Query new opinions
            new_opinions_query = db.session.query(
                Agent_Opinion.agent_id,
                Agent_Opinion.topic_id,
                Agent_Opinion.tid,
                Agent_Opinion.opinion,
                Agent_Opinion.id_interacted_with,
            ).filter(Agent_Opinion.tid.in_(round_ids))

            if filter_topic_id is not None:
                new_opinions_query = new_opinions_query.filter(
                    Agent_Opinion.topic_id == filter_topic_id
                )

            new_opinions = new_opinions_query.all()

            # Create list format for count_social_interactions
            new_opinions_with_rounds = [
                (
                    agent_id,
                    topic_id,
                    tid,
                    opinion,
                    id_interacted_with,
                    round_time_map[tid][0],
                    round_time_map[tid][1],
                )
                for agent_id, topic_id, tid, opinion, id_interacted_with in new_opinions
                if tid in round_time_map
            ]

            # Incrementally add new social interactions
            new_social_interactions = count_social_interactions(
                new_opinions_with_rounds
            )
            social_interactions += new_social_interactions

            # Update latest_opinions with new data
            for (
                agent_id,
                topic_id,
                tid,
                opinion,
                id_interacted_with,
                day,
                hour,
            ) in new_opinions_with_rounds:
                key = (agent_id, topic_id)

                # Update if this is newer than what we have
                if key not in latest_opinions or (day, hour) > (
                    latest_opinions[key]["day"],
                    latest_opinions[key]["hour"],
                ):
                    latest_opinions[key] = {
                        "tid": tid,
                        "opinion": opinion,
                        "id_interacted_with": id_interacted_with,
                        "day": day,
                        "hour": hour,
                    }

    else:
        # No previous cache - compute from scratch
        rounds_up_to_time = (
            db.session.query(Rounds.id)
            .filter(
                or_(
                    Rounds.day < filter_day,
                    and_(Rounds.day == filter_day, Rounds.hour <= filter_hour),
                )
            )
            .subquery()
        )

        base_query = (
            db.session.query(
                Agent_Opinion.agent_id,
                Agent_Opinion.topic_id,
                Agent_Opinion.tid,
                Agent_Opinion.opinion,
                Agent_Opinion.id_interacted_with,
                Rounds.day,
                Rounds.hour,
            )
            .join(Rounds, Agent_Opinion.tid == Rounds.id)
            .filter(Agent_Opinion.tid.in_(rounds_up_to_time))
        )

        if filter_topic_id is not None:
            base_query = base_query.filter(Agent_Opinion.topic_id == filter_topic_id)

        all_opinions = base_query.all()

        # Keep only the latest opinion per (agent_id, topic_id) pair
        latest_opinions = {}
        for (
            agent_id,
            topic_id,
            tid,
            opinion,
            id_interacted_with,
            day,
            hour,
        ) in all_opinions:
            key = (agent_id, topic_id)
            if key not in latest_opinions or (day, hour) > (
                latest_opinions[key]["day"],
                latest_opinions[key]["hour"],
            ):
                latest_opinions[key] = {
                    "tid": tid,
                    "opinion": opinion,
                    "id_interacted_with": id_interacted_with,
                    "day": day,
                    "hour": hour,
                }

        social_interactions = count_social_interactions(all_opinions)

    # Extract opinion values for binning
    opinion_data = [data["opinion"] for data in latest_opinions.values()]

    # Count unique agents
    unique_agents = len(set(key[0] for key in latest_opinions.keys()))

    # Get opinion groups and bin the data
    opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()
    binned_data = {group.name: 0 for group in opinion_groups}

    for opinion_value in opinion_data:
        for group in opinion_groups:
            if group.lower_bound <= opinion_value <= group.upper_bound:
                binned_data[group.name] += 1
                break

    # Prepare result before any database modifications
    result = {
        "total_opinions": len(opinion_data),
        "social_interactions": social_interactions,
        "unique_agents": unique_agents,
        "binned_data": binned_data,
    }

    # Prepare latest_opinions state for storage (for next incremental update)
    # Only store if incremental caching is supported
    latest_opinions_for_storage = None
    if incremental_supported:
        latest_opinions_for_storage = {}
        for (agent_id, topic_id), data in latest_opinions.items():
            agent_key = str(agent_id)
            topic_key = str(topic_id) if topic_id is not None else "null"

            if agent_key not in latest_opinions_for_storage:
                latest_opinions_for_storage[agent_key] = {}

            latest_opinions_for_storage[agent_key][topic_key] = {
                "opinion": data["opinion"],
                "day": data["day"],
                "hour": data["hour"],
            }

    # Store in cache (no expiry - cache persists indefinitely)
    try:
        # Create new cache entry
        cache_data = {
            "exp_id": expid,
            "day": filter_day,
            "hour": filter_hour,
            "topic_id": filter_topic_id,
            "total_opinions": result["total_opinions"],
            "social_interactions": result["social_interactions"],
            "unique_agents": result["unique_agents"],
            "binned_data": json.dumps(result["binned_data"]),
        }

        # Add latest_opinions_state only if column exists
        if incremental_supported and latest_opinions_for_storage is not None:
            cache_data["latest_opinions_state"] = json.dumps(
                latest_opinions_for_storage
            )

        cache_entry = OpinionEvolutionCache(**cache_data)
        db.session.add(cache_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error caching opinion stats: {str(e)}")

    return result


@experiments.route("/admin/opinion_evolution/<int:expid>")
@login_required
def opinion_evolution(expid):
    """
    Display opinion evolution page for an experiment.

    Shows distribution of agent opinions over time.
    For each (agent_id, topic_id) pair, shows the most recent opinion up to the selected day/hour.

    Note: Agent_Opinion.tid is a UUID FK to Rounds.id, where day/hour values are stored.
    """
    check_privileges(current_user.username)

    # Get experiment
    experiment = Exps.query.filter_by(idexp=expid).first()
    if not experiment:
        flash("Experiment not found.")
        return redirect("/admin/experiments")

    # Check if opinions are enabled for this experiment
    if not experiment.annotations or "opinions" not in experiment.annotations:
        flash("Opinion dynamics is not enabled for this experiment.")
        return redirect(f"/admin/experiment_details/{expid}")

    # Activate experiment if not active (to access its database)
    from y_web.experiment_context import register_experiment_database

    bind_key = f"db_exp_{expid}"

    # Ensure the experiment database is registered
    if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
        register_experiment_database(current_app, expid, experiment.db_name)

    # Temporarily switch to experiment database
    old_bind = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
    current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
        "SQLALCHEMY_BINDS"
    ][bind_key]

    try:
        # Import experiment-specific models
        from sqlalchemy import and_, func, or_

        from y_web.models import Agent_Opinion, Interests, Rounds

        # Get available topics from experiment database
        topics_query = db.session.query(Interests).all()
        # Convert to dictionaries immediately to avoid ObjectDeletedError when session closes
        topics = [{"iid": t.iid, "interest": t.interest} for t in topics_query]

        # Get max day and hour from Rounds table (start at day 1 hour 1 as per requirements)
        max_round = (
            db.session.query(Rounds)
            .order_by(Rounds.day.desc(), Rounds.hour.desc())
            .first()
        )
        max_day = max_round.day if max_round else 1
        max_hour = max_round.hour if max_round else 1

        # Get filter parameters from request (default to max values)
        filter_day = request.args.get("day", type=int, default=max_day)
        filter_hour = request.args.get("hour", type=int, default=max_hour)
        # Default to first topic on initial page load (to match UI which shows first topic as active)
        default_topic_id = topics[0]["iid"] if topics else None
        # Parse topic_id as string to support both integer and UUID topic_ids (HPC experiments)
        filter_topic_id_str = request.args.get(
            "topic_id",
            default=str(default_topic_id) if default_topic_id is not None else None,
        )
        if filter_topic_id_str:
            try:
                filter_topic_id = int(filter_topic_id_str)
            except ValueError:
                filter_topic_id = filter_topic_id_str  # Keep as string for UUID
        else:
            filter_topic_id = default_topic_id

        # Find all rounds up to the specified day/hour
        # Rounds where (day < filter_day) OR (day == filter_day AND hour <= filter_hour)
        rounds_up_to_time = (
            db.session.query(Rounds.id)
            .filter(
                or_(
                    Rounds.day < filter_day,
                    and_(Rounds.day == filter_day, Rounds.hour <= filter_hour),
                )
            )
            .subquery()
        )

        # Get all opinions where tid (FK to Rounds) is in the rounds up to our time
        base_query = (
            db.session.query(
                Agent_Opinion.agent_id,
                Agent_Opinion.topic_id,
                Agent_Opinion.tid,
                Agent_Opinion.opinion,
                Agent_Opinion.id_interacted_with,
                Rounds.day,
                Rounds.hour,
            )
            .join(Rounds, Agent_Opinion.tid == Rounds.id)
            .filter(Agent_Opinion.tid.in_(rounds_up_to_time))
        )

        # Apply topic filter if specified
        if filter_topic_id is not None:
            base_query = base_query.filter(Agent_Opinion.topic_id == filter_topic_id)

        # Get all opinions up to the selected time
        all_opinions = base_query.all()

        # Keep only the latest opinion per (agent_id, topic_id) pair
        # Latest means highest (day, hour) combination
        latest_opinions = {}
        for (
            agent_id,
            topic_id,
            tid,
            opinion,
            id_interacted_with,
            day,
            hour,
        ) in all_opinions:
            key = (agent_id, topic_id)
            if key not in latest_opinions or (day, hour) > (
                latest_opinions[key]["day"],
                latest_opinions[key]["hour"],
            ):
                latest_opinions[key] = {
                    "tid": tid,
                    "opinion": opinion,
                    "id_interacted_with": id_interacted_with,
                    "day": day,
                    "hour": hour,
                }

        # Extract opinion values for binning
        opinion_data = [data["opinion"] for data in latest_opinions.values()]

        # Count social interactions from ALL opinions up to this time (not just latest)
        social_interactions = count_social_interactions(all_opinions)

        # Count unique agents that have an opinion on the selected topic up to current timestamp
        # Extract unique agent_ids from latest_opinions keys (which are (agent_id, topic_id) tuples)
        unique_agents = len(
            set(key[0] for key in latest_opinions.keys())
        )  # key[0] is agent_id

        # Get opinion groups from dashboard database for binning
        opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()

        # Bin the opinions according to opinion_groups
        binned_data = {group.name: 0 for group in opinion_groups}
        unmatched_count = 0

        for opinion_value in opinion_data:
            # Find which bin this opinion belongs to
            matched = False
            for group in opinion_groups:
                if group.lower_bound <= opinion_value <= group.upper_bound:
                    binned_data[group.name] += 1
                    matched = True
                    break

            if not matched:
                unmatched_count += 1
                current_app.logger.warning(
                    f"Opinion value {opinion_value} does not match any opinion group for experiment {expid}"
                )

        # Prepare data for chart
        chart_labels = [group.name for group in opinion_groups]
        chart_values = [binned_data[group.name] for group in opinion_groups]

        # Generate group trends data (opinion group volumes over time)
        group_trends_data = generate_group_trends_data(
            expid, filter_day, filter_hour, filter_topic_id
        )

        # Generate agent time series data (default 50% sample)
        sample_percentage = request.args.get("sample_percentage", type=int, default=50)
        timeseries_data = generate_agent_timeseries_data(
            expid, filter_day, filter_hour, filter_topic_id, sample_percentage
        )

    finally:
        # Restore old bind if it existed, otherwise remove the temporary bind
        if old_bind is not None:
            current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind
        else:
            # If no previous bind existed, remove the temporary one
            current_app.config["SQLALCHEMY_BINDS"].pop("db_exp", None)

    return render_template(
        "admin/opinion_evolution.html",
        experiment=experiment,
        topics=topics,
        max_day=max_day,
        max_hour=max_hour,
        filter_day=filter_day,
        filter_hour=filter_hour,
        filter_topic_id=filter_topic_id,
        chart_labels=chart_labels,
        chart_values=chart_values,
        total_opinions=len(opinion_data),
        social_interactions=social_interactions,
        unique_agents=unique_agents,
        group_trends_data=group_trends_data,
        timeseries_data=timeseries_data,
    )


@experiments.route("/admin/opinion_evolution_data/<int:expid>")
@login_required
def opinion_evolution_data(expid):
    """
    API endpoint for getting opinion evolution data without page reload.

    Returns JSON with chart data based on filter parameters.
    For each (agent_id, topic_id) pair, returns the most recent opinion up to the selected day/hour.
    """
    check_privileges(current_user.username)

    # Get experiment
    experiment = Exps.query.filter_by(idexp=expid).first()
    if not experiment:
        return jsonify({"error": "Experiment not found"}), 404

    # Check if opinions are enabled for this experiment
    if not experiment.annotations or "opinions" not in experiment.annotations:
        return jsonify({"error": "Opinion dynamics not enabled"}), 400

    # Activate experiment if not active (to access its database)
    from y_web.experiment_context import register_experiment_database

    bind_key = f"db_exp_{expid}"

    # Ensure the experiment database is registered
    if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
        register_experiment_database(current_app, expid, experiment.db_name)

    # Temporarily switch to experiment database
    old_bind = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
    current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
        "SQLALCHEMY_BINDS"
    ][bind_key]

    try:
        # Import experiment-specific models
        from sqlalchemy import and_, or_

        from y_web.models import Agent_Opinion, Rounds

        # Get filter parameters from request
        filter_day = request.args.get("day", type=int, default=1)
        filter_hour = request.args.get("hour", type=int, default=1)

        # Get topic_id as string to support both integers and UUIDs (HPC experiments)
        filter_topic_id_str = request.args.get("topic_id", type=str, default=None)

        # Handle empty string or 'null' as None
        if filter_topic_id_str in ("", "null", None):
            filter_topic_id = None
        else:
            # Try to convert to int if it's a numeric string (standard experiments)
            # Otherwise keep as string (UUID for HPC experiments)
            try:
                filter_topic_id = int(filter_topic_id_str)
            except (ValueError, TypeError):
                filter_topic_id = filter_topic_id_str

        # Use caching for statistics computation
        stats = get_or_compute_opinion_stats(
            expid, filter_day, filter_hour, filter_topic_id
        )

        # Get opinion groups from dashboard database for binning
        opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()

        # Prepare data for chart
        chart_labels = [group.name for group in opinion_groups]
        chart_values = [
            stats["binned_data"].get(group.name, 0) for group in opinion_groups
        ]

        # Get sample percentage from request
        sample_percentage = request.args.get("sample_percentage", type=int, default=50)

        # Check if we should skip generating group trends data (for performance during animation)
        # Parse as string since type=bool doesn't work correctly in Flask (bool("false") == True)
        skip_trends_str = request.args.get("skip_trends", type=str, default="false")
        skip_trends = skip_trends_str.lower() in ("true", "1", "yes")

        # Generate group trends data (opinion group volumes over time) - unless skipped
        if not skip_trends:
            group_trends_data = generate_group_trends_data(
                expid, filter_day, filter_hour, filter_topic_id
            )
        else:
            group_trends_data = None

        # Generate agent time series data
        timeseries_data = generate_agent_timeseries_data(
            expid, filter_day, filter_hour, filter_topic_id, sample_percentage
        )

        return jsonify(
            {
                "chart_labels": chart_labels,
                "chart_values": chart_values,
                "total_opinions": stats["total_opinions"],
                "social_interactions": stats["social_interactions"],
                "unique_agents": stats["unique_agents"],
                "filter_day": filter_day,
                "filter_hour": filter_hour,
                "group_trends_data": group_trends_data,
                "timeseries_data": timeseries_data,
            }
        )

    finally:
        # Restore old bind if it existed, otherwise remove the temporary bind
        if old_bind is not None:
            current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind
        else:
            current_app.config["SQLALCHEMY_BINDS"].pop("db_exp", None)
