"""Recommender system and LLM update routes for clients."""
from flask import flash, redirect, url_for, request
from flask_login import current_user, login_required

from y_web import db
from y_web.src.models import (
    Agent,
    Agent_Population,
    Client,
    Exps,
    Population,
    User_mgmt,
)
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import clientsr
from ._crud import _get_experiment_mode

def _update_recsys_internal(uid, expected_mode):
    """Update recsys using the modality-specific route."""
    check_privileges(current_user.username)

    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.experiments"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.experiments"))

    actual_mode = _get_experiment_mode(exp)
    if actual_mode != expected_mode:
        flash("Update route does not match the experiment modality.", "error")
        if actual_mode == "hpc":
            return redirect(url_for("clientsr.client_details_hpc", uid=uid))
        if actual_mode == "forum":
            return redirect(url_for("clientsr.client_details_forum", uid=uid))
        return redirect(url_for("clientsr.client_details", uid=uid))

    # Update client's recsys settings
    client.crecsys = recsys_type
    client.frecsys = frecsys_type

    # get populations for client uid
    population = Population.query.filter_by(id=client.population_id).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=population.id).all()

    # updating the recommenders of the agents in the specific simulation instance (not in the population)
    for agent in agents:
        try:
            a = Agent.query.filter_by(id=agent.agent_id).first()
            user = (User_mgmt.query.filter_by(username=a.name)).first()
            user.frecsys_type = frecsys_type
            user.recsys_type = recsys_type
            db.session.commit()
        except:
            flash("The experiment needs to be activated first.", "error")
            return redirect(request.referrer)

    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/update_standard_recsys/<int:uid>", methods=["POST"])
@login_required
def update_standard_recsys(uid):
    """Update recommenders for a standard microblogging client."""
    return _update_recsys_internal(uid, "standard")


@clientsr.route("/admin/update_forum_recsys/<int:uid>", methods=["POST"])
@login_required
def update_forum_recsys(uid):
    """Update recommenders for a forum client."""
    return _update_recsys_internal(uid, "forum")


@clientsr.route("/admin/update_hpc_recsys/<int:uid>", methods=["POST"])
@login_required
def update_hpc_recsys(uid):
    """Update recommenders for an HPC client."""
    return _update_recsys_internal(uid, "hpc")


@clientsr.route("/admin/update_recsys/<int:uid>", methods=["POST"])
@login_required
def update_recsys(uid):
    """Backward-compatible dispatcher for recommender updates."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.experiments"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.experiments"))

    if getattr(exp, "simulator_type", "Standard") == "HPC":
        return update_hpc_recsys(uid)
    if exp.platform_type == "forum":
        return update_forum_recsys(uid)
    return update_standard_recsys(uid)


def _update_client_llm_internal(uid, expected_mode):
    """Update client LLM using the modality-specific route."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.experiments"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.experiments"))

    actual_mode = (
        "hpc"
        if getattr(exp, "simulator_type", "Standard") == "HPC"
        else ("forum" if exp.platform_type == "forum" else "standard")
    )
    if actual_mode != expected_mode:
        flash("Update route does not match the experiment modality.", "error")
        if actual_mode == "hpc":
            return redirect(url_for("clientsr.client_details_hpc", uid=uid))
        if actual_mode == "forum":
            return redirect(url_for("clientsr.client_details_forum", uid=uid))
        return redirect(url_for("clientsr.client_details", uid=uid))

    user_type = request.form.get("user_type")

    # get populations for client uid
    population = Population.query.filter_by(id=client.population_id).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=population.id).all()

    for agent in agents:
        try:
            a = Agent.query.filter_by(id=agent.agent_id).first()
            user = (User_mgmt.query.filter_by(username=a.name)).first()
            user.user_type = user_type
            db.session.commit()
        except:
            flash("The experiment needs to be activated first.", "error")
            return redirect(request.referrer)

    population.llm = user_type

    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/update_standard_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_standard_client_llm(uid):
    """Update LLM for a standard microblogging client."""
    return _update_client_llm_internal(uid, "standard")


@clientsr.route("/admin/update_forum_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_forum_client_llm(uid):
    """Update LLM for a forum client."""
    return _update_client_llm_internal(uid, "forum")


@clientsr.route("/admin/update_hpc_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_hpc_client_llm(uid):
    """Update LLM for an HPC client."""
    return _update_client_llm_internal(uid, "hpc")


@clientsr.route("/admin/update_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_llm(uid):
    """Backward-compatible dispatcher for client LLM updates."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.experiments"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.experiments"))

    if getattr(exp, "simulator_type", "Standard") == "HPC":
        return update_hpc_client_llm(uid)
    if exp.platform_type == "forum":
        return update_forum_client_llm(uid)
    return update_standard_client_llm(uid)
