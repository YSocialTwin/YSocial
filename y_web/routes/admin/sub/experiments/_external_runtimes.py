"""Admin panel for managing external runtime repositories."""

from __future__ import annotations

import re
import sys

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.src.external_runtime import (
    ExternalRuntimeError,
    clone_runtime_repo,
    delete_runtime_repo,
    download_runtime_release,
    fetch_runtime_repo,
    get_grouped_runtime_status,
    get_runtime_status,
    host_git_available,
    install_runtime_dependencies,
    load_plugins_index,
    log_external_runtime_action,
    plugin_metadata_for_runtime,
    read_external_runtime_logs,
    resolve_python_executable,
    runtime_spec,
    runtime_visible_to_user,
    update_runtime_repo,
    validate_runtime_repo,
)
from y_web.src.external_runtime.frontend_plugins import validate_frontend_suite
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
    "enable",
    "disable",
    "sync",
}

# Plugins shown as ONE entry in the plugin list: a server and a client, each installed/updated/removed independently
# from the entry's page. Acting on the entry key itself (the list's Remove) applies to both (server first).
_PAIRED_ENTRIES = {
    "microblogging": {
        "label": "Microblogging",
        "members": ("microblogging_server", "microblogging_client"),
        "description": "Microblogging simulator (timeline, posts, follows). Server and client are installed and updated independently from its page.",
    },
    "forum": {
        "label": "Forum",
        "members": ("forum_server", "forum_client"),
        "description": "Forum simulator (threads and replies). Server and client are installed and updated independently from its page.",
    },
}
_PAIR_OF_MEMBER = {m: k for k, v in _PAIRED_ENTRIES.items() for m in v["members"]}
_GITHUB_TOKEN_SESSION_KEY = "external_runtime_github_token"


def _require_admin_user():
    check_privileges(current_user.username)
    admin_user = db.session.scalars(
        select(Admin_users).filter_by(username=current_user.username)
    ).first()
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
    elif group_key == "photo_sharing":
        query = base_query.filter(Exps.platform_type == "photo_sharing")
    elif group_key == "forum":
        query = base_query.filter(Exps.platform_type == "forum")
    elif group_key == "hpc":
        query = base_query.filter(Exps.simulator_type == "HPC")
    elif group_key == "agent_plugins":
        return []
    elif group_key == "frontend_plugins":
        # Frontend plugin suites (e.g. Frontend Adds-on) are UI-only extensions; they
        # are never tied to a running simulation, so mutating actions on them
        # are never blocked by "active experiment" checks.
        return []
    else:
        return []
    return query.filter((Exps.running == 1) | (Exps.exp_status == "active")).all()


def _run_suite_schema_migration(repo_key: str) -> None:
    """After an installation, create the plugin's own tables (best effort)."""
    from flask import current_app

    from y_web.src.external_runtime.backend_plugins import (
        run_backend_plugin_schema_migrations,
    )

    outcome = run_backend_plugin_schema_migrations(current_app, [repo_key]).get(
        repo_key
    )
    if outcome and outcome.get("error"):
        flash(f"Schema migration failed: {outcome['error']}", "error")


def _toggle_plugin(repo_key: str, spec, admin_user, enabled: bool):
    """Enable/disable an installed backend-settings suite (E6)."""
    from y_web.src.external_runtime.backend_plugins import (
        set_plugin_enabled,
        suite_restart_required,
    )

    if spec.group != "backend_settings" or not spec.path.exists():
        flash("Only installed backend plugins can be enabled or disabled.", "error")
        return _external_runtimes_response(
            repo_key=repo_key, status="error", message="Not supported."
        )
    set_plugin_enabled(repo_key, enabled, admin_user.username)
    if enabled and suite_restart_required(repo_key):
        flash(
            f"{spec.label} enabled. Restart required: its routes are loaded at startup.",
            "warning",
        )
    else:
        flash(f"{spec.label} {'enabled' if enabled else 'disabled'}.", "success")
    return _external_runtimes_response(
        repo_key=repo_key,
        message=f"{spec.label} {'enabled' if enabled else 'disabled'}.",
    )


def _session_github_token() -> str | None:
    token = (session.get(_GITHUB_TOKEN_SESSION_KEY) or "").strip()
    return token or None


def _wants_json_response() -> bool:
    accept = (request.headers.get("Accept") or "").lower()
    requested_with = (request.headers.get("X-Requested-With") or "").lower()
    return "application/json" in accept or requested_with == "xmlhttprequest"


