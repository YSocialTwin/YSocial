"""Lifecycle routes for client execution (run/pause/resume/stop/reset)."""

import json
import os
import shutil

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.routes.admin.sub.experiments._helpers import (
    _experiment_configuration_update_required,
)
from y_web.src.models import (
    Client,
    Client_Execution,
    Exps,
    Population,
)
from y_web.src.simulation.adhoc_client import start_adhoc_client, stop_adhoc_client
from y_web.src.simulation.execution_backend import (
    start_client_for_experiment,
    stop_client_for_experiment,
)
from y_web.src.system.miscellanea import check_privileges, get_db_type
from y_web.src.system.path_utils import get_resource_path

from ._blueprint import clientsr


def _hpc_client_process_still_running(exp, client) -> bool:
    """Return whether the tracked HPC client PID is still active for this client."""
    try:
        from y_web.src.hpc.client import (
            _hpc_process_matches_client,
            _is_hpc_client_process,
            _resolve_hpc_experiment_folder,
            _tracked_process_is_alive,
        )

        pid = getattr(client, "pid", None)
        if not pid:
            return False
        pid = int(pid)
        if not _tracked_process_is_alive(pid):
            return False
        if not _is_hpc_client_process(pid):
            return False
        exp_folder = _resolve_hpc_experiment_folder(exp)
        return bool(
            _hpc_process_matches_client(
                pid,
                cli_name=getattr(client, "name", None),
                exp_folder=exp_folder,
            )
        )
    except Exception:
        return False


