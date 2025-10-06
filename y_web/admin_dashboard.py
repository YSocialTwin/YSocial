"""
Administrative dashboard routes.

Provides routes for the admin interface including the main dashboard view,
about page, and administrative functions for managing experiments, clients,
and system status monitoring.
"""

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
)
from flask_login import current_user, login_required

from y_web.utils import (
    get_llm_models,
    get_ollama_models,
    get_vllm_models,
)
from y_web.utils.miscellanea import llm_backend_status, ollama_status

from .models import Client, Client_Execution, Exps, Ollama_Pull
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
    )


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
