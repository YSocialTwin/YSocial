"""Admin panel for managing external runtime repositories."""

from __future__ import annotations

import re
import sys

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from y_web.src.external_runtime import (
    ExternalRuntimeError,
    clone_runtime_repo,
    delete_runtime_repo,
    download_runtime_release,
    fetch_runtime_repo,
    get_grouped_runtime_status,
    install_runtime_dependencies,
    load_plugins_index,
    log_external_runtime_action,
    plugin_metadata_for_runtime,
    read_external_runtime_logs,
    runtime_spec,
    runtime_visible_to_user,
    update_runtime_repo,
    validate_runtime_repo,
)
from y_web.src.models import Admin_users, Exps
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import experiments

_MUTATING_ACTIONS = {
    "acquire",
    "download_release",
    "clone",
    "fetch",
    "update",
    "install",
    "validate",
    "delete",
}
_GITHUB_TOKEN_SESSION_KEY = "external_runtime_github_token"


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
        query = base_query.filter(
            Exps.platform_type == "microblogging", Exps.simulator_type != "HPC"
        )
    elif group_key == "forum":
        query = base_query.filter(Exps.platform_type == "forum")
    elif group_key == "hpc":
        query = base_query.filter(Exps.simulator_type == "HPC")
    elif group_key == "agent_plugins":
        return []
    else:
        return []
    return query.filter((Exps.running == 1) | (Exps.exp_status == "active")).all()


def _session_github_token() -> str | None:
    token = (session.get(_GITHUB_TOKEN_SESSION_KEY) or "").strip()
    return token or None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return slug or "group"


def _visible_runtime_groups(admin_user, github_token: str | None):
    plugins_index = load_plugins_index(refresh=True)
    all_groups = get_grouped_runtime_status(github_token=github_token)
    visible_groups = []
    for group_info in all_groups:
        repos = []
        for repo in group_info["repos"]:
            spec = runtime_spec(repo["key"])
            if runtime_visible_to_user(spec, admin_user):
                repo = dict(repo)
                plugin_metadata = plugin_metadata_for_runtime(spec, plugins_index)
                if plugin_metadata:
                    repo["label"] = plugin_metadata.get("plugin_name") or repo["label"]
                    repo["plugin_metadata"] = plugin_metadata
                    repo["plugin_name"] = (
                        plugin_metadata.get("plugin_name") or repo["label"]
                    )
                    repo["plugin_category_label"] = (
                        plugin_metadata.get("category") or repo["category_label"]
                    )
                    repo["plugin_group_label"] = (
                        plugin_metadata.get("group") or repo["group_label"]
                    )
                    repo["plugin_description"] = (
                        plugin_metadata.get("description") or ""
                    )
                    repo["plugin_authors"] = plugin_metadata.get("authors") or []
                    repo["plugin_repository_url"] = (
                        plugin_metadata.get("repository_url") or repo["repo_url"]
                    )
                else:
                    repo["plugin_name"] = repo["label"]
                    repo["plugin_category_label"] = repo["category_label"]
                    repo["plugin_group_label"] = repo["group_label"]
                    repo["plugin_description"] = ""
                    repo["plugin_authors"] = []
                    repo["plugin_repository_url"] = repo["repo_url"]
                repos.append(repo)
        if repos:
            visible_groups.append(
                {
                    "group": group_info["group"],
                    "label": group_info["label"],
                    "repos": repos,
                }
            )
    return visible_groups


def _runtime_categories(grouped_status, active_group_usage):
    all_repos = [repo for group_info in grouped_status for repo in group_info["repos"]]
    categories = []
    plugin_category_map: dict[str, dict] = {}
    for repo in all_repos:
        category_label = repo.get("plugin_category_label") or "Agent Extensions"
        group_label = repo.get("plugin_group_label") or "Agent Plugins"
        category_key = _slugify(str(category_label))
        group_key = _slugify(str(group_label))

        category_entry = plugin_category_map.setdefault(
            category_key,
            {
                "key": category_key,
                "label": category_label,
                "description": f"Repositories classified under {category_label}.",
                "groups": {},
            },
        )
        group_entry = category_entry["groups"].setdefault(
            group_key,
            {
                "group": group_key,
                "label": group_label,
                "description": f"Repositories grouped as {group_label}.",
                "repos": [],
                "active_experiments": [],
            },
        )
        group_entry["repos"].append(repo)
        runtime_group = repo.get("group")
        for experiment in active_group_usage.get(runtime_group, []):
            if experiment not in group_entry["active_experiments"]:
                group_entry["active_experiments"].append(experiment)

    for category_entry in plugin_category_map.values():
        groups = list(category_entry["groups"].values())
        repo_count = sum(len(group_info["repos"]) for group_info in groups)
        installed_count = sum(
            1
            for group_info in groups
            for repo in group_info["repos"]
            if repo.get("installed")
        )
        categories.append(
            {
                "key": category_entry["key"],
                "label": category_entry["label"],
                "description": category_entry["description"],
                "groups": groups,
                "repo_count": repo_count,
                "installed_count": installed_count,
                "active_experiment_count": sum(
                    len(group_info["active_experiments"]) for group_info in groups
                ),
            }
        )
    return categories


