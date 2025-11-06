from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required

from y_web import db
from y_web.models import Exps, Jupyter_instances
from y_web.routes_admin.experiments_routes import experiment_details
from y_web.utils.jupyter_utils import *
from y_web.utils.miscellanea import ollama_status

lab = Blueprint("lab", __name__)


def __check_notebook_enabled():
    """Check if Jupyter Notebook functionality is enabled"""
    if current_app.config["ENABLE_NOTEBOOK"] is not False:
        return False
    else:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Jupyter Notebook functionality is disabled.",
                }
            ),
            403,
        )


@lab.route("/admin/lab_start/<experiment_id>", methods=["GET"])
@login_required
def api_start_jupyter(experiment_id):
    """API endpoint to start Jupyter Lab"""
    disabled = __check_notebook_enabled()
    if disabled is not False:
        return disabled

    try:
        exp_id = int(experiment_id)
    except (ValueError, TypeError):
        return (
            jsonify(
                {"success": False, "message": f"Invalid experiment ID: {experiment_id}"}
            ),
            400,
        )

    exp = db.session.query(Exps).filter_by(idexp=exp_id).first()
    if not exp:
        return (
            jsonify({"success": False, "message": f"Experiment not found: {exp_id}"}),
            404,
        )

    # determine the database type and set the notebook directory accordingly
    db_type = "sqlite"
    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        db_type = "postgresql"

    if db_type == "sqlite":
        path = exp.db_name.split(os.sep)
        notebook_dir = f"y_web{os.sep}{path[0]}{os.sep}{path[1]}{os.sep}notebooks"
    elif db_type == "postgresql":
        db_name = exp.db_name
        db_name = db_name.split("experiments_")[-1]
        notebook_dir = f"y_web{os.sep}experiments{os.sep}{db_name}{os.sep}notebooks"
    else:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Unsupported database type for experiment ID: {experiment_id}",
                }
            ),
            400,
        )

    success, message, instance_id = start_jupyter(
        exp_id,
        notebook_dir,
        current_host=request.host.split(":")[0],
        current_port=request.host.split(":")[1],
    )
    return jsonify({"success": success, "message": message, "instance_id": instance_id})


@lab.route("/admin/lab_stop/<instance_id>", methods=["GET"])
@login_required
def api_stop_jupyter(instance_id):
    """API endpoint to stop Jupyter Lab"""
    disabled = __check_notebook_enabled()
    if disabled is not False:
        return disabled

    try:
        instance_id_int = int(instance_id)
    except (ValueError, TypeError):
        return (
            jsonify(
                {"success": False, "message": f"Invalid instance ID: {instance_id}"}
            ),
            400,
        )

    success, message = stop_jupyter(instance_id_int)
    return jsonify({"success": success, "message": message})


@lab.route("/admin/lab_instances", methods=["GET"])
@login_required
def api_jupyter_instances():
    """API endpoint to get all Jupyter Lab instances"""
    disabled = __check_notebook_enabled()
    if disabled != False:
        return disabled

    instances = get_jupyter_instances()
    return jsonify({"instances": instances})


@lab.route("/admin/lab_create/<expid>", methods=["POST"])
@login_required
def api_create_notebook(expid):
    """API endpoint to create a new notebook"""
    disabled = __check_notebook_enabled()
    if disabled is not False:
        return disabled

    path = (
        db.session.query(Exps).filter_by(idexp=int(expid)).first().db_name.split(os.sep)
    )

    notebook_dir = f"y_web{os.sep}{path[0]}{os.sep}{path[1]}{os.sep}notebooks"

    try:
        filepath = create_notebook_with_template("untitled.ipynb", notebook_dir)
        return jsonify(
            {
                "success": True,
                "message": f"Notebook created at {filepath}",
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error creating notebook: {str(e)}"}
        )


@lab.route("/admin/lab/<int:exp_id>")
@login_required
def jupyter_page(exp_id):
    """Jupyter Lab embedded page for specific instance"""
    disabled = __check_notebook_enabled()
    if disabled is not False:
        return disabled

    instances = db.session.query(Jupyter_instances).all()
    JUPYTER_INSTANCES = {
        inst.exp_id: {
            "port": inst.port,
            "process": inst.process,
            "notebook_dir": Path(inst.notebook_dir),
        }
        for inst in instances
    }

    if exp_id not in JUPYTER_INSTANCES:
        return experiment_details(exp_id)

    inst = JUPYTER_INSTANCES[exp_id]
    try:
        proc = psutil.Process(int(inst["process"]))
        if not proc.is_running():
            return experiment_details(exp_id)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return experiment_details(exp_id)

    current_host = request.host.split(":")[0]
    jupyter_url = f"http://{current_host}:{inst['port']}/lab?token=embed-jupyter-token"

    ollamas = ollama_status()
    experiment = Exps.query.filter_by(idexp=exp_id).first()

    return render_template(
        "admin/jupyter.html",
        jupyter_url=jupyter_url,
        expid=exp_id,
        jupyter_port=inst["port"],
        jupyter_token="embed-jupyter-token",
        notebook_dir=str(inst["notebook_dir"]),
        ollamas=ollamas,
        experiment=experiment,
        current_host=current_host,
    )