@clientsr.route("/admin/reset_client/<int:uid>")
@login_required
def reset_client(uid):
    """Handle reset client operation."""
    check_privileges(current_user.username)

    from y_web.src.system.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # delete experiment json files
    client = Client.query.filter_by(id=uid).first()
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()
    path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}{population.name}.json"
    if os.path.exists(path):
        os.remove(path)

    path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json"
    if os.path.exists(path):
        os.remove(path)

    # copy the original prompts.json file
    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
        shutil.copy(
            prompts_src,
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json",
        )
    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copy(
            prompts_src,
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json",
        )
    else:
        raise Exception(f"unsupported platform: {exp.platform_type}")

    # delete client execution
    db.session.query(Client_Execution).filter_by(client_id=uid).delete()
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/extend_simulation/<int:id_client>", methods=["POST", "GET"])
@login_required
def extend_simulation(id_client):
    """Handle extend simulation operation."""
    check_privileges(current_user.username)

    # check if the client exists
    client = Client.query.filter_by(id=id_client).first()
    if client is None:
        flash("Client not found.", "error")
        return redirect(request.referrer)

    # get the days from the form
    days = int(request.form.get("days"))

    # get the client execution
    client_execution = Client_Execution.query.filter_by(client_id=id_client).first()

    # extend the simulation
    client_execution.expected_duration_rounds += int(days) * 24

    db.session.commit()

    # update the client days field
    client = db.session.query(Client).filter_by(id=id_client).first()
    client.days = int(client.days) + int(days)
    db.session.commit()

    # Check if the experiment was completed, and reset to stopped if so
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if exp and exp.exp_status == "completed":
        exp.exp_status = "stopped"
        db.session.commit()
        flash(
            f"Experiment '{exp.exp_name}' moved from completed to stopped (client duration extended).",
            "info",
        )

    # Update the client config JSON file for HPC experiments
    # This ensures the client uses the extended duration when restarted
    if exp and exp.simulator_type == "HPC":
        try:
            from y_web.src.system.path_utils import get_writable_path

            BASE = get_writable_path()
            dbtype = get_db_type()

            if dbtype == "sqlite":
                exp_folder = exp.db_name.split(os.sep)[1]
            else:
                exp_folder = exp.db_name.removeprefix("experiments_")

            # Get population for the client
            population = Population.query.filter_by(id=client.population_id).first()
            if not population:
                flash(
                    "Warning: Could not find population record. Extension applied to database only.",
                    "warning",
                )
            else:
                config_path = os.path.join(
                    BASE,
                    "y_web",
                    "experiments",
                    exp_folder,
                    f"client_{client.name}-{population.name}.json",
                )

                if os.path.exists(config_path):
                    # Read existing config
                    with open(config_path, "r") as f:
                        config = json.load(f)

                    # Update num_days in simulation config
                    if "simulation" in config:
                        config["simulation"]["num_days"] = days  # int(client.days)

                        # Write updated config back to file
                        with open(config_path, "w") as f:
                            json.dump(config, f, indent=2)

                        flash(
                            f"Client configuration file updated with extended duration ({client.days} days).",
                            "success",
                        )
                    else:
                        flash(
                            "Warning: Config file missing 'simulation' section. Extension applied to database only.",
                            "warning",
                        )
                else:
                    flash(
                        f"Warning: Client config file not found. Extension applied to database only.",
                        "warning",
                    )
        except Exception as e:
            flash(
                f"Warning: Could not update client config file: {str(e)}. Extension applied to database only.",
                "warning",
            )

        # Reset log metrics for HPC experiments to force re-parsing
        # This ensures plots (both client and server trends) show extended data
        try:
            from y_web.src.hpc.log_metrics import (
                update_client_log_metrics,
                update_server_log_metrics,
            )
            from y_web.src.hpc.log_offset import (
                reset_hpc_client_metrics,
                reset_hpc_server_metrics,
            )
            from y_web.src.system.path_utils import get_writable_path

            BASE = get_writable_path()

            # Get experiment folder for log files
            exp_uid = None
            if dbtype == "sqlite":
                exp_uid = exp.db_name.split(os.sep)[1]
            else:
                exp_uid = exp.db_name.removeprefix("experiments_")

            exp_folder_path = os.path.join(BASE, "y_web", "experiments", exp_uid)

            # For HPC experiments, logs are in /logs subfolder
            if exp.simulator_type == "HPC":
                log_folder_path = os.path.join(exp_folder_path, "logs")
            else:
                log_folder_path = exp_folder_path

            # Reset client metrics for this specific client
            reset_result_client = reset_hpc_client_metrics(exp.idexp, id_client)

            # Reset server metrics for the entire experiment
            # This is needed because server logs also reflect the extended simulation
            reset_result_server = reset_hpc_server_metrics(exp.idexp)

            # After resetting, immediately trigger re-parsing of existing log files
            # This populates the metrics with data from the original run
            reparse_success_client = False
            reparse_success_server = False

            if reset_result_client or reset_result_server:
                try:
                    # Re-parse client log if it exists and client reset succeeded
                    # Population is needed to construct the client log file name
                    if reset_result_client and population:
                        from y_web.src.hpc.client import resolve_hpc_client_log_path

                        client_log_path = resolve_hpc_client_log_path(
                            exp, client.name, log_folder=log_folder_path
                        )
                        if client_log_path and os.path.exists(client_log_path):
                            update_client_log_metrics(
                                exp.idexp, id_client, client_log_path, is_hpc=True
                            )
                            reparse_success_client = True

                    # Re-parse server log if it exists and server reset succeeded
                    if reset_result_server:
                        server_log_path = os.path.join(log_folder_path, "_server.log")
                        if os.path.exists(server_log_path):
                            update_server_log_metrics(
                                exp.idexp, server_log_path, is_hpc=True
                            )
                            reparse_success_server = True
                except Exception as e:
                    flash(
                        f"Warning: Metrics reset but re-parsing failed: {str(e)}. Plots will update on next refresh.",
                        "warning",
                    )

            # Provide comprehensive user feedback based on all possible outcomes
            if reset_result_client and reset_result_server:
                if reparse_success_client and reparse_success_server:
                    flash(
                        "Log metrics reset and re-parsed. Plots now show data from original run and will include extended data after client restart.",
                        "success",
                    )
                elif reparse_success_client or reparse_success_server:
                    # Partial re-parsing success
                    if reparse_success_client and not reparse_success_server:
                        flash(
                            "Client metrics reset and re-parsed. Server metrics reset but not re-parsed yet. Plots will fully update on next refresh.",
                            "success",
                        )
                    else:  # reparse_success_server and not reparse_success_client
                        flash(
                            "Server metrics reset and re-parsed. Client metrics reset but not re-parsed yet. Plots will fully update on next refresh.",
                            "success",
                        )
                else:
                    # Reset succeeded but re-parsing failed for both
                    flash(
                        "Log metrics reset. Plots will update with extended data on next refresh.",
                        "success",
                    )
            elif reset_result_client:
                # Only client reset succeeded
                if reparse_success_client:
                    flash(
                        "Client log metrics reset and re-parsed. Server metrics unchanged. Client plots updated.",
                        "success",
                    )
                else:
                    flash(
                        "Client log metrics reset. Server metrics unchanged. Client plots will update on next refresh.",
                        "success",
                    )
            elif reset_result_server:
                # Only server reset succeeded
                if reparse_success_server:
                    flash(
                        "Server log metrics reset and re-parsed. Client metrics unchanged. Server plots updated.",
                        "success",
                    )
                else:
                    flash(
                        "Server log metrics reset. Client metrics unchanged. Server plots will update on next refresh.",
                        "success",
                    )
            else:
                # Both resets failed
                flash(
                    "Warning: Could not reset log metrics. Plots may not show extended data.",
                    "warning",
                )
        except Exception as e:
            flash(
                f"Warning: Could not reset log metrics: {str(e)}. Plots may not show extended data.",
                "warning",
            )

    return redirect(request.referrer)


