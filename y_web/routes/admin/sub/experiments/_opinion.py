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

import networkx as nx
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
from ._helpers import (
    _current_admin_user_or_none,
    _load_stress_reward_experiment_context,
)


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


def _get_ordered_opinion_groups():
    """Return opinion groups sorted by numeric lower bound."""
    groups = OpinionGroup.query.all()
    return sorted(groups, key=lambda group: float(group.lower_bound))


def _opinion_group_contains(group, opinion_value):
    """Check whether an opinion value falls within a group's numeric bounds."""
    lower_bound = float(group.lower_bound)
    upper_bound = float(group.upper_bound)
    numeric_value = float(opinion_value)
    return lower_bound <= numeric_value <= upper_bound


def _build_propaganda_target_opinion_trend(
    db_path, filter_day, filter_hour, topic_id, target_uid
):
    """Return topic-specific opinion trends for one propaganda target."""
    if topic_id in (None, "", "null") or target_uid in (None, "", "null"):
        return {"timestamps": [], "timestamp_mapping": {}, "datasets": []}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        display_rounds = _get_stress_reward_display_rounds(conn, filter_day)
        if not display_rounds:
            return {"timestamps": [], "timestamp_mapping": {}, "datasets": []}

        opinion_rows = conn.execute(
            """
            SELECT
                ao.rowid AS row_order,
                ao.opinion,
                r.day,
                r.hour
            FROM agent_opinion ao
            JOIN rounds r
              ON ao.tid = r.id
            WHERE ao.agent_id = ?
              AND ao.topic_id = ?
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            ORDER BY r.day, r.hour, row_order
            """,
            (target_uid, str(topic_id), filter_day, filter_day, filter_hour),
        ).fetchall()

        interaction_rows = conn.execute(
            """
            SELECT
                r.day,
                COUNT(*) AS interaction_count
            FROM propaganda_activity pa
            JOIN rounds r
              ON r.id = pa.discussion_round_id
            WHERE pa.target_uid = ?
              AND pa.topic_id = ?
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY r.day
            ORDER BY r.day
            """,
            (target_uid, str(topic_id), filter_day, filter_day, filter_hour),
        ).fetchall()

    interactions_by_day = {
        int(row["day"]): int(row["interaction_count"]) for row in interaction_rows
    }
    latest_opinion = None
    current_index = 0
    sorted_rows = list(opinion_rows)
    timestamps = []
    timestamp_mapping = {}
    opinion_series = []
    interaction_series = []

    for round_row in display_rounds:
        target_day = int(round_row["day"])
        target_hour = int(round_row["hour"])

        while current_index < len(sorted_rows):
            row = sorted_rows[current_index]
            if row["day"] > target_day or (
                row["day"] == target_day and row["hour"] > target_hour
            ):
                break
            latest_opinion = float(row["opinion"])
            current_index += 1

        timestamps.append(float(target_day))
        timestamp_mapping[float(target_day)] = {
            "day": target_day,
            "hour": target_hour,
            "absolute": target_day * 24 + target_hour,
        }
        opinion_series.append(
            float(latest_opinion) if latest_opinion is not None else None
        )
        interaction_series.append(int(interactions_by_day.get(target_day, 0)))

    return {
        "timestamps": timestamps,
        "timestamp_mapping": timestamp_mapping,
        "datasets": [
            {"label": "Target Opinion", "data": opinion_series},
            {"label": "Propaganda Interactions", "data": interaction_series},
        ],
    }


def _build_propaganda_target_panel(
    db_path, filter_day, filter_hour, topic_id, selected_target_uid=None
):
    """Return propaganda target options and selected-target analytics."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        propaganda_count = conn.execute("""
                SELECT COUNT(*)
                FROM user_mgmt
                WHERE user_type = 'propaganda'
                """).fetchone()[0] or 0
        has_activity_table = conn.execute("""
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'propaganda_activity'
                """).fetchone() is not None
        if propaganda_count <= 0 or not has_activity_table:
            return {
                "available": False,
                "deployed_agents": int(propaganda_count),
                "active_topics": [],
                "selected_topic_has_data": False,
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        if topic_id in (None, "", "null"):
            active_topic_rows = conn.execute("""
                SELECT DISTINCT pa.topic_id AS topic_id, COALESCE(i.interest, pa.topic_id) AS topic_name
                FROM propaganda_activity pa
                LEFT JOIN interests i
                  ON i.iid = pa.topic_id
                ORDER BY topic_name ASC
                """).fetchall()
            return {
                "available": True,
                "deployed_agents": int(propaganda_count),
                "active_topics": [
                    {"topic_id": str(row["topic_id"]), "topic_name": row["topic_name"]}
                    for row in active_topic_rows
                ],
                "selected_topic_has_data": False,
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        active_topic_rows = conn.execute("""
            SELECT DISTINCT pa.topic_id AS topic_id, COALESCE(i.interest, pa.topic_id) AS topic_name
            FROM propaganda_activity pa
            LEFT JOIN interests i
              ON i.iid = pa.topic_id
            ORDER BY topic_name ASC
            """).fetchall()
        active_topics = [
            {"topic_id": str(row["topic_id"]), "topic_name": row["topic_name"]}
            for row in active_topic_rows
        ]

        option_rows = conn.execute(
            """
            SELECT
                pa.target_uid AS uid,
                tu.username AS username,
                COUNT(*) AS interaction_count,
                GROUP_CONCAT(DISTINCT pu.username) AS attacker_usernames
            FROM propaganda_activity pa
            JOIN rounds r
              ON r.id = pa.discussion_round_id
            JOIN user_mgmt tu
              ON tu.id = pa.target_uid
            JOIN user_mgmt pu
              ON pu.id = pa.propaganda_agent_uid
            WHERE pa.topic_id = ?
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY pa.target_uid, tu.username
            ORDER BY interaction_count DESC, tu.username ASC
            """,
            (str(topic_id), filter_day, filter_day, filter_hour),
        ).fetchall()

        options = [
            {
                "uid": str(row["uid"]),
                "username": row["username"],
                "interaction_count": int(row["interaction_count"] or 0),
                "attacker_usernames": sorted(
                    {
                        item.strip()
                        for item in str(row["attacker_usernames"] or "").split(",")
                        if item and item.strip()
                    }
                ),
            }
            for row in option_rows
            if row["uid"] is not None
        ]

        if not options:
            return {
                "available": True,
                "deployed_agents": int(propaganda_count),
                "active_topics": active_topics,
                "selected_topic_has_data": False,
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        valid_target_ids = {
            str(option.get("uid"))
            for option in options
            if isinstance(option, dict) and option.get("uid") is not None
        }
        if selected_target_uid not in valid_target_ids:
            selected_target_uid = (
                str(options[0].get("uid")) if isinstance(options[0], dict) else None
            )

        selected_option = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and str(option.get("uid")) == str(selected_target_uid)
            ),
            options[0],
        )
        selected_uid = str(selected_option.get("uid")) if selected_option else None
        selected_username = str(selected_option.get("username") or "")
        selected_attackers = selected_option.get("attacker_usernames") or []
        selected_interaction_count = int(selected_option.get("interaction_count") or 0)
        event_rows = conn.execute(
            """
            SELECT
                r.day,
                r.hour,
                COUNT(*) AS interaction_count,
                GROUP_CONCAT(DISTINCT pu.username) AS attacker_usernames
            FROM propaganda_activity pa
            JOIN rounds r
              ON r.id = pa.discussion_round_id
            JOIN user_mgmt pu
              ON pu.id = pa.propaganda_agent_uid
            WHERE pa.topic_id = ?
              AND pa.target_uid = ?
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY r.day, r.hour
            ORDER BY r.day DESC, r.hour DESC
            LIMIT 50
            """,
            (str(topic_id), selected_target_uid, filter_day, filter_day, filter_hour),
        ).fetchall()

    interaction_events = [
        {
            "day": int(row["day"]),
            "hour": int(row["hour"]),
            "interaction_count": int(row["interaction_count"] or 0),
            "attacker_usernames": sorted(
                {
                    item.strip()
                    for item in str(row["attacker_usernames"] or "").split(",")
                    if item and item.strip()
                }
            ),
        }
        for row in event_rows
    ]

    return {
        "available": True,
        "deployed_agents": int(propaganda_count),
        "active_topics": active_topics,
        "selected_topic_has_data": True,
        "options": options,
        "selected_uid": selected_uid,
        "selected_username": selected_username,
        "attacker_usernames": selected_attackers,
        "interaction_count": selected_interaction_count,
        "trend_data": _build_propaganda_target_opinion_trend(
            db_path, filter_day, filter_hour, topic_id, selected_uid
        ),
        "interaction_events": interaction_events,
    }


def _build_mop_target_opinion_trend(
    db_path, filter_day, filter_hour, topic_id, target_uid
):
    """Return topic-specific opinion trends for one MoP target."""
    if topic_id in (None, "", "null") or target_uid in (None, "", "null"):
        return {"timestamps": [], "timestamp_mapping": {}, "datasets": []}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        display_rounds = _get_stress_reward_display_rounds(conn, filter_day)
        if not display_rounds:
            return {"timestamps": [], "timestamp_mapping": {}, "datasets": []}

        opinion_rows = conn.execute(
            """
            SELECT
                ao.rowid AS row_order,
                ao.opinion,
                r.day,
                r.hour
            FROM agent_opinion ao
            JOIN rounds r
              ON ao.tid = r.id
            WHERE ao.agent_id = ?
              AND ao.topic_id = ?
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            ORDER BY r.day, r.hour, row_order
            """,
            (target_uid, str(topic_id), filter_day, filter_day, filter_hour),
        ).fetchall()

        interaction_rows = conn.execute(
            """
            WITH mop_users AS (
                SELECT id, username
                FROM user_mgmt
                WHERE user_type IN ('master_of_puppets', 'mop_puppet')
            ),
            mop_interactions AS (
                SELECT
                    m.user_id AS target_uid,
                    au.username AS attacker_username,
                    'mention' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM mentions m
                JOIN post p
                  ON p.id = m.post_id
                JOIN mop_users au
                  ON au.id = p.user_id
                JOIN rounds r
                  ON r.id = p.round
                JOIN post_topics pt
                  ON pt.post_id = p.id
                WHERE pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

                UNION ALL

                SELECT
                    target_post.user_id AS target_uid,
                    au.username AS attacker_username,
                    'reaction' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM reactions rr
                JOIN mop_users au
                  ON au.id = rr.user_id
                JOIN post target_post
                  ON target_post.id = rr.post_id
                JOIN rounds r
                  ON r.id = rr.round
                JOIN post_topics pt
                  ON pt.post_id = COALESCE(target_post.thread_id, target_post.id)
                WHERE pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

                UNION ALL

                SELECT
                    COALESCE(rep.to_uid, target_post.user_id) AS target_uid,
                    au.username AS attacker_username,
                    'report' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM reported rep
                JOIN mop_users au
                  ON au.id = rep.from_uid
                JOIN rounds r
                  ON r.id = rep.tid
                LEFT JOIN post target_post
                  ON target_post.id = rep.to_post
                LEFT JOIN post_topics pt
                  ON pt.post_id = COALESCE(target_post.thread_id, target_post.id)
                WHERE COALESCE(rep.to_uid, target_post.user_id) IS NOT NULL
                  AND pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            )
            SELECT day, COUNT(*) AS interaction_count
            FROM mop_interactions
            WHERE target_uid = ?
            GROUP BY day
            ORDER BY day
            """,
            (
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                target_uid,
            ),
        ).fetchall()

    interactions_by_day = {
        int(row["day"]): int(row["interaction_count"]) for row in interaction_rows
    }
    latest_opinion = None
    current_index = 0
    sorted_rows = list(opinion_rows)
    timestamps = []
    timestamp_mapping = {}
    opinion_series = []
    interaction_series = []

    for round_row in display_rounds:
        target_day = int(round_row["day"])
        target_hour = int(round_row["hour"])

        while current_index < len(sorted_rows):
            row = sorted_rows[current_index]
            if row["day"] > target_day or (
                row["day"] == target_day and row["hour"] > target_hour
            ):
                break
            latest_opinion = float(row["opinion"])
            current_index += 1

        timestamps.append(float(target_day))
        timestamp_mapping[float(target_day)] = {
            "day": target_day,
            "hour": target_hour,
            "absolute": target_day * 24 + target_hour,
        }
        opinion_series.append(
            float(latest_opinion) if latest_opinion is not None else None
        )
        interaction_series.append(int(interactions_by_day.get(target_day, 0)))

    return {
        "timestamps": timestamps,
        "timestamp_mapping": timestamp_mapping,
        "datasets": [
            {"label": "Target Opinion", "data": opinion_series},
            {"label": "MoP Interactions", "data": interaction_series},
        ],
    }


def _build_mop_target_panel(
    db_path, filter_day, filter_hour, topic_id, selected_target_uid=None
):
    """Return MoP target options and selected-target analytics."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        mop_count = conn.execute("""
                SELECT COUNT(*)
                FROM user_mgmt
                WHERE user_type = 'master_of_puppets'
                """).fetchone()[0] or 0
        if mop_count <= 0:
            return {
                "available": False,
                "deployed_agents": 0,
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        if topic_id in (None, "", "null"):
            return {
                "available": True,
                "deployed_agents": int(mop_count),
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        option_rows = conn.execute(
            """
            WITH mop_users AS (
                SELECT id, username
                FROM user_mgmt
                WHERE user_type IN ('master_of_puppets', 'mop_puppet')
            ),
            mop_interactions AS (
                SELECT
                    m.user_id AS target_uid,
                    au.username AS attacker_username,
                    'mention' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM mentions m
                JOIN post p
                  ON p.id = m.post_id
                JOIN mop_users au
                  ON au.id = p.user_id
                JOIN rounds r
                  ON r.id = p.round
                JOIN post_topics pt
                  ON pt.post_id = p.id
                WHERE pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

                UNION ALL

                SELECT
                    target_post.user_id AS target_uid,
                    au.username AS attacker_username,
                    'reaction' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM reactions rr
                JOIN mop_users au
                  ON au.id = rr.user_id
                JOIN post target_post
                  ON target_post.id = rr.post_id
                JOIN rounds r
                  ON r.id = rr.round
                JOIN post_topics pt
                  ON pt.post_id = COALESCE(target_post.thread_id, target_post.id)
                WHERE pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

                UNION ALL

                SELECT
                    COALESCE(rep.to_uid, target_post.user_id) AS target_uid,
                    au.username AS attacker_username,
                    'report' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM reported rep
                JOIN mop_users au
                  ON au.id = rep.from_uid
                JOIN rounds r
                  ON r.id = rep.tid
                LEFT JOIN post target_post
                  ON target_post.id = rep.to_post
                LEFT JOIN post_topics pt
                  ON pt.post_id = COALESCE(target_post.thread_id, target_post.id)
                WHERE COALESCE(rep.to_uid, target_post.user_id) IS NOT NULL
                  AND pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            )
            SELECT
                mi.target_uid AS uid,
                tu.username AS username,
                COUNT(*) AS interaction_count,
                GROUP_CONCAT(DISTINCT mi.attacker_username) AS attacker_usernames
            FROM mop_interactions mi
            JOIN user_mgmt tu
              ON tu.id = mi.target_uid
            WHERE tu.user_type NOT IN (
                'master_of_puppets',
                'mop_puppet',
                'propaganda',
                'stress_attacker',
                'comic_relief'
            )
            GROUP BY mi.target_uid, tu.username
            ORDER BY interaction_count DESC, tu.username ASC
            """,
            (
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
            ),
        ).fetchall()

        options = [
            {
                "uid": str(row["uid"]),
                "username": row["username"],
                "interaction_count": int(row["interaction_count"] or 0),
                "attacker_usernames": sorted(
                    {
                        item.strip()
                        for item in str(row["attacker_usernames"] or "").split(",")
                        if item and item.strip()
                    }
                ),
            }
            for row in option_rows
            if row["uid"] is not None
        ]

        if not options:
            return {
                "available": True,
                "deployed_agents": int(mop_count),
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        valid_target_ids = {
            str(option.get("uid"))
            for option in options
            if isinstance(option, dict) and option.get("uid") is not None
        }
        if selected_target_uid not in valid_target_ids:
            selected_target_uid = (
                str(options[0].get("uid")) if isinstance(options[0], dict) else None
            )

        selected_option = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and str(option.get("uid")) == str(selected_target_uid)
            ),
            options[0],
        )
        selected_uid = str(selected_option.get("uid")) if selected_option else None
        selected_username = str(selected_option.get("username") or "")
        selected_attackers = selected_option.get("attacker_usernames") or []
        selected_interaction_count = int(selected_option.get("interaction_count") or 0)
        event_rows = conn.execute(
            """
            WITH mop_users AS (
                SELECT id, username
                FROM user_mgmt
                WHERE user_type IN ('master_of_puppets', 'mop_puppet')
            ),
            mop_interactions AS (
                SELECT
                    m.user_id AS target_uid,
                    au.username AS attacker_username,
                    'mention' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM mentions m
                JOIN post p
                  ON p.id = m.post_id
                JOIN mop_users au
                  ON au.id = p.user_id
                JOIN rounds r
                  ON r.id = p.round
                JOIN post_topics pt
                  ON pt.post_id = p.id
                WHERE pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

                UNION ALL

                SELECT
                    target_post.user_id AS target_uid,
                    au.username AS attacker_username,
                    'reaction' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM reactions rr
                JOIN mop_users au
                  ON au.id = rr.user_id
                JOIN post target_post
                  ON target_post.id = rr.post_id
                JOIN rounds r
                  ON r.id = rr.round
                JOIN post_topics pt
                  ON pt.post_id = COALESCE(target_post.thread_id, target_post.id)
                WHERE pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

                UNION ALL

                SELECT
                    COALESCE(rep.to_uid, target_post.user_id) AS target_uid,
                    au.username AS attacker_username,
                    'report' AS interaction_type,
                    r.day AS day,
                    r.hour AS hour
                FROM reported rep
                JOIN mop_users au
                  ON au.id = rep.from_uid
                JOIN rounds r
                  ON r.id = rep.tid
                LEFT JOIN post target_post
                  ON target_post.id = rep.to_post
                LEFT JOIN post_topics pt
                  ON pt.post_id = COALESCE(target_post.thread_id, target_post.id)
                WHERE COALESCE(rep.to_uid, target_post.user_id) IS NOT NULL
                  AND pt.topic_id = ?
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            )
            SELECT
                day,
                hour,
                interaction_type,
                COUNT(*) AS interaction_count,
                GROUP_CONCAT(DISTINCT attacker_username) AS attacker_usernames
            FROM mop_interactions
            WHERE target_uid = ?
            GROUP BY day, hour, interaction_type
            ORDER BY day DESC, hour DESC, interaction_type ASC
            LIMIT 50
            """,
            (
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                str(topic_id),
                filter_day,
                filter_day,
                filter_hour,
                selected_target_uid,
            ),
        ).fetchall()

    interaction_events = [
        {
            "day": int(row["day"]),
            "hour": int(row["hour"]),
            "interaction_type": row["interaction_type"],
            "interaction_count": int(row["interaction_count"] or 0),
            "attacker_usernames": sorted(
                {
                    item.strip()
                    for item in str(row["attacker_usernames"] or "").split(",")
                    if item and item.strip()
                }
            ),
        }
        for row in event_rows
    ]

    return {
        "available": True,
        "deployed_agents": int(mop_count),
        "options": options,
        "selected_uid": selected_uid,
        "selected_username": selected_username,
        "attacker_usernames": selected_attackers,
        "interaction_count": selected_interaction_count,
        "trend_data": _build_mop_target_opinion_trend(
            db_path, filter_day, filter_hour, topic_id, selected_uid
        ),
        "interaction_events": interaction_events,
    }


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


def _is_legacy_opinion_cache_state(cache_entry):
    """Return True when a cached opinion state lacks row-order information.

    Older cache entries only stored day/hour and therefore cannot distinguish
    multiple Standard opinion updates written within the same simulation hour.
    """
    if cache_entry is None or not getattr(cache_entry, "latest_opinions_state", None):
        return False
    try:
        state = json.loads(cache_entry.latest_opinions_state)
    except Exception:
        return True

    for topics in state.values():
        if not isinstance(topics, dict):
            continue
        for opinion_state in topics.values():
            if not isinstance(opinion_state, dict):
                continue
            return "row_id" not in opinion_state
    return False


def _is_invalid_opinion_cache_entry(cache_entry):
    """Return True when a cached aggregate is internally inconsistent."""
    if cache_entry is None:
        return False
    try:
        binned = json.loads(cache_entry.binned_data or "{}")
        if not isinstance(binned, dict):
            return True
        total_binned = sum(int(v) for v in binned.values())
    except Exception:
        return True

    total_opinions = int(cache_entry.total_opinions or 0)
    unique_agents = int(cache_entry.unique_agents or 0)

    if unique_agents > total_opinions:
        return True
    if total_binned != total_opinions:
        return True
    return _is_legacy_opinion_cache_state(cache_entry)


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
    opinion_groups = _get_ordered_opinion_groups()

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
            Agent_Opinion.id,
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
    for (
        row_id,
        agent_id,
        topic_id,
        tid,
        opinion,
        opinion_day,
        opinion_hour,
    ) in all_opinions:
        opinions_by_time[(opinion_day, opinion_hour)].append(
            (row_id, agent_id, topic_id, opinion)
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
            for row_id, agent_id, topic_id, opinion in sorted(
                opinions_by_time[(time_day, time_hour)], key=lambda item: item[0]
            ):
                key = (agent_id, topic_id)
                latest_at_time[key] = opinion

            current_time_index += 1

        # Bin the opinions at this timestamp
        binned_counts = {group.name: 0 for group in opinion_groups}

        for opinion_value in latest_at_time.values():
            matched = False
            for group in opinion_groups:
                if _opinion_group_contains(group, opinion_value):
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
            Agent_Opinion.id,
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

    for (
        row_id,
        agent_id,
        topic_id,
        tid,
        opinion,
        opinion_day,
        opinion_hour,
    ) in all_opinions:
        opinions_by_time[(opinion_day, opinion_hour)].append(
            (row_id, agent_id, topic_id, opinion)
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
            for row_id, agent_id, topic_id, opinion in sorted(
                opinions_by_time[(time_day, time_hour)], key=lambda item: item[0]
            ):
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
    opinion_groups = _get_ordered_opinion_groups()

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
                if _opinion_group_contains(group, first_opinion):
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

    for row in all_opinions:
        if len(row) == 8:
            (
                _row_id,
                agent_id,
                topic_id,
                tid,
                opinion,
                id_interacted_with,
                day,
                hour,
            ) = row
        else:
            (
                agent_id,
                topic_id,
                tid,
                opinion,
                id_interacted_with,
                day,
                hour,
            ) = row
        if id_interacted_with == agent_id:
            continue
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

    if cache_entry and _is_invalid_opinion_cache_entry(cache_entry):
        OpinionEvolutionCache.query.filter_by(
            exp_id=expid, topic_id=filter_topic_id
        ).delete()
        db.session.commit()
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

    if previous_cache and _is_invalid_opinion_cache_entry(previous_cache):
        OpinionEvolutionCache.query.filter_by(
            exp_id=expid, topic_id=filter_topic_id
        ).delete()
        db.session.commit()
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
                Agent_Opinion.id,
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
                    row_id,
                    agent_id,
                    topic_id,
                    tid,
                    opinion,
                    id_interacted_with,
                    round_time_map[tid][0],
                    round_time_map[tid][1],
                )
                for row_id, agent_id, topic_id, tid, opinion, id_interacted_with in new_opinions
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
                row_id,
            ) in new_opinions_with_rounds:
                key = (agent_id, topic_id)

                # Update if this is newer than what we have
                if key not in latest_opinions or (day, hour, tid, row_id) > (
                    latest_opinions[key]["day"],
                    latest_opinions[key]["hour"],
                    latest_opinions[key].get("tid", -1),
                    latest_opinions[key].get("row_id", -1),
                ):
                    latest_opinions[key] = {
                        "tid": tid,
                        "row_id": row_id,
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
                Agent_Opinion.id,
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
            row_id,
            agent_id,
            topic_id,
            tid,
            opinion,
            id_interacted_with,
            day,
            hour,
        ) in all_opinions:
            key = (agent_id, topic_id)
            if key not in latest_opinions or (day, hour, tid, row_id) > (
                latest_opinions[key]["day"],
                latest_opinions[key]["hour"],
                latest_opinions[key].get("tid", -1),
                latest_opinions[key].get("row_id", -1),
            ):
                latest_opinions[key] = {
                    "tid": tid,
                    "row_id": row_id,
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
    opinion_groups = _get_ordered_opinion_groups()
    binned_data = {group.name: 0 for group in opinion_groups}

    for opinion_value in opinion_data:
        for group in opinion_groups:
            if _opinion_group_contains(group, opinion_value):
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
                "tid": data.get("tid"),
                "row_id": data.get("row_id"),
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
    opinion_db_path = _resolve_experiment_db_path(experiment)
    register_experiment_database(current_app, expid, opinion_db_name)

    # Initialize defaults before entering the DB-bound section so all early-return
    # and fallback paths can safely render without undefined locals.
    topics = []
    max_day = 1
    max_hour = 1
    filter_day = 1
    filter_hour = 1
    filter_topic_id = None
    opinion_data = []
    social_interactions = 0
    unique_agents = 0
    group_trends_data = []
    timeseries_data = []
    propaganda_targets = {
        "available": False,
        "deployed_agents": 0,
        "options": [],
        "selected_uid": None,
        "selected_username": None,
        "attacker_usernames": [],
        "interaction_count": 0,
        "trend_data": {
            "timestamps": [],
            "timestamp_mapping": {},
            "datasets": [],
        },
        "interaction_events": [],
    }
    mop_targets = {
        "available": False,
        "deployed_agents": 0,
        "options": [],
        "selected_uid": None,
        "selected_username": None,
        "attacker_usernames": [],
        "interaction_count": 0,
        "trend_data": {
            "timestamps": [],
            "timestamp_mapping": {},
            "datasets": [],
        },
        "interaction_events": [],
    }

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
                max_day=max_day,
                max_hour=max_hour,
                filter_day=filter_day,
                filter_hour=filter_hour,
                filter_topic_id=(topics[0]["iid"] if topics else None),
                chart_labels=[],
                chart_values=[],
                total_opinions=0,
                social_interactions=social_interactions,
                unique_agents=unique_agents,
                group_trends_data=group_trends_data,
                timeseries_data=timeseries_data,
                propaganda_targets=propaganda_targets,
                mop_targets=mop_targets,
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
        propaganda_target_uid = (
            str(request.args.get("propaganda_target_uid", "") or "").strip() or None
        )
        mop_target_uid = (
            str(request.args.get("mop_target_uid", "") or "").strip() or None
        )

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
                Agent_Opinion.id,
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
            row_id,
            agent_id,
            topic_id,
            tid,
            opinion,
            id_interacted_with,
            day,
            hour,
        ) in all_opinions:
            key = (agent_id, topic_id)
            if key not in latest_opinions or (day, hour, tid, row_id) > (
                latest_opinions[key]["day"],
                latest_opinions[key]["hour"],
                latest_opinions[key].get("tid", -1),
                latest_opinions[key].get("row_id", -1),
            ):
                latest_opinions[key] = {
                    "tid": tid,
                    "row_id": row_id,
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
        opinion_groups = _get_ordered_opinion_groups()

        # Bin the opinions according to opinion_groups
        binned_data = {group.name: 0 for group in opinion_groups}
        unmatched_count = 0

        for opinion_value in opinion_data:
            # Find which bin this opinion belongs to
            matched = False
            for group in opinion_groups:
                if _opinion_group_contains(group, opinion_value):
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
        propaganda_targets = _build_propaganda_target_panel(
            opinion_db_path,
            filter_day,
            filter_hour,
            filter_topic_id,
            selected_target_uid=propaganda_target_uid,
        )
        mop_targets = _build_mop_target_panel(
            opinion_db_path,
            filter_day,
            filter_hour,
            filter_topic_id,
            selected_target_uid=mop_target_uid,
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
        propaganda_targets=propaganda_targets,
        mop_targets=mop_targets,
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
    opinion_db_path = _resolve_experiment_db_path(experiment)
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
        propaganda_target_uid = (
            str(request.args.get("propaganda_target_uid", "") or "").strip() or None
        )
        mop_target_uid = (
            str(request.args.get("mop_target_uid", "") or "").strip() or None
        )

        # Use caching for statistics computation
        stats = get_or_compute_opinion_stats(
            expid, filter_day, filter_hour, filter_topic_id
        )

        # Get opinion groups from dashboard database for binning
        opinion_groups = _get_ordered_opinion_groups()

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
        propaganda_targets = _build_propaganda_target_panel(
            opinion_db_path,
            filter_day,
            filter_hour,
            filter_topic_id,
            selected_target_uid=propaganda_target_uid,
        )
        mop_targets = _build_mop_target_panel(
            opinion_db_path,
            filter_day,
            filter_hour,
            filter_topic_id,
            selected_target_uid=mop_target_uid,
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
                "propaganda_targets": propaganda_targets,
                "mop_targets": mop_targets,
            }
        )

    finally:
        # Restore old bind if it existed, otherwise remove the temporary bind
        if old_bind is not None:
            current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = old_bind
        else:
            current_app.config["SQLALCHEMY_BINDS"].pop("db_exp", None)


_STRESS_REWARD_LEVELS = [
    ("None", 0.0, 0.2),
    ("Low", 0.2, 0.4),
    ("Moderate", 0.4, 0.6),
    ("High", 0.6, 0.8),
    ("Extreme", 0.8, 1.0000001),
]


def _resolve_experiment_db_path(experiment):
    """Return the absolute sqlite path for experiment analytics views."""
    db_name = _resolve_opinion_experiment_db_name(experiment)
    if os.path.isabs(db_name):
        return db_name
    return os.path.join(get_writable_path(), "y_web", db_name)


def _resolve_network_analysis_db_path(experiment):
    """Return the experiment DB path used by network analytics.

    Photo-sharing experiments keep their simulation state in yphotosharing.db,
    while the dashboard metadata may still point to the legacy
    database_server.db file. Network analytics must therefore prefer the photo
    DB when it exists, otherwise they would inspect the wrong schema and report
    that the network-analysis tables are missing.
    """
    if getattr(experiment, "platform_type", "") == "photo_sharing":
        db_name = (
            str(getattr(experiment, "db_name", "") or "").replace("\\", os.sep).strip()
        )
        uid = get_experiment_uid_from_db_name(db_name)
        if uid:
            photo_db_path = os.path.join(
                get_writable_path(), "y_web", "experiments", uid, "yphotosharing.db"
            )
            if os.path.exists(photo_db_path):
                return photo_db_path

    return _resolve_experiment_db_path(experiment)


def _experiment_db_has_required_stress_reward_tables(db_path):
    """Check whether the experiment DB exposes stress/reward analytics tables."""
    if not db_path or not os.path.exists(db_path):
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

    return {"stress_reward", "rounds"}.issubset(tables)


def _get_stress_reward_max_round(db_path):
    """Return the latest available round coordinates for stress/reward analytics."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT day, hour FROM rounds ORDER BY day DESC, hour DESC LIMIT 1"
        ).fetchone()
    if not row:
        return 1, 1
    return int(row[0]), int(row[1])


