"""
Administrative dashboard routes.

Provides routes for the admin interface including the main dashboard view,
about page, and administrative functions for managing experiments, clients,
and system status monitoring.
"""

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
        return jsonify({"error": "llm_url parameter is required"}), 400

    try:
        models = get_llm_models(llm_url)
        if models:
            return jsonify({"success": True, "models": models, "url": llm_url})
        else:
            return (
                jsonify({"success": False, "message": f"No models found at {llm_url}"}),
                404,
            )
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Failed to connect to {llm_url}: {str(e)}",
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
        return jsonify({"error": "llm_url parameter is required"}), 400

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
                    "message": f"Failed to connect to {llm_url}: {str(e)}",
                }
            ),
            500,
        )


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
    user = Admin_users.query.filter_by(username=current_user.username).first()

    llm_backend = llm_backend_status()

    # Filter experiments based on user role + visibility grants
    if user.role in ("admin", "researcher"):
        all_experiments = get_visible_experiment_query(user).all()
    else:
        # Regular users should not access this page
        # They are redirected to their experiment feed
        flash("Access denied. Please use the experiment feed.")
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

    def _calculate_experiment_progress(experiments_list):
        """Return average client execution progress per experiment id."""
        progress_by_exp = {}
        for exp in experiments_list:
            clients = Client.query.filter_by(id_exp=exp.idexp).all()
            client_ids = [client.id for client in clients]
            if not client_ids:
                continue

            client_exec_rows = Client_Execution.query.filter(
                Client_Execution.client_id.in_(client_ids)
            ).all()
            client_exec_by_id = {row.client_id: row for row in client_exec_rows}

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
        return progress_by_exp

    # Helper function to build experiment data with clients
    def build_experiment_data(experiments_list):
        result = {}
        progress_by_exp = _calculate_experiment_progress(experiments_list)
        for e in experiments_list:
            clients = Client.query.filter_by(id_exp=e.idexp).all()
            client_data = []
            for client in clients:
                cl = Client_Execution.query.filter_by(client_id=client.id).first()
                client_executions = cl if cl is not None else -1
                client_data.append((client, client_executions))
            result[e.idexp] = {
                "experiment": e,
                "clients": client_data,
                "progress": progress_by_exp.get(e.idexp),
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
    ollama_pulls = Ollama_Pull.query.all()
    ollama_pulls = [(pull.model_name, float(pull.status)) for pull in ollama_pulls]

    dbtype = get_db_type()
    dbport = get_db_port()
    db_conn = check_connection()
    db_server = get_db_server()

    # Get jupyter instances and create a mapping by exp_id
    jupyter_instances = Jupyter_instances.query.all()
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

    return render_template(
        "admin/dashboard.html",
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
        notebook=current_app.config["ENABLE_NOTEBOOK"],
        total_experiments=total_experiments,
        # Telemetry notice
        show_telemetry_notice=show_telemetry_notice,
        can_manage_experiment=can_manage_experiment_for_current_user,
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
        per_page: Items per page (default 5)

    Returns:
        JSON with experiments data and pagination info
    """
    from flask import flash, redirect, url_for

    # Get current user
    user = Admin_users.query.filter_by(username=current_user.username).first()

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 5, type=int)

    # Filter experiments based on role + visibility grants
    if user.role in ("admin", "researcher"):
        all_experiments = get_visible_experiment_query(user).all()
    else:
        return jsonify({"error": "Access denied"}), 403

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

    # Apply pagination
    start = (page - 1) * per_page
    end = start + per_page
    paginated_experiments = experiments[start:end]

    # Build experiment data with clients
    result = []
    for exp in paginated_experiments:
        clients = Client.query.filter_by(id_exp=exp.idexp).all()
        client_data = []
        progress_values = []
        for client in clients:
            cl = Client_Execution.query.filter_by(client_id=client.id).first()
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
        exp_progress = int(sum(progress_values) / len(progress_values)) if progress_values else None
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
                "clients": client_data,
            }
        )

    return jsonify(
        {
            "experiments": result,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": ((total - 1) // per_page) + 1 if total > 0 else 1,
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
    user = Admin_users.query.filter_by(username=current_user.username).first()

    # Filter experiments based on role + visibility grants
    if user.role in ("admin", "researcher"):
        all_experiments = get_visible_experiment_query(user).all()
    else:
        return jsonify({"error": "Access denied"}), 403

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
    user = Admin_users.query.filter_by(username=current_user.username).first()

    # Get all jupyter instances from database
    all_db_instances = Jupyter_instances.query.all()

    # Filter instances based on user access
    filtered_instances = []
    for db_inst in all_db_instances:
        exp_id = db_inst.exp_id

        # Get experiment details
        exp = Exps.query.filter_by(idexp=exp_id).first()
        if not exp:
            continue

        # Check if user is admin or has access to this experiment
        if user.role == "admin":
            has_access = True
        else:
            user_exp = User_Experiment.query.filter_by(
                user_id=user.id, exp_id=exp_id
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

    user = Admin_users.query.filter_by(username=current_user.username).first()

    if not user or user.role != "admin":
        return jsonify({"success": False, "message": "Access denied"}), 403

    user.telemetry_notice_shown = True
    db.session.commit()

    return jsonify({"success": True})
