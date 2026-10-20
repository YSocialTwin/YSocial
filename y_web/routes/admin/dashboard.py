"""
Administrative dashboard routes.

Provides routes for the admin interface including the main dashboard view,
about page, and administrative functions for managing experiments, clients,
and system status monitoring.
"""

from collections import defaultdict

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
from flask_login import current_user, login_required
from sqlalchemy import select

from y_web import db
from y_web.i18n import gettext as _
from y_web.src.experiment.access import (
    get_visible_experiment_query,
    user_can_manage_experiment,
)
from y_web.src.llm.ollama_manager import get_ollama_models
from y_web.src.llm.vllm_manager import get_llm_models, get_vllm_models
from y_web.src.models import (
    Admin_users,
    Client,
    Client_Execution,
    Exps,
    Jupyter_instances,
    Ollama_Pull,
    User_Experiment,
)
from y_web.src.system.check_blog import (
    get_recent_blog_posts,
    refresh_blog_posts_if_stale,
)
from y_web.src.system.jupyter_utils import get_jupyter_instances
from y_web.src.system.miscellanea import (
    check_connection,
    check_privileges,
    get_db_port,
    get_db_server,
    get_db_type,
    llm_backend_status,
    ollama_status,
)

from .sub.experiments._helpers import _experiment_has_started_once

admin = Blueprint("admin", __name__)


def _normalize_llm_models_url(llm_url: str) -> str:
    """Normalize a user-provided LLM base URL for model discovery."""
    llm_url = str(llm_url or "").strip()
    if not llm_url:
        return ""
    if not llm_url.startswith("http"):
        llm_url = f"http://{llm_url}"
    if llm_url.endswith("/"):
        llm_url = llm_url[:-1]
    for suffix in ("/v1/models", "/models", "/api/tags", "/v1"):
        if llm_url.endswith(suffix):
            return llm_url[: -len(suffix)]
    return llm_url


def _is_embedding_model_name(model_name: str) -> bool:
    """Heuristic filter for embedding-capable models exposed by Ollama/OpenAI-compatible APIs."""
    lowered = str(model_name or "").strip().lower()
    if not lowered:
        return False
    embedding_markers = (
        "embed",
        "embedding",
        "bge",
        "e5",
        "gte",
        "snowflake-arctic",
        "nomic-embed",
        "mxbai",
    )
    return any(marker in lowered for marker in embedding_markers)


@admin.route("/admin/api/fetch_models")
@login_required
def fetch_models():
    """
    AJAX endpoint to fetch models from a custom LLM URL.

    Query params:
        llm_url: The LLM server URL to fetch models from

    Returns:
        JSON with models list or error message
    """
    from flask import jsonify

    llm_url = _normalize_llm_models_url(request.args.get("llm_url"))
    if not llm_url:
        return jsonify({"error": _("llm_url parameter is required")}), 400

    try:
        models = get_llm_models(llm_url)
        if models:
            return jsonify({"success": True, "models": models, "url": llm_url})
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": _("No models found at %(llm_url)s", llm_url=llm_url),
                    }
                ),
                404,
            )
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "message": _(
                        "Failed to connect to %(llm_url)s: %(error)s",
                        llm_url=llm_url,
                        error=str(e),
                    ),
                }
            ),
            500,
        )


@admin.route("/admin/api/fetch_embedding_models")
@login_required
def fetch_embedding_models():
    """AJAX endpoint to fetch only embedding models from a compatible LLM/Ollama server."""
    llm_url = _normalize_llm_models_url(request.args.get("llm_url"))
    if not llm_url:
        return jsonify({"error": _("llm_url parameter is required")}), 400

    try:
        models = [
            model
            for model in get_llm_models(llm_url)
            if _is_embedding_model_name(model)
        ]
        return jsonify({"success": True, "models": models, "url": llm_url})
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "message": _(
                        "Failed to connect to %(llm_url)s: %(error)s",
                        llm_url=llm_url,
                        error=str(e),
                    ),
                }
            ),
            500,
        )