def _get_stress_reward_display_rounds(conn, filter_day):
    """Return representative rounds for timeline display."""
    rows = conn.execute(
        """
        SELECT id, day, hour
        FROM rounds
        WHERE hour = 0 AND day <= ?
        ORDER BY day, hour
        """,
        (filter_day,),
    ).fetchall()
    if rows:
        return rows

    return conn.execute(
        """
        SELECT r.id, r.day, r.hour
        FROM rounds r
        JOIN (
            SELECT day, MIN(hour) AS min_hour
            FROM rounds
            WHERE day <= ?
            GROUP BY day
        ) picked
          ON r.day = picked.day AND r.hour = picked.min_hour
        ORDER BY r.day, r.hour
        """,
        (filter_day,),
    ).fetchall()


def _stress_reward_level_label(value):
    """Map an aggregate value to a named stress/reward level."""
    numeric_value = float(value)
    for label, lower, upper in _STRESS_REWARD_LEVELS:
        if lower <= numeric_value < upper:
            return label
    return _STRESS_REWARD_LEVELS[-1][0]


def _build_stress_reward_snapshot(db_path, filter_day, filter_hour):
    """Aggregate latest stress/reward values up to the requested time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT uid, variable, value
            FROM (
                SELECT
                    sr.uid AS uid,
                    sr.variable,
                    sr.value,
                    ROW_NUMBER() OVER (
                        PARTITION BY sr.uid, sr.variable
                        ORDER BY r.day DESC, r.hour DESC, sr.rowid DESC
                    ) AS rn
                FROM stress_reward sr
                JOIN rounds r
                  ON sr.tid = r.id
                WHERE sr.type = 'aggregate'
                  AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            ) latest
            WHERE rn = 1
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

    latest_aggregates = {
        (str(row["uid"]), row["variable"]): float(row["value"]) for row in rows
    }
    unique_agents = {str(row["uid"]) for row in rows}

    distributions = {
        "stress": {label: 0 for label, _, _ in _STRESS_REWARD_LEVELS},
        "reward": {label: 0 for label, _, _ in _STRESS_REWARD_LEVELS},
    }
    averages = {"stress": 0.0, "reward": 0.0}

    for variable in ("stress", "reward"):
        values = [
            value
            for (uid, current_variable), value in latest_aggregates.items()
            if current_variable == variable
        ]
        if values:
            averages[variable] = sum(values) / len(values)
        for value in values:
            distributions[variable][_stress_reward_level_label(value)] += 1

    return {
        "stress_labels": [label for label, _, _ in _STRESS_REWARD_LEVELS],
        "stress_values": [
            distributions["stress"][label] for label, _, _ in _STRESS_REWARD_LEVELS
        ],
        "reward_labels": [label for label, _, _ in _STRESS_REWARD_LEVELS],
        "reward_values": [
            distributions["reward"][label] for label, _, _ in _STRESS_REWARD_LEVELS
        ],
        "average_stress": averages["stress"],
        "average_reward": averages["reward"],
        "aggregate_rows": len(rows),
        "unique_agents": len(unique_agents),
    }


def _build_stress_reward_trends(db_path, filter_day, filter_hour):
    """Return average aggregate stress/reward values over time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        display_rounds = _get_stress_reward_display_rounds(conn, filter_day)
        if not display_rounds:
            return {"timestamps": [], "timestamp_mapping": {}, "datasets": []}

        all_rows = conn.execute(
            """
            SELECT
                sr.rowid AS row_order,
                sr.uid AS uid,
                sr.variable,
                sr.value,
                sr.type,
                r.day,
                r.hour
            FROM stress_reward sr
            JOIN rounds r
              ON sr.tid = r.id
            WHERE sr.type = 'aggregate'
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            ORDER BY r.day, r.hour, row_order
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

    latest_aggregates = {}
    current_index = 0
    sorted_rows = list(all_rows)
    timestamps = []
    timestamp_mapping = {}
    stress_series = []
    reward_series = []

    for round_row in display_rounds:
        target_day = int(round_row["day"])
        target_hour = int(round_row["hour"])

        while current_index < len(sorted_rows):
            row = sorted_rows[current_index]
            if row["day"] > target_day or (
                row["day"] == target_day and row["hour"] > target_hour
            ):
                break
            latest_aggregates[(str(row["uid"]), row["variable"])] = float(row["value"])
            current_index += 1

        stress_values = [
            value
            for (uid, variable), value in latest_aggregates.items()
            if variable == "stress"
        ]
        reward_values = [
            value
            for (uid, variable), value in latest_aggregates.items()
            if variable == "reward"
        ]

        timestamps.append(float(target_day))
        timestamp_mapping[float(target_day)] = {
            "day": target_day,
            "hour": target_hour,
            "absolute": target_day * 24 + target_hour,
        }
        stress_series.append(
            (sum(stress_values) / len(stress_values)) if stress_values else 0.0
        )
        reward_series.append(
            (sum(reward_values) / len(reward_values)) if reward_values else 0.0
        )

    return {
        "timestamps": timestamps,
        "timestamp_mapping": timestamp_mapping,
        "datasets": [
            {"label": "Average Stress", "data": stress_series},
            {"label": "Average Reward", "data": reward_series},
        ],
    }


def _stress_reward_sa_interaction_cte():
    """Return the shared CTE used to resolve Stress Attacker interactions."""
    return """
        WITH sa_users AS (
            SELECT id, username
            FROM user_mgmt
            WHERE user_type = 'stress_attacker'
        ),
        sa_interactions AS (
            SELECT
                parent.user_id AS target_uid,
                sa.username AS attacker_username,
                'comment' AS interaction_type,
                r.day AS day,
                r.hour AS hour
            FROM post p
            JOIN sa_users sa
              ON sa.id = p.user_id
            JOIN post parent
              ON parent.id = p.comment_to
            JOIN rounds r
              ON r.id = p.round
            WHERE parent.user_id IS NOT NULL
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

            UNION ALL

            SELECT
                COALESCE(rep.to_uid, target_post.user_id) AS target_uid,
                sa.username AS attacker_username,
                'report' AS interaction_type,
                r.day AS day,
                r.hour AS hour
            FROM reported rep
            JOIN sa_users sa
              ON sa.id = rep.from_uid
            JOIN rounds r
              ON r.id = rep.tid
            LEFT JOIN post target_post
              ON target_post.id = rep.to_post
            WHERE COALESCE(rep.to_uid, target_post.user_id) IS NOT NULL
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))

            UNION ALL

            SELECT
                target_post.user_id AS target_uid,
                sa.username AS attacker_username,
                'reaction' AS interaction_type,
                r.day AS day,
                r.hour AS hour
            FROM reactions rr
            JOIN sa_users sa
              ON sa.id = rr.user_id
            JOIN post target_post
              ON target_post.id = rr.post_id
            JOIN rounds r
              ON r.id = rr.round
            WHERE target_post.user_id IS NOT NULL
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
        )
    """


def _build_sa_target_trend(conn, target_uid, filter_day, filter_hour):
    """Return aggregate-only stress/reward trends for one SA target."""
    display_rounds = _get_stress_reward_display_rounds(conn, filter_day)
    if not display_rounds or not target_uid:
        return {"timestamps": [], "timestamp_mapping": {}, "datasets": []}

    rows = conn.execute(
        """
        SELECT
            sr.rowid AS row_order,
            sr.variable,
            sr.value,
            r.day,
            r.hour
        FROM stress_reward sr
        JOIN rounds r
          ON sr.tid = r.id
        WHERE sr.type = 'aggregate'
          AND sr.uid = ?
          AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
        ORDER BY r.day, r.hour, row_order
        """,
        (target_uid, filter_day, filter_day, filter_hour),
    ).fetchall()

    interaction_rows = conn.execute(
        _stress_reward_sa_interaction_cte() + """
        SELECT day, COUNT(*) AS interaction_count
        FROM sa_interactions
        WHERE target_uid = ?
        GROUP BY day
        ORDER BY day
        """,
        (filter_day, filter_day, filter_hour) * 3 + (target_uid,),
    ).fetchall()
    interactions_by_day = {
        int(row["day"]): int(row["interaction_count"]) for row in interaction_rows
    }

    latest_aggregates = {}
    current_index = 0
    sorted_rows = list(rows)
    timestamps = []
    timestamp_mapping = {}
    stress_series = []
    reward_series = []
    interaction_series = []

    for round_row in display_rounds:
        target_day = int(round_row["day"])
        target_hour = int(round_row["hour"])

        while current_index < len(sorted_rows):
            row = sorted_rows[current_index]
            if row["day"] > target_day or (
                row["day"] == target_day and row["hour"] > target_hour
            ):
                break
            latest_aggregates[row["variable"]] = float(row["value"])
            current_index += 1

        timestamps.append(float(target_day))
        timestamp_mapping[float(target_day)] = {
            "day": target_day,
            "hour": target_hour,
            "absolute": target_day * 24 + target_hour,
        }
        stress_series.append(float(latest_aggregates.get("stress", 0.0)))
        reward_series.append(float(latest_aggregates.get("reward", 0.0)))
        interaction_series.append(int(interactions_by_day.get(target_day, 0)))

    return {
        "timestamps": timestamps,
        "timestamp_mapping": timestamp_mapping,
        "datasets": [
            {"label": "Target Stress", "data": stress_series},
            {"label": "Target Reward", "data": reward_series},
            {"label": "SA Interactions", "data": interaction_series},
        ],
    }


def _build_stress_attacker_target_panel(
    db_path, filter_day, filter_hour, selected_target_uid=None
):
    """Return Stress Attacker target options and selected-target analytics."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        stress_attacker_count = conn.execute("""
                SELECT COUNT(*)
                FROM user_mgmt
                WHERE user_type = 'stress_attacker'
                """).fetchone()[0] or 0
        if stress_attacker_count <= 0:
            return {
                "available": False,
                "deployed_agents": 0,
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        option_rows = conn.execute(
            _stress_reward_sa_interaction_cte() + """
            SELECT
                i.target_uid AS uid,
                u.username AS username,
                COUNT(*) AS interaction_count,
                GROUP_CONCAT(DISTINCT i.attacker_username) AS attacker_usernames
            FROM sa_interactions i
            JOIN user_mgmt u
              ON u.id = i.target_uid
            GROUP BY i.target_uid, u.username
            ORDER BY interaction_count DESC, u.username ASC
            """,
            (filter_day, filter_day, filter_hour) * 3,
        ).fetchall()

        options = [
            {
                "uid": str(row["uid"]),
                "username": row["username"],
                "interaction_count": int(row["interaction_count"] or 0),
                "attacker_usernames": sorted(
                    {
                        item.strip()
                        for item in str(row["attacker_usernames"] or "").split(",")
                        if item and item.strip()
                    }
                ),
            }
            for row in option_rows
            if row["uid"] is not None
        ]

        if not options:
            return {
                "available": True,
                "deployed_agents": int(stress_attacker_count),
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "attacker_usernames": [],
                "interaction_count": 0,
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        valid_target_ids = {
            str(option.get("uid"))
            for option in options
            if isinstance(option, dict) and option.get("uid") is not None
        }
        if selected_target_uid not in valid_target_ids:
            selected_target_uid = (
                str(options[0].get("uid")) if isinstance(options[0], dict) else None
            )

        selected_option = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and str(option.get("uid")) == str(selected_target_uid)
            ),
            options[0],
        )
        selected_uid = str(selected_option.get("uid")) if selected_option else None
        selected_username = str(selected_option.get("username") or "")
        selected_attackers = selected_option.get("attacker_usernames") or []
        selected_interaction_count = int(selected_option.get("interaction_count") or 0)
        interaction_rows = conn.execute(
            _stress_reward_sa_interaction_cte() + """
            SELECT
                day,
                hour,
                interaction_type,
                COUNT(*) AS interaction_count,
                GROUP_CONCAT(DISTINCT attacker_username) AS attacker_usernames
            FROM sa_interactions
            WHERE target_uid = ?
            GROUP BY day, hour, interaction_type
            ORDER BY day DESC, hour DESC, interaction_type ASC
            LIMIT 50
            """,
            (filter_day, filter_day, filter_hour) * 3 + (selected_target_uid,),
        ).fetchall()

        interaction_events = [
            {
                "day": int(row["day"]),
                "hour": int(row["hour"]),
                "interaction_type": row["interaction_type"],
                "interaction_count": int(row["interaction_count"] or 0),
                "attacker_usernames": sorted(
                    {
                        item.strip()
                        for item in str(row["attacker_usernames"] or "").split(",")
                        if item and item.strip()
                    }
                ),
            }
            for row in interaction_rows
        ]

        return {
            "available": True,
            "deployed_agents": int(stress_attacker_count),
            "options": options,
            "selected_uid": selected_uid,
            "selected_username": selected_username,
            "attacker_usernames": selected_attackers,
            "interaction_count": selected_interaction_count,
            "trend_data": _build_sa_target_trend(
                conn, selected_uid, filter_day, filter_hour
            ),
            "interaction_events": interaction_events,
        }


def _build_moderator_target_trend(conn, target_uid, filter_day, filter_hour):
    """Return per-day toxicity trends and moderation counts for one moderated target."""
    display_rounds = _get_stress_reward_display_rounds(conn, filter_day)
    if not display_rounds or not target_uid:
        return {"timestamps": [], "timestamp_mapping": {}, "datasets": []}

    toxicity_rows = conn.execute(
        """
        SELECT
            r.day AS day,
            AVG(pt.toxicity) AS average_toxicity,
            MAX(pt.toxicity) AS peak_toxicity,
            COUNT(*) AS annotated_posts
        FROM post_toxicity pt
        JOIN post p
          ON p.id = pt.post_id
        JOIN rounds r
          ON r.id = p.round
        WHERE p.user_id = ?
          AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
        GROUP BY r.day
        ORDER BY r.day
        """,
        (target_uid, filter_day, filter_day, filter_hour),
    ).fetchall()
    toxicity_by_day = {
        int(row["day"]): {
            "average_toxicity": _safe_float(row["average_toxicity"], digits=6),
            "peak_toxicity": _safe_float(row["peak_toxicity"], digits=6),
            "annotated_posts": _safe_int(row["annotated_posts"]),
        }
        for row in toxicity_rows
    }

    moderation_rows = conn.execute(
        """
        SELECT
            r.day AS day,
            COUNT(*) AS moderation_count
        FROM plugin_moderation_actions ma
        JOIN rounds r
          ON r.id = ma.round_id
        WHERE ma.moderated_agent_id = ?
          AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
        GROUP BY r.day
        ORDER BY r.day
        """,
        (target_uid, filter_day, filter_day, filter_hour),
    ).fetchall()
    moderation_by_day = {
        int(row["day"]): _safe_int(row["moderation_count"]) for row in moderation_rows
    }

    timestamps = []
    timestamp_mapping = {}
    average_series = []
    peak_series = []
    moderation_series = []

    for round_row in display_rounds:
        target_day = int(round_row["day"])
        target_hour = int(round_row["hour"])
        timestamps.append(float(target_day))
        timestamp_mapping[float(target_day)] = {
            "day": target_day,
            "hour": target_hour,
            "absolute": target_day * 24 + target_hour,
        }
        daily_toxicity = toxicity_by_day.get(target_day, {})
        average_series.append(float(daily_toxicity.get("average_toxicity", 0.0)))
        peak_series.append(float(daily_toxicity.get("peak_toxicity", 0.0)))
        moderation_series.append(int(moderation_by_day.get(target_day, 0)))

    return {
        "timestamps": timestamps,
        "timestamp_mapping": timestamp_mapping,
        "datasets": [
            {"label": "Average Target Toxicity", "data": average_series},
            {"label": "Peak Target Toxicity", "data": peak_series},
            {"label": "Moderator Actions", "data": moderation_series},
        ],
    }


def _build_moderator_target_panel(
    db_path, filter_day, filter_hour, selected_target_uid=None
):
    """Return moderator target options and selected-target toxicity analytics."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        moderator_count = conn.execute("""
                SELECT COUNT(*)
                FROM user_mgmt
                WHERE user_type = 'moderator'
                """).fetchone()[0] or 0
        if moderator_count <= 0:
            return {
                "available": False,
                "deployed_agents": 0,
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "moderation_count": 0,
                "moderator_usernames": [],
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        if not _experiment_db_has_required_tables(
            db_path, {"plugin_moderation_actions", "post_toxicity", "post", "rounds"}
        ):
            return {
                "available": True,
                "deployed_agents": int(moderator_count),
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "moderation_count": 0,
                "moderator_usernames": [],
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        option_rows = conn.execute(
            """
            SELECT
                ma.moderated_agent_id AS uid,
                u.username AS username,
                COUNT(*) AS moderation_count,
                GROUP_CONCAT(DISTINCT moderator.username) AS moderator_usernames
            FROM plugin_moderation_actions ma
            JOIN rounds r
              ON r.id = ma.round_id
            JOIN user_mgmt u
              ON u.id = ma.moderated_agent_id
            JOIN user_mgmt moderator
              ON moderator.id = ma.moderator_agent_id
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY ma.moderated_agent_id, u.username
            ORDER BY moderation_count DESC, u.username ASC
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

        options = [
            {
                "uid": str(row["uid"]),
                "username": row["username"],
                "moderation_count": int(row["moderation_count"] or 0),
                "moderator_usernames": sorted(
                    {
                        item.strip()
                        for item in str(row["moderator_usernames"] or "").split(",")
                        if item and item.strip()
                    }
                ),
            }
            for row in option_rows
            if row["uid"] is not None
        ]

        if not options:
            return {
                "available": True,
                "deployed_agents": int(moderator_count),
                "options": [],
                "selected_uid": None,
                "selected_username": None,
                "moderation_count": 0,
                "moderator_usernames": [],
                "trend_data": {
                    "timestamps": [],
                    "timestamp_mapping": {},
                    "datasets": [],
                },
                "interaction_events": [],
            }

        valid_target_ids = {
            str(option.get("uid"))
            for option in options
            if isinstance(option, dict) and option.get("uid") is not None
        }
        if selected_target_uid not in valid_target_ids:
            selected_target_uid = (
                str(options[0].get("uid")) if isinstance(options[0], dict) else None
            )

        selected_option = next(
            (
                option
                for option in options
                if isinstance(option, dict)
                and str(option.get("uid")) == str(selected_target_uid)
            ),
            options[0],
        )
        selected_uid = str(selected_option.get("uid")) if selected_option else None
        selected_username = str(selected_option.get("username") or "")
        selected_moderation_count = int(selected_option.get("moderation_count") or 0)
        selected_moderators = selected_option.get("moderator_usernames") or []

        interaction_rows = conn.execute(
            """
            SELECT
                r.day AS day,
                r.hour AS hour,
                ma.moderation_type AS moderation_type,
                COUNT(*) AS moderation_count,
                GROUP_CONCAT(DISTINCT moderator.username) AS moderator_usernames
            FROM plugin_moderation_actions ma
            JOIN rounds r
              ON r.id = ma.round_id
            JOIN user_mgmt moderator
              ON moderator.id = ma.moderator_agent_id
            WHERE ma.moderated_agent_id = ?
              AND (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY r.day, r.hour, ma.moderation_type
            ORDER BY r.day DESC, r.hour DESC, ma.moderation_type ASC
            LIMIT 50
            """,
            (selected_target_uid, filter_day, filter_day, filter_hour),
        ).fetchall()

        interaction_events = [
            {
                "day": int(row["day"]),
                "hour": int(row["hour"]),
                "moderation_type": row["moderation_type"],
                "moderation_count": int(row["moderation_count"] or 0),
                "moderator_usernames": sorted(
                    {
                        item.strip()
                        for item in str(row["moderator_usernames"] or "").split(",")
                        if item and item.strip()
                    }
                ),
            }
            for row in interaction_rows
        ]

        return {
            "available": True,
            "deployed_agents": int(moderator_count),
            "options": options,
            "selected_uid": selected_uid,
            "selected_username": selected_username,
            "moderation_count": selected_moderation_count,
            "moderator_usernames": selected_moderators,
            "trend_data": _build_moderator_target_trend(
                conn, selected_uid, filter_day, filter_hour
            ),
            "interaction_events": interaction_events,
        }


