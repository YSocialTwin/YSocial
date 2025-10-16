from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from y_web import db
from y_web.models import Exps, Jupyter_instances
from y_web.routes_admin.experiments_routes import experiment_details
from y_web.utils.jupyter_utils import *
from y_web.utils.miscellanea import ollama_status

lab = Blueprint("lab", __name__)


@lab.route("/admin/lab_start/<experiment_id>", methods=["GET"])
@login_required
def api_start_jupyter(experiment_id):
    """API endpoint to start Jupyter Lab"""

    exp_id = experiment_id  # Use experiment_dir as notebook_dir
    path = (
        db.session.query(Exps)
        .filter_by(idexp=int(exp_id))
        .first()
        .db_name.split(os.sep)
    )

    notebook_dir = f"y_web{os.sep}{path[0]}{os.sep}{path[1]}{os.sep}notebooks"

    success, message, instance_id = start_jupyter(exp_id, notebook_dir)
    return jsonify({"success": success, "message": message, "instance_id": instance_id})


@lab.route("/admin/lab_stop/<instance_id>", methods=["GET"])
@login_required
def api_stop_jupyter(instance_id):
    """API endpoint to stop Jupyter Lab"""

    success, message = stop_jupyter(instance_id)
    return jsonify({"success": success, "message": message})


@lab.route("/admin/lab_instances", methods=["GET"])
@login_required
def api_jupyter_instances():
    """API endpoint to get all Jupyter Lab instances"""
    instances = get_jupyter_instances()
    return jsonify({"instances": instances})


@lab.route("/admin/lab_create/<expid>", methods=["POST"])
@login_required
def api_create_notebook(expid):
    """API endpoint to create a new notebook"""
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

    jupyter_url = f"http://localhost:{inst['port']}/lab?token=embed-jupyter-token"

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
    )
