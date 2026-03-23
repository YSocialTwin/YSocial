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
    experiments,
    OPINION_CACHE_EXPIRY_MINUTES,
    MAX_HPC_PER_GROUP,
    DEFAULT_FEED_LIMITS,
    DEFAULT_EXPERIMENT_EMBEDDING_SETTINGS,
    DEFAULT_FORUM_EMBEDDING_SETTINGS,
    DEFAULT_FORUM_AVATAR_SETTINGS,
    FORUM_FEED_REQUEST_HEADERS,
    _schedule_check_lock,
    _EXP_IDS_MARKER_RE,
)
from ._helpers import *  # noqa: F401,F403
from ._helpers import (
    _current_admin_user,
    _inject_related_experiment_ids,
    _is_path_in_temp_data,
    _notifications_temp_data_dir,
    _sanitize_filename,
    _serialize_download_notification,
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
    from y_web.src.system.path_utils import get_writable_path

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
    from y_web.src.system.path_utils import get_writable_path

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