@experiments.route("/admin/external_runtimes")
@login_required
def external_runtimes():
    admin_user = _require_admin_user()
    if admin_user is None:
        return redirect(url_for("experiments.settings"))

    github_token = _session_github_token()
    grouped_status = _visible_runtime_groups(admin_user, github_token)
    active_group_usage = {
        group_info["group"]: _runtime_group_active_experiments(group_info["group"])
        for group_info in grouped_status
    }
    runtime_categories = _runtime_categories(grouped_status, active_group_usage)
    recent_logs = read_external_runtime_logs(limit=120)
    selected_repo_key = (request.args.get("repo_key") or "").strip()
    selected_repo_logs = read_external_runtime_logs(
        limit=30, repo_key=selected_repo_key or None
    )
    return render_template(
        "admin/external_runtimes.html",
        grouped_runtime_status=grouped_status,
        runtime_categories=runtime_categories,
        active_group_usage=active_group_usage,
        current_python_executable=sys.executable,
        recent_runtime_logs=recent_logs,
        selected_repo_key=selected_repo_key,
        selected_repo_logs=selected_repo_logs,
        github_session_authenticated=bool(github_token),
    )


@experiments.route("/admin/external_runtimes/github_session", methods=["POST"])
@login_required
def external_runtime_github_session():
    admin_user = _require_admin_user()
    if admin_user is None:
        return redirect(url_for("experiments.settings"))

    action = (request.form.get("github_session_action") or "").strip().lower()
    if action == "connect":
        token = (request.form.get("github_token") or "").strip()
        if not token:
            flash("Provide a GitHub token before connecting.", "error")
        else:
            session[_GITHUB_TOKEN_SESSION_KEY] = token
            flash("GitHub session enabled for plugin release access.", "success")
    elif action == "disconnect":
        session.pop(_GITHUB_TOKEN_SESSION_KEY, None)
        flash("GitHub session cleared.", "success")
    else:
        flash("Unsupported GitHub session action.", "error")

    return redirect(url_for("experiments.external_runtimes"))


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

    if not runtime_visible_to_user(spec, admin_user):
        flash("You do not have visibility on this plugin repository.", "error")
        return redirect(url_for("experiments.external_runtimes"))

    github_token = _session_github_token()
    branch = (request.form.get("branch") or spec.default_branch).strip()
    release_tag = (request.form.get("release_tag") or "").strip() or None
    install_source = (request.form.get("install_source") or "release").strip().lower()
    if action in {
        "acquire",
        "download_release",
        "clone",
        "fetch",
        "update",
        "install",
        "delete",
    }:
        active_experiments = _runtime_group_active_experiments(spec.group)
        if active_experiments:
            names = ", ".join(exp.exp_name for exp in active_experiments[:3])
            extra = (
                ""
                if len(active_experiments) <= 3
                else f" and {len(active_experiments) - 3} more"
            )
            flash(
                f"Stop active {spec.group_label.lower()} experiments before modifying {spec.label}: {names}{extra}.",
                "error",
            )
            return redirect(url_for("experiments.external_runtimes", repo_key=repo_key))

    try:
        if action == "acquire":
            if install_source == "git":
                clone_runtime_repo(repo_key, branch, admin_user.username)
                flash(f"Cloned {spec.label} on branch {branch}.", "success")
            else:
                download_runtime_release(
                    repo_key,
                    release_tag,
                    admin_user.username,
                    github_token=github_token,
                )
                flash(
                    f"Installed {spec.label} from GitHub release {release_tag or 'latest available release'}.",
                    "success",
                )
        elif action == "download_release":
            download_runtime_release(
                repo_key,
                release_tag,
                admin_user.username,
                github_token=github_token,
            )
            flash(
                f"Installed {spec.label} from GitHub release {release_tag or 'latest available release'}.",
                "success",
            )
        elif action == "clone":
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
        log_external_runtime_action(
            repo_key,
            action,
            admin_user.username,
            release_tag or branch,
            False,
            str(exc),
        )
        flash(str(exc), "error")

    return redirect(url_for("experiments.external_runtimes", repo_key=repo_key))


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

    if not runtime_visible_to_user(spec, admin_user):
        flash("You do not have visibility on this plugin repository.", "error")
        return redirect(url_for("experiments.external_runtimes"))

    return render_template(
        "admin/external_runtime_logs.html",
        runtime_repo=spec,
        runtime_logs=read_external_runtime_logs(limit=250, repo_key=repo_key),
    )