@experiments.route("/admin/stress_reward_evolution/<int:expid>")
@login_required
def stress_reward_evolution(expid):
    """Display stress/reward evolution analytics for a stress-enabled experiment."""
    experiment, _experiment_dir, error_response = (
        _load_stress_reward_experiment_context(expid, require_manage=False)
    )
    if error_response is not None:
        return error_response

    db_path = _resolve_experiment_db_path(experiment)
    if not _experiment_db_has_required_stress_reward_tables(db_path):
        flash(
            "The current experiment database does not contain stress/reward evolution tables.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=expid))

    max_day, max_hour = _get_stress_reward_max_round(db_path)
    filter_day = request.args.get("day", type=int, default=max_day)
    filter_hour = request.args.get("hour", type=int, default=max_hour)
    selected_target_uid = str(request.args.get("target_uid", "") or "").strip() or None
    snapshot = _build_stress_reward_snapshot(db_path, filter_day, filter_hour)
    trend_data = _build_stress_reward_trends(db_path, filter_day, filter_hour)
    sa_targets = _build_stress_attacker_target_panel(
        db_path, filter_day, filter_hour, selected_target_uid=selected_target_uid
    )

    return render_template(
        "admin/stress_reward_evolution.html",
        experiment=experiment,
        max_day=max_day,
        max_hour=max_hour,
        filter_day=filter_day,
        filter_hour=filter_hour,
        snapshot=snapshot,
        trend_data=trend_data,
        sa_targets=sa_targets,
    )


@experiments.route("/admin/stress_reward_evolution_data/<int:expid>")
@login_required
def stress_reward_evolution_data(expid):
    """Return stress/reward evolution analytics for a selected simulation time."""
    experiment, _experiment_dir, error_response = (
        _load_stress_reward_experiment_context(expid, require_manage=False)
    )
    if error_response is not None:
        return jsonify({"error": "Stress/reward analytics not available"}), 400

    db_path = _resolve_experiment_db_path(experiment)
    if not _experiment_db_has_required_stress_reward_tables(db_path):
        return (
            jsonify(
                {
                    "error": "The current experiment database does not contain stress/reward evolution tables."
                }
            ),
            400,
        )

    filter_day = request.args.get("day", type=int, default=1)
    filter_hour = request.args.get("hour", type=int, default=1)
    selected_target_uid = str(request.args.get("target_uid", "") or "").strip() or None
    snapshot = _build_stress_reward_snapshot(db_path, filter_day, filter_hour)
    trend_data = _build_stress_reward_trends(db_path, filter_day, filter_hour)
    sa_targets = _build_stress_attacker_target_panel(
        db_path, filter_day, filter_hour, selected_target_uid=selected_target_uid
    )

    return jsonify(
        {
            "filter_day": filter_day,
            "filter_hour": filter_hour,
            "snapshot": snapshot,
            "trend_data": trend_data,
            "sa_targets": sa_targets,
        }
    )


def _load_annotation_experiment_context(
    uid, annotation_key, annotation_label, require_manage=False
):
    """Load an experiment where a specific annotation is enabled."""
    check_privileges(current_user.username)

    experiment = Exps.query.filter_by(idexp=uid).first()
    if not experiment:
        flash("Experiment not found", "error")
        return None, None, redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user_or_none()
    if require_manage and not user_can_manage_experiment(admin_user, experiment):
        flash("You do not have permission to manage this experiment.", "error")
        return None, None, redirect(url_for("experiments.experiment_details", uid=uid))

    db_path = _resolve_experiment_db_path(experiment)
    config_path = os.path.join(
        os.path.dirname(db_path),
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

    enabled = bool(config.get(f"{annotation_key}_annotation"))
    if not enabled:
        enabled = bool(
            experiment.annotations and annotation_key in experiment.annotations
        )

    if not enabled:
        flash(
            f"Enable {annotation_label} annotation in Experiment Configuration first.",
            "warning",
        )
        return None, None, redirect(url_for("experiments.experiment_details", uid=uid))

    return experiment, db_path, None


def _load_network_experiment_context(uid, require_manage=False):
    """Load an experiment for network analytics."""
    check_privileges(current_user.username)

    experiment = Exps.query.filter_by(idexp=uid).first()
    if not experiment:
        flash("Experiment not found", "error")
        return None, None, redirect(url_for("experiments.settings"))

    admin_user = _current_admin_user_or_none()
    if require_manage and not user_can_manage_experiment(admin_user, experiment):
        flash("You do not have permission to manage this experiment.", "error")
        return None, None, redirect(url_for("experiments.experiment_details", uid=uid))

    return experiment, _resolve_network_analysis_db_path(experiment), None


def _experiment_db_has_required_tables(db_path, required_tables):
    """Check whether the experiment DB exposes a given set of tables."""
    if not db_path or not os.path.exists(db_path):
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

    return set(required_tables).issubset(tables)


def _get_annotation_max_round(db_path):
    """Return the latest round coordinates available in the experiment DB."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT day, hour FROM rounds ORDER BY day DESC, hour DESC LIMIT 1"
        ).fetchone()
    if not row:
        return 1, 1
    return int(row[0]), int(row[1])


def _build_annotation_time_condition(round_alias="r"):
    return f"({round_alias}.day < ? OR ({round_alias}.day = ? AND {round_alias}.hour <= ?))"


def _safe_float(value, digits=3):
    if value in (None, ""):
        return 0.0
    return round(float(value), digits)


def _safe_int(value):
    if value in (None, ""):
        return 0
    return int(value)


def _parse_recommendation_post_ids(raw_value):
    if raw_value in (None, ""):
        return []
    if isinstance(raw_value, (list, tuple)):
        return [str(item) for item in raw_value if str(item).strip()]
    text = str(raw_value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
        except Exception:
            pass
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()]
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def _gaussian_kde_series(values):
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return [], []
    if len(numeric_values) == 1:
        value = numeric_values[0]
        return [round(value, 3)], [1.0]

    mean = sum(numeric_values) / len(numeric_values)
    variance = sum((value - mean) ** 2 for value in numeric_values) / max(
        len(numeric_values) - 1, 1
    )
    std_dev = variance**0.5
    bandwidth = max(0.35, 1.06 * std_dev * (len(numeric_values) ** (-1 / 5)))
    x_min = max(0.0, min(numeric_values) - bandwidth)
    x_max = max(numeric_values) + bandwidth
    if x_max <= x_min:
        x_max = x_min + 1.0

    num_points = min(80, max(24, len(numeric_values) * 12))
    step = (x_max - x_min) / max(num_points - 1, 1)
    xs = [x_min + (index * step) for index in range(num_points)]
    coefficient = 1.0 / ((2.0 * 3.141592653589793) ** 0.5)
    ys = []
    for x_value in xs:
        density = 0.0
        for sample in numeric_values:
            z = (x_value - sample) / bandwidth
            density += coefficient * (2.718281828459045 ** (-0.5 * z * z))
        density /= len(numeric_values) * bandwidth
        ys.append(round(density, 6))
    return [round(x_value, 3) for x_value in xs], ys


def _truncate_text(text, max_len=96):
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _safe_ratio(numerator, denominator, digits=4):
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), digits)


def _degree_bin_label(lower, upper=None):
    if upper is None:
        return f"{lower}+"
    if lower == upper:
        return str(lower)
    return f"{lower}-{upper}"


def _degree_bin_spec(max_degree):
    bins = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 9), (10, 19)]
    if max_degree >= 20:
        bins.append((20, None))
    return bins


def _histogram_from_degrees(degrees, bin_spec):
    counts = []
    for lower, upper in bin_spec:
        if upper is None:
            counts.append(sum(1 for degree in degrees if degree >= lower))
        else:
            counts.append(sum(1 for degree in degrees if lower <= degree <= upper))
    return counts


def _ccdf_from_degrees(degrees):
    positive_degrees = [int(degree) for degree in degrees if int(degree) > 0]
    if not positive_degrees:
        return [1], [0.0001]

    max_degree = max(positive_degrees)
    x_values = list(range(1, max_degree + 1))
    total = len(degrees)
    y_values = [
        round(sum(1 for degree in degrees if int(degree) >= x_value) / total, 4)
        for x_value in x_values
    ]
    return x_values, y_values


def _follow_round_column(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(follow)").fetchall()}
    if "round" in columns:
        return "round"
    if "tid" in columns:
        return "tid"
    return None


def _table_round_column(conn, table_name):
    columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if "round" in columns:
        return "round"
    if "tid" in columns:
        return "tid"
    return None


def _network_graph_metrics(graph):
    node_count = graph.number_of_nodes()
    edge_count = graph.number_of_edges()
    active_nodes = sum(1 for node in graph.nodes if graph.degree(node) > 0)
    isolates = nx.number_of_isolates(graph) if node_count else 0
    density = nx.density(graph) if node_count > 1 else 0.0
    weak_components = list(nx.weakly_connected_components(graph)) if node_count else []
    component_count = len(weak_components)
    largest_component_size = max(
        (len(component) for component in weak_components), default=0
    )
    largest_component_share = _safe_ratio(largest_component_size, node_count, digits=4)
    reciprocity = nx.reciprocity(graph)
    reciprocity = 0.0 if reciprocity is None else round(float(reciprocity), 4)
    undirected = graph.to_undirected()
    clustering = (
        round(float(nx.transitivity(undirected)), 4)
        if undirected.number_of_nodes() > 2 and undirected.number_of_edges() > 0
        else 0.0
    )
    avg_out_degree = round(edge_count / node_count, 4) if node_count else 0.0
    avg_in_degree = round(edge_count / node_count, 4) if node_count else 0.0

    return {
        "node_count": node_count,
        "active_nodes": active_nodes,
        "edge_count": edge_count,
        "density": round(float(density), 4),
        "component_count": component_count,
        "largest_component_size": largest_component_size,
        "largest_component_share": largest_component_share,
        "isolates": isolates,
        "reciprocity": reciprocity,
        "clustering": clustering,
        "avg_out_degree": avg_out_degree,
        "avg_in_degree": avg_in_degree,
    }


def _available_network_analysis_types(db_path):
    available = []
    with sqlite3.connect(db_path) as conn:
        table_names = {
            row["name"] if isinstance(row, sqlite3.Row) else row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    if "follow" in table_names:
        available.append("follow")
    if "mentions" in table_names and "post" in table_names:
        available.append("mention")
    return available


def _build_network_analytics_payload(
    db_path,
    filter_day,
    filter_hour,
    selected_uid=None,
    network_type="follow",
    granularity="day",
):
    """Build network analytics up to the selected simulation time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        network_type = str(network_type or "follow").strip().lower()
        if network_type not in {"follow", "mention"}:
            network_type = "follow"
        granularity = str(granularity or "day").strip().lower()
        if granularity not in {"day", "hour"}:
            granularity = "day"

        user_rows = conn.execute(
            "SELECT id, username FROM user_mgmt ORDER BY username ASC"
        ).fetchall()
        user_ids = [str(row["id"]) for row in user_rows]
        usernames = {str(row["id"]): row["username"] for row in user_rows}

        graph = nx.DiGraph()
        graph.add_nodes_from(user_ids)
        if granularity == "hour":
            timeline_points = [
                (int(row["day"]), int(row["hour"]))
                for row in conn.execute(
                    """
                    SELECT day, hour
                    FROM rounds
                    WHERE (day < ? OR (day = ? AND hour <= ?))
                    ORDER BY day ASC, hour ASC
                    """,
                    (filter_day, filter_day, filter_hour),
                ).fetchall()
            ]
        else:
            timeline_points = [
                (int(row["day"]), None)
                for row in conn.execute(
                    """
                    SELECT DISTINCT day
                    FROM rounds
                    WHERE (day < ? OR (day = ? AND hour <= ?))
                    ORDER BY day ASC
                    """,
                    (filter_day, filter_day, filter_hour),
                ).fetchall()
            ]

        if network_type == "follow":
            round_column = _table_round_column(conn, "follow")
        else:
            round_column = _table_round_column(conn, "mentions")

        if not round_column:
            metrics = _network_graph_metrics(graph)
            events = []
            all_events = []
            snapshots = [(point, dict(metrics)) for point in timeline_points]
        else:
            if network_type == "follow":
                events = conn.execute(
                    f"""
                    SELECT
                        f.rowid AS event_order,
                        CAST(f.user_id AS TEXT) AS user_id,
                        CAST(f.follower_id AS TEXT) AS follower_id,
                        LOWER(COALESCE(f.action, 'follow')) AS action,
                        r.day AS day,
                        r.hour AS hour
                    FROM follow f
                    JOIN rounds r ON r.id = f.{round_column}
                    WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                    ORDER BY r.day ASC, r.hour ASC, f.rowid ASC
                    """,
                    (filter_day, filter_day, filter_hour),
                ).fetchall()
                all_events = conn.execute(f"""
                    SELECT
                        f.rowid AS event_order,
                        CAST(f.user_id AS TEXT) AS user_id,
                        CAST(f.follower_id AS TEXT) AS follower_id,
                        LOWER(COALESCE(f.action, 'follow')) AS action,
                        r.day AS day,
                        r.hour AS hour
                    FROM follow f
                    JOIN rounds r ON r.id = f.{round_column}
                    ORDER BY r.day ASC, r.hour ASC, f.rowid ASC
                    """).fetchall()
            else:
                events = conn.execute(
                    f"""
                    SELECT
                        m.rowid AS event_order,
                        CAST(m.user_id AS TEXT) AS user_id,
                        CAST(p.user_id AS TEXT) AS follower_id,
                        'mention' AS action,
                        r.day AS day,
                        r.hour AS hour
                    FROM mentions m
                    JOIN post p ON p.id = m.post_id
                    JOIN rounds r ON r.id = m.{round_column}
                    WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                    ORDER BY r.day ASC, r.hour ASC, m.rowid ASC
                    """,
                    (filter_day, filter_day, filter_hour),
                ).fetchall()
                all_events = conn.execute(f"""
                    SELECT
                        m.rowid AS event_order,
                        CAST(m.user_id AS TEXT) AS user_id,
                        CAST(p.user_id AS TEXT) AS follower_id,
                        'mention' AS action,
                        r.day AS day,
                        r.hour AS hour
                    FROM mentions m
                    JOIN post p ON p.id = m.post_id
                    JOIN rounds r ON r.id = m.{round_column}
                    ORDER BY r.day ASC, r.hour ASC, m.rowid ASC
                    """).fetchall()

            events_by_point = {}
            for event in events:
                event_day = int(event["day"] or 0)
                event_hour = int(event["hour"] or 0)
                event_point = (
                    (event_day, event_hour)
                    if granularity == "hour"
                    else (event_day, None)
                )
                events_by_point.setdefault(event_point, []).append(event)

            snapshots = []
            for point in timeline_points:
                for event in events_by_point.get(point, []):
                    source = str(event["follower_id"])
                    target = str(event["user_id"])
                    action = str(event["action"] or "follow").lower()
                    if source not in graph:
                        graph.add_node(source)
                    if target not in graph:
                        graph.add_node(target)

                    if action == "unfollow":
                        if graph.has_edge(source, target):
                            graph.remove_edge(source, target)
                    else:
                        graph.add_edge(source, target)
                snapshots.append((point, _network_graph_metrics(graph)))

            metrics = _network_graph_metrics(graph)

        full_graph = nx.DiGraph()
        full_graph.add_nodes_from(user_ids)
        for event in all_events:
            source = str(event["follower_id"])
            target = str(event["user_id"])
            action = str(event["action"] or "follow").lower()
            if source not in full_graph:
                full_graph.add_node(source)
            if target not in full_graph:
                full_graph.add_node(target)
            if action == "unfollow":
                if full_graph.has_edge(source, target):
                    full_graph.remove_edge(source, target)
            else:
                full_graph.add_edge(source, target)

        in_degrees = dict(graph.in_degree())
        out_degrees = dict(graph.out_degree())
        total_degrees = dict(graph.degree())
        degree_x_values, in_degree_ccdf = _ccdf_from_degrees(list(in_degrees.values()))
        _, out_degree_ccdf = _ccdf_from_degrees(list(out_degrees.values()))

        ego_candidates = sorted(
            (node for node in graph.nodes() if total_degrees.get(node, 0) > 0),
            key=lambda node: (
                total_degrees.get(node, 0),
                usernames.get(node, str(node)).lower(),
            ),
            reverse=True,
        )
        selected_uid = str(selected_uid or "").strip() or None
        if selected_uid and selected_uid not in graph:
            selected_uid = None

        active_neighbors = set()
        appeared_neighbors_current = set()
        appeared_neighbors_full = set()
        if selected_uid:
            for event in events:
                source = str(event["follower_id"])
                target = str(event["user_id"])
                if source == selected_uid:
                    appeared_neighbors_current.add(target)
                elif target == selected_uid:
                    appeared_neighbors_current.add(source)
            for event in all_events:
                source = str(event["follower_id"])
                target = str(event["user_id"])
                if source == selected_uid:
                    appeared_neighbors_full.add(target)
                elif target == selected_uid:
                    appeared_neighbors_full.add(source)

            active_neighbors.update(
                str(node) for node in graph.successors(selected_uid)
            )
            active_neighbors.update(
                str(node) for node in graph.predecessors(selected_uid)
            )

        ego_nodes_full = [selected_uid] if selected_uid else []
        ego_nodes_full.extend(
            [
                node
                for node in appeared_neighbors_full
                if node in usernames and node != selected_uid
            ]
        )
        layout_graph = nx.Graph()
        if selected_uid:
            ego_node_set_full = set(ego_nodes_full)
            layout_graph.add_nodes_from(ego_node_set_full)
            for source, target in full_graph.edges():
                if source in ego_node_set_full and target in ego_node_set_full:
                    layout_graph.add_edge(source, target)
            if layout_graph.number_of_nodes() > 1:
                ego_positions = nx.spring_layout(
                    layout_graph,
                    seed=42,
                    pos={selected_uid: (0.0, 0.0)},
                    fixed=[selected_uid],
                )
            else:
                ego_positions = {selected_uid: (0.0, 0.0)}
        else:
            ego_positions = {}

        ego_nodes_payload = []
        if selected_uid:
            appeared_now = {selected_uid} | appeared_neighbors_current
            for node in ego_nodes_full:
                if node not in appeared_now:
                    continue
                x_pos, y_pos = ego_positions.get(node, (0.0, 0.0))
                ego_nodes_payload.append(
                    {
                        "id": node,
                        "label": usernames.get(node, str(node)),
                        "x": round(float(x_pos), 5),
                        "y": round(float(y_pos), 5),
                        "is_ego": node == selected_uid,
                        "is_active": node == selected_uid or node in active_neighbors,
                    }
                )

        ego_edges_payload = []
        if selected_uid:
            visible_nodes = {node["id"] for node in ego_nodes_payload}
            position_lookup = {node["id"]: node for node in ego_nodes_payload}
            active_edge_pairs = set()
            for source, target in graph.edges():
                if source in visible_nodes and target in visible_nodes:
                    edge_key = tuple(sorted((source, target)))
                    active_edge_pairs.add(edge_key)
            for source, target in sorted(active_edge_pairs):
                source_node = position_lookup.get(source)
                target_node = position_lookup.get(target)
                if not source_node or not target_node:
                    continue
                ego_edges_payload.append(
                    {
                        "source": source,
                        "target": target,
                        "x1": source_node["x"],
                        "y1": source_node["y"],
                        "x2": target_node["x"],
                        "y2": target_node["y"],
                    }
                )

    snapshots = locals().get("snapshots", [])
    timestamps = [
        (
            f"Day {point[0]}, Hour {point[1]}"
            if point[1] is not None
            else f"Day {point[0]}"
        )
        for point, _ in snapshots
    ]
    trend_metrics = [metric for _, metric in snapshots]

    network_label = "follow" if network_type == "follow" else "mention"
    network_title = "Follow Network" if network_type == "follow" else "Mention Network"
    edge_label = "Edges" if network_type == "follow" else "Mention Edges"
    structure_description = (
        "Daily evolution of density and transitivity in the follow network."
        if network_type == "follow"
        else "Daily evolution of density and transitivity in the mention network."
    )
    size_description = (
        "Daily evolution of active nodes and directed follow edges."
        if network_type == "follow"
        else "Daily evolution of active nodes and directed mention edges."
    )
    ego_description = (
        "Select an account to inspect its evolving one-hop ego follow network. Nodes keep their layout once they appear; the selected account stays highlighted."
        if network_type == "follow"
        else "Select an account to inspect its evolving one-hop ego mention network. Nodes keep their layout once they appear; the selected account stays highlighted."
    )

    stats = [
        {
            "key": "node_count",
            "label": "Nodes",
            "value": metrics["node_count"],
            "color": "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
        },
        {
            "key": "edge_count",
            "label": "Edges",
            "value": metrics["edge_count"],
            "color": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
        },
        {
            "key": "density",
            "label": "Density",
            "value": f"{metrics['density']:.4f}",
            "color": "linear-gradient(135deg, #14b8a6 0%, #0f766e 100%)",
        },
        {
            "key": "component_count",
            "label": "Components",
            "value": metrics["component_count"],
            "color": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        },
        {
            "key": "largest_component_size",
            "label": "Largest Component",
            "value": metrics["largest_component_size"],
            "color": "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
        },
        {
            "key": "current_day",
            "label": "Current Day",
            "value": f"Day {filter_day}",
            "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)",
        },
        {
            "key": "current_hour",
            "label": "Current Hour",
            "value": f"Hour {filter_hour}",
            "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)",
        },
    ]

    return {
        "page_title": "Network Analysis",
        "title": "Network Analysis",
        "description": f"Track how the {network_label} network evolves across the experiment.",
        "network_type": network_type,
        "granularity": granularity,
        "network_type_options": [
            {"value": "follow", "label": "Follow Network"},
            {"value": "mention", "label": "Mention Network"},
        ],
        "granularity_options": [
            {"value": "day", "label": "Daily"},
            {"value": "hour", "label": "Hourly"},
        ],
        "stats": stats,
        "distribution": {
            "title": "In-Degree CCDF",
            "description": f"Current in-degree complementary cumulative distribution in log-log scale for the {network_label} network.",
            "type": "line",
            "labels": [str(value) for value in degree_x_values],
            "datasets": [
                {
                    "label": "In-Degree CCDF",
                    "data": in_degree_ccdf,
                    "borderColor": "#60a5fa",
                    "fill": False,
                    "tension": 0.15,
                },
            ],
            "options": {
                "beginAtZero": False,
                "min": 0.0001,
                "max": 1,
                "xType": "logarithmic",
                "yType": "logarithmic",
            },
        },
        "trend": {
            "title": "Out-Degree CCDF",
            "description": f"Current out-degree complementary cumulative distribution in log-log scale for the {network_label} network.",
            "type": "line",
            "labels": [str(value) for value in degree_x_values],
            "datasets": [
                {
                    "label": "Out-Degree CCDF",
                    "data": out_degree_ccdf,
                    "borderColor": "#a78bfa",
                    "fill": False,
                    "tension": 0.15,
                },
            ],
            "options": {
                "beginAtZero": False,
                "min": 0.0001,
                "max": 1,
                "xType": "logarithmic",
                "yType": "logarithmic",
            },
        },
        "secondary": {
            "title": "Network Size Over Time",
            "description": size_description,
            "type": "line",
            "labels": timestamps,
            "datasets": [
                {
                    "label": "Active Nodes",
                    "data": [metric["active_nodes"] for metric in trend_metrics],
                    "borderColor": "#2563eb",
                    "fill": False,
                    "tension": 0.25,
                },
                {
                    "label": edge_label,
                    "data": [metric["edge_count"] for metric in trend_metrics],
                    "borderColor": "#7c3aed",
                    "fill": False,
                    "tension": 0.25,
                },
            ],
            "options": {"beginAtZero": True},
        },
        "component_share": {
            "title": "Largest Component Share Over Time",
            "description": "Share of nodes contained in the largest weakly connected component by day.",
            "type": "line",
            "labels": timestamps,
            "datasets": [
                {
                    "label": "Largest Component Share",
                    "data": [
                        metric["largest_component_share"] for metric in trend_metrics
                    ],
                    "borderColor": "#0ea5e9",
                    "fill": False,
                    "tension": 0.25,
                }
            ],
            "options": {"beginAtZero": True, "max": 1},
        },
        "network_structure": {
            "title": "Structural Metrics Over Time",
            "description": structure_description,
            "type": "line",
            "labels": timestamps,
            "datasets": [
                {
                    "label": "Density",
                    "data": [metric["density"] for metric in trend_metrics],
                    "borderColor": "#14b8a6",
                    "fill": False,
                    "tension": 0.25,
                },
                {
                    "label": "Transitivity",
                    "data": [metric["clustering"] for metric in trend_metrics],
                    "borderColor": "#ec4899",
                    "fill": False,
                    "tension": 0.25,
                },
            ],
            "options": {"beginAtZero": True, "max": 1},
        },
        "ego_network": {
            "title": f"{network_title} Ego Network Over Time",
            "description": ego_description,
            "selected_uid": selected_uid,
            "selected_username": (
                usernames.get(selected_uid, "—") if selected_uid else "—"
            ),
            "options": [
                {
                    "uid": node,
                    "username": usernames.get(node, str(node)),
                    "degree": total_degrees.get(node, 0),
                }
                for node in ego_candidates[:250]
            ],
            "nodes": ego_nodes_payload,
            "edges": ego_edges_payload,
        },
        "summary": {
            "title": "",
            "columns": [],
            "rows": [],
            "empty_message": "",
        },
    }


def _topic_name_mapping(expid, conn):
    topic_names = {}
    table_names = {
        row["name"] if isinstance(row, sqlite3.Row) else row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "interests" in table_names:
        for row in conn.execute("SELECT iid, interest FROM interests").fetchall():
            topic_names[str(row["iid"])] = row["interest"]

    for topic in _resolve_opinion_evolution_topics(expid):
        topic_id = str(topic.get("iid"))
        topic_name = topic.get("interest")
        if topic_id and topic_name and topic_id not in topic_names:
            topic_names[topic_id] = topic_name

    return topic_names


def _build_topic_evolution_payload(
    expid, db_path, filter_day, filter_hour, selected_topic_ids=None, trend_mode="daily"
):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        topic_names = _topic_name_mapping(expid, conn)
        table_names = {
            row["name"] if isinstance(row, sqlite3.Row) else row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        reported_round_column = (
            _table_round_column(conn, "reported") if "reported" in table_names else None
        )
        total_population = _safe_int(
            conn.execute("SELECT COUNT(*) AS c FROM user_mgmt").fetchone()["c"]
        )

        event_queries = ["""
            SELECT
                pt.topic_id AS topic_id,
                p.user_id AS actor_id,
                r.day AS day,
                r.hour AS hour,
                'content' AS event_type
            FROM post_topics pt
            JOIN post p ON p.id = pt.post_id
            JOIN rounds r ON r.id = p.round
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            """]
        params = [filter_day, filter_day, filter_hour]

        if "reactions" in table_names:
            event_queries.append("""
                SELECT
                    pt.topic_id AS topic_id,
                    re.user_id AS actor_id,
                    r.day AS day,
                    r.hour AS hour,
                    'reaction' AS event_type
                FROM post_topics pt
                JOIN reactions re ON re.post_id = pt.post_id
                JOIN rounds r ON r.id = re.round
                WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                """)
            params.extend([filter_day, filter_day, filter_hour])

        if "reported" in table_names and reported_round_column:
            event_queries.append(f"""
                SELECT
                    pt.topic_id AS topic_id,
                    rp.from_uid AS actor_id,
                    r.day AS day,
                    r.hour AS hour,
                    'report' AS event_type
                FROM post_topics pt
                JOIN reported rp ON rp.to_post = pt.post_id
                JOIN rounds r ON r.id = rp.{reported_round_column}
                WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                """)
            params.extend([filter_day, filter_day, filter_hour])

        topic_events_sql = " UNION ALL ".join(event_queries)

        current_volume_rows = conn.execute(
            f"""
            WITH topic_events AS (
                {topic_events_sql}
            )
            SELECT topic_id, COUNT(*) AS total_volume
            FROM topic_events
            GROUP BY topic_id
            ORDER BY total_volume DESC, topic_id ASC
            """,
            tuple(params),
        ).fetchall()

        topic_options = [
            {
                "topic_id": str(row["topic_id"]),
                "topic_name": topic_names.get(
                    str(row["topic_id"]), str(row["topic_id"])
                ),
                "total_volume": _safe_int(row["total_volume"]),
            }
            for row in current_volume_rows
        ]

        selected_topic_ids = [
            str(topic_id)
            for topic_id in (selected_topic_ids or [])
            if str(topic_id) in {option["topic_id"] for option in topic_options}
        ]
        if not selected_topic_ids:
            selected_topic_ids = [option["topic_id"] for option in topic_options[:5]]

        if selected_topic_ids:
            placeholders = ",".join(["?"] * len(selected_topic_ids))
            selected_clause = f" WHERE topic_id IN ({placeholders}) "
            selected_params = tuple(selected_topic_ids)
        else:
            selected_clause = " WHERE 1 = 0 "
            selected_params = tuple()

        selected_volume_rows = conn.execute(
            f"""
            WITH topic_events AS (
                {topic_events_sql}
            )
            SELECT topic_id, day, COUNT(*) AS total_volume
            FROM topic_events
            {selected_clause}
            GROUP BY topic_id, day
            ORDER BY day ASC, topic_id ASC
            """,
            tuple(params) + selected_params,
        ).fetchall()

        participant_rows = conn.execute(
            f"""
            WITH topic_events AS (
                {topic_events_sql}
            )
            SELECT topic_id, day, COUNT(DISTINCT actor_id) AS participants
            FROM topic_events
            {selected_clause}
            GROUP BY topic_id, day
            ORDER BY day ASC, topic_id ASC
            """,
            tuple(params) + selected_params,
        ).fetchall()

        actor_day_rows = conn.execute(
            f"""
            WITH topic_events AS (
                {topic_events_sql}
            )
            SELECT DISTINCT topic_id, actor_id, day
            FROM topic_events
            {selected_clause}
            ORDER BY day ASC, topic_id ASC
            """,
            tuple(params) + selected_params,
        ).fetchall()

        lifecycle_rows = conn.execute(
            f"""
            WITH topic_events AS (
                {topic_events_sql}
            ),
            daily AS (
                SELECT topic_id, day, COUNT(*) AS total_volume
                FROM topic_events
                GROUP BY topic_id, day
            ),
            first_last AS (
                SELECT topic_id, MIN(day) AS first_day, MAX(day) AS last_day
                FROM daily
                GROUP BY topic_id
            )
            SELECT
                d.day AS day,
                COUNT(DISTINCT d.topic_id) AS active_topics,
                SUM(CASE WHEN fl.first_day = d.day THEN 1 ELSE 0 END) AS new_topics,
                SUM(CASE WHEN fl.last_day = d.day THEN 1 ELSE 0 END) AS vanished_topics
            FROM daily d
            JOIN first_last fl ON fl.topic_id = d.topic_id
            GROUP BY d.day
            ORDER BY d.day ASC
            """,
            tuple(params),
        ).fetchall()

        summary_rows = conn.execute(
            f"""
            WITH topic_events AS (
                {topic_events_sql}
            ),
            daily AS (
                SELECT topic_id, day, COUNT(*) AS total_volume
                FROM topic_events
                GROUP BY topic_id, day
            )
            SELECT
                te.topic_id AS topic_id,
                COUNT(*) AS total_volume,
                COUNT(DISTINCT te.actor_id) AS participants,
                MIN(te.day) AS first_day,
                MAX(te.day) AS last_day,
                SUM(CASE WHEN te.day = ? THEN 1 ELSE 0 END) AS current_day_volume
            FROM topic_events te
            {selected_clause}
            GROUP BY te.topic_id
            ORDER BY total_volume DESC, te.topic_id ASC
            """,
            tuple(params) + ((filter_day,) + selected_params),
        ).fetchall()

    trend_mode = str(trend_mode or "daily").strip().lower()
    if trend_mode not in {"daily", "cumulative"}:
        trend_mode = "daily"

    days = sorted(
        {int(row["day"]) for row in lifecycle_rows}
        | {int(row["day"]) for row in selected_volume_rows}
    )
    volume_by_topic_day = defaultdict(dict)
    for row in selected_volume_rows:
        volume_by_topic_day[str(row["topic_id"])][int(row["day"])] = _safe_int(
            row["total_volume"]
        )
    participants_by_topic_day = defaultdict(dict)
    for row in participant_rows:
        participants_by_topic_day[str(row["topic_id"])][int(row["day"])] = _safe_int(
            row["participants"]
        )

    if trend_mode == "cumulative":
        for topic_id in selected_topic_ids:
            running_volume = 0
            for day in days:
                running_volume += volume_by_topic_day[topic_id].get(day, 0)
                volume_by_topic_day[topic_id][day] = running_volume
        seen_by_topic = defaultdict(set)
        for row in actor_day_rows:
            topic_id = str(row["topic_id"])
            seen_by_topic[topic_id].add(str(row["actor_id"]))
            participants_by_topic_day[topic_id][int(row["day"])] = len(
                seen_by_topic[topic_id]
            )
        for topic_id in selected_topic_ids:
            last_value = 0
            for day in days:
                if day in participants_by_topic_day[topic_id]:
                    last_value = participants_by_topic_day[topic_id][day]
                participants_by_topic_day[topic_id][day] = last_value

    active_topic_count = max(
        (_safe_int(row["active_topics"]) for row in lifecycle_rows), default=0
    )
    new_topic_count = sum(_safe_int(row["new_topics"]) for row in lifecycle_rows)
    vanished_topic_count = sum(
        _safe_int(row["vanished_topics"]) for row in lifecycle_rows
    )

    topic_palette = [
        "#2563eb",
        "#7c3aed",
        "#0f766e",
        "#ea580c",
        "#db2777",
        "#0891b2",
        "#65a30d",
        "#b45309",
    ]

    def _topic_color(topic_id):
        if topic_id in selected_topic_ids:
            return topic_palette[
                selected_topic_ids.index(topic_id) % len(topic_palette)
            ]
        return topic_palette[0]

    topic_labels = [
        next(
            (
                option["topic_name"]
                for option in topic_options
                if option["topic_id"] == topic_id
            ),
            topic_id,
        )
        for topic_id in selected_topic_ids
    ]

    if trend_mode == "cumulative":
        trend_definition = {
            "title": "Topic Volume Cumulative Trend",
            "description": "Cumulative topic-related activity volume for the selected topics.",
            "type": "line",
            "labels": [f"Day {day}" for day in days],
            "datasets": [
                {
                    "label": topic_labels[index],
                    "data": [volume_by_topic_day[topic_id].get(day, 0) for day in days],
                    "borderColor": _topic_color(topic_id),
                    "backgroundColor": "transparent",
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2.5,
                    "tension": 0.28,
                }
                for index, topic_id in enumerate(selected_topic_ids)
            ],
            "options": {"beginAtZero": True, "legendPosition": "bottom"},
        }
        secondary_definition = {
            "title": "Population Reach Cumulative Trend",
            "description": "Cumulative share of the population that has been involved with each selected topic.",
            "type": "line",
            "labels": [f"Day {day}" for day in days],
            "datasets": [
                {
                    "label": topic_labels[index],
                    "data": [
                        round(
                            100.0
                            * participants_by_topic_day[topic_id].get(day, 0)
                            / max(total_population, 1),
                            2,
                        )
                        for day in days
                    ],
                    "borderColor": _topic_color(topic_id),
                    "backgroundColor": "transparent",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2.25,
                    "tension": 0.28,
                }
                for index, topic_id in enumerate(selected_topic_ids)
            ],
            "options": {"beginAtZero": True, "max": 100, "legendPosition": "bottom"},
        }
    else:
        trend_cells = []
        secondary_cells = []
        for row_index, topic_id in enumerate(selected_topic_ids):
            row_daily_values = [
                volume_by_topic_day[topic_id].get(day, 0) for day in days
            ]
            row_max = max(row_daily_values) if row_daily_values else 0
            for col_index, day in enumerate(days):
                actual_volume = volume_by_topic_day[topic_id].get(day, 0)
                participants = participants_by_topic_day[topic_id].get(day, 0)
                reach_pct = round(100.0 * participants / max(total_population, 1), 2)
                trend_cells.append(
                    {
                        "x": col_index,
                        "y": row_index,
                        "actual": actual_volume,
                        "intensity": (
                            round(actual_volume / row_max, 4) if row_max else 0.0
                        ),
                        "topic_label": topic_labels[row_index],
                        "time_label": f"Day {day}",
                    }
                )
                secondary_cells.append(
                    {
                        "x": col_index,
                        "y": row_index,
                        "actual": participants,
                        "percent": reach_pct,
                        "intensity": round(reach_pct / 100.0, 4),
                        "topic_label": topic_labels[row_index],
                        "time_label": f"Day {day}",
                    }
                )
        trend_definition = {
            "title": "Topic Volume Heatmap",
            "description": "Each row is a selected topic, each column is a day, and color depth is normalized within each topic row. Tooltips report actual daily volume.",
            "type": "heatmap",
            "labels": [f"Day {day}" for day in days],
            "row_labels": topic_labels,
            "cells": trend_cells,
            "options": {
                "colorStart": [239, 246, 255],
                "colorEnd": [37, 99, 235],
                "legendDisplay": False,
                "tooltipMode": "volume",
            },
        }
        secondary_definition = {
            "title": "Population Reach Heatmap",
            "description": "Each row is a selected topic, each column is a day, and color depth reflects the share of the population reached that day.",
            "type": "heatmap",
            "labels": [f"Day {day}" for day in days],
            "row_labels": topic_labels,
            "cells": secondary_cells,
            "options": {
                "colorStart": [240, 253, 244],
                "colorEnd": [21, 128, 61],
                "legendDisplay": False,
                "tooltipMode": "reach",
            },
        }

    stats = [
        {
            "key": "selected_topics",
            "label": "Selected Topics",
            "value": len(selected_topic_ids),
            "color": "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
        },
        {
            "key": "active_topics",
            "label": "Active Topics",
            "value": active_topic_count,
            "color": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
        },
        {
            "key": "emerged_topics",
            "label": "Emerging Topics",
            "value": new_topic_count,
            "color": "linear-gradient(135deg, #10b981 0%, #059669 100%)",
        },
        {
            "key": "vanished_topics",
            "label": "Vanishing Topics",
            "value": vanished_topic_count,
            "color": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        },
        {
            "key": "current_day",
            "label": "Current Day",
            "value": f"Day {filter_day}",
            "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)",
        },
        {
            "key": "current_hour",
            "label": "Current Hour",
            "value": f"Hour {filter_hour}",
            "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)",
        },
    ]

    return {
        "page_title": "Topic Evolution",
        "title": "Topic Evolution",
        "description": "Track topic diffusion, emergence, and disappearance through content and interaction activity.",
        "stats": stats,
        "trend_mode": trend_mode,
        "selector_label": "Topics to Visualize",
        "selector_hint": "Cmd/Ctrl for multi-select",
        "trend_mode_options": [
            {"value": "daily", "label": "Daily Heatmap"},
            {"value": "cumulative", "label": "Cumulative Trends"},
        ],
        "selected_ids": selected_topic_ids,
        "selector_options": [
            {
                "value": option["topic_id"],
                "label": f"{option['topic_name']} ({option['total_volume']})",
            }
            for option in topic_options
        ],
        "selected_topic_ids": selected_topic_ids,
        "topic_options": topic_options,
        "distribution": {
            "title": "Topic Footprint at Selected Time",
            "description": "Cumulative topic-related volume up to the selected time, including content and downstream interactions.",
            "type": "bar",
            "labels": [
                next(
                    (
                        option["topic_name"]
                        for option in topic_options
                        if option["topic_id"] == topic_id
                    ),
                    topic_id,
                )
                for topic_id in selected_topic_ids
            ],
            "datasets": [
                {
                    "label": "Total Volume",
                    "data": [
                        next(
                            (
                                option["total_volume"]
                                for option in topic_options
                                if option["topic_id"] == topic_id
                            ),
                            0,
                        )
                        for topic_id in selected_topic_ids
                    ],
                    "backgroundColor": [
                        _topic_color(topic_id) for topic_id in selected_topic_ids
                    ],
                    "borderRadius": 8,
                    "maxBarThickness": 24,
                }
            ],
            "options": {"beginAtZero": True, "indexAxis": "y", "legendDisplay": False},
        },
        "trend": trend_definition,
        "secondary": secondary_definition,
        "topic_lifecycle": {
            "title": "Topic Lifecycle Over Time",
            "description": "Compact view of how many topics remain active, emerge, and disappear across the observed horizon.",
            "type": "line",
            "labels": [f"Day {int(row['day'])}" for row in lifecycle_rows],
            "datasets": [
                {
                    "label": "Active Topics",
                    "data": [_safe_int(row["active_topics"]) for row in lifecycle_rows],
                    "borderColor": "#8b5cf6",
                    "backgroundColor": "rgba(124, 58, 237, 0.10)",
                    "fill": True,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2.5,
                    "tension": 0.28,
                },
                {
                    "label": "New Topics",
                    "data": [_safe_int(row["new_topics"]) for row in lifecycle_rows],
                    "borderColor": "#10b981",
                    "backgroundColor": "transparent",
                    "borderDash": [6, 4],
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                    "tension": 0.25,
                },
                {
                    "label": "Vanished Topics",
                    "data": [
                        _safe_int(row["vanished_topics"]) for row in lifecycle_rows
                    ],
                    "borderColor": "#f59e0b",
                    "backgroundColor": "transparent",
                    "borderDash": [3, 3],
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                    "tension": 0.25,
                },
            ],
            "options": {"beginAtZero": True, "legendPosition": "bottom"},
        },
        "summary": {
            "title": "Selected Topic Summary",
            "columns": [
                "Topic",
                "First Seen",
                "Last Seen",
                "Total Volume",
                "Distinct Participants",
                "Population Share",
                "Current Day Volume",
            ],
            "rows": [
                [
                    next(
                        (
                            option["topic_name"]
                            for option in topic_options
                            if option["topic_id"] == str(row["topic_id"])
                        ),
                        str(row["topic_id"]),
                    ),
                    f"Day {_safe_int(row['first_day'])}",
                    f"Day {_safe_int(row['last_day'])}",
                    _safe_int(row["total_volume"]),
                    _safe_int(row["participants"]),
                    f"{round(100.0 * _safe_int(row['participants']) / max(total_population, 1), 2)}%",
                    _safe_int(row["current_day_volume"]),
                ]
                for row in summary_rows
            ],
            "empty_message": "No topic activity has been recorded up to the selected time.",
        },
    }


def _build_hashtag_evolution_payload(
    db_path, filter_day, filter_hour, selected_hashtag_ids=None, trend_mode="daily"
):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        table_names = {
            row["name"] if isinstance(row, sqlite3.Row) else row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        reported_round_column = (
            _table_round_column(conn, "reported") if "reported" in table_names else None
        )
        total_population = _safe_int(
            conn.execute("SELECT COUNT(*) AS c FROM user_mgmt").fetchone()["c"]
        )

        event_queries = ["""
            SELECT
                ph.hashtag_id AS hashtag_id,
                p.user_id AS actor_id,
                r.day AS day,
                r.hour AS hour,
                'content' AS event_type
            FROM post_hashtags ph
            JOIN post p ON p.id = ph.post_id
            JOIN rounds r ON r.id = p.round
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            """]
        params = [filter_day, filter_day, filter_hour]

        if "reactions" in table_names:
            event_queries.append("""
                SELECT
                    ph.hashtag_id AS hashtag_id,
                    re.user_id AS actor_id,
                    r.day AS day,
                    r.hour AS hour,
                    'reaction' AS event_type
                FROM post_hashtags ph
                JOIN reactions re ON re.post_id = ph.post_id
                JOIN rounds r ON r.id = re.round
                WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                """)
            params.extend([filter_day, filter_day, filter_hour])

        if "reported" in table_names and reported_round_column:
            event_queries.append(f"""
                SELECT
                    ph.hashtag_id AS hashtag_id,
                    rp.from_uid AS actor_id,
                    r.day AS day,
                    r.hour AS hour,
                    'report' AS event_type
                FROM post_hashtags ph
                JOIN reported rp ON rp.to_post = ph.post_id
                JOIN rounds r ON r.id = rp.{reported_round_column}
                WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                """)
            params.extend([filter_day, filter_day, filter_hour])

        hashtag_events_sql = " UNION ALL ".join(event_queries)

        current_volume_rows = conn.execute(
            f"""
            WITH hashtag_events AS (
                {hashtag_events_sql}
            )
            SELECT
                he.hashtag_id,
                h.hashtag,
                COUNT(*) AS total_volume
            FROM hashtag_events he
            JOIN hashtags h ON h.id = he.hashtag_id
            GROUP BY he.hashtag_id, h.hashtag
            ORDER BY total_volume DESC, h.hashtag ASC
            """,
            tuple(params),
        ).fetchall()

        hashtag_options = [
            {
                "hashtag_id": str(row["hashtag_id"]),
                "hashtag_name": str(row["hashtag"]),
                "total_volume": _safe_int(row["total_volume"]),
            }
            for row in current_volume_rows
        ]

        selected_hashtag_ids = [
            str(hashtag_id)
            for hashtag_id in (selected_hashtag_ids or [])
            if str(hashtag_id) in {option["hashtag_id"] for option in hashtag_options}
        ]
        if not selected_hashtag_ids:
            selected_hashtag_ids = [
                option["hashtag_id"] for option in hashtag_options[:5]
            ]

        if selected_hashtag_ids:
            placeholders = ",".join(["?"] * len(selected_hashtag_ids))
            selected_clause = f" WHERE hashtag_id IN ({placeholders}) "
            selected_params = tuple(selected_hashtag_ids)
        else:
            selected_clause = " WHERE 1 = 0 "
            selected_params = tuple()

        selected_volume_rows = conn.execute(
            f"""
            WITH hashtag_events AS (
                {hashtag_events_sql}
            )
            SELECT hashtag_id, day, COUNT(*) AS total_volume
            FROM hashtag_events
            {selected_clause}
            GROUP BY hashtag_id, day
            ORDER BY day ASC, hashtag_id ASC
            """,
            tuple(params) + selected_params,
        ).fetchall()

        participant_rows = conn.execute(
            f"""
            WITH hashtag_events AS (
                {hashtag_events_sql}
            )
            SELECT hashtag_id, day, COUNT(DISTINCT actor_id) AS participants
            FROM hashtag_events
            {selected_clause}
            GROUP BY hashtag_id, day
            ORDER BY day ASC, hashtag_id ASC
            """,
            tuple(params) + selected_params,
        ).fetchall()

        actor_day_rows = conn.execute(
            f"""
            WITH hashtag_events AS (
                {hashtag_events_sql}
            )
            SELECT DISTINCT hashtag_id, actor_id, day
            FROM hashtag_events
            {selected_clause}
            ORDER BY day ASC, hashtag_id ASC
            """,
            tuple(params) + selected_params,
        ).fetchall()

        lifecycle_rows = conn.execute(
            f"""
            WITH hashtag_events AS (
                {hashtag_events_sql}
            ),
            daily AS (
                SELECT hashtag_id, day, COUNT(*) AS total_volume
                FROM hashtag_events
                GROUP BY hashtag_id, day
            ),
            first_last AS (
                SELECT hashtag_id, MIN(day) AS first_day, MAX(day) AS last_day
                FROM daily
                GROUP BY hashtag_id
            )
            SELECT
                d.day AS day,
                COUNT(DISTINCT d.hashtag_id) AS active_topics,
                SUM(CASE WHEN fl.first_day = d.day THEN 1 ELSE 0 END) AS new_topics,
                SUM(CASE WHEN fl.last_day = d.day THEN 1 ELSE 0 END) AS vanished_topics
            FROM daily d
            JOIN first_last fl ON fl.hashtag_id = d.hashtag_id
            GROUP BY d.day
            ORDER BY d.day ASC
            """,
            tuple(params),
        ).fetchall()

        summary_rows = conn.execute(
            f"""
            WITH hashtag_events AS (
                {hashtag_events_sql}
            )
            SELECT
                he.hashtag_id AS hashtag_id,
                h.hashtag AS hashtag,
                COUNT(*) AS total_volume,
                COUNT(DISTINCT he.actor_id) AS participants,
                MIN(he.day) AS first_day,
                MAX(he.day) AS last_day,
                SUM(CASE WHEN he.day = ? THEN 1 ELSE 0 END) AS current_day_volume
            FROM hashtag_events he
            JOIN hashtags h ON h.id = he.hashtag_id
            {selected_clause}
            GROUP BY he.hashtag_id, h.hashtag
            ORDER BY total_volume DESC, h.hashtag ASC
            """,
            tuple(params) + ((filter_day,) + selected_params),
        ).fetchall()

    trend_mode = str(trend_mode or "daily").strip().lower()
    if trend_mode not in {"daily", "cumulative"}:
        trend_mode = "daily"

    days = sorted(
        {int(row["day"]) for row in lifecycle_rows}
        | {int(row["day"]) for row in selected_volume_rows}
    )
    volume_by_hashtag_day = defaultdict(dict)
    for row in selected_volume_rows:
        volume_by_hashtag_day[str(row["hashtag_id"])][int(row["day"])] = _safe_int(
            row["total_volume"]
        )
    participants_by_hashtag_day = defaultdict(dict)
    for row in participant_rows:
        participants_by_hashtag_day[str(row["hashtag_id"])][int(row["day"])] = (
            _safe_int(row["participants"])
        )

    if trend_mode == "cumulative":
        for hashtag_id in selected_hashtag_ids:
            running_volume = 0
            for day in days:
                running_volume += volume_by_hashtag_day[hashtag_id].get(day, 0)
                volume_by_hashtag_day[hashtag_id][day] = running_volume
        seen_by_hashtag = defaultdict(set)
        for row in actor_day_rows:
            hashtag_id = str(row["hashtag_id"])
            seen_by_hashtag[hashtag_id].add(str(row["actor_id"]))
            participants_by_hashtag_day[hashtag_id][int(row["day"])] = len(
                seen_by_hashtag[hashtag_id]
            )
        for hashtag_id in selected_hashtag_ids:
            last_value = 0
            for day in days:
                if day in participants_by_hashtag_day[hashtag_id]:
                    last_value = participants_by_hashtag_day[hashtag_id][day]
                participants_by_hashtag_day[hashtag_id][day] = last_value

    active_hashtag_count = max(
        (_safe_int(row["active_topics"]) for row in lifecycle_rows), default=0
    )
    new_hashtag_count = sum(_safe_int(row["new_topics"]) for row in lifecycle_rows)
    vanished_hashtag_count = sum(
        _safe_int(row["vanished_topics"]) for row in lifecycle_rows
    )

    hashtag_palette = [
        "#2563eb",
        "#7c3aed",
        "#0f766e",
        "#ea580c",
        "#db2777",
        "#0891b2",
        "#65a30d",
        "#b45309",
    ]

    def _hashtag_color(hashtag_id):
        if hashtag_id in selected_hashtag_ids:
            return hashtag_palette[
                selected_hashtag_ids.index(hashtag_id) % len(hashtag_palette)
            ]
        return hashtag_palette[0]

    hashtag_labels = [
        next(
            (
                option["hashtag_name"]
                for option in hashtag_options
                if option["hashtag_id"] == hashtag_id
            ),
            hashtag_id,
        )
        for hashtag_id in selected_hashtag_ids
    ]

    if trend_mode == "cumulative":
        trend_definition = {
            "title": "Hashtag Volume Cumulative Trend",
            "description": "Cumulative hashtag-related activity volume for the selected hashtags.",
            "type": "line",
            "labels": [f"Day {day}" for day in days],
            "datasets": [
                {
                    "label": hashtag_labels[index],
                    "data": [
                        volume_by_hashtag_day[hashtag_id].get(day, 0) for day in days
                    ],
                    "borderColor": _hashtag_color(hashtag_id),
                    "backgroundColor": "transparent",
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2.5,
                    "tension": 0.28,
                }
                for index, hashtag_id in enumerate(selected_hashtag_ids)
            ],
            "options": {"beginAtZero": True, "legendPosition": "bottom"},
        }
        secondary_definition = {
            "title": "Hashtag Reach Cumulative Trend",
            "description": "Cumulative share of the population that has been involved with each selected hashtag.",
            "type": "line",
            "labels": [f"Day {day}" for day in days],
            "datasets": [
                {
                    "label": hashtag_labels[index],
                    "data": [
                        round(
                            100.0
                            * participants_by_hashtag_day[hashtag_id].get(day, 0)
                            / max(total_population, 1),
                            2,
                        )
                        for day in days
                    ],
                    "borderColor": _hashtag_color(hashtag_id),
                    "backgroundColor": "transparent",
                    "fill": False,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2.25,
                    "tension": 0.28,
                }
                for index, hashtag_id in enumerate(selected_hashtag_ids)
            ],
            "options": {"beginAtZero": True, "max": 100, "legendPosition": "bottom"},
        }
    else:
        trend_cells = []
        secondary_cells = []
        for row_index, hashtag_id in enumerate(selected_hashtag_ids):
            row_daily_values = [
                volume_by_hashtag_day[hashtag_id].get(day, 0) for day in days
            ]
            row_max = max(row_daily_values) if row_daily_values else 0
            for col_index, day in enumerate(days):
                actual_volume = volume_by_hashtag_day[hashtag_id].get(day, 0)
                participants = participants_by_hashtag_day[hashtag_id].get(day, 0)
                reach_pct = round(100.0 * participants / max(total_population, 1), 2)
                trend_cells.append(
                    {
                        "x": col_index,
                        "y": row_index,
                        "actual": actual_volume,
                        "intensity": (
                            round(actual_volume / row_max, 4) if row_max else 0.0
                        ),
                        "topic_label": hashtag_labels[row_index],
                        "time_label": f"Day {day}",
                    }
                )
                secondary_cells.append(
                    {
                        "x": col_index,
                        "y": row_index,
                        "actual": participants,
                        "percent": reach_pct,
                        "intensity": round(reach_pct / 100.0, 4),
                        "topic_label": hashtag_labels[row_index],
                        "time_label": f"Day {day}",
                    }
                )
        trend_definition = {
            "title": "Hashtag Volume Heatmap",
            "description": "Each row is a selected hashtag, each column is a day, and color depth is normalized within each hashtag row. Tooltips report actual daily volume.",
            "type": "heatmap",
            "labels": [f"Day {day}" for day in days],
            "row_labels": hashtag_labels,
            "cells": trend_cells,
            "options": {
                "colorStart": [239, 246, 255],
                "colorEnd": [37, 99, 235],
                "legendDisplay": False,
                "tooltipMode": "volume",
            },
        }
        secondary_definition = {
            "title": "Population Reach Heatmap",
            "description": "Each row is a selected hashtag, each column is a day, and color depth reflects the share of the population reached that day.",
            "type": "heatmap",
            "labels": [f"Day {day}" for day in days],
            "row_labels": hashtag_labels,
            "cells": secondary_cells,
            "options": {
                "colorStart": [240, 253, 244],
                "colorEnd": [21, 128, 61],
                "legendDisplay": False,
                "tooltipMode": "reach",
            },
        }

    stats = [
        {
            "key": "selected_topics",
            "label": "Selected Hashtags",
            "value": len(selected_hashtag_ids),
            "color": "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
        },
        {
            "key": "active_topics",
            "label": "Active Hashtags",
            "value": active_hashtag_count,
            "color": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
        },
        {
            "key": "emerged_topics",
            "label": "Emerging Hashtags",
            "value": new_hashtag_count,
            "color": "linear-gradient(135deg, #10b981 0%, #059669 100%)",
        },
        {
            "key": "vanished_topics",
            "label": "Vanishing Hashtags",
            "value": vanished_hashtag_count,
            "color": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        },
        {
            "key": "current_day",
            "label": "Current Day",
            "value": f"Day {filter_day}",
            "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)",
        },
        {
            "key": "current_hour",
            "label": "Current Hour",
            "value": f"Hour {filter_hour}",
            "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)",
        },
    ]

    return {
        "page_title": "Hashtag Evolution",
        "title": "Hashtag Evolution",
        "description": "Track hashtag diffusion, emergence, and disappearance through content and interaction activity.",
        "stats": stats,
        "trend_mode": trend_mode,
        "selector_label": "Hashtags to Visualize",
        "selector_hint": "Cmd/Ctrl for multi-select",
        "trend_mode_options": [
            {"value": "daily", "label": "Daily Heatmap"},
            {"value": "cumulative", "label": "Cumulative Trends"},
        ],
        "selected_ids": selected_hashtag_ids,
        "selector_options": [
            {
                "value": option["hashtag_id"],
                "label": f"#{option['hashtag_name']} ({option['total_volume']})",
            }
            for option in hashtag_options
        ],
        "selected_topic_ids": selected_hashtag_ids,
        "topic_options": [
            {
                "topic_id": option["hashtag_id"],
                "topic_name": f"#{option['hashtag_name']}",
                "total_volume": option["total_volume"],
            }
            for option in hashtag_options
        ],
        "distribution": {
            "title": "Hashtag Footprint at Selected Time",
            "description": "Cumulative hashtag-related volume up to the selected time, including content and downstream interactions.",
            "type": "bar",
            "labels": [
                next(
                    (
                        f"#{option['hashtag_name']}"
                        for option in hashtag_options
                        if option["hashtag_id"] == hashtag_id
                    ),
                    hashtag_id,
                )
                for hashtag_id in selected_hashtag_ids
            ],
            "datasets": [
                {
                    "label": "Total Volume",
                    "data": [
                        next(
                            (
                                option["total_volume"]
                                for option in hashtag_options
                                if option["hashtag_id"] == hashtag_id
                            ),
                            0,
                        )
                        for hashtag_id in selected_hashtag_ids
                    ],
                    "backgroundColor": [
                        _hashtag_color(hashtag_id)
                        for hashtag_id in selected_hashtag_ids
                    ],
                    "borderRadius": 8,
                    "maxBarThickness": 24,
                }
            ],
            "options": {"beginAtZero": True, "indexAxis": "y", "legendDisplay": False},
        },
        "trend": trend_definition,
        "secondary": secondary_definition,
        "topic_lifecycle": {
            "title": "Hashtag Lifecycle Over Time",
            "description": "Compact view of how many hashtags remain active, emerge, and disappear across the observed horizon.",
            "type": "line",
            "labels": [f"Day {int(row['day'])}" for row in lifecycle_rows],
            "datasets": [
                {
                    "label": "Active Hashtags",
                    "data": [_safe_int(row["active_topics"]) for row in lifecycle_rows],
                    "borderColor": "#8b5cf6",
                    "backgroundColor": "rgba(124, 58, 237, 0.10)",
                    "fill": True,
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2.5,
                    "tension": 0.28,
                },
                {
                    "label": "New Hashtags",
                    "data": [_safe_int(row["new_topics"]) for row in lifecycle_rows],
                    "borderColor": "#10b981",
                    "backgroundColor": "transparent",
                    "borderDash": [6, 4],
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                    "tension": 0.25,
                },
                {
                    "label": "Vanished Hashtags",
                    "data": [
                        _safe_int(row["vanished_topics"]) for row in lifecycle_rows
                    ],
                    "borderColor": "#f59e0b",
                    "backgroundColor": "transparent",
                    "borderDash": [3, 3],
                    "pointRadius": 0,
                    "pointHoverRadius": 4,
                    "borderWidth": 2,
                    "tension": 0.25,
                },
            ],
            "options": {"beginAtZero": True, "legendPosition": "bottom"},
        },
        "summary": {
            "title": "Selected Hashtag Summary",
            "columns": [
                "Hashtag",
                "First Seen",
                "Last Seen",
                "Total Volume",
                "Distinct Participants",
                "Population Share",
                "Current Day Volume",
            ],
            "rows": [
                [
                    f"#{str(row['hashtag'])}",
                    f"Day {_safe_int(row['first_day'])}",
                    f"Day {_safe_int(row['last_day'])}",
                    _safe_int(row["total_volume"]),
                    _safe_int(row["participants"]),
                    f"{round(100.0 * _safe_int(row['participants']) / max(total_population, 1), 2)}%",
                    _safe_int(row["current_day_volume"]),
                ]
                for row in summary_rows
            ],
            "empty_message": "No hashtag activity has been recorded up to the selected time.",
        },
    }


def _build_toxicity_analytics_payload(
    db_path,
    filter_day,
    filter_hour,
    threshold=0.1,
    selected_target_uid=None,
):
    """Aggregate toxicity annotations up to a selected simulation time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        time_condition = _build_annotation_time_condition("r")
        toxicity_columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(post_toxicity)").fetchall()
            if row["name"] not in {"id", "post_id"}
        ]
        preferred_order = [
            "toxicity",
            "severe_toxicity",
            "identity_attack",
            "insult",
            "profanity",
            "threat",
            "sexually_explicit",
            "flirtation",
        ]
        toxicity_columns = [
            column for column in preferred_order if column in set(toxicity_columns)
        ] or toxicity_columns

        snapshot = conn.execute(
            f"""
            WITH selected AS (
                SELECT pt.post_id, pt.toxicity
                FROM post_toxicity pt
                JOIN post p ON p.id = pt.post_id
                JOIN rounds r ON r.id = p.round
                WHERE {time_condition}
            )
            SELECT
                COUNT(*) AS annotated_posts,
                AVG(toxicity) AS average_toxicity,
                MAX(toxicity) AS peak_toxicity
            FROM selected
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchone()

        trend_sql = ",\n                ".join(
            [f"AVG(pt.{column}) AS avg_{column}" for column in toxicity_columns]
        )
        trend_rows = conn.execute(
            f"""
            SELECT
                r.day AS day,
                {trend_sql}
            FROM post_toxicity pt
            JOIN post p ON p.id = pt.post_id
            JOIN rounds r ON r.id = p.round
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY r.day
            ORDER BY r.day
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

        category_trend_sql = ",\n                ".join(
            [
                f"100.0 * AVG(CASE WHEN pt.{column} >= ? THEN 1.0 ELSE 0.0 END) AS pct_{column}"
                for column in toxicity_columns
            ]
        )
        category_trend_rows = conn.execute(
            f"""
            SELECT
                r.day AS day,
                COUNT(*) AS annotated_posts,
                {category_trend_sql}
            FROM post_toxicity pt
            JOIN post p ON p.id = pt.post_id
            JOIN rounds r ON r.id = p.round
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY r.day
            ORDER BY r.day
            """,
            (
                *([threshold] * len(toxicity_columns)),
                filter_day,
                filter_day,
                filter_hour,
            ),
        ).fetchall()

        distribution_rows = conn.execute(
            f"""
            WITH selected AS (
                SELECT
                    CASE
                        WHEN pt.toxicity >= 1.0 THEN 9
                        ELSE CAST(pt.toxicity * 10 AS INT)
                    END AS bucket
                FROM post_toxicity pt
                JOIN post p ON p.id = pt.post_id
                JOIN rounds r ON r.id = p.round
                WHERE {time_condition}
            )
            SELECT bucket, COUNT(*) AS bucket_count
            FROM selected
            GROUP BY bucket
            ORDER BY bucket
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

        top_rows = conn.execute(
            """
            SELECT
                u.username,
                p.tweet,
                pt.toxicity,
                r.day,
                r.hour
            FROM post_toxicity pt
            JOIN post p ON p.id = pt.post_id
            JOIN user_mgmt u ON u.id = p.user_id
            JOIN rounds r ON r.id = p.round
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            ORDER BY pt.toxicity DESC, r.day DESC, r.hour DESC
            LIMIT 10
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

    snapshot = snapshot or {}
    bucket_counts = [0] * 10
    for row in distribution_rows:
        bucket_index = max(0, min(9, int(row["bucket"] or 0)))
        bucket_counts[bucket_index] = _safe_int(row["bucket_count"])
    non_empty_bucket_indices = [
        index for index, count in enumerate(bucket_counts) if count > 0
    ]
    if not non_empty_bucket_indices:
        non_empty_bucket_indices = [0]

    distribution_labels = [
        f"{index / 10:.1f}-{(index + 1) / 10:.1f}" for index in non_empty_bucket_indices
    ]
    distribution_data = [bucket_counts[index] for index in non_empty_bucket_indices]

    max_average_toxicity = max(
        [
            _safe_float(row[f"avg_{column}"], digits=6)
            for row in trend_rows
            for column in toxicity_columns
        ]
        or [0.0]
    )
    average_y_max = min(1.0, max(0.05, max_average_toxicity + 0.02))
    max_category_percentage = max(
        [
            _safe_float(row[f"pct_{column}"], digits=6)
            for row in category_trend_rows
            for column in toxicity_columns
        ]
        or [0.0]
    )
    category_y_max = max(1.0, max_category_percentage)
    category_palette = [
        "#dc2626",
        "#7c3aed",
        "#0ea5e9",
        "#f97316",
        "#eab308",
        "#14b8a6",
        "#ec4899",
        "#64748b",
    ]
    category_labels = {
        "toxicity": "Toxicity",
        "severe_toxicity": "Severe Toxicity",
        "identity_attack": "Identity Attack",
        "insult": "Insult",
        "profanity": "Profanity",
        "threat": "Threat",
        "sexually_explicit": "Sexually Explicit",
        "flirtation": "Flirtation",
    }
    stats = [
        {
            "key": "annotated_posts",
            "label": "Annotated Posts",
            "value": _safe_int(snapshot["annotated_posts"]),
            "color": "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
        },
        {
            "key": "average_toxicity",
            "label": "Average Toxicity",
            "value": f"{_safe_float(snapshot['average_toxicity']):.3f}",
            "color": "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
        },
        {
            "key": "peak_toxicity",
            "label": "Peak Toxicity",
            "value": f"{_safe_float(snapshot['peak_toxicity']):.3f}",
            "color": "linear-gradient(135deg, #7c2d12 0%, #9a3412 100%)",
        },
        {
            "key": "current_day",
            "label": "Current Day",
            "value": f"Day {filter_day}",
            "color": "linear-gradient(135deg, #10b981 0%, #059669 100%)",
        },
        {
            "key": "current_hour",
            "label": "Current Hour",
            "value": f"Hour {filter_hour}",
            "color": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        },
    ]

    return {
        "page_title": "Toxicity Evolution",
        "title": "Toxicity Evolution",
        "description": "Track how toxic content annotations accumulate over time.",
        "stats": stats,
        "distribution": {
            "title": "Toxicity Distribution",
            "description": "Current toxicity score distribution across annotated posts, using 0.1 bins.",
            "type": "bar",
            "labels": distribution_labels,
            "datasets": [
                {
                    "label": "Posts",
                    "data": distribution_data,
                    "backgroundColor": [
                        (
                            "#93c5fd"
                            if bucket_index < 3
                            else (
                                "#fbbf24"
                                if bucket_index < 6
                                else "#fb7185" if bucket_index < 8 else "#b91c1c"
                            )
                        )
                        for bucket_index in non_empty_bucket_indices
                    ],
                    "borderColor": "#ffffff",
                    "borderWidth": 1,
                }
            ],
            "options": {"beginAtZero": True},
        },
        "trend": {
            "title": "Average Toxicity Trend",
            "description": "Daily average score for each toxicity category up to the selected time.",
            "type": "line",
            "labels": [f"Day {int(row['day'])}" for row in trend_rows],
            "datasets": [
                {
                    "label": category_labels.get(
                        column, column.replace("_", " ").title()
                    ),
                    "data": [_safe_float(row[f"avg_{column}"]) for row in trend_rows],
                    "borderColor": category_palette[index % len(category_palette)],
                    "fill": False,
                    "tension": 0.25,
                }
                for index, column in enumerate(toxicity_columns)
            ],
            "options": {"beginAtZero": True, "max": average_y_max},
        },
        "secondary": {
            "title": "Toxicity Category Trends",
            "description": f"Daily percentage of annotated posts crossing the {threshold:.1f} threshold for each toxicity category.",
            "type": "line",
            "labels": [f"Day {int(row['day'])}" for row in category_trend_rows],
            "datasets": [
                {
                    "label": category_labels.get(
                        column, column.replace("_", " ").title()
                    ),
                    "data": [
                        _safe_float(row[f"pct_{column}"]) for row in category_trend_rows
                    ],
                    "borderColor": category_palette[index % len(category_palette)],
                    "fill": False,
                    "tension": 0.25,
                }
                for index, column in enumerate(toxicity_columns)
            ],
            "options": {"beginAtZero": True, "max": category_y_max},
        },
        "summary": {
            "title": "Most Toxic Posts",
            "columns": ["Author", "Toxicity", "When", "Content"],
            "rows": [
                [
                    row["username"],
                    f"{_safe_float(row['toxicity']):.3f}",
                    f"Day {row['day']}, Hour {row['hour']}",
                    _truncate_text(row["tweet"]),
                ]
                for row in top_rows
            ],
            "empty_message": "No toxicity annotations have been recorded up to the selected time.",
        },
        "moderator_targets": _build_moderator_target_panel(
            db_path,
            filter_day,
            filter_hour,
            selected_target_uid=selected_target_uid,
        ),
    }


def _build_sentiment_analytics_payload(db_path, filter_day, filter_hour):
    """Aggregate sentiment annotations up to a selected simulation time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        time_condition = _build_annotation_time_condition("r")

        snapshot = conn.execute(
            f"""
            WITH post_sentiment_dedup AS (
                SELECT
                    ps.post_id,
                    AVG(ps.compound) AS compound
                FROM post_sentiment ps
                JOIN rounds r ON r.id = ps.round
                WHERE {time_condition}
                GROUP BY ps.post_id
            )
            SELECT
                COUNT(*) AS annotated_posts,
                AVG(compound) AS average_compound,
                SUM(CASE WHEN compound > 0.05 THEN 1 ELSE 0 END) AS positive_count,
                SUM(CASE WHEN compound < -0.05 THEN 1 ELSE 0 END) AS negative_count,
                SUM(CASE WHEN compound >= -0.05 AND compound <= 0.05 THEN 1 ELSE 0 END) AS neutral_count
            FROM post_sentiment_dedup
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchone()

        trend_rows = conn.execute(
            """
            WITH per_post AS (
                SELECT
                    r.day AS day,
                    ps.post_id,
                    AVG(ps.compound) AS compound
                FROM post_sentiment ps
                JOIN rounds r ON r.id = ps.round
                WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                GROUP BY r.day, ps.post_id
            )
            SELECT
                day,
                AVG(compound) AS average_compound,
                SUM(CASE WHEN compound > 0.05 THEN 1 ELSE 0 END) AS positive_count,
                SUM(CASE WHEN compound < -0.05 THEN 1 ELSE 0 END) AS negative_count,
                SUM(CASE WHEN compound >= -0.05 AND compound <= 0.05 THEN 1 ELSE 0 END) AS neutral_count
            FROM per_post
            GROUP BY day
            ORDER BY day
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

        extreme_rows = conn.execute(
            """
            WITH post_sentiment_dedup AS (
                SELECT
                    ps.post_id,
                    AVG(ps.compound) AS compound
                FROM post_sentiment ps
                JOIN rounds r ON r.id = ps.round
                WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                GROUP BY ps.post_id
            )
            SELECT
                u.username,
                p.tweet,
                d.compound,
                r.day,
                r.hour
            FROM post_sentiment_dedup d
            JOIN post p ON p.id = d.post_id
            JOIN user_mgmt u ON u.id = p.user_id
            JOIN rounds r ON r.id = p.round
            ORDER BY ABS(d.compound) DESC, r.day DESC, r.hour DESC
            LIMIT 10
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

    snapshot = snapshot or {}
    stats = [
        {
            "key": "annotated_posts",
            "label": "Annotated Posts",
            "value": _safe_int(snapshot["annotated_posts"]),
            "color": "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
        },
        {
            "key": "average_compound",
            "label": "Average Compound",
            "value": f"{_safe_float(snapshot['average_compound']):.3f}",
            "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)",
        },
        {
            "key": "positive_count",
            "label": "Positive Posts",
            "value": _safe_int(snapshot["positive_count"]),
            "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)",
        },
        {
            "key": "current_day",
            "label": "Current Day",
            "value": f"Day {filter_day}",
            "color": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
        },
        {
            "key": "current_hour",
            "label": "Current Hour",
            "value": f"Hour {filter_hour}",
            "color": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        },
    ]

    return {
        "page_title": "Sentiment Evolution",
        "title": "Sentiment Evolution",
        "description": "Inspect how sentiment annotations evolve across the experiment.",
        "stats": stats,
        "distribution": {
            "title": "Sentiment Distribution",
            "description": "Current polarity breakdown across annotated posts.",
            "type": "doughnut",
            "labels": ["Positive", "Neutral", "Negative"],
            "datasets": [
                {
                    "label": "Posts",
                    "data": [
                        _safe_int(snapshot["positive_count"]),
                        _safe_int(snapshot["neutral_count"]),
                        _safe_int(snapshot["negative_count"]),
                    ],
                    "backgroundColor": ["#22c55e", "#94a3b8", "#ef4444"],
                }
            ],
            "options": {},
        },
        "trend": {
            "title": "Average Compound Trend",
            "description": "Average sentiment compound by day up to the selected time.",
            "type": "line",
            "labels": [f"Day {int(row['day'])}" for row in trend_rows],
            "datasets": [
                {
                    "label": "Average Compound",
                    "data": [
                        _safe_float(row["average_compound"]) for row in trend_rows
                    ],
                    "borderColor": "#2563eb",
                    "backgroundColor": "rgba(37, 99, 235, 0.16)",
                    "fill": True,
                    "tension": 0.3,
                }
            ],
            "options": {"min": -1, "max": 1},
        },
        "secondary": {
            "title": "Sentiment Mix Over Time",
            "description": "Positive, neutral, and negative post counts by day.",
            "type": "bar",
            "labels": [f"Day {int(row['day'])}" for row in trend_rows],
            "datasets": [
                {
                    "label": "Positive",
                    "data": [_safe_int(row["positive_count"]) for row in trend_rows],
                    "backgroundColor": "#22c55e",
                },
                {
                    "label": "Neutral",
                    "data": [_safe_int(row["neutral_count"]) for row in trend_rows],
                    "backgroundColor": "#94a3b8",
                },
                {
                    "label": "Negative",
                    "data": [_safe_int(row["negative_count"]) for row in trend_rows],
                    "backgroundColor": "#ef4444",
                },
            ],
            "options": {"beginAtZero": True, "stacked": True},
        },
        "summary": {
            "title": "Most Polarized Posts",
            "columns": ["Author", "Compound", "When", "Content"],
            "rows": [
                [
                    row["username"],
                    f"{_safe_float(row['compound']):.3f}",
                    f"Day {row['day']}, Hour {row['hour']}",
                    _truncate_text(row["tweet"]),
                ]
                for row in extreme_rows
            ],
            "empty_message": "No sentiment annotations have been recorded up to the selected time.",
        },
    }


def _build_emotion_analytics_payload(db_path, filter_day, filter_hour):
    """Aggregate emotion statistics up to a selected simulation time."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        time_condition = _build_annotation_time_condition("r")

        distribution_rows = conn.execute(
            f"""
            SELECT
                e.emotion,
                COUNT(*) AS emotion_count
            FROM post_emotions pe
            JOIN emotions e ON e.id = pe.emotion_id
            JOIN post p ON p.id = pe.post_id
            JOIN rounds r ON r.id = p.round
            WHERE {time_condition}
            GROUP BY e.emotion
            ORDER BY emotion_count DESC, e.emotion ASC
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

        stats_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_tags,
                COUNT(DISTINCT pe.post_id) AS annotated_posts,
                COUNT(DISTINCT pe.emotion_id) AS unique_emotions
            FROM post_emotions pe
            JOIN post p ON p.id = pe.post_id
            JOIN rounds r ON r.id = p.round
            WHERE {time_condition}
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchone()

        top_emotions = [row["emotion"] for row in distribution_rows[:5]]
        placeholders = ",".join("?" for _ in top_emotions) if top_emotions else ""
        trend_rows = []
        if top_emotions:
            trend_rows = conn.execute(
                f"""
                SELECT
                    r.day AS day,
                    e.emotion,
                    COUNT(*) AS emotion_count
                FROM post_emotions pe
                JOIN emotions e ON e.id = pe.emotion_id
                JOIN post p ON p.id = pe.post_id
                JOIN rounds r ON r.id = p.round
                WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                  AND e.emotion IN ({placeholders})
                GROUP BY r.day, e.emotion
                ORDER BY r.day, e.emotion
                """,
                (filter_day, filter_day, filter_hour, *top_emotions),
            ).fetchall()

        secondary_rows = conn.execute(
            """
            SELECT
                r.day AS day,
                COUNT(*) AS emotion_tags,
                COUNT(DISTINCT pe.post_id) AS annotated_posts
            FROM post_emotions pe
            JOIN post p ON p.id = pe.post_id
            JOIN rounds r ON r.id = p.round
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            GROUP BY r.day
            ORDER BY r.day
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

    stats_row = stats_row or {}
    top_emotion = distribution_rows[0]["emotion"] if distribution_rows else "—"
    trend_by_emotion = defaultdict(dict)
    days = []
    for row in trend_rows:
        day = int(row["day"])
        if day not in days:
            days.append(day)
        trend_by_emotion[row["emotion"]][day] = int(row["emotion_count"] or 0)

    stats = [
        {
            "key": "annotated_posts",
            "label": "Annotated Posts",
            "value": _safe_int(stats_row["annotated_posts"]),
            "color": "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
        },
        {
            "key": "total_tags",
            "label": "Emotion Tags",
            "value": _safe_int(stats_row["total_tags"]),
            "color": "linear-gradient(135deg, #ec4899 0%, #db2777 100%)",
        },
        {
            "key": "top_emotion",
            "label": "Top Emotion",
            "value": top_emotion,
            "color": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
        },
        {
            "key": "current_day",
            "label": "Current Day",
            "value": f"Day {filter_day}",
            "color": "linear-gradient(135deg, #10b981 0%, #059669 100%)",
        },
        {
            "key": "current_hour",
            "label": "Current Hour",
            "value": f"Hour {filter_hour}",
            "color": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        },
    ]

    return {
        "page_title": "Emotion Statistics",
        "title": "Emotion Statistics",
        "description": "Track which emotions are being annotated in experiment content.",
        "stats": stats,
        "distribution": {
            "title": "Emotion Distribution",
            "description": "Current distribution of annotated emotions.",
            "type": "bar",
            "labels": [row["emotion"] for row in distribution_rows[:10]],
            "datasets": [
                {
                    "label": "Emotion Tags",
                    "data": [
                        int(row["emotion_count"] or 0) for row in distribution_rows[:10]
                    ],
                    "backgroundColor": "#8b5cf6",
                }
            ],
            "options": {"beginAtZero": True},
        },
        "trend": {
            "title": "Top Emotions Over Time",
            "description": "Daily counts for the most frequent emotions so far.",
            "type": "line",
            "labels": [f"Day {day}" for day in days],
            "datasets": [
                {
                    "label": emotion,
                    "data": [trend_by_emotion[emotion].get(day, 0) for day in days],
                    "tension": 0.3,
                }
                for emotion in top_emotions
            ],
            "options": {"beginAtZero": True},
        },
        "secondary": {
            "title": "Annotation Volume",
            "description": "Total emotion tags versus distinct annotated posts per day.",
            "type": "bar",
            "labels": [f"Day {int(row['day'])}" for row in secondary_rows],
            "datasets": [
                {
                    "label": "Emotion Tags",
                    "data": [_safe_int(row["emotion_tags"]) for row in secondary_rows],
                    "backgroundColor": "#c084fc",
                },
                {
                    "label": "Annotated Posts",
                    "data": [
                        _safe_int(row["annotated_posts"]) for row in secondary_rows
                    ],
                    "backgroundColor": "#60a5fa",
                },
            ],
            "options": {"beginAtZero": True},
        },
        "summary": {
            "title": "Top Emotions",
            "columns": ["Emotion", "Tags"],
            "rows": [
                [row["emotion"], _safe_int(row["emotion_count"])]
                for row in distribution_rows[:15]
            ],
            "empty_message": "No emotion annotations have been recorded up to the selected time.",
        },
    }


def _build_recsys_evolution_payload(
    db_path, filter_day, filter_hour, selected_author_uid=None
):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        table_names = {
            row["name"] if isinstance(row, sqlite3.Row) else row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        user_rows = conn.execute("""
            SELECT id, username, COALESCE(NULLIF(TRIM(recsys_type), ''), 'unknown') AS recsys_type
            FROM user_mgmt
            ORDER BY username ASC
            """).fetchall()
        usernames = {str(row["id"]): str(row["username"]) for row in user_rows}
        recsys_by_user = {
            str(row["id"]): str(row["recsys_type"] or "unknown") for row in user_rows
        }
        recommendation_rows = conn.execute(
            """
            SELECT rec.user_id, rec.post_ids, rec.round, r.day, r.hour
            FROM recommendations rec
            JOIN rounds r ON r.id = rec.round
            WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
            ORDER BY r.day ASC, r.hour ASC, rec.id ASC
            """,
            (filter_day, filter_day, filter_hour),
        ).fetchall()

        post_ids = []
        expanded_rows = []
        for row in recommendation_rows:
            receiver_uid = str(row["user_id"])
            parsed_post_ids = _parse_recommendation_post_ids(row["post_ids"])
            if not parsed_post_ids:
                continue
            post_ids.extend(parsed_post_ids)
            expanded_rows.append(
                {
                    "receiver_uid": receiver_uid,
                    "round": row["round"],
                    "day": _safe_int(row["day"]),
                    "hour": _safe_int(row["hour"]),
                    "post_ids": parsed_post_ids,
                }
            )

        unique_post_ids = sorted(set(post_ids))
        post_rows = []
        if unique_post_ids:
            placeholders = ",".join(["?"] * len(unique_post_ids))
            post_rows = conn.execute(
                f"""
                SELECT id, user_id, COALESCE(tweet, '') AS tweet
                FROM post
                WHERE id IN ({placeholders})
                """,
                tuple(unique_post_ids),
            ).fetchall()
        post_authors = {str(row["id"]): str(row["user_id"]) for row in post_rows}
        post_texts = {str(row["id"]): str(row["tweet"] or "") for row in post_rows}

        recommendation_events_by_recsys = defaultdict(int)
        recommendation_count_by_post = defaultdict(int)
        recommendation_count_by_author = defaultdict(int)
        unique_recipients_by_author = defaultdict(set)
        per_post_recipients_by_author = defaultdict(lambda: defaultdict(set))
        daily_unique_reach_by_author = defaultdict(lambda: defaultdict(set))
        daily_reach_series_by_author = {}
        daily_unique_authors_seen_by_receiver = defaultdict(lambda: defaultdict(set))

        for event in expanded_rows:
            recommendation_events_by_recsys[
                recsys_by_user.get(event["receiver_uid"], "unknown")
            ] += 1
            for post_id in event["post_ids"]:
                recommendation_count_by_post[post_id] += 1
                author_uid = post_authors.get(post_id)
                if not author_uid:
                    continue
                recommendation_count_by_author[author_uid] += 1
                unique_recipients_by_author[author_uid].add(event["receiver_uid"])
                per_post_recipients_by_author[author_uid][post_id].add(
                    event["receiver_uid"]
                )
                daily_unique_reach_by_author[author_uid][_safe_int(event["day"])].add(
                    event["receiver_uid"]
                )
                if author_uid != event["receiver_uid"]:
                    daily_unique_authors_seen_by_receiver[event["receiver_uid"]][
                        _safe_int(event["day"])
                    ].add(author_uid)

        sorted_recsys = sorted(
            recommendation_events_by_recsys.items(),
            key=lambda item: (-item[1], item[0]),
        )
        sorted_post_counts = sorted(recommendation_count_by_post.values())
        sorted_author_counts = sorted(recommendation_count_by_author.values())
        author_option_rows = sorted(
            recommendation_count_by_author.keys(),
            key=lambda uid: (
                -recommendation_count_by_author[uid],
                usernames.get(uid, str(uid)).lower(),
            ),
        )

        if (
            selected_author_uid
            and selected_author_uid not in recommendation_count_by_author
        ):
            selected_author_uid = None
        if selected_author_uid:
            selected_author_uid = str(selected_author_uid)

        distribution_counts_by_post_frequency = defaultdict(int)
        for count in recommendation_count_by_post.values():
            distribution_counts_by_post_frequency[int(count)] += 1

        def _frequency_histogram(distribution_map, value_label, color):
            keys = sorted(distribution_map.keys())
            return {
                "type": "bar",
                "labels": [str(key) for key in keys],
                "datasets": [
                    {
                        "label": value_label,
                        "data": [distribution_map[key] for key in keys],
                        "backgroundColor": color,
                        "borderRadius": 8,
                    }
                ],
                "options": {"beginAtZero": True},
            }

        selected_author_panel = {
            "available": bool(author_option_rows),
            "selected_uid": selected_author_uid,
            "selected_username": (
                usernames.get(selected_author_uid, "—") if selected_author_uid else "—"
            ),
            "options": [
                {
                    "uid": uid,
                    "username": usernames.get(uid, str(uid)),
                    "recommendation_count": recommendation_count_by_author[uid],
                    "unique_recipients": len(
                        unique_recipients_by_author.get(uid, set())
                    ),
                }
                for uid in author_option_rows[:250]
            ],
            "unique_recipients": 0,
            "total_recommendations": 0,
            "recommended_posts": 0,
            "followers_count": 0,
            "followees_count": 0,
            "reach_trend": {
                "title": "Cumulative Unique Recipients Reached",
                "description": "Select an author to inspect how many unique agents received recommendations for their posts over time.",
                "type": "line",
                "labels": [],
                "datasets": [],
                "options": {"beginAtZero": True},
            },
            "receiver_diversity_trend": {
                "title": "Unique Authors Recommended to Selected User",
                "description": "Cumulative number of distinct authors whose contents have been recommended to the selected user.",
                "type": "line",
                "labels": [],
                "datasets": [],
                "options": {"beginAtZero": True},
            },
            "post_distribution": {
                "title": "Recommendation Distribution for Selected Author",
                "description": "Per-post distribution of how often the selected author’s posts have been recommended.",
                "type": "bar",
                "labels": [],
                "datasets": [],
                "options": {"beginAtZero": True},
            },
            "summary_rows": [],
        }

        if selected_author_uid:
            distinct_days = [
                _safe_int(row["day"])
                for row in conn.execute(
                    """
                    SELECT DISTINCT day
                    FROM rounds
                    WHERE (day < ? OR (day = ? AND hour <= ?))
                    ORDER BY day ASC
                    """,
                    (filter_day, filter_day, filter_hour),
                ).fetchall()
            ]

            def _author_cumulative_reach_series(author_uid):
                author_uid = str(author_uid)
                if author_uid in daily_reach_series_by_author:
                    return daily_reach_series_by_author[author_uid]
                running_recipients = set()
                reach_series = []
                for day in distinct_days:
                    running_recipients.update(
                        daily_unique_reach_by_author.get(author_uid, {}).get(day, set())
                    )
                    reach_series.append(len(running_recipients))
                daily_reach_series_by_author[author_uid] = reach_series
                return reach_series

            reach_series = _author_cumulative_reach_series(selected_author_uid)

            followers = set()
            followees = set()
            if "follow" in table_names:
                round_column = _table_round_column(conn, "follow")
                if round_column:
                    follow_rows = conn.execute(
                        f"""
                        SELECT f.user_id, f.follower_id, COALESCE(f.action, 'follow') AS action
                        FROM follow f
                        JOIN rounds r ON r.id = f.{round_column}
                        WHERE (r.day < ? OR (r.day = ? AND r.hour <= ?))
                        ORDER BY r.day ASC, r.hour ASC, f.rowid ASC
                        """,
                        (filter_day, filter_day, filter_hour),
                    ).fetchall()
                    following_map = defaultdict(set)
                    for row in follow_rows:
                        source_uid = str(row["user_id"])
                        target_uid = str(row["follower_id"])
                        action = str(row["action"] or "follow").strip().lower()
                        if action == "follow":
                            following_map[source_uid].add(target_uid)
                        elif action == "unfollow":
                            following_map[source_uid].discard(target_uid)
                    followees = set(following_map.get(selected_author_uid, set()))
                    followers = {
                        source_uid
                        for source_uid, targets in following_map.items()
                        if selected_author_uid in targets
                    }

            def _average_series_for_authors(author_uids):
                ordered = [str(uid) for uid in sorted(set(author_uids))]
                if not ordered:
                    return []
                all_series = [_author_cumulative_reach_series(uid) for uid in ordered]
                if not all_series:
                    return []
                return [
                    round(
                        sum(series[index] for series in all_series) / len(all_series),
                        2,
                    )
                    for index in range(len(distinct_days))
                ]

            running_seen_authors = set()
            receiver_diversity_series = []
            for day in distinct_days:
                running_seen_authors.update(
                    daily_unique_authors_seen_by_receiver.get(
                        selected_author_uid, {}
                    ).get(day, set())
                )
                receiver_diversity_series.append(len(running_seen_authors))

            follower_avg_series = _average_series_for_authors(followers)
            followee_avg_series = _average_series_for_authors(followees)

            def _receiver_cumulative_diversity_series(receiver_uid):
                receiver_uid = str(receiver_uid)
                running_authors = set()
                diversity_series = []
                for day in distinct_days:
                    running_authors.update(
                        daily_unique_authors_seen_by_receiver.get(receiver_uid, {}).get(
                            day, set()
                        )
                    )
                    diversity_series.append(len(running_authors))
                return diversity_series

            def _average_receiver_diversity_series(receiver_uids):
                ordered = [str(uid) for uid in sorted(set(receiver_uids))]
                if not ordered:
                    return []
                all_series = [
                    _receiver_cumulative_diversity_series(uid) for uid in ordered
                ]
                if not all_series:
                    return []
                return [
                    round(
                        sum(series[index] for series in all_series) / len(all_series),
                        2,
                    )
                    for index in range(len(distinct_days))
                ]

            follower_receiver_diversity_avg_series = _average_receiver_diversity_series(
                followers
            )
            followee_receiver_diversity_avg_series = _average_receiver_diversity_series(
                followees
            )

            selected_post_counts = {
                post_id: recommendation_count_by_post[post_id]
                for post_id, author_uid in post_authors.items()
                if author_uid == selected_author_uid
                and recommendation_count_by_post.get(post_id, 0) > 0
            }
            kde_xs, kde_ys = _gaussian_kde_series(selected_post_counts.values())
            selected_author_panel.update(
                {
                    "selected_username": usernames.get(
                        selected_author_uid, str(selected_author_uid)
                    ),
                    "unique_recipients": len(
                        unique_recipients_by_author.get(selected_author_uid, set())
                    ),
                    "total_recommendations": recommendation_count_by_author.get(
                        selected_author_uid, 0
                    ),
                    "recommended_posts": len(selected_post_counts),
                    "followers_count": len(followers),
                    "followees_count": len(followees),
                    "reach_trend": {
                        "title": "Unique Agents Reached by Recommendations",
                        "description": "Cumulative reach of the selected author, plus the average cumulative reach of the authors following them and the authors they follow.",
                        "type": "line",
                        "labels": [f"Day {day}" for day in distinct_days],
                        "datasets": (
                            [
                                {
                                    "label": "Selected Author",
                                    "data": reach_series,
                                    "borderColor": "#2563eb",
                                    "backgroundColor": "rgba(37, 99, 235, 0.14)",
                                    "fill": True,
                                    "pointRadius": 0,
                                    "pointHoverRadius": 4,
                                    "borderWidth": 2.5,
                                    "tension": 0.28,
                                }
                            ]
                            + (
                                [
                                    {
                                        "label": "Avg. Reach of People Following This Author",
                                        "data": follower_avg_series,
                                        "borderColor": "#8b5cf6",
                                        "backgroundColor": "transparent",
                                        "fill": False,
                                        "pointRadius": 0,
                                        "pointHoverRadius": 4,
                                        "borderWidth": 2.0,
                                        "borderDash": [6, 4],
                                        "tension": 0.28,
                                    }
                                ]
                                if follower_avg_series
                                else []
                            )
                            + (
                                [
                                    {
                                        "label": "Avg. Reach of People This Author Follows",
                                        "data": followee_avg_series,
                                        "borderColor": "#10b981",
                                        "backgroundColor": "transparent",
                                        "fill": False,
                                        "pointRadius": 0,
                                        "pointHoverRadius": 4,
                                        "borderWidth": 2.0,
                                        "borderDash": [3, 3],
                                        "tension": 0.28,
                                    }
                                ]
                                if followee_avg_series
                                else []
                            )
                        ),
                        "options": {"beginAtZero": True},
                    },
                    "receiver_diversity_trend": {
                        "title": "Unique Authors Recommended to Selected User",
                        "description": "Cumulative number of distinct authors recommended to the selected user, plus the average cumulative diversity seen by the people following them and the people they follow.",
                        "type": "line",
                        "labels": [f"Day {day}" for day in distinct_days],
                        "datasets": (
                            [
                                {
                                    "label": "Selected User",
                                    "data": receiver_diversity_series,
                                    "borderColor": "#f59e0b",
                                    "backgroundColor": "rgba(245, 158, 11, 0.14)",
                                    "fill": True,
                                    "pointRadius": 0,
                                    "pointHoverRadius": 4,
                                    "borderWidth": 2.5,
                                    "tension": 0.28,
                                }
                            ]
                            + (
                                [
                                    {
                                        "label": "Avg. Diversity of People Following This Author",
                                        "data": follower_receiver_diversity_avg_series,
                                        "borderColor": "#8b5cf6",
                                        "backgroundColor": "transparent",
                                        "fill": False,
                                        "pointRadius": 0,
                                        "pointHoverRadius": 4,
                                        "borderWidth": 2.0,
                                        "borderDash": [6, 4],
                                        "tension": 0.28,
                                    }
                                ]
                                if follower_receiver_diversity_avg_series
                                else []
                            )
                            + (
                                [
                                    {
                                        "label": "Avg. Diversity of People This Author Follows",
                                        "data": followee_receiver_diversity_avg_series,
                                        "borderColor": "#10b981",
                                        "backgroundColor": "transparent",
                                        "fill": False,
                                        "pointRadius": 0,
                                        "pointHoverRadius": 4,
                                        "borderWidth": 2.0,
                                        "borderDash": [3, 3],
                                        "tension": 0.28,
                                    }
                                ]
                                if followee_receiver_diversity_avg_series
                                else []
                            )
                        ),
                        "options": {"beginAtZero": True},
                    },
                    "post_distribution": {
                        "title": "Recommendation Distribution for Selected Author",
                        "description": "Kernel density estimate of recommendation counts across the selected author’s posts.",
                        "type": "line",
                        "labels": [],
                        "datasets": [
                            {
                                "label": "Density",
                                "data": [
                                    {"x": kde_xs[index], "y": kde_ys[index]}
                                    for index in range(len(kde_xs))
                                ],
                                "borderColor": "#7c3aed",
                                "backgroundColor": "rgba(124, 58, 237, 0.14)",
                                "fill": True,
                                "pointRadius": 0,
                                "pointHoverRadius": 4,
                                "borderWidth": 2.5,
                                "tension": 0.28,
                            }
                        ],
                        "options": {
                            "beginAtZero": True,
                            "legendDisplay": False,
                            "xType": "linear",
                            "xTitle": "Recommendation Count",
                            "yTitle": "Density",
                        },
                    },
                    "summary_rows": [
                        [
                            post_id,
                            _truncate_text(post_texts.get(post_id, "")),
                            count,
                            len(
                                per_post_recipients_by_author[selected_author_uid].get(
                                    post_id, set()
                                )
                            ),
                        ]
                        for post_id, count in sorted(
                            selected_post_counts.items(),
                            key=lambda item: (-item[1], item[0]),
                        )[:25]
                    ],
                }
            )

    stats = [
        {
            "key": "recommendation_events",
            "label": "Recommendation Events",
            "value": len(expanded_rows),
            "color": "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
        },
        {
            "key": "recommended_slots",
            "label": "Recommended Slots",
            "value": sum(recommendation_count_by_post.values()),
            "color": "linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)",
        },
        {
            "key": "distinct_posts",
            "label": "Distinct Recommended Posts",
            "value": len(recommendation_count_by_post),
            "color": "linear-gradient(135deg, #10b981 0%, #059669 100%)",
        },
        {
            "key": "distinct_authors",
            "label": "Authors Reached",
            "value": len(recommendation_count_by_author),
            "color": "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        },
        {
            "key": "current_day",
            "label": "Current Day",
            "value": f"Day {filter_day}",
            "color": "linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)",
        },
        {
            "key": "current_hour",
            "label": "Current Hour",
            "value": f"Hour {filter_hour}",
            "color": "linear-gradient(135deg, #22c55e 0%, #16a34a 100%)",
        },
    ]

    summary_rows = []
    for uid in author_option_rows[:25]:
        summary_rows.append(
            [
                usernames.get(uid, str(uid)),
                recommendation_count_by_author[uid],
                len(unique_recipients_by_author.get(uid, set())),
                len(
                    {
                        post_id
                        for post_id, author_uid in post_authors.items()
                        if author_uid == uid
                        and recommendation_count_by_post.get(post_id, 0) > 0
                    }
                ),
                recsys_by_user.get(uid, "unknown"),
            ]
        )

    return {
        "page_title": "Recommendation System Evolution",
        "title": "Recommendation System Evolution",
        "description": "Analyze how content recommendation exposure is distributed across posts, authors, and recommender configurations.",
        "stats": stats,
        "distribution": {
            "title": "Content Recsys Used",
            "description": "Number of recommendation events served to receivers grouped by their configured content recommender.",
            "type": "bar",
            "labels": [item[0] for item in sorted_recsys],
            "datasets": [
                {
                    "label": "Recommendation Events",
                    "data": [item[1] for item in sorted_recsys],
                    "backgroundColor": "#2563eb",
                    "borderRadius": 8,
                }
            ],
            "options": {"beginAtZero": True},
        },
        "trend": {
            "title": "Distribution of Content Recommendation Counts",
            "description": "Histogram of how many times individual posts have been recommended.",
            **_frequency_histogram(
                distribution_counts_by_post_frequency,
                "Posts",
                "#8b5cf6",
            ),
        },
        "secondary": {
            "title": "Distribution of Author Recommendation Counts",
            "description": "Each bar is one author, and its height is the total number of times that author’s posts appeared in recommendation sets.",
            "type": "bar",
            "labels": [usernames.get(uid, str(uid)) for uid in author_option_rows[:25]],
            "datasets": [
                {
                    "label": "Recommendation Appearances",
                    "data": [
                        recommendation_count_by_author[uid]
                        for uid in author_option_rows[:25]
                    ],
                    "backgroundColor": "#10b981",
                    "borderRadius": 8,
                    "maxBarThickness": 28,
                }
            ],
            "options": {"beginAtZero": True, "legendDisplay": False},
        },
        "summary": {
            "title": "Most Reached Authors",
            "columns": [
                "Author",
                "Total Recommendations",
                "Unique Recipients",
                "Recommended Posts",
                "Own Recsys",
            ],
            "rows": summary_rows,
            "empty_message": "No recommendation events have been recorded up to the selected time.",
        },
        "recsys_author": selected_author_panel,
    }


_ANNOTATION_ANALYTICS_REGISTRY = {
    "toxicity": {
        "label": "toxicity",
        "title": "Toxicity Evolution",
        "required_tables": {"post_toxicity", "post", "rounds"},
        "builder": _build_toxicity_analytics_payload,
    },
    "sentiment": {
        "label": "sentiment",
        "title": "Sentiment Evolution",
        "required_tables": {"post_sentiment", "rounds"},
        "builder": _build_sentiment_analytics_payload,
    },
    "emotion": {
        "label": "emotion",
        "title": "Emotion Statistics",
        "required_tables": {"post_emotions", "emotions", "post", "rounds"},
        "builder": _build_emotion_analytics_payload,
    },
}


def _render_annotation_analytics_page(expid, annotation_key):
    config = _ANNOTATION_ANALYTICS_REGISTRY[annotation_key]
    experiment, db_path, error_response = _load_annotation_experiment_context(
        expid, annotation_key, config["label"], require_manage=False
    )
    if error_response is not None:
        return error_response

    if not _experiment_db_has_required_tables(db_path, config["required_tables"]):
        flash(
            f"The current experiment database does not contain {config['title'].lower()} tables.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=expid))

    max_day, max_hour = _get_annotation_max_round(db_path)
    filter_day = request.args.get("day", type=int, default=max_day)
    filter_hour = request.args.get("hour", type=int, default=max_hour)
    threshold = request.args.get("threshold", type=float, default=0.1)
    selected_target_uid = str(request.args.get("target_uid", "") or "").strip() or None
    if annotation_key == "toxicity":
        threshold = max(0.0, min(1.0, threshold))
        analytics = config["builder"](
            db_path,
            filter_day,
            filter_hour,
            threshold,
            selected_target_uid=selected_target_uid,
        )
    else:
        analytics = config["builder"](db_path, filter_day, filter_hour)

    return render_template(
        "admin/annotation_analytics.html",
        experiment=experiment,
        page_key=annotation_key,
        page_title=config["title"],
        max_day=max_day,
        max_hour=max_hour,
        filter_day=filter_day,
        filter_hour=filter_hour,
        threshold=threshold,
        analytics=analytics,
        data_url=url_for(f"experiments.{annotation_key}_analytics_data", expid=expid),
    )


def _annotation_analytics_json(expid, annotation_key):
    config = _ANNOTATION_ANALYTICS_REGISTRY[annotation_key]
    experiment, db_path, error_response = _load_annotation_experiment_context(
        expid, annotation_key, config["label"], require_manage=False
    )
    if error_response is not None:
        return jsonify({"error": f"{config['title']} not available"}), 400

    if not _experiment_db_has_required_tables(db_path, config["required_tables"]):
        return jsonify({"error": f"{config['title']} tables not available"}), 400

    filter_day = request.args.get("day", type=int, default=1)
    filter_hour = request.args.get("hour", type=int, default=1)
    threshold = request.args.get("threshold", type=float, default=0.1)
    selected_target_uid = str(request.args.get("target_uid", "") or "").strip() or None
    if annotation_key == "toxicity":
        threshold = max(0.0, min(1.0, threshold))
        analytics = config["builder"](
            db_path,
            filter_day,
            filter_hour,
            threshold,
            selected_target_uid=selected_target_uid,
        )
    else:
        analytics = config["builder"](db_path, filter_day, filter_hour)
    return jsonify(
        {
            "filter_day": filter_day,
            "filter_hour": filter_hour,
            "threshold": threshold,
            "analytics": analytics,
        }
    )


@experiments.route("/admin/toxicity_evolution/<int:expid>")
@login_required
def toxicity_evolution(expid):
    return _render_annotation_analytics_page(expid, "toxicity")


@experiments.route("/admin/toxicity_evolution_data/<int:expid>")
@login_required
def toxicity_analytics_data(expid):
    return _annotation_analytics_json(expid, "toxicity")


@experiments.route("/admin/sentiment_evolution/<int:expid>")
@login_required
def sentiment_evolution(expid):
    return _render_annotation_analytics_page(expid, "sentiment")


@experiments.route("/admin/sentiment_evolution_data/<int:expid>")
@login_required
def sentiment_analytics_data(expid):
    return _annotation_analytics_json(expid, "sentiment")


@experiments.route("/admin/emotion_statistics/<int:expid>")
@login_required
def emotion_statistics(expid):
    return _render_annotation_analytics_page(expid, "emotion")


@experiments.route("/admin/emotion_statistics_data/<int:expid>")
@login_required
def emotion_analytics_data(expid):
    return _annotation_analytics_json(expid, "emotion")


def emotion_statistics_data(expid):
    return emotion_analytics_data(expid)


@experiments.route("/admin/topic_evolution/<int:expid>")
@login_required
def topic_evolution(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return error_response

    required_tables = {"post_topics", "post", "rounds", "user_mgmt"}
    if not _experiment_db_has_required_tables(db_path, required_tables):
        flash(
            "The current experiment database does not contain topic-evolution tables.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=expid))

    max_day, max_hour = _get_annotation_max_round(db_path)
    filter_day = request.args.get("day", type=int, default=max_day)
    filter_hour = request.args.get("hour", type=int, default=max_hour)
    trend_mode = str(request.args.get("trend_mode", "daily") or "").strip().lower()
    selected_topic_ids = [
        str(topic_id)
        for topic_id in request.args.getlist("topic_ids")
        if str(topic_id).strip()
    ]
    analytics = _build_topic_evolution_payload(
        expid,
        db_path,
        filter_day,
        filter_hour,
        selected_topic_ids=selected_topic_ids,
        trend_mode=trend_mode,
    )

    return render_template(
        "admin/annotation_analytics.html",
        experiment=experiment,
        page_key="topic",
        page_title="Topic Evolution",
        max_day=max_day,
        max_hour=max_hour,
        filter_day=filter_day,
        filter_hour=filter_hour,
        threshold=0.1,
        analytics=analytics,
        data_url=url_for("experiments.topic_evolution_data", expid=expid),
    )


@experiments.route("/admin/topic_evolution_data/<int:expid>")
@login_required
def topic_evolution_data(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return jsonify({"error": "Topic evolution not available"}), 400

    required_tables = {"post_topics", "post", "rounds", "user_mgmt"}
    if not _experiment_db_has_required_tables(db_path, required_tables):
        return jsonify({"error": "Topic-evolution tables not available"}), 400

    filter_day = request.args.get("day", type=int, default=1)
    filter_hour = request.args.get("hour", type=int, default=1)
    trend_mode = str(request.args.get("trend_mode", "daily") or "").strip().lower()
    selected_topic_ids = [
        str(topic_id)
        for topic_id in request.args.getlist("topic_ids")
        if str(topic_id).strip()
    ]
    analytics = _build_topic_evolution_payload(
        expid,
        db_path,
        filter_day,
        filter_hour,
        selected_topic_ids=selected_topic_ids,
        trend_mode=trend_mode,
    )
    return jsonify(
        {
            "filter_day": filter_day,
            "filter_hour": filter_hour,
            "threshold": 0.1,
            "analytics": analytics,
        }
    )


@experiments.route("/admin/hashtag_evolution/<int:expid>")
@login_required
def hashtag_evolution(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return error_response

    required_tables = {"post_hashtags", "hashtags", "post", "rounds", "user_mgmt"}
    if not _experiment_db_has_required_tables(db_path, required_tables):
        flash(
            "The current experiment database does not contain hashtag-evolution tables.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=expid))

    max_day, max_hour = _get_annotation_max_round(db_path)
    filter_day = request.args.get("day", type=int, default=max_day)
    filter_hour = request.args.get("hour", type=int, default=max_hour)
    trend_mode = str(request.args.get("trend_mode", "daily") or "").strip().lower()
    selected_hashtag_ids = [
        str(hashtag_id)
        for hashtag_id in request.args.getlist("topic_ids")
        if str(hashtag_id).strip()
    ]
    analytics = _build_hashtag_evolution_payload(
        db_path,
        filter_day,
        filter_hour,
        selected_hashtag_ids=selected_hashtag_ids,
        trend_mode=trend_mode,
    )

    return render_template(
        "admin/annotation_analytics.html",
        experiment=experiment,
        page_key="hashtag",
        page_title="Hashtag Evolution",
        max_day=max_day,
        max_hour=max_hour,
        filter_day=filter_day,
        filter_hour=filter_hour,
        threshold=0.1,
        analytics=analytics,
        data_url=url_for("experiments.hashtag_evolution_data", expid=expid),
    )


@experiments.route("/admin/hashtag_evolution_data/<int:expid>")
@login_required
def hashtag_evolution_data(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return jsonify({"error": "Hashtag evolution not available"}), 400

    required_tables = {"post_hashtags", "hashtags", "post", "rounds", "user_mgmt"}
    if not _experiment_db_has_required_tables(db_path, required_tables):
        return jsonify({"error": "Hashtag-evolution tables not available"}), 400

    filter_day = request.args.get("day", type=int, default=1)
    filter_hour = request.args.get("hour", type=int, default=1)
    trend_mode = str(request.args.get("trend_mode", "daily") or "").strip().lower()
    selected_hashtag_ids = [
        str(hashtag_id)
        for hashtag_id in request.args.getlist("topic_ids")
        if str(hashtag_id).strip()
    ]
    analytics = _build_hashtag_evolution_payload(
        db_path,
        filter_day,
        filter_hour,
        selected_hashtag_ids=selected_hashtag_ids,
        trend_mode=trend_mode,
    )
    return jsonify(
        {
            "filter_day": filter_day,
            "filter_hour": filter_hour,
            "threshold": 0.1,
            "analytics": analytics,
        }
    )


@experiments.route("/admin/recsys_evolution/<int:expid>")
@login_required
def recsys_evolution(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return error_response

    required_tables = {"recommendations", "post", "rounds", "user_mgmt"}
    if not _experiment_db_has_required_tables(db_path, required_tables):
        flash(
            "The current experiment database does not contain recommendation-tracking tables.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=expid))

    max_day, max_hour = _get_annotation_max_round(db_path)
    filter_day = request.args.get("day", type=int, default=max_day)
    filter_hour = request.args.get("hour", type=int, default=max_hour)
    selected_author_uid = str(request.args.get("target_uid", "") or "").strip() or None
    analytics = _build_recsys_evolution_payload(
        db_path,
        filter_day,
        filter_hour,
        selected_author_uid=selected_author_uid,
    )

    return render_template(
        "admin/annotation_analytics.html",
        experiment=experiment,
        page_key="recsys",
        page_title="Recommendation System Evolution",
        max_day=max_day,
        max_hour=max_hour,
        filter_day=filter_day,
        filter_hour=filter_hour,
        threshold=0.1,
        analytics=analytics,
        data_url=url_for("experiments.recsys_evolution_data", expid=expid),
    )


@experiments.route("/admin/recsys_evolution_data/<int:expid>")
@login_required
def recsys_evolution_data(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return jsonify({"error": "Recommendation analytics not available"}), 400

    required_tables = {"recommendations", "post", "rounds", "user_mgmt"}
    if not _experiment_db_has_required_tables(db_path, required_tables):
        return jsonify({"error": "Recommendation-tracking tables not available"}), 400

    filter_day = request.args.get("day", type=int, default=1)
    filter_hour = request.args.get("hour", type=int, default=1)
    selected_author_uid = str(request.args.get("target_uid", "") or "").strip() or None
    analytics = _build_recsys_evolution_payload(
        db_path,
        filter_day,
        filter_hour,
        selected_author_uid=selected_author_uid,
    )
    return jsonify(
        {
            "filter_day": filter_day,
            "filter_hour": filter_hour,
            "threshold": 0.1,
            "analytics": analytics,
        }
    )


@experiments.route("/admin/network_analysis/<int:expid>")
@login_required
def network_analysis(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return error_response

    required_tables = {"rounds", "user_mgmt"}
    available_network_types = _available_network_analysis_types(db_path)
    if (not _experiment_db_has_required_tables(db_path, required_tables)) or (
        not available_network_types
    ):
        flash(
            "The current experiment database does not contain supported network-analysis tables.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=expid))

    max_day, max_hour = _get_annotation_max_round(db_path)
    filter_day = request.args.get("day", type=int, default=max_day)
    filter_hour = request.args.get("hour", type=int, default=max_hour)
    selected_uid = str(request.args.get("target_uid", "") or "").strip() or None
    network_type = (
        str(request.args.get("network_type", available_network_types[0]) or "")
        .strip()
        .lower()
    )
    granularity = str(request.args.get("granularity", "day") or "").strip().lower()
    if network_type not in available_network_types:
        network_type = available_network_types[0]
    if granularity not in {"day", "hour"}:
        granularity = "day"
    analytics = _build_network_analytics_payload(
        db_path,
        filter_day,
        filter_hour,
        selected_uid=selected_uid,
        network_type=network_type,
        granularity=granularity,
    )
    analytics["network_type_options"] = [
        option
        for option in analytics.get("network_type_options", [])
        if option["value"] in available_network_types
    ]

    return render_template(
        "admin/annotation_analytics.html",
        experiment=experiment,
        page_key="network",
        page_title="Network Analysis",
        max_day=max_day,
        max_hour=max_hour,
        filter_day=filter_day,
        filter_hour=filter_hour,
        threshold=0.1,
        analytics=analytics,
        data_url=url_for("experiments.network_analysis_data", expid=expid),
    )


@experiments.route("/admin/network_analysis_data/<int:expid>")
@login_required
def network_analysis_data(expid):
    experiment, db_path, error_response = _load_network_experiment_context(
        expid, require_manage=False
    )
    if error_response is not None:
        return jsonify({"error": "Network analysis not available"}), 400

    required_tables = {"rounds", "user_mgmt"}
    available_network_types = _available_network_analysis_types(db_path)
    if (not _experiment_db_has_required_tables(db_path, required_tables)) or (
        not available_network_types
    ):
        return jsonify({"error": "Network-analysis tables not available"}), 400

    filter_day = request.args.get("day", type=int, default=1)
    filter_hour = request.args.get("hour", type=int, default=1)
    selected_uid = str(request.args.get("target_uid", "") or "").strip() or None
    network_type = (
        str(request.args.get("network_type", available_network_types[0]) or "")
        .strip()
        .lower()
    )
    granularity = str(request.args.get("granularity", "day") or "").strip().lower()
    if network_type not in available_network_types:
        network_type = available_network_types[0]
    if granularity not in {"day", "hour"}:
        granularity = "day"
    analytics = _build_network_analytics_payload(
        db_path,
        filter_day,
        filter_hour,
        selected_uid=selected_uid,
        network_type=network_type,
        granularity=granularity,
    )
    analytics["network_type_options"] = [
        option
        for option in analytics.get("network_type_options", [])
        if option["value"] in available_network_types
    ]
    return jsonify(
        {
            "filter_day": filter_day,
            "filter_hour": filter_hour,
            "threshold": 0.1,
            "analytics": analytics,
        }
    )
