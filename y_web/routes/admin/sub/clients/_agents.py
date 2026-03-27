"""Agent activity and archetype update routes."""

import json
import os

from flask import flash, redirect, request
from flask_login import current_user, login_required

from y_web import db
from y_web.src.models import (
    Client,
    Exps,
    Population,
)
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import clientsr


@clientsr.route("/admin/update_agents_activity/<int:uid>", methods=["POST"])
@login_required
def update_agents_activity(uid):
    """Update agents activity."""
    check_privileges(current_user.username)

    # get data from form
    activity = {}
    for x in request.form:
        activity[str(x)] = float(request.form.get(str(x)))

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.src.system.path_utils import get_writable_path

    BASE = get_writable_path()
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
            config["simulation"]["hourly_activity"] = activity
            # save the new configuration
            json.dump(config, open(path, "w"), indent=4)
    else:
        flash("Configuration file not found.", "error")

    return redirect(request.referrer)


@clientsr.route("/admin/reset_agents_activity/<int:uid>")
@login_required
def reset_agents_activity(uid):
    """Handle reset agents activity operation."""
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.src.system.path_utils import get_writable_path

    BASE = get_writable_path()
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
            config["simulation"]["hourly_activity"] = {
                "10": 0.021,
                "16": 0.032,
                "8": 0.020,
                "12": 0.024,
                "15": 0.032,
                "17": 0.032,
                "23": 0.025,
                "6": 0.017,
                "18": 0.032,
                "11": 0.022,
                "13": 0.027,
                "14": 0.030,
                "20": 0.030,
                "21": 0.029,
                "7": 0.018,
                "22": 0.027,
                "9": 0.020,
                "3": 0.020,
                "5": 0.017,
                "4": 0.018,
                "1": 0.021,
                "2": 0.020,
                "0": 0.023,
                "19": 0.031,
            }
            # save the new configuration
            json.dump(config, open(path, "w"), indent=4)
    else:
        flash("Configuration file not found.", "error")

    return redirect(request.referrer)