@clientsr.route("/admin/run_client/<int:uid>/<int:idexp>")
@login_required
def run_client(uid, idexp):
    """Handle run client operation."""
    from ..experiments import experiment_details

    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before running clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # For remote experiments, allow running clients without server check
    # For local experiments, check if the experiment is already running
    if exp.is_remote == 0 and exp.running == 0:
        return redirect(request.referrer)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()

    try:
        start_client_for_experiment(exp, client, population, resume=True)

        # set the client running status
        db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
        db.session.commit()

        # For remote experiments, set experiment to running when first client starts
        if exp.is_remote == 1 and exp.running == 0:
            db.session.query(Exps).filter_by(idexp=idexp).update(
                {Exps.running: 1, Exps.exp_status: "active"}
            )
            db.session.commit()
    except FileNotFoundError as e:
        # Display the error message to the user
        flash(f"Error starting client: {str(e)}", "error")
    except RuntimeError as e:
        flash(str(e), "warning")
    except Exception as e:
        # Catch any other errors
        flash(f"Unexpected error starting client: {str(e)}", "error")

    return experiment_details(idexp)


@clientsr.route("/admin/resume_client/<int:uid>/<int:idexp>")
@login_required
def resume_client(uid, idexp):
    """Handle resume client operation."""
    from ..experiments import experiment_details

    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before running clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # For remote experiments, allow running clients without server check
    # For local experiments, check if the experiment is already running
    if exp.is_remote == 0 and exp.running == 0:
        return redirect(request.referrer)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()

    try:
        start_client_for_experiment(exp, client, population, resume=True)

        # set the client running status
        db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
        db.session.commit()

        # For remote experiments, set experiment to running when first client starts
        if exp.is_remote == 1 and exp.running == 0:
            db.session.query(Exps).filter_by(idexp=idexp).update(
                {Exps.running: 1, Exps.exp_status: "active"}
            )
            db.session.commit()
    except FileNotFoundError as e:
        # Display the error message to the user
        flash(f"Error starting client: {str(e)}", "error")
    except RuntimeError as e:
        flash(str(e), "warning")
    except Exception as e:
        # Catch any other errors
        flash(f"Unexpected error starting client: {str(e)}", "error")

    return experiment_details(idexp)


