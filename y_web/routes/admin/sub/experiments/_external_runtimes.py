"""Admin panel for managing external runtime repositories."""

from __future__ import annotations

import sys

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from y_web.src.external_runtime import (
    ExternalRuntimeError,
    clone_runtime_repo,
    delete_runtime_repo,
    fetch_runtime_repo,
    get_grouped_runtime_status,
    log_external_runtime_action,
    read_external_runtime_logs,
    runtime_spec,
    update_runtime_repo,
    install_runtime_dependencies,
    validate_runtime_repo,
)
from y_web.src.models import Admin_users, Exps
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import experiments

_MUTATING_ACTIONS = {"clone", "fetch", "update", "install", "validate", "delete"}


def _require_admin_user():
    check_privileges(current_user.username)
    admin_user = Admin_users.query.filter_by(username=current_user.username).first()
    if admin_user is None or admin_user.role != "admin":
        flash("Only administrators can manage external runtime repositories.", "error")
        return None
    return admin_user


def _runtime_group_active_experiments(group_key: str) -> list[Exps]:
    base_query = Exps.query.filter(Exps.is_remote == 0)
    if group_key == "microblogging":
        query = base_query.filter(Exps.platform_type == "microblogging", Exps.simulator_type != "HPC")
    elif group_key == "forum":
        query = base_query.filter(Exps.platform_type == "forum")
    elif group_key == "hpc":
        query = base_query.filter(Exps.simulator_type == "HPC")
    else:
        return []
    return query.filter((Exps.running == 1) | (Exps.exp_status == "active")).all()


@experiments.route("/admin/external_runtimes")
@login_required
def external_runtimes():
    admin_user = _require_admin_user()
    if admin_user is None:
        return redirect(url_for("experiments.settings"))

    grouped_status = get_grouped_runtime_status()
    active_group_usage = {
        group_info["group"]: _runtime_group_active_experiments(group_info["group"])
        for group_info in grouped_status
    }
    recent_logs = read_external_runtime_logs(limit=120)
    return render_template(
        "admin/external_runtimes.html",
        grouped_runtime_status=grouped_status,
        active_group_usage=active_group_usage,
        current_python_executable=sys.executable,
        recent_runtime_logs=recent_logs,
    )


@experiments.route("/admin/external_runtimes/<repo_key>/<action>", methods=["POST"])
@login_required
def external_runtime_action(repo_key: str, action: str):
    admin_user = _require_admin_user()
    if admin_user is None:
        return redirect(url_for("experiments.settings"))

    if action not in _MUTATING_ACTIONS:
        flash("Unsupported runtime action.", "error")
        return redirect(url_for("experiments.external_runtimes"))

    try:
        spec = runtime_spec(repo_key)
    except KeyError:
        flash("Unknown external runtime repository.", "error")
        return redirect(url_for("experiments.external_runtimes"))

    branch = (request.form.get("branch") or spec.default_branch).strip()
    if action in {"clone", "fetch", "update", "install", "delete"}:
        active_experiments = _runtime_group_active_experiments(spec.group)
        if active_experiments:
            names = ", ".join(exp.exp_name for exp in active_experiments[:3])
            extra = "" if len(active_experiments) <= 3 else f" and {len(active_experiments) - 3} more"
            flash(
                f"Stop active {spec.group_label.lower()} experiments before modifying {spec.label}: {names}{extra}.",
                "error",
            )
            return redirect(url_for("experiments.external_runtimes"))

    try:
        if action == "clone":
            clone_runtime_repo(repo_key, branch, admin_user.username)
            flash(f"Cloned {spec.label} on branch {branch}.", "success")
        elif action == "fetch":
            fetch_runtime_repo(repo_key, branch, admin_user.username)
            flash(f"Fetched {spec.label} from branch {branch}.", "success")
        elif action == "update":
            update_runtime_repo(repo_key, branch, admin_user.username)
            flash(f"Updated {spec.label} to branch {branch}.", "success")
        elif action == "install":
            install_runtime_dependencies(repo_key, admin_user.username)
            flash(f"Installed dependencies for {spec.label}.", "success")
        elif action == "validate":
            validate_runtime_repo(repo_key, admin_user.username)
            flash(f"Validated {spec.label}.", "success")
        elif action == "delete":
            delete_runtime_repo(repo_key, admin_user.username)
            flash(f"Deleted {spec.label}.", "success")
    except ExternalRuntimeError as exc:
        log_external_runtime_action(repo_key, action, admin_user.username, branch, False, str(exc))
        flash(str(exc), "error")

    return redirect(url_for("experiments.external_runtimes"))


@experiments.route("/admin/external_runtimes/<repo_key>/logs")
@login_required
def external_runtime_logs(repo_key: str):
    admin_user = _require_admin_user()
    if admin_user is None:
        return redirect(url_for("experiments.settings"))

    try:
        spec = runtime_spec(repo_key)
    except KeyError:
        flash("Unknown external runtime repository.", "error")
        return redirect(url_for("experiments.external_runtimes"))

    return render_template(
        "admin/external_runtime_logs.html",
        runtime_repo=spec,
        runtime_logs=read_external_runtime_logs(limit=250, repo_key=repo_key),
    )