def _external_runtimes_response(
    *,
    repo_key: str | None = None,
    status: str = "ok",
    message: str = "",
    preserve_repo_key: bool = True,
):
    refresh_url = "/admin/external_runtimes"
    if repo_key and preserve_repo_key:
        refresh_url = f"{refresh_url}/{_PAIR_OF_MEMBER.get(repo_key, repo_key)}"
    if _wants_json_response():
        payload = {
            "status": status,
            "message": message,
            "repo_key": repo_key or "",
            "redirect_url": refresh_url,
        }
        return jsonify(payload)
    return redirect(refresh_url)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return slug or "group"


def _decorate_repo(repo: dict, spec, plugins_index) -> dict:
    repo = dict(repo)
    plugin_metadata = plugin_metadata_for_runtime(spec, plugins_index)
    if plugin_metadata:
        repo["label"] = plugin_metadata.get("plugin_name") or repo["label"]
        repo["plugin_metadata"] = plugin_metadata
        repo["plugin_name"] = plugin_metadata.get("plugin_name") or repo["label"]
        repo["plugin_category_label"] = (
            plugin_metadata.get("category") or repo["category_label"]
        )
        repo["plugin_group_label"] = plugin_metadata.get("group") or repo["group_label"]
        repo["plugin_description"] = plugin_metadata.get("description") or ""
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
    if repo.get("group") == "frontend_plugins" and repo.get("installed"):
        try:
            repo["frontend_modules_report"] = validate_frontend_suite(repo["key"])
        except Exception:
            repo["frontend_modules_report"] = None
    if repo.get("group") == "backend_settings":
        from y_web.src.external_runtime.backend_plugins import (
            plugin_enabled,
            suite_restart_required,
        )

        repo["plugin_togglable"] = bool(repo.get("installed"))
        repo["plugin_enabled"] = plugin_enabled(repo["key"])
        repo["restart_required"] = suite_restart_required(repo["key"])
    return repo


def _visible_runtime_groups(
    admin_user, github_token: str | None, *, include_remote_metadata: bool
):
    plugins_index = load_plugins_index(refresh=True)
    all_groups = get_grouped_runtime_status(
        github_token=github_token, include_remote_metadata=include_remote_metadata
    )
    visible_groups = []
    for group_info in all_groups:
        repos = []
        for repo in group_info["repos"]:
            spec = runtime_spec(repo["key"])
            if runtime_visible_to_user(spec, admin_user):
                repos.append(_decorate_repo(repo, spec, plugins_index))
        if repos:
            visible_groups.append(
                {
                    "group": group_info["group"],
                    "label": group_info["label"],
                    "repos": repos,
                }
            )
    return visible_groups


def _make_entry(key: str, repos: list[dict]) -> dict:
    """One row of the plugin list: a single repository, or a server+client pair."""
    paired = _PAIRED_ENTRIES.get(key)
    installed = [bool(r.get("installed")) for r in repos]
    if all(installed):
        state, state_label = "installed", "Installed"
    elif any(installed):
        state, state_label = "partial", "Partially installed"
    else:
        state, state_label = "missing", "Not installed"
    first = repos[0]
    togglable = [r for r in repos if r.get("plugin_togglable")]
    return {
        "key": key,
        "label": paired["label"] if paired else first["label"],
        "description": (
            paired["description"] if paired else (first.get("plugin_description") or "")
        ),
        "category": first.get("plugin_category_label")
        or first.get("category_label")
        or "",
        "paired": bool(paired),
        "members": repos,
        "state": state,
        "state_label": state_label,
        "any_exists": any(r.get("exists") for r in repos),
        "enabled": bool(togglable) and all(r.get("plugin_enabled") for r in togglable),
        "togglable": bool(togglable),
        "restart_required": any(r.get("restart_required") for r in repos),
    }


def _plugin_entries(grouped_status) -> list[dict]:
    """Flatten the grouped status into list entries, merging the paired plugins into one row."""
    by_key = {r["key"]: r for g in grouped_status for r in g["repos"]}
    entries, seen = [], set()
    for group_info in grouped_status:
        for repo in group_info["repos"]:
            pair_key = _PAIR_OF_MEMBER.get(repo["key"])
            if pair_key:
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                members = [
                    by_key[m]
                    for m in _PAIRED_ENTRIES[pair_key]["members"]
                    if m in by_key
                ]
                entries.append(_make_entry(pair_key, members))
            else:
                entries.append(_make_entry(repo["key"], [repo]))
    return entries


@experiments.route("/admin/external_runtimes")
@login_required
def external_runtimes():
    admin_user = _require_admin_user()
    if admin_user is None:
        return _external_runtimes_response(status="error", message="Unauthorized")

    grouped_status = _visible_runtime_groups(
        admin_user, _session_github_token(), include_remote_metadata=False
    )
    return render_template(
        "admin/external_runtimes.html",
        plugin_entries=_plugin_entries(grouped_status),
    )