DASHBOARD_GROUPS_PER_PAGE = 5


def _group_name(exp):
    """Group an experiment belongs to ("No group" when empty)."""
    group = getattr(exp, "exp_group", None)
    return group if group and group.strip() else "No group"


def _sorted_group_names(names):
    """Group order used by the dashboard (same as the Jinja ``sort`` filter)."""
    return sorted(names, key=lambda n: n.lower())


def _page_of_groups(group_names, page, per_page):
    """Names of the groups on 1-based *page* and the number of pages."""
    names = _sorted_group_names(group_names)
    pages = ((len(names) - 1) // per_page) + 1 if names else 1
    page = min(max(page, 1), pages)
    return names[(page - 1) * per_page : page * per_page], pages


def _dashboard_news(limit=4):
    """Latest blog posts for the "News from the Agents" box (read from the admin DB)."""
    try:
        # the stored posts are refreshed in the background when they are old
        refresh_blog_posts_if_stale(current_app._get_current_object())
        return get_recent_blog_posts(limit)
    except Exception:
        return []


@admin.route("/admin/dashboard")
@login_required
def dashboard():
    """
    Display main administrative dashboard.

    Shows experiments categorized by status (active, completed, stopped/scheduled),
    clients, execution status, Ollama models, and database connection information.
    Requires admin privileges.

    Returns:
        Rendered dashboard template with system status information
    """
    # Get current user
    user = db.session.scalars(
        select(Admin_users).filter_by(username=current_user.username)
    ).first()

    llm_backend = llm_backend_status()

    # Filter experiments based on user role + visibility grants
    if user.role in ("admin", "researcher"):
        all_experiments = (
            get_visible_experiment_query(user).order_by(Exps.idexp.asc()).all()
        )
    else:
        # Regular users should not access this page
        # They are redirected to their experiment feed
        flash(_("Access denied. Please use the experiment feed."))
        return redirect(url_for("auth.login"))

    # Categorize experiments by status
    active_experiments = []
    completed_experiments = []
    stopped_experiments = []  # includes both "stopped" and "scheduled"

    for exp in all_experiments:
        # Get exp_status, default to determining from running field for backward compatibility
        exp_status = getattr(exp, "exp_status", None)
        if exp_status is None:
            # Backward compatibility: determine status from running field
            exp_status = "active" if exp.running == 1 else "stopped"

        if exp_status == "active":
            active_experiments.append(exp)
        elif exp_status == "completed":
            completed_experiments.append(exp)
        else:  # "stopped" or "scheduled"
            stopped_experiments.append(exp)

    # Save total counts (all experiments loaded, no limiting)
    total_running = len(active_experiments)
    total_completed = len(completed_experiments)
    total_stopped = len(stopped_experiments)

    exp_ids = [exp.idexp for exp in all_experiments]
    clients_by_exp = defaultdict(list)
    client_exec_by_id = {}
    if exp_ids:
        all_clients = db.session.scalars(
            select(Client).filter(Client.id_exp.in_(exp_ids))
        ).all()
        client_ids = []
        for client in all_clients:
            clients_by_exp[client.id_exp].append(client)
            client_ids.append(client.id)

        if client_ids:
            exec_rows = db.session.scalars(
                select(Client_Execution).filter(
                    Client_Execution.client_id.in_(client_ids)
                )
            ).all()
            client_exec_by_id = {row.client_id: row for row in exec_rows}

    def _calculate_experiment_progress(experiments_list):
        """Return average client execution progress per experiment id."""
        progress_by_exp = {}
        for exp in experiments_list:
            clients = clients_by_exp.get(exp.idexp, [])
            has_started_once = _experiment_has_started_once(exp, clients=clients)
            total_progress = 0
            count = 0
            for client in clients:
                client_exec = client_exec_by_id.get(client.id)
                if not client_exec or client_exec.expected_duration_rounds <= 0:
                    continue
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
                progress_by_exp[exp.idexp] = int(total_progress / count)
            elif has_started_once:
                progress_by_exp[exp.idexp] = 0
        return progress_by_exp

    # Helper function to build experiment data with clients
    def build_experiment_data(experiments_list):
        result = {}
        progress_by_exp = _calculate_experiment_progress(experiments_list)
        for e in experiments_list:
            clients = clients_by_exp.get(e.idexp, [])
            has_started_once = _experiment_has_started_once(e, clients=clients)
            client_data = []
            for client in clients:
                client_executions = client_exec_by_id.get(client.id, -1)
                client_data.append((client, client_executions))
            exp_progress = progress_by_exp.get(e.idexp)
            if exp_progress is None and has_started_once:
                exp_progress = 0
            result[e.idexp] = {
                "experiment": e,
                "clients": client_data,
                "progress": exp_progress,
                "progress_label": "NA" if exp_progress is None else f"{exp_progress}%",
                "has_started_once": has_started_once,
            }
        return result

    # Helper function to group experiments by exp_group
    def group_experiments_by_group(experiments_list):
        from collections import defaultdict

        grouped = defaultdict(list)
        for e in experiments_list:
            group_name = (
                e.exp_group if e.exp_group and e.exp_group.strip() else "No group"
            )
            grouped[group_name].append(e)
        return dict(grouped)

    # Group experiments by their group for each status
    active_groups = group_experiments_by_group(active_experiments)
    completed_groups = group_experiments_by_group(completed_experiments)
    stopped_groups = group_experiments_by_group(stopped_experiments)

    # Build experiment data for each group
    active_exps_by_group = {
        group: build_experiment_data(exps) for group, exps in active_groups.items()
    }
    completed_exps_by_group = {
        group: build_experiment_data(exps) for group, exps in completed_groups.items()
    }
    stopped_exps_by_group = {
        group: build_experiment_data(exps) for group, exps in stopped_groups.items()
    }

    # Completed / stopped boxes are paginated by group (not by experiment)
    first_completed, completed_group_pages = _page_of_groups(
        completed_exps_by_group.keys(), 1, DASHBOARD_GROUPS_PER_PAGE
    )
    first_stopped, stopped_group_pages = _page_of_groups(
        stopped_exps_by_group.keys(), 1, DASHBOARD_GROUPS_PER_PAGE
    )
    completed_exps_by_group = {g: completed_exps_by_group[g] for g in first_completed}
    stopped_exps_by_group = {g: stopped_exps_by_group[g] for g in first_stopped}

    # Keep the old format for backward compatibility (flatten all groups)
    active_exps = build_experiment_data(active_experiments)
    completed_exps = build_experiment_data(completed_experiments)
    stopped_exps = build_experiment_data(stopped_experiments)

    total_experiments = len(all_experiments)

    # get installed LLM models from the configured server
    models = []
    try:
        # Use the generic function that works with any OpenAI-compatible server
        models = get_llm_models()
    except:
        pass

    # get all ollama pulls
    ollama_pulls = db.session.scalars(select(Ollama_Pull)).all()
    ollama_pulls = [(pull.model_name, float(pull.status)) for pull in ollama_pulls]

    dbtype = get_db_type()
    dbport = get_db_port()
    db_conn = check_connection()
    db_server = get_db_server()

    # Get jupyter instances and create a mapping by exp_id
    jupyter_instances = db.session.scalars(select(Jupyter_instances)).all()
    jupyter_by_exp = {}
    for jupyter in jupyter_instances:
        # Check if process is actually running
        import psutil

        is_running = False
        if jupyter.process is not None:
            try:
                proc = psutil.Process(int(jupyter.process))
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    is_running = True
            except (psutil.NoSuchProcess, ValueError, TypeError):
                pass

        jupyter_by_exp[jupyter.exp_id] = {
            "port": jupyter.port,
            "notebook_dir": jupyter.notebook_dir,
            "status": "Active" if is_running else "Inactive",
            "running": is_running,
        }

    has_jupyter_sessions = len(jupyter_instances) > 0

    # Check if admin needs to see telemetry notice (first login)
    show_telemetry_notice = user.role == "admin" and not user.telemetry_notice_shown

    def can_manage_experiment_for_current_user(experiment):
        return user_can_manage_experiment(user, experiment)

    try:
        from y_web.src.external_runtime.backend_plugins import (
            training_dashboard_overview,
        )

        training_overview = training_dashboard_overview(current_user)
    except Exception:
        training_overview = None

    return render_template(
        "admin/dashboard.html",
        training_overview=training_overview,
        running_experiments=active_exps,
        completed_experiments=completed_exps,
        stopped_experiments=stopped_exps,
        # New grouped data
        running_experiments_by_group=active_exps_by_group,
        completed_experiments_by_group=completed_exps_by_group,
        stopped_experiments_by_group=stopped_exps_by_group,
        total_running=total_running,
        total_completed=total_completed,
        total_stopped=total_stopped,
        completed_group_pages=completed_group_pages,
        stopped_group_pages=stopped_group_pages,
        llm_backend=llm_backend,
        models=models,
        active_pulls=ollama_pulls,
        len=len,
        dbtype=dbtype,
        dbport=dbport,
        db_conn=db_conn,
        db_server=db_server,
        has_jupyter_sessions=has_jupyter_sessions,
        jupyter_by_exp=jupyter_by_exp,
        notebook=current_app.config.get("ENABLE_NOTEBOOK", True),
        total_experiments=total_experiments,
        # Telemetry notice
        show_telemetry_notice=show_telemetry_notice,
        can_manage_experiment=can_manage_experiment_for_current_user,
        news_posts=_dashboard_news(),
    )


@admin.route("/admin/dashboard/experiments/<status>")
@login_required
def dashboard_experiments_by_status(status):
    """
    API endpoint to get experiments by status with pagination for dashboard.

    Args:
        status: Experiment status ('running', 'completed', 'stopped')

    Query params:
        page: Page number (1-based, default 1)
        per_page: Groups per page (default 5)

    Returns:
        JSON with experiments data and pagination info
    """
    from flask import flash, redirect, url_for

    # Get current user
    user = db.session.scalars(
        select(Admin_users).filter_by(username=current_user.username)
    ).first()

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 5, type=int)

    # Filter experiments based on role + visibility grants
    if user.role in ("admin", "researcher"):
        all_experiments = (
            get_visible_experiment_query(user).order_by(Exps.idexp.asc()).all()
        )
    else:
        return jsonify({"error": _("Access denied")}), 403

    # Categorize experiments by status
    experiments = []
    for exp in all_experiments:
        exp_status = getattr(exp, "exp_status", None)
        if exp_status is None:
            exp_status = "active" if exp.running == 1 else "stopped"

        if status == "running" and exp_status == "active":
            experiments.append(exp)
        elif status == "completed" and exp_status == "completed":
            experiments.append(exp)
        elif status == "stopped" and exp_status in ("stopped", "scheduled"):
            experiments.append(exp)

    total = len(experiments)

    # Pagination is by group: a page holds `per_page` groups with all their experiments
    exps_by_group = defaultdict(list)
    for exp in experiments:
        exps_by_group[_group_name(exp)].append(exp)
    page_groups, total_pages = _page_of_groups(exps_by_group.keys(), page, per_page)
    page = min(max(page, 1), total_pages)
    paginated_experiments = [e for g in page_groups for e in exps_by_group[g]]

    paginated_exp_ids = [exp.idexp for exp in paginated_experiments]
    clients_by_exp = defaultdict(list)
    client_exec_by_id = {}
    if paginated_exp_ids:
        paginated_clients = db.session.scalars(
            select(Client).filter(Client.id_exp.in_(paginated_exp_ids))
        ).all()
        client_ids = []
        for client in paginated_clients:
            clients_by_exp[client.id_exp].append(client)
            client_ids.append(client.id)

        if client_ids:
            exec_rows = db.session.scalars(
                select(Client_Execution).filter(
                    Client_Execution.client_id.in_(client_ids)
                )
            ).all()
            client_exec_by_id = {row.client_id: row for row in exec_rows}

    # Build experiment data with clients
    result = []
    for exp in paginated_experiments:
        clients = clients_by_exp.get(exp.idexp, [])
        has_started_once = _experiment_has_started_once(exp, clients=clients)
        client_data = []
        progress_values = []
        for client in clients:
            cl = client_exec_by_id.get(client.id)
            elapsed = cl.elapsed_time if cl else 0
            expected = cl.expected_duration_rounds if cl else 0
            progress = min(100, int((elapsed / expected) * 100)) if expected > 0 else 0
            client_data.append(
                {
                    "id": client.id,
                    "name": client.name,
                    "status": client.status,
                    "progress": progress,
                    "elapsed": elapsed,
                    "expected": expected,
                    "days": client.days,
                }
            )
            if expected > 0:
                progress_values.append(progress)
        exp_progress = (
            int(sum(progress_values) / len(progress_values))
            if progress_values
            else (0 if has_started_once else None)
        )
        result.append(
            {
                "idexp": exp.idexp,
                "exp_name": exp.exp_name,
                "running": exp.running,
                "status": exp.status,
                "exp_status": exp_status,
                "owner": exp.owner,
                "simulator_type": (
                    exp.simulator_type if hasattr(exp, "simulator_type") else "Standard"
                ),
                "can_manage": user_can_manage_experiment(user, exp),
                "progress": exp_progress,
                "progress_label": "NA" if exp_progress is None else f"{exp_progress}%",
                "has_started_once": has_started_once,
                "clients": client_data,
            }
        )

    by_id = {item["idexp"]: item for item in result}
    groups = [
        {
            "name": g,
            "experiments": [by_id[e.idexp] for e in exps_by_group[g]],
        }
        for g in page_groups
    ]

    return jsonify(
        {
            "experiments": result,
            "groups": groups,
            "total": total,
            "total_groups": len(exps_by_group),
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    )


@admin.route("/admin/dashboard/status")
@login_required
def dashboard_status():
    """
    API endpoint to get current experiment status counts for dashboard refresh.

    Returns:
        JSON with counts of running, completed, and stopped experiments
    """
    # Get current user
    user = db.session.scalars(
        select(Admin_users).filter_by(username=current_user.username)
    ).first()

    # Filter experiments based on role + visibility grants
    if user.role in ("admin", "researcher"):
        all_experiments = get_visible_experiment_query(user).all()
    else:
        return jsonify({"error": _("Access denied")}), 403

    # Count experiments by status
    running_count = 0
    completed_count = 0
    stopped_count = 0

    for exp in all_experiments:
        exp_status = getattr(exp, "exp_status", None)
        if exp_status is None:
            exp_status = "active" if exp.running == 1 else "stopped"

        if exp_status == "active":
            running_count += 1
        elif exp_status == "completed":
            completed_count += 1
        else:
            stopped_count += 1

    return jsonify(
        {
            "running": running_count,
            "completed": completed_count,
            "stopped": stopped_count,
        }
    )


@admin.route("/admin/models_data")
@login_required
def models_data():
    """
    API endpoint for LLM models data table.

    Returns server-side paginated models data for DataTable display.

    Returns:
        JSON with 'data' array of model objects and 'total' count
    """
    check_privileges(current_user.username)
    llm_backend = llm_backend_status()

    # get installed LLM models from the configured server
    models = []
    try:
        models = get_llm_models()
    except Exception:
        pass

    # search filter
    search = request.args.get("search")
    if search:
        models = [m for m in models if search.lower() in m.lower()]

    total = len(models)

    # sorting
    sort = request.args.get("sort")
    if sort:
        for s in sort.split(","):
            if len(s) > 0:
                direction = s[0]
                # For simple list, we just sort by name
                if direction == "-":
                    models = sorted(models, reverse=True)
                else:
                    models = sorted(models)

    # pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        models = models[start : start + length]

    return {
        "data": [
            {"model_name": model, "backend": llm_backend["backend"]} for model in models
        ],
        "total": total,
    }


@admin.route("/admin/jupyter_data")
@login_required
def jupyter_data():
    """
    API endpoint for JupyterLab sessions data table.

    Returns JupyterLab sessions for experiments the current user has access to.
    Shows only sessions for experiments where user is admin or has explicit access.

    Returns:
        JSON with 'data' array of jupyter session objects and 'total' count
    """
    import psutil

    check_privileges(current_user.username)

    # Get current user
    user = db.session.scalars(
        select(Admin_users).filter_by(username=current_user.username)
    ).first()

    # Get all jupyter instances from database
    all_db_instances = db.session.scalars(select(Jupyter_instances)).all()

    # Filter instances based on user access
    filtered_instances = []
    for db_inst in all_db_instances:
        exp_id = db_inst.exp_id

        # Get experiment details
        exp = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
        if not exp:
            continue

        # Check if user is admin or has access to this experiment
        if user.role == "admin":
            has_access = True
        else:
            user_exp = db.session.scalars(
                select(User_Experiment).filter_by(user_id=user.id, exp_id=exp_id)
            ).first()
            has_access = user_exp is not None

        if has_access:
            # Check if process is actually running
            is_running = False
            if db_inst.process is not None:
                try:
                    proc = psutil.Process(int(db_inst.process))
                    if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                        is_running = True
                except (psutil.NoSuchProcess, ValueError, TypeError):
                    pass

            filtered_instances.append(
                {
                    "exp_id": exp_id,
                    "exp_name": exp.exp_name,
                    "port": db_inst.port,
                    "notebook_dir": db_inst.notebook_dir,
                    "status": "Active" if is_running else "Inactive",
                    "running": is_running,
                }
            )

    # search filter
    search = request.args.get("search")
    if search:
        filtered_instances = [
            i for i in filtered_instances if search.lower() in i["exp_name"].lower()
        ]

    total = len(filtered_instances)

    # sorting
    sort = request.args.get("sort")
    if sort:
        for s in sort.split(","):
            if len(s) > 0:
                direction = s[0]
                field = s[1:]
                reverse = direction == "-"

                if field == "exp_name":
                    filtered_instances = sorted(
                        filtered_instances,
                        key=lambda x: x.get("exp_name", ""),
                        reverse=reverse,
                    )
                elif field == "status":
                    filtered_instances = sorted(
                        filtered_instances,
                        key=lambda x: x.get("status", ""),
                        reverse=reverse,
                    )

    # pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        filtered_instances = filtered_instances[start : start + length]

    return {
        "data": filtered_instances,
        "total": total,
    }


@admin.route("/admin/about")
@login_required
def about():
    """
    Display about page with team and project information.

    Returns:
        Rendered about page template
    """
    check_privileges(current_user.username)
    return render_template("admin/about.html")


@admin.route("/admin/dismiss_telemetry_notice", methods=["POST"])
@login_required
def dismiss_telemetry_notice():
    """
    Mark telemetry notice as shown for the current admin user.

    Returns:
        JSON response with success status
    """
    from y_web import db

    user = db.session.scalars(
        select(Admin_users).filter_by(username=current_user.username)
    ).first()

    if not user or user.role != "admin":
        return jsonify({"success": False, "message": _("Access denied")}), 403

    user.telemetry_notice_shown = True
    db.session.commit()

    return jsonify({"success": True})