@clientsr.route("/admin/update_agent_archetypes/<int:uid>", methods=["POST"])
@login_required
def update_agent_archetypes(uid):
    """Update agent archetypes and transition probabilities."""
    check_privileges(current_user.username)

    # Get data from form with validation
    try:
        archetype_validator = (
            float(request.form.get("archetype_validator", "0")) / 100.0
        )
        archetype_broadcaster = (
            float(request.form.get("archetype_broadcaster", "0")) / 100.0
        )
        archetype_explorer = float(request.form.get("archetype_explorer", "0")) / 100.0

        # Get transition probabilities
        trans_val_val = float(request.form.get("trans_val_val", "0")) / 100.0
        trans_val_broad = float(request.form.get("trans_val_broad", "0")) / 100.0
        trans_val_expl = float(request.form.get("trans_val_expl", "0")) / 100.0
        trans_broad_broad = float(request.form.get("trans_broad_broad", "0")) / 100.0
        trans_broad_val = float(request.form.get("trans_broad_val", "0")) / 100.0
        trans_broad_expl = float(request.form.get("trans_broad_expl", "0")) / 100.0
        trans_expl_expl = float(request.form.get("trans_expl_expl", "0")) / 100.0
        trans_expl_val = float(request.form.get("trans_expl_val", "0")) / 100.0
        trans_expl_broad = float(request.form.get("trans_expl_broad", "0")) / 100.0
    except (ValueError, TypeError) as e:
        flash(f"Invalid input values: {str(e)}", "error")
        return redirect(request.referrer)

    # Validate that percentages sum to approximately 100%
    archetype_sum = archetype_validator + archetype_broadcaster + archetype_explorer
    if abs(archetype_sum - 1.0) > 0.01:
        flash(
            f"Archetype percentages must sum to 100% (current sum: {archetype_sum * 100:.1f}%)",
            "error",
        )
        return redirect(request.referrer)

    # Validate transition probabilities sum to 100% for each row
    val_sum = trans_val_val + trans_val_broad + trans_val_expl
    broad_sum = trans_broad_broad + trans_broad_val + trans_broad_expl
    expl_sum = trans_expl_expl + trans_expl_val + trans_expl_broad

    if abs(val_sum - 1.0) > 0.01:
        flash(
            f"Validator transition probabilities must sum to 100% (current sum: {val_sum * 100:.1f}%)",
            "error",
        )
        return redirect(request.referrer)
    if abs(broad_sum - 1.0) > 0.01:
        flash(
            f"Broadcaster transition probabilities must sum to 100% (current sum: {broad_sum * 100:.1f}%)",
            "error",
        )
        return redirect(request.referrer)
    if abs(expl_sum - 1.0) > 0.01:
        flash(
            f"Explorer transition probabilities must sum to 100% (current sum: {expl_sum * 100:.1f}%)",
            "error",
        )
        return redirect(request.referrer)

    # Get client details
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(request.referrer)

    # Update client with new values
    client.archetype_validator = archetype_validator
    client.archetype_broadcaster = archetype_broadcaster
    client.archetype_explorer = archetype_explorer
    client.trans_val_val = trans_val_val
    client.trans_val_broad = trans_val_broad
    client.trans_val_expl = trans_val_expl
    client.trans_broad_broad = trans_broad_broad
    client.trans_broad_val = trans_broad_val
    client.trans_broad_expl = trans_broad_expl
    client.trans_expl_expl = trans_expl_expl
    client.trans_expl_val = trans_expl_val
    client.trans_expl_broad = trans_expl_broad

    db.session.commit()

    # Update client configuration JSON file
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.src.system.path_utils import get_writable_path

    BASE = get_writable_path()
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)

            # Add agent archetypes section if not present
            if "agent_archetypes" not in config:
                config["agent_archetypes"] = {}

            config["agent_archetypes"] = {
                "distribution": {
                    "validator": archetype_validator,
                    "broadcaster": archetype_broadcaster,
                    "explorer": archetype_explorer,
                },
                "transitions": {
                    "validator": {
                        "validator": trans_val_val,
                        "broadcaster": trans_val_broad,
                        "explorer": trans_val_expl,
                    },
                    "broadcaster": {
                        "validator": trans_broad_val,
                        "broadcaster": trans_broad_broad,
                        "explorer": trans_broad_expl,
                    },
                    "explorer": {
                        "validator": trans_expl_val,
                        "broadcaster": trans_expl_broad,
                        "explorer": trans_expl_expl,
                    },
                },
            }

            # Save the new configuration
            with open(path, "w") as f:
                json.dump(config, f, indent=4)
    else:
        flash("Configuration file not found.", "error")

    flash("Agent archetypes updated successfully.", "success")
    return redirect(request.referrer)


@clientsr.route("/admin/reset_agent_archetypes/<int:uid>")
@login_required
def reset_agent_archetypes(uid):
    """Reset agent archetypes and transitions to default Bluesky values."""
    check_privileges(current_user.username)

    # Get client details
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(request.referrer)

    # Reset to default Bluesky values
    client.archetype_validator = 0.52
    client.archetype_broadcaster = 0.20
    client.archetype_explorer = 0.28
    client.trans_val_val = 0.853
    client.trans_val_broad = 0.081
    client.trans_val_expl = 0.066
    client.trans_broad_broad = 0.729
    client.trans_broad_val = 0.195
    client.trans_broad_expl = 0.075
    client.trans_expl_expl = 0.490
    client.trans_expl_val = 0.364
    client.trans_expl_broad = 0.146

    db.session.commit()

    # Update client configuration JSON file
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.src.system.path_utils import get_writable_path

    BASE = get_writable_path()
    exp_folder = experiment.db_name.split(os.sep)[1]

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)

            config["agent_archetypes"] = {
                "distribution": {
                    "validator": 0.52,
                    "broadcaster": 0.20,
                    "explorer": 0.28,
                },
                "transitions": {
                    "validator": {
                        "validator": 0.853,
                        "broadcaster": 0.081,
                        "explorer": 0.066,
                    },
                    "broadcaster": {
                        "validator": 0.195,
                        "broadcaster": 0.729,
                        "explorer": 0.075,
                    },
                    "explorer": {
                        "validator": 0.364,
                        "broadcaster": 0.146,
                        "explorer": 0.490,
                    },
                },
            }

            # Save the new configuration
            with open(path, "w") as f:
                json.dump(config, f, indent=4)
    else:
        flash("Configuration file not found.", "error")

    flash("Agent archetypes reset to default values.", "success")
    return redirect(request.referrer)