@experiments.route("/admin/external_runtimes/<entry_key>")
@login_required
def external_runtime_detail(entry_key: str):
    """Dedicated page to install, update or remove one plugin (or one server+client pair)."""
    admin_user = _require_admin_user()
    if admin_user is None:
        return redirect(url_for("experiments.settings"))

    member_keys = (
        _PAIRED_ENTRIES[entry_key]["members"]
        if entry_key in _PAIRED_ENTRIES
        else (entry_key,)
    )
    github_token = _session_github_token()
    plugins_index = load_plugins_index(refresh=True)
    repos = []
    for key in member_keys:
        try:
            spec = runtime_spec(key)
        except KeyError:
            flash("Unknown external runtime repository.", "error")
            return redirect(url_for("experiments.external_runtimes"))
        if not runtime_visible_to_user(spec, admin_user):
            flash("You do not have visibility on this plugin repository.", "error")
            return redirect(url_for("experiments.external_runtimes"))
        status = get_runtime_status(
            key, github_token=github_token, include_remote_metadata=True
        )
        repos.append(_decorate_repo(status.to_dict(), spec, plugins_index))

    entry = _make_entry(entry_key, repos)
    branch_sets = [set(r.get("available_branches") or []) for r in repos]
    common_branches = sorted(set.intersection(*branch_sets)) if branch_sets else []
    default_branch = repos[0].get("current_branch") or repos[0].get("default_branch")
    if repos[0].get("available_releases") and not entry["paired"]:
        releases = repos[0]["available_releases"]
    else:
        releases = []
    logs = []
    for key in member_keys:
        logs.extend(read_external_runtime_logs(limit=30, repo_key=key))
    logs.sort(key=lambda e: str(e.get("timestamp") or ""), reverse=True)
    active = _runtime_group_active_experiments(repos[0]["group"])
    return render_template(
        "admin/external_runtime_detail.html",
        entry=entry,
        common_branches=common_branches,
        default_branch=default_branch,
        releases=releases,
        latest_release_tag=repos[0].get("latest_release_tag"),
        releases_enabled=all(r.get("releases_enabled") for r in repos),
        release_error=next(
            (r.get("release_error") for r in repos if r.get("release_error")), None
        ),
        runtime_logs=logs[:40],
        active_experiments=active,
        github_session_authenticated=bool(github_token),
        current_python_executable=resolve_python_executable(),
        host_git_available=host_git_available(),
    )


@experiments.route("/admin/external_runtimes/github_session", methods=["POST"])
@login_required
def external_runtime_github_session():
    admin_user = _require_admin_user()
    if admin_user is None:
        return _external_runtimes_response(status="error", message="Unauthorized")

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

    target = (request.form.get("next") or "").strip()
    if target.startswith("/admin/external_runtimes") and not target.startswith("//"):
        return redirect(target)
    return _external_runtimes_response(message="GitHub session updated.")


@experiments.route("/admin/external_runtimes/<repo_key>/<action>", methods=["POST"])
@login_required
def external_runtime_action(repo_key: str, action: str):
    """Run an action on one repository, or on every member of a paired entry (server first)."""
    pair = _PAIRED_ENTRIES.get(repo_key)
    if not pair:
        return _external_runtime_action_single(repo_key, action)
    if action in {"enable", "disable"}:
        return _external_runtime_action_single(pair["members"][0], action)
    # removing goes client first, everything else server first
    members = pair["members"][::-1] if action == "delete" else pair["members"]
    response = None
    for member in members:
        before = _flashed_errors()
        response = _external_runtime_action_single(member, action)
        if _flashed_errors() > before:
            break  # do not install a client next to a server that failed
    return response


def _flashed_errors() -> int:
    return sum(1 for category, _ in session.get("_flashes", []) if category == "error")


