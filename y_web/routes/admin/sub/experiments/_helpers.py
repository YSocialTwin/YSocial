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
from copy import deepcopy
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import requests
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

DEFAULT_STRESS_REWARD_SYSTEM = {
    "coupling": {
        "reward_buffers_stress_alpha": 0.30,
        "stress_reduces_reward_beta": 0.20,
    },
    "churn": {
        "enabled": False,
        "stress_weight": 1.5,
        "reward_weight": 1.0,
        "bias": -2.2,
        "temperature": 0.35,
        "min_probability": 0.0,
        "max_probability": 0.95,
    },
    "events": {
        "reaction": {
            "like": {"stress": -0.005, "reward": 0.03},
            "dislike": {"stress": 0.05, "reward": -0.03},
        },
        "report": {
            "mass_report": {"stress": 0.12, "reward": -0.05},
        },
        "comment": {
            "positive": {"stress": -0.02, "reward": 0.07},
            "neutral": {"stress": 0.0, "reward": 0.01},
            "critical": {"stress": 0.06, "reward": -0.02},
            "hostile": {"stress": 0.14, "reward": -0.07},
            "supportive": {"stress": -0.05, "reward": 0.08},
        },
        "share": {
            "positive": {"stress": -0.01, "reward": 0.08},
            "hostile": {"stress": 0.12, "reward": -0.06},
        },
        "moderation": {
            "protected": {"stress": -0.08, "reward": 0.03},
            "sanctioned": {"stress": 0.05, "reward": -0.06},
        },
    },
}


