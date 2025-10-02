"""
Administrative dashboard routes.

Provides routes for the admin interface including the main dashboard view,
about page, and administrative functions for managing experiments, clients,
and system status monitoring.
"""

from flask import (
    Blueprint,
    render_template,
)
from flask_login import login_required, current_user

from .models import Exps, Client, Client_Execution, Ollama_Pull
from y_web.utils import (
    get_ollama_models,
)

from y_web.utils.miscellanea import ollama_status

from .utils import check_privileges, get_db_type, get_db_port, check_connection, get_db_server


admin = Blueprint("admin", __name__)


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

    # get installed ollama models, if any
    models = []
    try:
        models = get_ollama_models()
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