def _external_runtime_action_single(repo_key: str, action: str):
    admin_user = _require_admin_user()
    if admin_user is None:
        return _external_runtimes_response(
            repo_key=repo_key, status="error", message="Unauthorized"
        )

    if action not in _MUTATING_ACTIONS:
        flash("Unsupported runtime action.", "error")
        return _external_runtimes_response(
            repo_key=repo_key, status="error", message="Unsupported runtime action."
        )

    try:
        spec = runtime_spec(repo_key)
    except KeyError:
        flash("Unknown external runtime repository.", "error")
        return _external_runtimes_response(
            repo_key=repo_key,
            status="error",
            message="Unknown external runtime repository.",
        )

    if not runtime_visible_to_user(spec, admin_user):
        flash("You do not have visibility on this plugin repository.", "error")
        return _external_runtimes_response(
            repo_key=repo_key, status="error", message="Not visible."
        )

    if action in {"enable", "disable"}:
        return _toggle_plugin(repo_key, spec, admin_user, action == "enable")

    github_token = _session_github_token()
    branch = (request.form.get("branch") or spec.default_branch).strip()
    release_tag = (request.form.get("release_tag") or "").strip() or None
    install_source = (request.form.get("install_source") or "release").strip().lower()
    git_available = host_git_available()
    if action in {
        "acquire",
        "download_release",
        "clone",
        "fetch",
        "update",
        "install",
        "sync",
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
            return _external_runtimes_response(
                repo_key=repo_key,
                status="error",
                message=f"Stop active {spec.group_label.lower()} experiments before modifying {spec.label}.",
            )
    sync = action == "sync"
    if sync:
        # "Install / Update" of the detail page: pick the concrete step for this repository.
        wants_git = install_source == "git"
        exists = spec.path.exists() or spec.path.is_symlink()
        if exists and spec.path.is_symlink():
            flash(
                f"{spec.label} is a symlinked development checkout: update it from its own repository.",
                "error",
            )
            return _external_runtimes_response(
                repo_key=repo_key, status="error", message="Symlinked checkout."
            )
        is_git = exists and (spec.path / ".git").exists()
        if not exists:
            action = "acquire"
        elif is_git and wants_git:
            action = "update"
        else:
            action = "reinstall"
        if (wants_git or action == "update") and not git_available:
            flash(
                f"Git is not available on this host. Use the release source for {spec.label}.",
                "error",
            )
            return _external_runtimes_response(
                repo_key=repo_key, status="error", message="Git is not available."
            )
    if action in {"clone", "fetch", "update"} and not git_available:
        flash(
            f"Git is not available on this host. Use the release install flow for {spec.label}.",
            "error",
        )
        return _external_runtimes_response(
            repo_key=repo_key,
            status="error",
            message=f"Git is not available on this host for {spec.label}.",
        )
    if action == "install" and not git_available and not spec.path.exists():
        flash(
            f"Git is not available on this host. Install {spec.label} from a GitHub release first.",
            "error",
        )
        return _external_runtimes_response(
            repo_key=repo_key,
            status="error",
            message=f"Git is not available on this host for {spec.label}.",
        )

    try:
        installed_now = False
        if action == "reinstall":
            # the installed copy came from another source: replace it (dependencies and validation follow)
            delete_runtime_repo(repo_key, admin_user.username)
            action = "acquire"
        if action == "acquire":
            if install_source == "git":
                clone_runtime_repo(
                    repo_key, branch, admin_user.username, github_token=github_token
                )
                flash(f"Cloned {spec.label} on branch {branch}.", "success")
                installed_now = True
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
                installed_now = True
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
            installed_now = True
        elif action == "clone":
            clone_runtime_repo(
                    repo_key, branch, admin_user.username, github_token=github_token
                )
            flash(f"Cloned {spec.label} on branch {branch}.", "success")
            installed_now = True
        elif action == "fetch":
            fetch_runtime_repo(
                repo_key, branch, admin_user.username, github_token=github_token
            )
            flash(f"Fetched {spec.label} from branch {branch}.", "success")
        elif action == "update":
            update_runtime_repo(
                repo_key, branch, admin_user.username, github_token=github_token
            )
            flash(f"Updated {spec.label} to branch {branch}.", "success")
            if sync:
                installed_now = (
                    True  # an update also refreshes dependencies, validation and schema
                )
        elif action == "install":
            install_runtime_dependencies(repo_key, admin_user.username)
            flash(f"Installed dependencies for {spec.label}.", "success")
        elif action == "validate":
            validate_runtime_repo(repo_key, admin_user.username)
            flash(f"Validated {spec.label}.", "success")
        elif action == "delete":
            delete_runtime_repo(repo_key, admin_user.username)
            flash(f"Deleted {spec.label}.", "success")

        if installed_now:
            install_runtime_dependencies(repo_key, admin_user.username)
            flash(f"Installed dependencies for {spec.label}.", "success")
            validate_runtime_repo(repo_key, admin_user.username)
            flash(f"Validated {spec.label}.", "success")
            _run_suite_schema_migration(repo_key)
            from y_web.src.external_runtime.backend_plugins import (
                suite_restart_required,
            )

            if suite_restart_required(repo_key):
                flash(
                    f"Restart required: {spec.label} routes are loaded at startup.",
                    "warning",
                )
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

    return _external_runtimes_response(
        repo_key=repo_key,
        message=f"{spec.label} action completed.",
        preserve_repo_key=(action != "delete"),
    )


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