def _deep_update_dict(base, updates):
    result = deepcopy(base)
    for key, value in (updates or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_update_dict(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def default_stress_reward_config():
    return {
        "enabled": False,
        "backward_rounds": 24,
        "system": deepcopy(DEFAULT_STRESS_REWARD_SYSTEM),
    }


def normalize_stress_reward_config(raw_config):
    normalized = default_stress_reward_config()
    if not isinstance(raw_config, dict):
        return normalized

    normalized["enabled"] = bool(raw_config.get("enabled", normalized["enabled"]))
    try:
        normalized["backward_rounds"] = int(
            raw_config.get("backward_rounds", normalized["backward_rounds"]) or 24
        )
    except Exception:
        normalized["backward_rounds"] = 24
    normalized["system"] = _deep_update_dict(
        normalized["system"], raw_config.get("system") or {}
    )
    normalized["system"]["churn"]["enabled"] = bool(
        normalized["system"].get("churn", {}).get("enabled", False)
    )
    return normalized


def sync_stress_reward_client_config(client_config, stress_reward_config):
    """Write normalized stress/reward settings into a client config dict."""
    if not isinstance(client_config, dict):
        client_config = {}
    normalized = normalize_stress_reward_config(stress_reward_config)
    client_config["stress_reward"] = {
        "enabled": bool(normalized.get("enabled", False)),
        "backward_rounds": int(normalized.get("backward_rounds", 24) or 24),
        "system": deepcopy(normalized.get("system") or {}),
    }
    return client_config


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


def _experiment_configuration_box_present(experiment):
    """Return whether experiment_details should show a configuration block."""
    if experiment is None:
        return False
    return True


def _experiment_uses_llm_agents(experiment):
    """Resolve whether an experiment is configured to use LLM agents."""
    if experiment is None:
        return False

    default_enabled = bool(getattr(experiment, "llm_agents_enabled", 0))

    try:
        from y_web.src.system.path_utils import get_writable_path

        exp_folder = _get_experiment_folder(
            get_writable_path(), experiment, _get_database_type()
        )
        if not os.path.isdir(exp_folder):
            return default_enabled

        client_files = [
            filename
            for filename in os.listdir(exp_folder)
            if filename.endswith(".json") and filename.startswith("client")
        ]
        if not client_files:
            return default_enabled

        saw_llm_config = False
        for client_file in client_files:
            client_path = os.path.join(exp_folder, client_file)
            try:
                with open(client_path, "r") as f:
                    client_config = json.load(f)
            except Exception:
                continue

            llm_agents_value = (
                client_config.get("agents", {}).get("llm_agents")
                if isinstance(client_config, dict)
                else None
            )
            if llm_agents_value is None:
                continue

            saw_llm_config = True
            if not (
                isinstance(llm_agents_value, list)
                and len(llm_agents_value) == 1
                and llm_agents_value[0] is None
            ):
                return True

        if saw_llm_config:
            return False
    except Exception:
        pass

    return default_enabled


def _experiment_configuration_update_required(experiment):
    """Return whether experiment workflows must stay locked until config is acknowledged."""
    if not _experiment_configuration_box_present(experiment):
        return False

    try:
        from y_web.src.system.path_utils import get_writable_path

        base_dir = get_writable_path()
        cfg_path = os.path.join(
            _get_experiment_folder(base_dir, experiment, _get_database_type()),
            (
                "server_config.json"
                if getattr(experiment, "simulator_type", "Standard") == "HPC"
                else "config_server.json"
            ),
        )
        if not os.path.exists(cfg_path):
            return True
        with open(cfg_path, "r") as f:
            config = json.load(f)
        return not bool(config.get("experiment_configuration_confirmed"))
    except Exception:
        return True


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

    subreddit = _normalize_subreddit_input(item.get("subreddit", ""))
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


def _normalize_subreddit_input(value):
    """Normalize a subreddit identifier from a slug, /r/ path, or Reddit URL."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    lowered = raw_value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        parsed = urlparse(raw_value)
        host = parsed.netloc.lower()
        if host.endswith("reddit.com"):
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0].lower() == "r":
                return parts[1].strip().lower()
        return ""

    lowered = lowered[2:] if lowered.startswith("r/") else lowered
    lowered = lowered.strip("/")
    return lowered


def _read_feed_with_headers(feed_url):
    """Fetch a forum feed with explicit headers to avoid upstream blocks."""
    try:
        response = requests.get(
            feed_url,
            headers=FORUM_FEED_REQUEST_HEADERS,
            timeout=15,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.content
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None:
            raise HTTPError(
                feed_url,
                response.status_code,
                response.reason,
                response.headers,
                None,
            ) from exc
        raise
    except requests.RequestException as exc:
        raise URLError(str(exc)) from exc


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
    from y_web.src.system.path_utils import get_writable_path

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
        from y_web.src.system.path_utils import get_writable_path

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

    from y_web.src.system.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return None, None, redirect(url_for("experiments.settings"))

    experiment_dir = os.path.join(base_dir, "y_web", "experiments", exp_folder)
    os.makedirs(experiment_dir, exist_ok=True)
    return experiment, experiment_dir, None


def _load_memory_capable_experiment_context(uid, require_manage=True):
    """Load a memory-capable experiment and its writable directory."""
    check_privileges(current_user.username)

    experiment = Exps.query.filter_by(idexp=uid).first()
    if not experiment:
        flash("Experiment not found", "error")
        return None, None, redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user_or_none()
    if require_manage and not user_can_manage_experiment(admin_user, experiment):
        flash("You do not have permission to manage this experiment.", "error")
        return (
            None,
            None,
            redirect(url_for("experiments.experiment_details", uid=uid)),
        )

    from y_web.src.system.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return None, None, redirect(url_for("experiments.settings"))

    experiment_dir = os.path.join(base_dir, "y_web", "experiments", exp_folder)
    os.makedirs(experiment_dir, exist_ok=True)
    return experiment, experiment_dir, None


def _load_stress_reward_experiment_context(uid, require_manage=True):
    """Load a stress/reward-enabled experiment and its directory."""
    check_privileges(current_user.username)

    experiment = Exps.query.filter_by(idexp=uid).first()
    if not experiment:
        flash("Experiment not found", "error")
        return None, None, redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user_or_none()
    if require_manage and not user_can_manage_experiment(admin_user, experiment):
        flash("You do not have permission to manage this experiment.", "error")
        return None, None, redirect(url_for("experiments.experiment_details", uid=uid))

    if getattr(experiment, "platform_type", "") not in {
        "microblogging",
        "forum",
        "hpc",
    }:
        flash(
            "Stress/reward settings are available only for microblogging, forum, and HPC experiments.",
            "error",
        )
        return None, None, redirect(url_for("experiments.experiment_details", uid=uid))

    from y_web.src.system.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return None, None, redirect(url_for("experiments.settings"))

    experiment_dir = os.path.join(base_dir, "y_web", "experiments", exp_folder)
    os.makedirs(experiment_dir, exist_ok=True)

    config_path = os.path.join(
        experiment_dir,
        (
            "server_config.json"
            if experiment.simulator_type == "HPC"
            else "config_server.json"
        ),
    )
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                config = json.load(handle) or {}
        except Exception:
            config = {}

    stress_reward_cfg = normalize_stress_reward_config(config.get("stress_reward"))
    if not bool(stress_reward_cfg.get("enabled", False)):
        flash("Enable stress/reward in Experiment Configuration first.", "warning")
        return None, None, redirect(url_for("experiments.experiment_details", uid=uid))

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
                    health["article_count"] = int(
                        conn.execute(text("SELECT COUNT(*) FROM articles")).scalar()
                        or 0
                    )
                    health["image_post_count"] = int(
                        conn.execute(text("SELECT COUNT(*) FROM image_posts")).scalar()
                        or 0
                    )
                    health["rss_post_count"] = int(
                        conn.execute(
                            text(
                                "SELECT COUNT(*) FROM post WHERE news_id IS NOT NULL AND news_id NOT IN (-1, 0)"
                            )
                        ).scalar()
                        or 0
                    )
                    health["image_share_post_count"] = int(
                        conn.execute(
                            text(
                                "SELECT COUNT(*) FROM post WHERE image_post_id IS NOT NULL AND image_post_id NOT IN (-1, 0)"
                            )
                        ).scalar()
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
    """Load persisted memory embedding settings from experiment server config."""
    config_path = os.path.join(experiment_dir, "config_server.json")
    if not os.path.exists(config_path):
        hpc_config_path = os.path.join(experiment_dir, "server_config.json")
        if os.path.exists(hpc_config_path):
            config_path = hpc_config_path
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
    from y_web.src.content.avatars import normalize_forum_avatar_mode

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
