"""
Administrative dashboard routes.

Provides routes for the admin interface including the main dashboard view,
about page, and administrative functions for managing experiments, clients,
and system status monitoring.
"""

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from y_web.utils import (
    get_llm_models,
    get_ollama_models,
    get_vllm_models,
)
from y_web.utils.jupyter_utils import get_jupyter_instances
from y_web.utils.miscellanea import llm_backend_status, ollama_status

from .models import (
    Admin_users,
    Client,
    Client_Execution,
    Exps,
    Jupyter_instances,
    Ollama_Pull,
    User_Experiment,
)
from .utils import (
    check_connection,
    check_privileges,
    get_db_port,
    get_db_server,
    get_db_type,
)

admin = Blueprint("admin", __name__)


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

    llm_url = request.args.get("llm_url")
    if not llm_url:
        return jsonify({"error": "llm_url parameter is required"}), 400

    # Normalize URL
    if not llm_url.startswith("http"):
        llm_url = f"http://{llm_url}"
    if not llm_url.endswith("/v1"):
        llm_url = f"{llm_url}/v1"

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

    # Filter experiments based on user role
    if user.role == "admin":
        # Admin sees all experiments
        all_experiments = Exps.query.all()
    elif user.role == "researcher":
        # Researcher sees only experiments they own
        all_experiments = Exps.query.filter_by(owner=user.username).all()
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

    # Save total counts before limiting to 5
    total_running = len(active_experiments)
    total_completed = len(completed_experiments)
    total_stopped = len(stopped_experiments)
    
    # Limit to 5 per section
    active_experiments = active_experiments[:5]
    completed_experiments = completed_experiments[:5]
    stopped_experiments = stopped_experiments[:5]

    # Helper function to build experiment data with clients
    def build_experiment_data(experiments_list):
        result = {}
        for e in experiments_list:
            clients = Client.query.filter_by(id_exp=e.idexp).all()
            client_data = []
            for client in clients:
                cl = Client_Execution.query.filter_by(client_id=client.id).first()
                client_executions = cl if cl is not None else -1
                client_data.append((client, client_executions))
            result[e.idexp] = {"experiment": e, "clients": client_data}
        return result

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

    return render_template(
        "admin/dashboard.html",
        running_experiments=active_exps,
        completed_experiments=completed_exps,
        stopped_experiments=stopped_exps,
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
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 5, type=int)
    
    # Filter experiments based on user role
    if user.role == "admin":
        all_experiments = Exps.query.all()
    elif user.role == "researcher":
        all_experiments = Exps.query.filter_by(owner=user.username).all()
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
        for client in clients:
            cl = Client_Execution.query.filter_by(client_id=client.id).first()
            elapsed = cl.elapsed_time if cl else 0
            expected = cl.expected_duration_rounds if cl else 0
            progress = min(100, int((elapsed / expected) * 100)) if expected > 0 else 0
            client_data.append({
                "id": client.id,
                "name": client.name,
                "status": client.status,
                "progress": progress,
                "elapsed": elapsed,
                "expected": expected
            })
        result.append({
            "idexp": exp.idexp,
            "exp_name": exp.exp_name,
            "running": exp.running,
            "status": exp.status,
            "clients": client_data
        })
    
    return jsonify({
        "experiments": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": ((total - 1) // per_page) + 1 if total > 0 else 1
    })


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
    from . import db

    user = Admin_users.query.filter_by(username=current_user.username).first()

    if not user or user.role != "admin":
        return jsonify({"success": False, "message": "Access denied"}), 403

    user.telemetry_notice_shown = True
    db.session.commit()

    return jsonify({"success": True})