@clientsr.route("/admin/pause_client/<int:uid>/<int:idexp>")
@login_required
def pause_client(uid, idexp):
    """Handle pause client operation."""
    from ..experiments import experiment_details

    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=idexp).first()
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before changing client execution state.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # get client and experiment
    client = Client.query.filter_by(id=uid).first()
    if client is None:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    stop_result = stop_client_for_experiment(exp, client, pause=True)

    if exp.simulator_type == "HPC":
        if _hpc_client_process_still_running(exp, client):
            client.status = 1
            flash(
                f"HPC client '{client.name}' is still running; status kept as running.",
                "warning",
            )
        elif stop_result is False:
            flash(
                f"Unable to confirm stop for HPC client '{client.name}'.",
                "warning",
            )
        else:
            client.status = 0
        db.session.commit()
    else:
        client.status = 0
        db.session.commit()

    # For remote experiments, check if all clients are stopped
    if exp.is_remote == 1:
        all_clients = Client.query.filter_by(id_exp=idexp).all()
        any_running = any(c.status == 1 for c in all_clients)
        if not any_running and exp.running == 1:
            # All clients stopped, set experiment to stopped
            db.session.query(Exps).filter_by(idexp=idexp).update(
                {Exps.running: 0, Exps.exp_status: "stopped"}
            )
            db.session.commit()

    return experiment_details(idexp)  # redirect(request.referrer)


@clientsr.route("/admin/stop_client/<int:uid>/<int:idexp>")
@login_required
def stop_client(uid, idexp):
    """Handle stop client operation."""
    from ..experiments import experiment_details

    check_privileges(current_user.username)

    # get client and experiment
    client = Client.query.filter_by(id=uid).first()
    exp = Exps.query.filter_by(idexp=idexp).first()
    if client is None:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))
    if exp is None:
        flash("Experiment not found.", "error")
        return redirect(request.referrer)

    stop_result = stop_client_for_experiment(exp, client, pause=False)

    if exp.simulator_type == "HPC":
        if _hpc_client_process_still_running(exp, client):
            client.status = 1
            flash(
                f"HPC client '{client.name}' is still running; status kept as running.",
                "warning",
            )
        elif stop_result is False:
            flash(
                f"Unable to confirm stop for HPC client '{client.name}'.",
                "warning",
            )
        else:
            client.status = 0
        db.session.commit()
    else:
        client.status = 0
        db.session.commit()

    # For remote experiments, check if all clients are stopped
    if exp.is_remote == 1:
        all_clients = Client.query.filter_by(id_exp=idexp).all()
        any_running = any(c.status == 1 for c in all_clients)
        if not any_running and exp.running == 1:
            # All clients stopped, set experiment to stopped
            db.session.query(Exps).filter_by(idexp=idexp).update(
                {Exps.running: 0, Exps.exp_status: "stopped"}
            )
            db.session.commit()

    return experiment_details(idexp)  # redirect(request.referrer)


@clientsr.route("/admin/run_adhoc_client/<int:idexp>/<path:client_key>")
@login_required
def run_adhoc_client(idexp, client_key):
    """Start a file-backed ad hoc plugin client."""
    from ..experiments import experiment_details

    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=idexp).first()
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before running ad hoc clients for this experiment.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    if exp.is_remote == 0 and exp.running == 0:
        flash("Start the experiment server before running ad hoc clients.", "warning")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    try:
        start_adhoc_client(exp, client_key)
    except FileNotFoundError as e:
        flash(f"Error starting ad hoc client: {str(e)}", "error")
    except Exception as e:
        flash(f"Unexpected error starting ad hoc client: {str(e)}", "error")

    return experiment_details(idexp)


@clientsr.route("/admin/pause_adhoc_client/<int:idexp>/<path:client_key>")
@login_required
def pause_adhoc_client(idexp, client_key):
    """Pause a file-backed ad hoc plugin client."""
    from ..experiments import experiment_details

    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=idexp).first()
    if _experiment_configuration_update_required(exp):
        flash(
            "Update Experiment Configuration before changing ad hoc client execution state.",
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    try:
        stop_adhoc_client(exp, client_key, pause=True)
    except FileNotFoundError as e:
        flash(f"Error pausing ad hoc client: {str(e)}", "error")
    except Exception as e:
        flash(f"Unexpected error pausing ad hoc client: {str(e)}", "error")

    return experiment_details(idexp)
