"""
Ollama LLM management routes.

Administrative routes for managing Ollama LLM models including starting
the server, pulling/downloading models, deleting models, and monitoring
download progress.
"""

from flask import (
    Blueprint,
    redirect,
    request,
)
from flask_login import login_required, current_user

from y_web.models import Ollama_Pull
from y_web.utils import (
    start_ollama_server,
    is_ollama_running,
    is_ollama_installed,
    pull_ollama_model,
    delete_ollama_model,
    delete_model_pull,
)
import json
from y_web import db
from y_web.utils.miscellanea import check_privileges

ollama = Blueprint("ollama", __name__)


def ollama_status():
    """
    Get Ollama service status.
    
    Returns:
        Dictionary with 'status' (running) and 'installed' flags
    """
    return {
        "status": is_ollama_running(),
        "installed": is_ollama_installed(),
    }


@ollama.route("/admin/start_ollama/", methods=["POST", "GET"])
@login_required
def start_ollama():
    """
    Start the Ollama LLM server.
    
    Returns:
        Redirect to referrer page
    """
    check_privileges(current_user.username)

    # start the ollama server
    start_ollama_server()

    return redirect(request.referrer)


@ollama.route("/admin/ollama_pull/", methods=["POST"])
@login_required
def ollama_pull():
    """
    Initiate download of an Ollama model.
    
    Form data:
        model_name: Name of model to download
        
    Returns:
        Redirect to referrer page
    """
    check_privileges(current_user.username)

    # get model_name by form
    model_name = request.form.get("model_name")

    # pull the model from the ollama server
    try:
        pull_ollama_model(model_name)
    except:
        return redirect(request.referrer)

    return redirect(request.referrer)


@ollama.route("/admin/ollama_cancel_pull/<string:model_name>", methods=["POST"])
@login_required
def ollama_cancel_pull(model_name):
    """
    Cancel an ongoing model download.
    
    Args:
        model_name: Name of model to cancel download for
        
    Returns:
        Redirect to referrer page
    """
    check_privileges(current_user.username)

    delete_model_pull(model_name)

    return redirect(request.referrer)


@ollama.route("/admin/delete_model/<string:model_name>")
@login_required
def delete_model(model_name):
    """
    Delete an Ollama model from the system.
    
    Args:
        model_name: Name of model to delete
        
    Returns:
        Redirect to referrer page
    """
    check_privileges(current_user.username)

    # delete the model from the ollama server
    delete_ollama_model(model_name)

    Ollama_Pull.query.filter_by(model_name=model_name).delete()
    db.session.commit()

    return redirect(request.referrer)


@ollama.route("/admin/pull_progress/<string:model_name>")
def get_pull_progress(model_name):
    """
    Get download progress for an Ollama model (AJAX endpoint).
    
    Args:
        model_name: Name of model to check progress for
        
    Returns:
        JSON with 'progress' (0-100) and 'model_name'
    """
    # get client_execution
    model = Ollama_Pull.query.filter_by(model_name=model_name).first()

    if model is None:
        return json.dumps({"progress": 0})
    progress = int(100 * float(model.status))

    if progress == 100:
        # delete the model from the table
        db.session.query(Ollama_Pull).delete()

    return json.dumps({"progress": progress, "model_name": model.model_name})
