import psutil
from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required

from y_web import db
from y_web.src.experiment.helpers import get_experiment_dir
from y_web.routes.admin.sub.experiments import experiment_details
from y_web.src.models import Exps, Jupyter_instances
from y_web.src.system.jupyter_utils import *
from y_web.src.system.miscellanea import ollama_status

lab = Blueprint("lab", __name__)


def __check_notebook_enabled():
    """Check if Jupyter Notebook functionality is enabled"""
    if current_app.config.get("ENABLE_NOTEBOOK", True) is not False:
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


def _get_request_host_and_port():
    """Return the request host and port with a safe fallback when no port is present."""
    host = request.host or ""
    if ":" in host:
        host_name, host_port = host.rsplit(":", 1)
        return host_name, host_port

    return host, str(request.environ.get("SERVER_PORT", 80))


def _get_request_origin():
    """Return the browser-visible origin used to reach the admin app."""
    host_url = request.host_url or ""
    if host_url.endswith("/"):
        host_url = host_url[:-1]
    return host_url


def _get_notebook_dir(exp: Exps):
    """Return the notebook directory for an experiment."""
    return get_experiment_dir(exp) / "notebooks"


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

    notebook_dir = _get_notebook_dir(exp)
    if not notebook_dir:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Could not resolve notebook directory for experiment ID: {experiment_id}",
                }
            ),
            400,
        )

    current_host, current_port = _get_request_host_and_port()
    current_origin = _get_request_origin()

    success, message, instance_id = start_jupyter(
        exp_id,
        str(notebook_dir),
        current_host=current_host,
        current_port=current_port,
        current_origin=current_origin,
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

    exp = db.session.query(Exps).filter_by(idexp=int(expid)).first()
    if not exp:
        return jsonify({"success": False, "message": f"Experiment not found: {expid}"}), 404

    notebook_dir = _get_notebook_dir(exp)

    try:
        filepath = create_notebook_with_template("untitled.ipynb", str(notebook_dir))
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
    if not inst["process"]:
        return experiment_details(exp_id)

    try:
        proc = psutil.Process(int(inst["process"]))
        if not proc.is_running():
            return experiment_details(exp_id)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return experiment_details(exp_id)

    current_host, current_port = _get_request_host_and_port()
    jupyter_url = f"http://{current_host}:{inst['port']}/lab?token=embed-jupyter-token"

    experiment = Exps.query.filter_by(idexp=exp_id).first()

    return render_template(
        "admin/jupyter.html",
        jupyter_url=jupyter_url,
        expid=exp_id,
        jupyter_port=inst["port"],
        jupyter_token="embed-jupyter-token",
        notebook_dir=str(inst["notebook_dir"]),
        experiment=experiment,
        current_host=current_host,
        current_port=current_port,
    )
