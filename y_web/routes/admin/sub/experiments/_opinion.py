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
import sqlite3
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
from y_web.src.system.path_utils import get_resource_path, get_writable_path

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


def _resolve_opinion_evolution_topics(expid):
    """Return topic metadata for opinion evolution pages.

    Prefer the experiment-local Interests table because opinion_evolution filters
    directly on Agent_Opinion.topic_id values stored in the experiment DB.
    Fall back to the dashboard mapping only for legacy datasets that do not expose
    Interests.
    """
    try:
        from y_web.src.models import Interests

        topics_query = db.session.query(Interests).all()
        topics = [{"iid": t.iid, "interest": t.interest} for t in topics_query]
        if topics:
            return topics
    except Exception:
        pass

    topic_links = Exp_Topic.query.filter_by(exp_id=expid).all()
    if topic_links:
        topic_ids = [link.topic_id for link in topic_links]
        topic_rows = (
            db.session.query(Topic_List).filter(Topic_List.id.in_(topic_ids)).all()
        )
        topic_names_by_id = {topic.id: topic.name for topic in topic_rows}
        return [
            {
                "iid": link.topic_id,
                "interest": topic_names_by_id.get(link.topic_id, str(link.topic_id)),
            }
            for link in topic_links
        ]

    return []


def _resolve_opinion_experiment_db_name(experiment):
    """Resolve the sqlite database path that should back opinion evolution."""
    db_name = (
        str(getattr(experiment, "db_name", "") or "").replace("\\", os.sep).strip()
    )
    uid = get_experiment_uid_from_db_name(db_name)
    if not uid:
        return db_name

    experiment_dir = os.path.join(get_writable_path(), "y_web", "experiments", uid)
    candidates = []

    if db_name:
        candidates.append(db_name)

    server_config_path = os.path.join(experiment_dir, "server_config.json")
    if os.path.exists(server_config_path):
        try:
            with open(server_config_path, "r") as handle:
                server_config = json.load(handle)
            sqlite_cfg = (server_config.get("database") or {}).get("sqlite") or {}
            sqlite_filename = str(sqlite_cfg.get("filename") or "").strip()
            if sqlite_filename:
                candidates.append(
                    os.path.join("experiments", uid, os.path.basename(sqlite_filename))
                )
            database_uri = str(server_config.get("database_uri") or "").strip()
            if database_uri:
                candidates.append(
                    os.path.join("experiments", uid, os.path.basename(database_uri))
                )
        except Exception:
            pass

    candidates.extend(
        [
            os.path.join("experiments", uid, "simulation.db"),
            os.path.join("experiments", uid, "database_server.db"),
        ]
    )

    seen = set()
    normalized_candidates = []
    for candidate in candidates:
        normalized = str(candidate or "").replace("\\", os.sep)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_candidates.append(normalized)

    required_tables = {"rounds", "agent_opinion"}
    fallback_existing = None
    for candidate in normalized_candidates:
        db_path = os.path.join(get_writable_path(), "y_web", candidate)
        if not os.path.exists(db_path):
            continue
        if fallback_existing is None:
            fallback_existing = candidate
        try:
            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            if required_tables.issubset(tables):
                return candidate
        except sqlite3.Error:
            continue

    return fallback_existing or db_name


def _experiment_db_has_required_opinion_tables(db_uri):
    """Check whether the currently bound experiment DB can serve opinion evolution."""
    if not db_uri or not db_uri.startswith("sqlite:///"):
        return True

    db_path = db_uri.replace("sqlite:///", "", 1)
    if not os.path.exists(db_path):
        return False

    try:
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
    except sqlite3.Error:
        return False

    return {"rounds", "agent_opinion"}.issubset(tables)


def _resolve_opinion_cold_start_value(experiment):
    """Resolve the configured opinion cold-start strategy for an experiment."""
    db_name = (
        str(getattr(experiment, "db_name", "") or "").replace("\\", os.sep).strip()
    )
    uid = get_experiment_uid_from_db_name(db_name)
    if not uid:
        return "neutral"

    experiment_dir = os.path.join(get_writable_path(), "y_web", "experiments", uid)
    for entry in os.listdir(experiment_dir) if os.path.isdir(experiment_dir) else []:
        if not entry.startswith("client_") or not entry.endswith(".json"):
            continue
        config_path = os.path.join(experiment_dir, entry)
        try:
            with open(config_path, "r") as handle:
                config = json.load(handle)
            params = (
                (config.get("simulation") or {})
                .get("opinion_dynamics", {})
                .get("parameters", {})
            )
            cold_start = str(params.get("cold_start") or "").strip().lower()
            if cold_start:
                return cold_start
        except Exception:
            continue

    return "neutral"


