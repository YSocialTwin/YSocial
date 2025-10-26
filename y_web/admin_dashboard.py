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

    Shows experiments, clients, execution status, Ollama models,
    and database connection information. Requires admin privileges.

    Returns:
        Rendered dashboard template with system status information
    """
    check_privileges(current_user.username)
    ollamas = ollama_status()
    llm_backend = llm_backend_status()

    # get all experiments
    experiments = Exps.query.all()
    # get all clients for each experiment
    exps = {}
    for e in experiments:
        exps[e.idexp] = {
            "experiment": e,
            "clients": Client.query.filter_by(id_exp=e.idexp).all(),
        }

    res = {}
    # get clients with client_execution information
    for exp, data in exps.items():
        res[exp] = {"experiment": data["experiment"], "clients": []}
        for client in data["clients"]:
            cl = Client_Execution.query.filter_by(client_id=client.id).first()
            client_executions = cl if cl is not None else -1
            res[exp]["clients"].append((client, client_executions))

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

    return render_template(
        "admin/dashboard.html",
        experiments=res,
        ollamas=ollamas,
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
    ollamas = ollama_status()
    return render_template("admin/about.html", ollamas=ollamas)