def _bootstrap_initial_agent_opinions_if_missing(expid, experiment):
    """Populate initial experiment-local agent_opinion rows when the table is empty.

    Standard experiments created during the regression window can have opinion
    dynamics enabled but no seeded opinion rows. The original page logic expects
    experiment-local Agent_Opinion data, so bootstrap a first neutral/random
    snapshot in the current experiment DB and invalidate cached aggregates.
    """
    from y_web.src.models import Agent_Opinion, Interests, Rounds, User_mgmt

    if db.session.query(Agent_Opinion.id).limit(1).first() is not None:
        return 0

    first_round = (
        db.session.query(Rounds)
        .order_by(Rounds.day.asc(), Rounds.hour.asc(), Rounds.id.asc())
        .first()
    )
    if first_round is None:
        return 0

    topics = db.session.query(Interests).order_by(Interests.iid.asc()).all()
    users = db.session.query(User_mgmt).filter(User_mgmt.is_page == 0).all()
    if not topics or not users:
        return 0

    cold_start = _resolve_opinion_cold_start_value(experiment)
    inserted = 0

    for user in users:
        for topic in topics:
            if cold_start == "random":
                opinion_value = random.random()
            else:
                opinion_value = 0.5

            db.session.add(
                Agent_Opinion(
                    agent_id=user.id,
                    tid=first_round.id,
                    topic_id=topic.iid,
                    id_interacted_with=user.id,
                    id_post=-1,
                    opinion=opinion_value,
                )
            )
            inserted += 1

    if inserted:
        db.session.commit()
        OpinionEvolutionCache.query.filter_by(exp_id=expid).delete()
        OpinionEvolutionSampledAgents.query.filter_by(exp_id=expid).delete()
        db.session.commit()

    return inserted


def _invalidate_stale_opinion_evolution_cache(expid):
    """Drop cached opinion-evolution frames if they outlive the current experiment DB.

    Experiments can be reset or rerun while keeping the same dashboard experiment id.
    In that case the dashboard cache may still contain frames from a previous run
    (for example day 11) while the current experiment DB only goes to an earlier
    point (for example day 2). When that happens the animation appears broken
    because the page reuses stale aggregates/samples.
    """
    from y_web.src.models import Rounds

    max_round = (
        db.session.query(Rounds.day, Rounds.hour)
        .order_by(Rounds.day.desc(), Rounds.hour.desc())
        .first()
    )
    if max_round is None:
        return False

    latest_cache = (
        OpinionEvolutionCache.query.filter_by(exp_id=expid)
        .order_by(OpinionEvolutionCache.day.desc(), OpinionEvolutionCache.hour.desc())
        .first()
    )
    if latest_cache is None:
        return False

    db_max_time = int(max_round.day) * 24 + int(max_round.hour)
    cache_max_time = int(latest_cache.day) * 24 + int(latest_cache.hour)

    if cache_max_time <= db_max_time:
        return False

    OpinionEvolutionCache.query.filter_by(exp_id=expid).delete()
    OpinionEvolutionSampledAgents.query.filter_by(exp_id=expid).delete()
    db.session.commit()
    return True


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

    from y_web.src.models import Agent_Opinion, Rounds

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

    from y_web.src.models import Agent_Opinion, Rounds

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

    from y_web.src.models import Agent_Opinion, Rounds

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
    from y_web.src.experiment.context import register_experiment_database

    bind_key = f"db_exp_{expid}"
    opinion_db_name = _resolve_opinion_experiment_db_name(experiment)
    register_experiment_database(current_app, expid, opinion_db_name)

    # Temporarily switch to experiment database
    old_bind = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
    current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
        "SQLALCHEMY_BINDS"
    ][bind_key]

    try:
        bound_db_uri = current_app.config["SQLALCHEMY_BINDS"].get(bind_key)
        if not _experiment_db_has_required_opinion_tables(bound_db_uri):
            flash(
                "The current experiment database does not contain opinion evolution tables.",
                "warning",
            )
            return render_template(
                "admin/opinion_evolution.html",
                experiment=experiment,
                topics=topics,
                max_day=1,
                max_hour=1,
                filter_day=1,
                filter_hour=1,
                filter_topic_id=(topics[0]["iid"] if topics else None),
                chart_labels=[],
                chart_values=[],
                total_opinions=0,
                social_interactions=0,
                unique_agents=0,
                group_trends_data=[],
                timeseries_data=[],
            )

        _invalidate_stale_opinion_evolution_cache(expid)
        _bootstrap_initial_agent_opinions_if_missing(expid, experiment)
        topics = _resolve_opinion_evolution_topics(expid)

        # Import experiment-specific models
        from sqlalchemy import and_, func, or_

        from y_web.src.models import Agent_Opinion, Rounds

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
    from y_web.src.experiment.context import register_experiment_database

    bind_key = f"db_exp_{expid}"
    opinion_db_name = _resolve_opinion_experiment_db_name(experiment)
    register_experiment_database(current_app, expid, opinion_db_name)

    # Temporarily switch to experiment database
    old_bind = current_app.config["SQLALCHEMY_BINDS"].get("db_exp")
    current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
        "SQLALCHEMY_BINDS"
    ][bind_key]

    try:
        bound_db_uri = current_app.config["SQLALCHEMY_BINDS"].get(bind_key)
        if not _experiment_db_has_required_opinion_tables(bound_db_uri):
            return (
                jsonify(
                    {
                        "error": "The current experiment database does not contain opinion evolution tables."
                    }
                ),
                400,
            )

        _invalidate_stale_opinion_evolution_cache(expid)
        _bootstrap_initial_agent_opinions_if_missing(expid, experiment)

        # Import experiment-specific models
        from sqlalchemy import and_, or_

        from y_web.src.models import Agent_Opinion, Rounds

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
