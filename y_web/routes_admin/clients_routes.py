"""
Client simulation management routes.

Administrative routes for configuring and managing simulation clients,
including behavior parameters, LLM settings, network topology, and
client execution control (start/pause/resume/terminate).
"""

import json
import os
import random
import shutil
import sys
import traceback

import faker
import networkx as nx
import numpy as np
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from y_web import db
from y_web.models import (
    ActivityProfile,
    AgeClass,
    Agent,
    Agent_Population,
    Agent_Profile,
    Client,
    Client_Execution,
    Content_Recsys,
    Exp_Topic,
    Exps,
    Follow_Recsys,
    OpinionDistribution,
    OpinionGroup,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Topic_List,
    User_mgmt,
)
from y_web.utils import (
    get_db_type,
    get_llm_models,
    get_ollama_models,
    start_client,
    start_hpc_client,
    stop_hpc_client,
    terminate_client,
)
from y_web.utils.desktop_file_handler import send_file_desktop
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status
from y_web.utils.path_utils import get_resource_path

clientsr = Blueprint("clientsr", __name__)

# Constants for opinion distribution sampling
DISTRIBUTION_SCALE_FACTOR = 10.0  # Scale factor for gamma/lognormal distributions


def allocate_topics_by_percentage(topics, topic_percentages):
    """
    Allocate topics to an agent based on specified interest percentages.

    Args:
        topics: List of topic names
        topic_percentages: Dict mapping topic names to percentage (0-100)

    Returns:
        List of topics the agent is interested in
    """
    agent_topics = []
    for topic in topics:
        percentage = topic_percentages.get(
            topic, 100.0
        )  # Default to 100% if not specified
        # Randomly decide if agent is interested based on percentage
        if random.random() <= percentage / 100.0:
            agent_topics.append(topic)

    # Ensure at least one topic if any topics have non-zero percentage
    if not agent_topics and any(topic_percentages.get(t, 100.0) > 0 for t in topics):
        # Pick one topic probabilistically based on percentages
        valid_topics = [t for t in topics if topic_percentages.get(t, 100.0) > 0]
        if valid_topics:
            weights = [topic_percentages.get(t, 100.0) for t in valid_topics]
            agent_topics = [random.choices(valid_topics, weights=weights)[0]]

    return agent_topics if agent_topics else []


@clientsr.route("/admin/reset_client/<int:uid>")
@login_required
def reset_client(uid):
    """Handle reset client operation."""
    check_privileges(current_user.username)

    from y_web.utils.path_utils import get_writable_path

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
    days = request.form.get("days")

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
            from y_web.utils.path_utils import get_writable_path

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
            from y_web.utils.log_metrics import (
                reset_hpc_client_metrics,
                reset_hpc_server_metrics,
                update_client_log_metrics,
                update_server_log_metrics,
            )
            from y_web.utils.path_utils import get_writable_path

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
                        client_log_path = os.path.join(
                            log_folder_path, f"{client.name}_client.log"
                        )
                        if os.path.exists(client_log_path):
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
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # For remote experiments, allow running clients without server check
    # For local experiments, check if the experiment is already running
    if exp.is_remote == 0 and exp.running == 0:
        return redirect(request.referrer)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()
    if exp.simulator_type == "HPC":
        start_hpc_client(exp, client, population)
    else:
        start_client(exp, client, population, resume=True)

    # set the client running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    # For remote experiments, set experiment to running when first client starts
    if exp.is_remote == 1 and exp.running == 0:
        db.session.query(Exps).filter_by(idexp=idexp).update(
            {Exps.running: 1, Exps.exp_status: "active"}
        )
        db.session.commit()

    return experiment_details(idexp)


@clientsr.route("/admin/resume_client/<int:uid>/<int:idexp>")
@login_required
def resume_client(uid, idexp):
    """Handle resume client operation."""
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # For remote experiments, allow running clients without server check
    # For local experiments, check if the experiment is already running
    if exp.is_remote == 0 and exp.running == 0:
        return redirect(request.referrer)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()
    if exp.simulator_type == "HPC":
        start_hpc_client(exp, client, population)
    else:
        start_client(exp, client, population, resume=True)

    # set the client running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    # For remote experiments, set experiment to running when first client starts
    if exp.is_remote == 1 and exp.running == 0:
        db.session.query(Exps).filter_by(idexp=idexp).update(
            {Exps.running: 1, Exps.exp_status: "active"}
        )
        db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/pause_client/<int:uid>/<int:idexp>")
@login_required
def pause_client(uid, idexp):
    """Handle pause client operation."""
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client and experiment
    client = Client.query.filter_by(id=uid).first()
    exp = Exps.query.filter_by(idexp=idexp).first()

    if exp.simulator_type == "HPC":
        stop_hpc_client(client)
    else:
        terminate_client(client, pause=True)

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
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client and experiment
    client = Client.query.filter_by(id=uid).first()
    exp = Exps.query.filter_by(idexp=idexp).first()

    if exp.simulator_type == "HPC":
        stop_hpc_client(client)
    else:
        terminate_client(client, pause=False)

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


@clientsr.route("/admin/clients")
@login_required
def clients_list():
    """Display list of experiments for client management selection."""
    check_privileges(current_user.username)
    
    # Get all experiments
    experiments = Exps.query.all()
    
    return render_template(
        "admin/select_experiment_clients.html",
        experiments=experiments,
    )


@clientsr.route("/admin/clients/<idexp>")
@login_required
def clients(idexp):
    """Handle clients operation."""
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()

    # get only populations already associated with this experiment
    pop_exp_associations = Population_Experiment.query.filter_by(id_exp=idexp).all()
    population_ids = [pe.id_population for pe in pop_exp_associations]

    # get only populations  that are not associated with this experiment
    pops = (
        Population.query.filter(~Population.id.in_(population_ids)).all()
        if population_ids
        else Population.query.all()
    )

    # Get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topics_list = [{"id": t.id, "name": t.name} for t in topics_objs]

    # Check if LLM agents are enabled for this experiment
    llm_agents_enabled = (
        exp.llm_agents_enabled if hasattr(exp, "llm_agents_enabled") else True
    )

    # Check simulator type to render appropriate template
    simulator_type = (
        exp.simulator_type if hasattr(exp, "simulator_type") else "Standard"
    )

    # Get all recsys and filter by enabled field based on simulator type
    crecsys_all = Content_Recsys.query.all()
    frecsys_all = Follow_Recsys.query.all()

    if simulator_type == "HPC":
        template_name = "admin/clients_hpc.html"
        # Filter for HPC - only show recsys with "HPC" in enabled field
        crecsys = [r for r in crecsys_all if r.enabled and "HPC" in r.enabled]
        frecsys = [r for r in frecsys_all if r.enabled and "HPC" in r.enabled]
    else:
        template_name = "admin/clients.html"
        # Filter for Standard - only show recsys with "Standard" in enabled field
        crecsys = [r for r in crecsys_all if r.enabled and "Standard" in r.enabled]
        frecsys = [r for r in frecsys_all if r.enabled and "Standard" in r.enabled]

    return render_template(
        template_name,
        experiment=exp,
        populations=pops,
        crecsys=crecsys,
        frecsys=frecsys,
        llm_agents_enabled=llm_agents_enabled,
        topics=topics_list,
    )


def generate_hpc_client_config(
    client_name,
    namespace,
    llm_backend,
    llm_config,
    llm_v_config,
    simulation_config,
    agents_config,
    logging_config,
    enable_sentiment,
    emotion_annotation,
    enable_toxicity,
    perspective_api_key,
    server_address=None,
    server_port=None,
):
    """Generate client configuration for HPC simulator type.

    Args:
        client_name: Name of the client
        namespace: Experiment name (not db_name)
        server_address: Server address for remote experiments
        server_port: Server port for remote experiments
        ...
    """
    config = {
        "client_name": client_name,
        "namespace": namespace,
        "server": {"address": server_address, "port": server_port},
        "llm": llm_config,
        "llm_v": llm_v_config,
        "simulation": simulation_config,
        "agents": agents_config,
        "logging": logging_config,
    }
    return config


def create_hpc_client(exp, name, descr, population_id, form_data):
    """Create an HPC client with comprehensive configuration from form and server config."""
    import json
    import shutil

    from y_web.utils.path_utils import get_resource_path, get_writable_path

    BASE_DIR = get_writable_path()

    # Get population
    population = Population.query.filter_by(id=population_id).first()
    if not population:
        flash("Population not found")
        return redirect(request.referrer)

    # Check if client name already exists
    if Client.query.filter_by(name=name).first():
        flash("Client name already exists.", "error")
        return redirect(request.referrer)

    # Extract all form data
    days = int(form_data.get("days", "3"))
    percentage_new_agents_iteration = float(
        form_data.get("percentage_new_agents_iteration", "0.0")
    )
    percentage_removed_agents_iteration = float(
        form_data.get("percentage_removed_agents_iteration", "0.0")
    )
    max_length_thread_reading = int(form_data.get("max_length_thread_reading", "5"))
    reading_from_follower_ratio = float(
        form_data.get("reading_from_follower_ratio", "0.6")
    )
    probability_of_daily_follow = float(
        form_data.get("probability_of_daily_follow", "0.1")
    )
    probability_of_secondary_follow = float(
        form_data.get("probability_of_secondary_follow", "0.1")
    )
    attention_window = int(form_data.get("attention_window", "336"))
    visibility_rounds = int(form_data.get("visibility_rounds", "36"))
    batch_size = int(form_data.get("batch_size", "100"))

    # Follow action decay parameters
    follow_decay_enabled = form_data.get("follow_decay_enabled") == "on"
    follow_decay_function = form_data.get("follow_decay_function", "exponential")
    follow_decay_half_life = int(form_data.get("follow_decay_half_life", "168"))
    follow_decay_rate = float(form_data.get("follow_decay_rate", "0.01"))
    follow_decay_min_ratio = float(form_data.get("follow_decay_min_ratio", "0.1"))

    # Action likelihoods
    post = float(form_data.get("post", "3.0"))
    share = float(form_data.get("share", "1.0"))
    image = float(form_data.get("image", "0.0"))
    comment = float(form_data.get("comment", "5.0"))
    read = float(form_data.get("read", "2.0"))
    news = float(form_data.get("news", "0.0"))
    search = float(form_data.get("search", "5.0"))
    vote = float(form_data.get("vote", "0.0"))
    share_link = float(form_data.get("share_link", "0.0"))
    # Follow action - default 0.0 matches form default. Previously hardcoded at 0.1,
    # now configurable via form field
    follow = float(form_data.get("follow", "0.0"))

    # RecSys
    crecsys = form_data.get("recsys_type", "random")
    if crecsys == "ContentRecSys":
        crecsys = "random"
    frecsys = form_data.get("frecsys_type", "random")
    if frecsys == "FollowRecSys":
        frecsys = "random"

    # Agent archetypes
    enable_archetypes = form_data.get("enable_archetypes") == "on"
    agent_downcast = form_data.get("agent_downcast") == "on"
    archetype_validator = float(form_data.get("archetype_validator", "0.33"))
    archetype_broadcaster = float(form_data.get("archetype_broadcaster", "0.33"))
    archetype_explorer = float(form_data.get("archetype_explorer", "0.34"))

    # Archetype transitions
    trans_val_val = float(form_data.get("trans_val_val", "0.85"))
    trans_val_broad = float(form_data.get("trans_val_broad", "0.1"))
    trans_val_expl = float(form_data.get("trans_val_expl", "0.05"))
    trans_broad_val = float(form_data.get("trans_broad_val", "0.1"))
    trans_broad_broad = float(form_data.get("trans_broad_broad", "0.8"))
    trans_broad_expl = float(form_data.get("trans_broad_expl", "0.1"))
    trans_expl_val = float(form_data.get("trans_expl_val", "0.05"))
    trans_expl_broad = float(form_data.get("trans_expl_broad", "0.1"))
    trans_expl_expl = float(form_data.get("trans_expl_expl", "0.85"))

    # Extract LLM backend
    llm_backend = form_data.get(
        "llm_backend", "ollama"
    )  # Changed default from vllm to ollama for HPC

    # Check if LLM agents are enabled
    llm_agents_enabled = (
        bool(exp.llm_agents_enabled) if hasattr(exp, "llm_agents_enabled") else True
    )

    # Build LLM config based on backend and LLM agents enabled status
    if not llm_agents_enabled:
        # LLM agents not enabled - use Ollama defaults for consistency
        llm_config = {
            "address": "localhost",
            "port": 11434,
            "model": "llama3.2",
            "temperature": 0.9,
            "llm_api_key": "NULL",
            "llm_max_tokens": -1,
        }
        llm_v_config = {
            "address": "localhost",
            "port": 11434,
            "model": "minicpm-v",
            "temperature": 0.5,
            "llm_api_key": "NULL",
            "llm_max_tokens": 300,
        }
    elif llm_backend == "vllm":
        llm_config = {
            "backend": "vllm",
            "model": form_data.get("llm_model", "AMead10/Llama-3.2-3B-Instruct-AWQ"),
            "temperature": float(form_data.get("llm_temperature", "0.9")),
            "max_tokens": int(form_data.get("llm_max_tokens", "256")),
            "max_model_len": int(form_data.get("llm_max_model_len", "4096")),
            "tensor_parallel_size": int(form_data.get("llm_tensor_parallel_size", "1")),
            "gpu_memory_utilization": float(
                form_data.get("llm_gpu_memory_utilization", "0.15")
            ),
            "enable_flashattention": form_data.get("llm_enable_flashattention")
            == "true",
            "num_actors": int(form_data.get("llm_num_actors", "4")),
            "gpu_per_actor": float(form_data.get("llm_gpu_per_actor", "1.0")),
            "reuse_actors": form_data.get("llm_reuse_actors") == "true",
            "actor_name_prefix": form_data.get("llm_actor_name_prefix", "ysim_llm"),
        }

        llm_v_config = {
            "model": form_data.get("llm_v_model", "openbmb/MiniCPM-V-2_6-int4"),
            "temperature": float(form_data.get("llm_v_temperature", "0.5")),
            "max_tokens": int(form_data.get("llm_v_max_tokens", "300")),
            "max_model_len": int(form_data.get("llm_v_max_model_len", "4096")),
            "gpu_memory_utilization": float(
                form_data.get("llm_v_gpu_memory_utilization", "0.15")
            ),
        }
    else:  # ollama
        llm_config = {
            "address": "localhost",
            "port": 11434,
            "model": form_data.get("user_type", "llama3.2"),
            "temperature": float(form_data.get("llm_temperature", "0.7")),
            "llm_api_key": "NULL",
            "llm_max_tokens": -1,
        }
        llm_v_config = {}

    # Get activity profiles for population
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )
    activity_profiles = [a.activity_profile for a in activity_profiles]
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )
    profiles = {ap.name: ap.hours for ap in activity_profiles}

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = form_data.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    # Get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=exp.idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    discussion_topics = [t.name for t in topics_objs]
    topics = discussion_topics  # Use topic names (strings) for JSON serialization

    # Get topic interest percentages from form
    topic_percentages = {}
    for topic_obj in topics_objs:
        percentage_key = f"topic_interest_{topic_obj.id}"
        percentage_value = form_data.get(percentage_key, "100")
        try:
            topic_percentages[topic_obj.name] = float(percentage_value)
        except (ValueError, TypeError):
            topic_percentages[topic_obj.name] = 100.0  # Default to 100% if invalid

    # Read server config to get shared values
    if "database_server.db" in exp.db_name:
        uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")

    exp_dir = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}"
    server_config_path = f"{exp_dir}{os.sep}config_server.json"

    # Get sentiment and emotion annotation from server config
    annotations = exp.annotations.split(",") if exp.annotations else []
    enable_sentiment = "sentiment" in annotations
    emotion_annotation = "emotion" in annotations
    enable_toxicity = "toxicity" in annotations
    perspective_api_key = (
        exp.perspective_api if hasattr(exp, "perspective_api") else None
    )

    # Build simulation config (with annotation fields inside)
    simulation_config = {
        "num_days": days,
        "num_slots_per_day": 24,
        "heartbeat_interval": 5,
        "note": "num_days=0 means infinite simulation, set to a positive number to limit duration. heartbeat_interval in seconds (default: 5).",
        "percentage_new_agents_iteration": percentage_new_agents_iteration,
        "percentage_removed_agents_iteration": percentage_removed_agents_iteration,
        "discussion_topics": discussion_topics,
        "activity_profiles": profiles,
        "hourly_activity": hourly_activity,
        "actions_likelihood": {
            "post": post,
            "image": image,
            "news": news,
            "comment": comment,
            "read": read,
            "share": share,
            "search": search,
            "cast": vote,
            "share_link": share_link,
            "follow": follow,
        },
        "agent_archetypes": {
            "enabled": enable_archetypes,
            "agent_downcast": agent_downcast,
            "distribution": {
                "validator": archetype_validator,
                "broadcaster": archetype_broadcaster,
                "explorer": archetype_explorer,
            },
        },
        "enable_sentiment": enable_sentiment,
        "emotion_annotation": emotion_annotation,
        "enable_toxicity": enable_toxicity,
        "perspective_api_key": perspective_api_key,
    }

    # Build agents config
    agents_config = {
        "reading_from_follower_ratio": reading_from_follower_ratio,
        "max_length_thread_reading": max_length_thread_reading,
        "attention_window": attention_window,
        "probability_of_daily_follow": probability_of_daily_follow,
        "probability_of_secondary_follow": probability_of_secondary_follow,
        "follow_action_decay": {
            "enabled": follow_decay_enabled,
            "decay_function": follow_decay_function,
            "half_life_rounds": follow_decay_half_life,
            "decay_rate": follow_decay_rate,
            "min_probability_ratio": follow_decay_min_ratio,
        },
        "batch_size": batch_size,
        "churn": {
            "enabled": True,
            "churn_probability": 0.01,
            "inactivity_threshold": 5,
            "churn_percentage": 0.1,
        },
        "new_agents": {
            "enabled": True,
            "probability_new_agents": 0.01,
            "percentage_new_agents": 0.01,
        },
    }

    # Logging config
    logging_config = {
        "enable_execution_log": True,
        "enable_actor_log": True,
        "enable_client_log": True,
        "enable_console_log": True,
        "enable_llm_usage_log": True,
    }

    # Generate HPC client config
    # For remote experiments, include server address and port
    server_address = exp.server if exp.is_remote == 1 else None
    server_port = exp.port if exp.is_remote == 1 else None

    config = generate_hpc_client_config(
        client_name=name,
        namespace=exp.exp_name,
        llm_backend=llm_backend,
        llm_config=llm_config,
        llm_v_config=llm_v_config,
        simulation_config=simulation_config,
        agents_config=agents_config,
        logging_config=logging_config,
        enable_sentiment=enable_sentiment,
        emotion_annotation=emotion_annotation,
        enable_toxicity=enable_toxicity,
        perspective_api_key=perspective_api_key,
        server_address=server_address,
        server_port=server_port,
    )

    # Save config file using standard naming pattern
    config_filename = f"{exp_dir}{os.sep}client_{name}-{population.name}.json"
    with open(config_filename, "w") as f:
        json.dump(config, f, indent=2)

    # Create agent population file (same as standard pipeline)
    population_filename = f"{exp_dir}{os.sep}{population.name}.json"

    # Get agents for this population
    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    # Assign archetypes to agents based on distribution probabilities
    num_agents = len(agents)
    archetype_assignments = []

    if enable_archetypes and num_agents > 0:
        # Build list of active archetypes and their probabilities
        active_archetypes = []
        active_probabilities = []

        if archetype_validator > 0:
            active_archetypes.append("validator")
            active_probabilities.append(archetype_validator)

        if archetype_broadcaster > 0:
            active_archetypes.append("broadcaster")
            active_probabilities.append(archetype_broadcaster)

        if archetype_explorer > 0:
            active_archetypes.append("explorer")
            active_probabilities.append(archetype_explorer)

        # Normalize probabilities if they don't sum to 1
        if len(active_probabilities) > 0:
            total_prob = sum(active_probabilities)
            if total_prob > 0:
                active_probabilities = [p / total_prob for p in active_probabilities]
                # Assign archetypes to agents using numpy random choice
                import numpy as np

                archetype_assignments = np.random.choice(
                    active_archetypes, size=num_agents, p=active_probabilities
                ).tolist()
            else:
                archetype_assignments = [None] * num_agents
        else:
            archetype_assignments = [None] * num_agents
    else:
        archetype_assignments = [None] * num_agents

    # Build agent population JSON
    import random
    import uuid

    import faker

    population_data = {"agents": []}
    for idx, agent in enumerate(agents):
        custom_prompt = Agent_Profile.query.filter_by(agent_id=agent.id).first()
        custom_prompt = custom_prompt.profile if custom_prompt else None

        # Allocate topics based on specified percentages
        interests = allocate_topics_by_percentage(topics, topic_percentages)

        activity_profile_obj = (
            db.session.query(ActivityProfile)
            .filter_by(id=agent.activity_profile)
            .first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        # Get opinions enabled from experiment annotations
        opinions_enabled = "opinions" in (
            exp.annotations.split(",") if exp.annotations else []
        )

        agent_data = {
            "id": str(uuid.uuid4()),
            "username": agent.name,
            "email": f"{agent.name}@ysocial.it",
            "password": f"{agent.name}",
            "age": agent.age,
            "user_type": "agent",
            "leaning": agent.leaning,
            "interests": [interests, len(interests)],
            "oe": agent.oe,
            "co": agent.co,
            "ex": agent.ex,
            "ag": agent.ag,
            "ne": agent.ne,
            "recsys_type": crecsys,
            "frecsys_type": frecsys,
            "language": agent.language,
            "owner": exp.owner,
            "education_level": agent.education_level,
            "round_actions": int(agent.round_actions),
            "gender": agent.gender,
            "nationality": agent.nationality,
            "toxicity": agent.toxicity,
            "is_page": 0,
            "prompts": custom_prompt,
            "daily_activity_level": agent.daily_activity_level,
            "profession": agent.profession,
            "activity_profile": activity_profile_name,
            "archetype": archetype_assignments[idx],
            "opinions": (
                {i: random.random() for i in interests} if opinions_enabled else None
            ),
            "llm": bool(exp.llm_agents_enabled),
        }
        population_data["agents"].append(agent_data)

    # Add pages to population data
    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

    for page in pages:
        # Get page topics
        page_topics = (
            db.session.query(Exp_Topic, Topic_List)
            .join(Topic_List)
            .filter(Exp_Topic.exp_id == exp.idexp, Exp_Topic.topic_id == Topic_List.id)
            .all()
        )
        page_topics = [t[1].name for t in page_topics]
        page_topics = list(set(page_topics) & set(topics))

        activity_profile_obj = (
            db.session.query(ActivityProfile)
            .filter_by(id=page.activity_profile)
            .first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        page_data = {
            "id": str(uuid.uuid4()),
            "username": page.name,
            "email": f"{page.name}@ysocial.it",
            "password": f"{page.name}",
            "age": 0,
            "user_type": "page",
            "leaning": page.leaning,
            "interests": [page_topics, len(page_topics)],
            "oe": "",
            "co": "",
            "ex": "",
            "ag": "",
            "ne": "",
            "recsys_type": "",
            "frecsys_type": "",
            "language": "english",
            "owner": exp.owner,
            "education_level": "",
            "round_actions": 3,
            "gender": "",
            "nationality": "",
            "toxicity": "none",
            "is_page": 1,
            "feed_url": page.feed,
            "activity_profile": activity_profile_name,
        }
        population_data["agents"].append(page_data)

    # Save population file
    with open(population_filename, "w") as f:
        json.dump(population_data, f, indent=4)

    # Copy prompts file into the experiment folder
    # For HPC experiments, use prompts_hpc.json from data_schema and rename to prompts.json
    # Always copy for HPC to ensure correct prompts file (overwrites if exists)
    prompts_dest = f"{exp_dir}{os.sep}prompts.json"

    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts_hpc.json"))
        shutil.copyfile(prompts_src, prompts_dest)
    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copyfile(prompts_src, prompts_dest)

    # Create population assignment if not exists
    pop_exp = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=exp.idexp
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp.idexp)
        db.session.add(pop_exp)
        db.session.commit()

    # Create client record in database
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp.idexp,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        probability_of_secondary_follow=probability_of_secondary_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        share_link=share_link,
        follow=follow,
        crecsys=crecsys,
        frecsys=frecsys,
        archetype_validator=archetype_validator,
        archetype_broadcaster=archetype_broadcaster,
        archetype_explorer=archetype_explorer,
        trans_val_val=trans_val_val,
        trans_val_broad=trans_val_broad,
        trans_val_expl=trans_val_expl,
        trans_broad_broad=trans_broad_broad,
        trans_broad_val=trans_broad_val,
        trans_broad_expl=trans_broad_expl,
        trans_expl_expl=trans_expl_expl,
        trans_expl_val=trans_expl_val,
        trans_expl_broad=trans_expl_broad,
        status=0,
    )
    db.session.add(client)
    db.session.commit()

    # Create Client_Execution entry for progress tracking
    # For infinite clients (days = -1), set expected_duration_rounds to -1
    # HPC uses 24 slots per day
    expected_rounds = -1 if days == -1 else days * 24
    client_exec = Client_Execution(
        client_id=client.id,
        last_active_hour=-1,
        last_active_day=-1,
        expected_duration_rounds=expected_rounds,
    )
    db.session.add(client_exec)
    db.session.commit()

    # Handle optional network configuration (same logic as Standard clients)
    network_model = form_data.get("network_model")
    network_p = form_data.get("network_p")
    network_m = form_data.get("network_m")
    network_file = request.files.get(
        "network_file"
    )  # Get from request.files, not form_data

    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"HPC client network config - model: {network_model}, file: {network_file.filename if network_file else None}"
    )

    if network_model or (network_file and network_file.filename):
        # Get agents and pages for the population (same logic as Standard)
        agent_pops = Agent_Population.query.filter_by(population_id=population_id).all()
        agents = [Agent.query.filter_by(id=ap.agent_id).first() for ap in agent_pops]
        agent_ids = [a.name for a in agents if a]

        page_pops = Page_Population.query.filter_by(population_id=population_id).all()
        pages_list = [Page.query.filter_by(id=pp.page_id).first() for pp in page_pops]
        page_ids = [p.name for p in pages_list if p]

        # Combine agent and page IDs
        all_node_ids = agent_ids + page_ids

        network_path = f"{exp_dir}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file (replicate Standard logic exactly)
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w") as o:
                    error, error2 = False, False
                    with open(temp_path, "r") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            # Validate agent_1 (same logic as Standard)
                            agent_1 = Agent.query.filter_by(name=l[0]).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = Page.query.filter_by(name=l[0]).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            # Validate agent_2 (same logic as Standard)
                            agent_2 = Agent.query.filter_by(name=l[1]).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = Page.query.filter_by(name=l[1]).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    f"Agent {l[0]} or {l[1]} not found in network file.",
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
                logger.info(f"HPC client network file created: {network_path}")
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    "Network file format error: provide a csv file containing two columns with agent names. No header required.",
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation (replicate Standard logic exactly)
            # Extract parameters with defaults
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1
            k = int(form_data.get("network_k")) if form_data.get("network_k") else 4
            ws_p = (
                float(form_data.get("network_ws_p"))
                if form_data.get("network_ws_p")
                else 0.3
            )
            plc_m = (
                int(form_data.get("network_plc_m"))
                if form_data.get("network_plc_m")
                else 2
            )
            plc_p = (
                float(form_data.get("network_plc_p"))
                if form_data.get("network_plc_p")
                else 0.5
            )
            blocks = (
                int(form_data.get("network_blocks"))
                if form_data.get("network_blocks")
                else 3
            )
            p_in = (
                float(form_data.get("network_p_in"))
                if form_data.get("network_p_in")
                else 0.3
            )
            p_out = (
                float(form_data.get("network_p_out"))
                if form_data.get("network_p_out")
                else 0.05
            )
            tau1 = (
                float(form_data.get("network_tau1"))
                if form_data.get("network_tau1")
                else 2.5
            )
            tau2 = (
                float(form_data.get("network_tau2"))
                if form_data.get("network_tau2")
                else 1.5
            )
            mu = (
                float(form_data.get("network_mu"))
                if form_data.get("network_mu")
                else 0.1
            )
            avg_degree = (
                int(form_data.get("network_avg_degree"))
                if form_data.get("network_avg_degree")
                else 5
            )

            n = len(all_node_ids)

            # Generate network based on selected model
            if network_model == "BA":
                g = nx.barabasi_albert_graph(n, m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(n, p=p)
            elif network_model == "WS":
                g = nx.watts_strogatz_graph(n, k=k, p=ws_p)
            elif network_model == "PLC":
                g = nx.powerlaw_cluster_graph(n, m=plc_m, p=plc_p)
            elif network_model == "C":
                g = nx.complete_graph(n)
            elif network_model == "SBM":
                # Divide nodes into blocks
                block_sizes = [n // blocks] * blocks
                # Add remaining nodes to last block
                block_sizes[-1] += n % blocks
                # Create probability matrix
                probs = [
                    [p_in if i == j else p_out for j in range(blocks)]
                    for i in range(blocks)
                ]
                g = nx.stochastic_block_model(block_sizes, probs)
            elif network_model == "LFR":
                # LFR benchmark with community structure
                # Calculate min_community: at least 5 nodes, at most n/3 to allow multiple communities
                min_community = min(max(5, n // 10), n // 3)
                g = nx.LFR_benchmark_graph(
                    n=n,
                    tau1=tau1,
                    tau2=tau2,
                    mu=mu,
                    average_degree=avg_degree,
                    min_community=min_community,
                )
            else:
                g = None

            if g:
                # Since the network is undirected and Y assumes directed relations,
                # we need to write the edges in both directions (same as Standard)
                with open(network_path, "w") as f:
                    for n in g.edges:
                        f.write(f"{all_node_ids[n[0]]},{all_node_ids[n[1]]}\n")
                        f.write(f"{all_node_ids[n[1]]},{all_node_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()
                logger.info(
                    f"HPC client synthetic network created: {network_path}, type: {network_model}"
                )

    flash(f"HPC client '{name}' created successfully")

    # Check if opinions annotation is present and redirect to opinion configuration
    opinions_enabled = "opinions" in (
        exp.annotations.split(",") if exp.annotations else []
    )
    if opinions_enabled:
        return redirect(
            url_for(
                "clientsr.opinion_configuration", idexp=exp.idexp, client_id=client.id
            )
        )

    return redirect(f"/admin/experiment_details/{exp.idexp}")


@clientsr.route("/admin/create_client", methods=["POST"])
@login_required
def create_client():
    """Create client."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")

    # Check if this is an HPC client
    is_hpc = request.form.get("is_hpc") == "true"

    # Check if LLM agents are enabled for this experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()

    # For HPC clients, use simplified config generation
    if is_hpc:
        return create_hpc_client(exp, name, descr, population_id, request.form)

    # Continue with standard client creation for non-HPC
    days = request.form.get("days")
    percentage_new_agents_iteration = request.form.get(
        "percentage_new_agents_iteration"
    )
    percentage_removed_agents_iteration = request.form.get(
        "percentage_removed_agents_iteration"
    )
    max_length_thread_reading = request.form.get("max_length_thread_reading")
    reading_from_follower_ratio = request.form.get("reading_from_follower_ratio")
    probability_of_daily_follow = request.form.get("probability_of_daily_follow")
    probability_of_secondary_follow = request.form.get(
        "probability_of_secondary_follow"
    )
    attention_window = request.form.get("attention_window")
    visibility_rounds = request.form.get("visibility_rounds")
    post = request.form.get("post")
    share = request.form.get("share")
    image = request.form.get("image")
    comment = request.form.get("comment")
    read = request.form.get("read")
    news = request.form.get("news")
    search = request.form.get("search")
    vote = request.form.get("vote")
    share_link = request.form.get("share_link")

    llm_agents_enabled = (
        exp.llm_agents_enabled if (exp and hasattr(exp, "llm_agents_enabled")) else True
    )

    annotations = {an: None for an in exp.annotations.split(",")}
    if "opinions" in annotations:
        opinions_enabled = True
    else:
        opinions_enabled = False

    # Get LLM parameters from form, or use defaults if LLM agents are disabled
    if llm_agents_enabled:
        llm = request.form.get("llm")
        llm_api_key = request.form.get("llm_api_key")
        llm_max_tokens = request.form.get("llm_max_tokens")
        llm_temperature = request.form.get("llm_temperature")
        llm_v_agent = request.form.get("llm_v_agent")
        llm_v = request.form.get("llm_v")
        llm_v_api_key = request.form.get("llm_v_api_key")
        llm_v_max_tokens = request.form.get("llm_v_max_tokens")
        llm_v_temperature = request.form.get("llm_v_temperature")
        user_type = request.form.get("user_type")
    else:
        # Use default values when LLM agents are disabled
        llm = "http://127.0.0.1:11434/v1"
        llm_api_key = "NULL"
        llm_max_tokens = "-1"
        llm_temperature = "1.5"
        llm_v_agent = "minicpm-v"
        llm_v = "http://127.0.0.1:11434/v1"
        llm_v_api_key = "NULL"
        llm_v_max_tokens = "300"
        llm_v_temperature = "0.5"
        user_type = ""

    crecsys = request.form.get("recsys_type")
    frecsys = request.form.get("frecsys_type")

    # Get agent archetype enabled status
    enable_archetypes = request.form.get("enable_archetypes") == "on"

    # Get agent archetype values (optional, with defaults)
    try:
        archetype_validator = (
            float(request.form.get("archetype_validator", "52")) / 100.0
        )
        archetype_broadcaster = (
            float(request.form.get("archetype_broadcaster", "20")) / 100.0
        )
        archetype_explorer = float(request.form.get("archetype_explorer", "28")) / 100.0
        trans_val_val = float(request.form.get("trans_val_val", "85.3")) / 100.0
        trans_val_broad = float(request.form.get("trans_val_broad", "8.1")) / 100.0
        trans_val_expl = float(request.form.get("trans_val_expl", "6.6")) / 100.0
        trans_broad_broad = float(request.form.get("trans_broad_broad", "72.9")) / 100.0
        trans_broad_val = float(request.form.get("trans_broad_val", "19.5")) / 100.0
        trans_broad_expl = float(request.form.get("trans_broad_expl", "7.5")) / 100.0
        trans_expl_expl = float(request.form.get("trans_expl_expl", "49.0")) / 100.0
        trans_expl_val = float(request.form.get("trans_expl_val", "36.4")) / 100.0
        trans_expl_broad = float(request.form.get("trans_expl_broad", "14.6")) / 100.0
    except (ValueError, TypeError) as e:
        flash(f"Invalid archetype values: {str(e)}", "error")
        return redirect(request.referrer)

    # Validate simulation parameters
    errors = []
    # Validate numeric fields
    try:
        days = int(days)
        # days = -1 means infinite/run-until-stopped
        if days != -1 and days < 1:
            errors.append(
                "Days must be at least 1, or use -1 for infinite duration (run until stopped)"
            )
    except (ValueError, TypeError):
        errors.append("Days must be a valid integer")
    try:
        max_length_thread_reading = int(max_length_thread_reading)
    except (ValueError, TypeError):
        errors.append("Max Length Thread Reading must be a valid integer")
    try:
        attention_window = int(attention_window)
    except (ValueError, TypeError):
        errors.append("Attention Window must be a valid integer")
    try:
        visibility_rounds = int(visibility_rounds)
    except (ValueError, TypeError):
        errors.append("Visibility Rounds must be a valid integer")

    # Validate probability fields (must be float in [0, 1])
    try:
        percentage_new_agents_iteration = float(percentage_new_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% New Agents (daily) must be a valid number")
        percentage_new_agents_iteration = None
    try:
        percentage_removed_agents_iteration = float(percentage_removed_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% Daily Churn must be a valid number")
        percentage_removed_agents_iteration = None
    try:
        reading_from_follower_ratio = float(reading_from_follower_ratio)
    except (ValueError, TypeError):
        errors.append("Timeline Follower Ratio must be a valid number")
        reading_from_follower_ratio = None
    try:
        probability_of_daily_follow = float(probability_of_daily_follow)
    except (ValueError, TypeError):
        errors.append("Probability Daily Follow must be a valid number")
        probability_of_daily_follow = None
    try:
        probability_of_secondary_follow = float(probability_of_secondary_follow)
    except (ValueError, TypeError):
        errors.append("Probability Secondary Follow must be a valid number")
        probability_of_secondary_follow = None

    # Check probability ranges
    probabilities = {
        "% New Agents (daily)": percentage_new_agents_iteration,
        "% Daily Churn": percentage_removed_agents_iteration,
        "Timeline Follower Ratio": reading_from_follower_ratio,
        "Probability Daily Follow": probability_of_daily_follow,
        "Probability Secondary Follow": probability_of_secondary_follow,
    }
    for field_name, value in probabilities.items():
        if value is not None and not (0 <= value <= 1):
            errors.append(f"{field_name} must be between 0 and 1")

    if errors:
        for error in errors:
            flash(error)
        return redirect(request.referrer)

    # Fetch optional network configuration
    network_model = request.form.get("network_model")
    network_p = request.form.get("network_p")
    network_m = request.form.get("network_m")
    network_file = request.files.get("network_file")

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = request.form.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass  # Ignore invalid values, use defaults

    # get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=exp_id).all()
    topics_ids = [t.topic_id for t in topics]
    # get the topics names from the Topic_list table
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topics = [t.name for t in topics_objs]

    # Get topic interest percentages from form
    topic_percentages = {}
    for topic_obj in topics_objs:
        percentage_key = f"topic_interest_{topic_obj.id}"
        percentage_value = request.form.get(percentage_key, "100")
        try:
            topic_percentages[topic_obj.name] = float(percentage_value)
        except (ValueError, TypeError):
            topic_percentages[topic_obj.name] = 100.0  # Default to 100% if invalid

    # if name already exists, return to the previous page
    if Client.query.filter_by(name=name).first():
        flash("Client name already exists.", "error")
        return redirect(request.referrer)

    exp = Exps.query.filter_by(idexp=exp_id).first()

    # get population
    population = Population.query.filter_by(id=population_id).first()

    if population is None:
        flash("Population not found.", "error")
        return redirect(request.referrer)

    # check if the population is already assigned to the experiment
    # if not, add it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=exp_id
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp_id)
        db.session.add(pop_exp)
        db.session.commit()

    # create the Client object
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp_id,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        share_link=share_link,
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=llm_max_tokens,
        llm_temperature=llm_temperature,
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=llm_v_max_tokens,
        llm_v_temperature=llm_v_temperature,
        probability_of_secondary_follow=probability_of_secondary_follow,
        crecsys=crecsys,
        frecsys=frecsys,
        status=0,
        archetype_validator=archetype_validator,
        archetype_broadcaster=archetype_broadcaster,
        archetype_explorer=archetype_explorer,
        trans_val_val=trans_val_val,
        trans_val_broad=trans_val_broad,
        trans_val_expl=trans_val_expl,
        trans_broad_broad=trans_broad_broad,
        trans_broad_val=trans_broad_val,
        trans_broad_expl=trans_broad_expl,
        trans_expl_expl=trans_expl_expl,
        trans_expl_val=trans_expl_val,
        trans_expl_broad=trans_expl_broad,
    )

    db.session.add(client)
    db.session.commit()

    # If experiment was completed, reset status to stopped since a new client was added
    if exp.exp_status == "completed":
        exp.exp_status = "stopped"
        db.session.commit()

    # Get LLM URL from environment (set by y_social.py)
    import os

    # get population activity profiles
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )

    activity_profiles = [a.activity_profile for a in activity_profiles]

    # get all activity profiles from the db where id in activity_profiles
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )

    profiles = {ap.name: ap.hours for ap in activity_profiles}

    annotations = exp.annotations.split(",")
    emotion_annotation = "emotion" in annotations

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    config = {
        "servers": {
            "llm": llm,
            "llm_api_key": llm_api_key,
            "llm_max_tokens": int(llm_max_tokens),
            "llm_temperature": float(llm_temperature),
            "llm_v": llm_v,
            "llm_v_api_key": llm_v_api_key,
            "llm_v_max_tokens": int(llm_v_max_tokens),
            "llm_v_temperature": float(llm_v_temperature),
            "api": f"http://{exp.server}:{exp.port}/",
        },
        "simulation": {
            "name": name,
            "population": population.name,
            "client": "YClientWeb",
            "days": int(days),
            "slots": 24,
            "percentage_new_agents_iteration": float(percentage_new_agents_iteration),
            "percentage_removed_agents_iteration": float(
                percentage_removed_agents_iteration
            ),
            "activity_profiles": profiles,
            "hourly_activity": hourly_activity,
            "actions_likelihood": {
                "post": float(post),
                "image": float(image) if image is not None else 0,
                "news": float(news) if news is not None else 0,
                "comment": float(comment) if comment is not None else 0,
                "read": float(read) if read is not None else 0,
                "share": float(share) if share is not None else 0,
                "search": float(search) if search is not None else 0,
                "cast": float(vote) if vote is not None else 0,
                "share_link": float(share_link) if share_link is not None else 0,
            },
            "emotion_annotation": emotion_annotation,
            "agent_archetypes": {
                "enabled": enable_archetypes,
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
            },
        },
        "posts": {
            "visibility_rounds": int(visibility_rounds),
            "emotions": {
                "admiration": None,
                "amusement": None,
                "anger": None,
                "annoyance": None,
                "approval": None,
                "caring": None,
                "confusion": None,
                "curiosity": None,
                "desire": None,
                "disappointment": None,
                "disapproval": None,
                "disgust": None,
                "embarrassment": None,
                "excitement": None,
                "fear": None,
                "gratitude": None,
                "grief": None,
                "joy": None,
                "love": None,
                "nervousness": None,
                "optimism": None,
                "pride": None,
                "realization": None,
                "relief": None,
                "remorse": None,
                "sadness": None,
                "surprise": None,
                "trust": None,
            },
        },
        "agents": {
            "llm_v_agent": "minicpm-v",
            "reading_from_follower_ratio": float(reading_from_follower_ratio),
            "max_length_thread_reading": int(max_length_thread_reading),
            "attention_window": int(attention_window),
            "probability_of_daily_follow": float(probability_of_daily_follow),
            "probability_of_secondary_follow": float(probability_of_secondary_follow),
            "age": {"min": 18, "max": 65},
            "political_leaning": [],
            "toxicity_levels": [],
            "languages": [],
            "llm_agents": [],
            "education_levels": [],
            "round_actions": {"min": 1, "max": 3},
            "n_interests": {"min": 1, "max": 5},
            "interests": [],
            "big_five": {
                "oe": ["inventive/curious", "consistent/cautious"],
                "co": ["extravagant/careless", "efficient/organized"],
                "ex": ["outgoing/energetic", "solitary/reserved"],
                "ag": ["critical/judgmental", "friendly/compassionate"],
                "ne": ["resilient/confident", "sensitive/nervous"],
            },
        },
    }

    # get population agents
    agents = Agent_Population.query.filter_by(population_id=population_id).all()
    # get agents political leaning
    political_leaning = set(
        [Agent.query.filter_by(id=a.agent_id).first().leaning for a in agents]
    )
    # get agents' age
    age = set([Agent.query.filter_by(id=a.agent_id).first().age for a in agents])
    # get agents toxicity levels
    toxicity = set(
        [Agent.query.filter_by(id=a.agent_id).first().toxicity for a in agents]
    )
    # get agents' language
    language = set(
        [Agent.query.filter_by(id=a.agent_id).first().language for a in agents]
    )
    # get agents' type
    ag_type = set(
        [Agent.query.filter_by(id=a.agent_id).first().ag_type for a in agents]
    )
    # get agents' education level
    education_level = set(
        [Agent.query.filter_by(id=a.agent_id).first().education_level for a in agents]
    )

    config["agents"]["political_leanings"] = list(political_leaning)
    config["agents"]["age"]["min"] = min(age)
    config["agents"]["age"]["max"] = max(age)
    config["agents"]["toxicity_levels"] = list(toxicity)
    config["agents"]["languages"] = list(language)
    config["agents"]["llm_agents"] = list(ag_type)
    config["agents"]["education_levels"] = list(education_level)
    config["agents"]["round_actions"] = {"min": 1, "max": 3}
    config["agents"]["n_interests"] = {"min": 1, "max": 5}

    # check db type
    if "database_server.db" in exp.db_name:  # sqlite
        uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    with open(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f, indent=4)

    data_base_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    # copy prompts.json into the experiment folder

    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
        shutil.copyfile(
            prompts_src,
            f"{data_base_path}prompts.json",
        )

    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copyfile(
            prompts_src,
            f"{data_base_path}prompts.json",
        )
    else:
        raise Exception(f"unsupported platform: {exp.platform_type}")

    # Create agent population file
    writable_base = get_writable_path()

    if "database_server.db" in exp.db_name:
        # exp.db_name is like "experiments/uid/database_server.db"
        filename = os.path.join(
            writable_base,
            "y_web",
            exp.db_name.split("database_server.db")[0],
            f"{population.name.replace(' ', '')}.json",
        )
    else:
        # Legacy format
        filename = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp.db_name.replace("experiments_", ""),
            f"{population.name.replace(' ', '')}.json",
        )

    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    # get the agent details
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    # Assign archetypes to agents based on distribution probabilities
    num_agents = len(agents)
    archetype_assignments = []

    if enable_archetypes and num_agents > 0:
        # Build list of active archetypes and their probabilities
        active_archetypes = []
        active_probabilities = []

        if archetype_validator > 0:
            active_archetypes.append("validator")
            active_probabilities.append(archetype_validator)

        if archetype_broadcaster > 0:
            active_archetypes.append("broadcaster")
            active_probabilities.append(archetype_broadcaster)

        if archetype_explorer > 0:
            active_archetypes.append("explorer")
            active_probabilities.append(archetype_explorer)

        # Normalize probabilities if they don't sum to 1
        if len(active_probabilities) > 0:
            total_prob = sum(active_probabilities)
            if total_prob > 0:
                active_probabilities = [p / total_prob for p in active_probabilities]
                # Assign archetypes to agents using numpy random choice
                archetype_assignments = np.random.choice(
                    active_archetypes, size=num_agents, p=active_probabilities
                ).tolist()
            else:
                # If all probabilities are 0, assign None
                archetype_assignments = [None] * num_agents
        else:
            # No active archetypes
            archetype_assignments = [None] * num_agents
    else:
        # Archetypes disabled, assign None to all agents
        archetype_assignments = [None] * num_agents

    res = {"agents": []}
    for idx, a in enumerate(agents):
        custom_prompt = Agent_Profile.query.filter_by(agent_id=a.id).first()

        if custom_prompt:
            custom_prompt = custom_prompt.profile

        # Allocate topics based on specified percentages
        interests = allocate_topics_by_percentage(topics, topic_percentages)

        ints = [interests, len(interests)]

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=a.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": a.name,
                "email": f"{a.name}@ysocial.it",
                "password": f"{a.name}",
                "age": a.age,
                "type": user_type,  # ,a.ag_type,
                "leaning": a.leaning,
                "interests": ints,
                "oe": a.oe,
                "co": a.co,
                "ex": a.ex,
                "ag": a.ag,
                "ne": a.ne,
                "rec_sys": crecsys,
                "frec_sys": frecsys,
                "language": a.language,
                "owner": exp.owner,
                "education_level": a.education_level,
                "round_actions": int(a.round_actions),
                "gender": a.gender,
                "nationality": a.nationality,
                "toxicity": a.toxicity,
                "is_page": 0,
                "prompts": custom_prompt if custom_prompt else None,
                "daily_activity_level": a.daily_activity_level,
                "profession": a.profession,
                "activity_profile": activity_profile_name,
                "archetype": archetype_assignments[idx],
                "opinions": (
                    {i: random.random() for i in ints[0]} if opinions_enabled else None
                ),  # @todo: check initial opinions
            }
        )

    # get the pages associated with the population
    pages = Page_Population.query.filter_by(population_id=population.id).all()
    pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

    for p in pages:
        # get pages topics
        page_topics = (
            db.session.query(Exp_Topic, Topic_List)
            .join(Topic_List)
            .filter(Exp_Topic.exp_id == exp_id, Exp_Topic.topic_id == Topic_List.id)
            .all()
        )
        page_topics = [t[1].name for t in page_topics]
        page_topics = list(set(page_topics) & set(topics))

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=p.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": p.name,
                "email": f"{p.name}@ysocial.it",
                "password": f"{p.name}",
                "age": 0,
                "type": user_type,
                "leaning": p.leaning,
                "interests": [page_topics, len(page_topics)],
                "oe": "",
                "co": "",
                "ex": "",
                "ag": "",
                "ne": "",
                "rec_sys": "",
                "frec_sys": "",
                "language": "english",
                "owner": exp.owner,
                "education_level": "",
                "round_actions": 3,
                "gender": "",
                "nationality": "",
                "toxicity": "none",
                "is_page": 1,
                "feed_url": p.feed,
                "activity_profile": activity_profile_name,
            }
        )

    print(f"Saving agents to {filename}")
    json.dump(res, open(filename, "w"), indent=4)

    # Handle optional network configuration
    if network_model or network_file:
        # get populations for client
        populations = Population.query.filter_by(id=client.population_id).all()
        # get agents for the populations
        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

        from y_web.utils.path_utils import get_writable_path

        BASE = get_writable_path()
        dbtypte = get_db_type()

        if dbtypte == "sqlite":
            exp_folder = exp.db_name.split(os.sep)[1]
        else:
            exp_folder = exp.db_name.removeprefix("experiments_")

        network_path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w") as o:
                    error, error2 = False, False
                    with open(temp_path, "r") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            agent_1 = Agent.query.filter_by(name=l[0]).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = Page.query.filter_by(name=l[0]).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            agent_2 = Agent.query.filter_by(name=l[1]).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = Page.query.filter_by(name=l[1]).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    f"Agent {l[0]} or {l[1]} not found in network file.",
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    "Network file format error: provide a csv file containing two columns with agent names. No header required.",
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation
            # Extract parameters with defaults
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1
            k = (
                int(request.form.get("network_k"))
                if request.form.get("network_k")
                else 4
            )
            ws_p = (
                float(request.form.get("network_ws_p"))
                if request.form.get("network_ws_p")
                else 0.3
            )
            plc_m = (
                int(request.form.get("network_plc_m"))
                if request.form.get("network_plc_m")
                else 2
            )
            plc_p = (
                float(request.form.get("network_plc_p"))
                if request.form.get("network_plc_p")
                else 0.5
            )
            blocks = (
                int(request.form.get("network_blocks"))
                if request.form.get("network_blocks")
                else 3
            )
            p_in = (
                float(request.form.get("network_p_in"))
                if request.form.get("network_p_in")
                else 0.3
            )
            p_out = (
                float(request.form.get("network_p_out"))
                if request.form.get("network_p_out")
                else 0.05
            )
            tau1 = (
                float(request.form.get("network_tau1"))
                if request.form.get("network_tau1")
                else 2.5
            )
            tau2 = (
                float(request.form.get("network_tau2"))
                if request.form.get("network_tau2")
                else 1.5
            )
            mu = (
                float(request.form.get("network_mu"))
                if request.form.get("network_mu")
                else 0.1
            )
            avg_degree = (
                int(request.form.get("network_avg_degree"))
                if request.form.get("network_avg_degree")
                else 5
            )

            n = len(agent_ids)

            # Generate network based on selected model
            if network_model == "BA":
                g = nx.barabasi_albert_graph(n, m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(n, p=p)
            elif network_model == "WS":
                g = nx.watts_strogatz_graph(n, k=k, p=ws_p)
            elif network_model == "PLC":
                g = nx.powerlaw_cluster_graph(n, m=plc_m, p=plc_p)
            elif network_model == "C":
                g = nx.complete_graph(n)
            elif network_model == "SBM":
                # Divide nodes into blocks
                block_sizes = [n // blocks] * blocks
                # Add remaining nodes to last block
                block_sizes[-1] += n % blocks
                # Create probability matrix
                probs = [
                    [p_in if i == j else p_out for j in range(blocks)]
                    for i in range(blocks)
                ]
                g = nx.stochastic_block_model(block_sizes, probs)
            elif network_model == "LFR":
                # LFR benchmark with community structure
                # Calculate min_community: at least 5 nodes, at most n/3 to allow multiple communities
                min_community = min(max(5, n // 10), n // 3)
                g = nx.LFR_benchmark_graph(
                    n=n,
                    tau1=tau1,
                    tau2=tau2,
                    mu=mu,
                    average_degree=avg_degree,
                    min_community=min_community,
                )
            else:
                g = None

            if g:
                # since the network is undirected and Y assume directed relations we need to write the edges in both directions
                with open(network_path, "w") as f:
                    for n in g.edges:
                        f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
                        f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)
    telemetry.log_event(
        data={
            "action": "create_client",
            "data": {
                "llm_agents_enabled": llm_agents_enabled,
                "days": days,
                "percentage_new_agents_iteration": percentage_new_agents_iteration,
                "percentage_removed_agents_iteration": percentage_removed_agents_iteration,
                "max_length_thread_reading": max_length_thread_reading,
                "reading_from_follower_ratio": reading_from_follower_ratio,
                "probability_of_daily_follow": probability_of_daily_follow,
                "attention_window": attention_window,
                "visibility_rounds": visibility_rounds,
                "actions": {
                    "post": post,
                    "share": share,
                    "image": image,
                    "comment": comment,
                    "read": read,
                    "news": news,
                    "search": search,
                    "vote": vote,
                    "share_link": share_link,
                },
                "llm": user_type,
                "probability_of_secondary_follow": probability_of_secondary_follow,
                "crecsys": crecsys,
                "frecsys": frecsys,
            },
        }
    )

    # Check if opinions annotation is present and redirect to opinion configuration
    if opinions_enabled:
        return redirect(
            url_for("clientsr.opinion_configuration", idexp=exp_id, client_id=client.id)
        )

    # load experiment_details page
    from .experiments_routes import experiment_details

    return experiment_details(int(exp_id))


@clientsr.route("/admin/delete_client/<int:uid>")
@login_required
def delete_client(uid):
    """Delete client."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    exp_id = client.id_exp
    pop_id = client.population_id

    Client_Execution.query.filter_by(client_id=uid).delete()
    db.session.commit()

    # delete association of population and experiment if no other client is using it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=client.population_id, id_exp=exp_id
    ).first()
    if pop_exp:
        other_clients = Client.query.filter_by(
            id_exp=exp_id, population_id=client.population_id
        ).all()
        if len(other_clients) == 0:
            db.session.delete(pop_exp)
            db.session.commit()

    db.session.delete(client)
    db.session.commit()

    from y_web.utils.path_utils import get_writable_path

    # remove the db file on the client
    BASE_PATH = get_writable_path()
    path = f"{BASE_PATH}{os.sep}external{os.sep}YClient{os.sep}experiments{os.sep}{client.name}.db"
    if os.path.exists(path):
        os.remove(path)
    else:
        print(f"File {path} does not exist.")

    # remove agent population
    Population_Experiment.query.filter_by(id_population=pop_id).delete()
    db.session.commit()

    from .experiments_routes import experiment_details

    return experiment_details(exp_id)


@clientsr.route("/admin/client_details/<int:uid>")
@login_required
def client_details(uid):
    """Handle client details operation."""
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()

    # Redirect HPC clients to dedicated HPC client details page
    if (
        experiment
        and hasattr(experiment, "simulator_type")
        and experiment.simulator_type == "HPC"
    ):
        return redirect(url_for("clientsr.client_details_hpc", uid=uid))

    # get population for the client
    population = Population.query.filter_by(id=client.population_id).first()
    # get the pages included to the population
    pages = (
        db.session.query(Page, Page_Population)
        .join(Page_Population)
        .filter(Page_Population.population_id == client.population_id)
        .all()
    )

    # get the client configuration file
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = experiment.db_name.split(os.sep)[1]
    else:
        exp_folder = experiment.db_name.removeprefix("experiments_")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
    else:
        config = None

    # open the agent population file to get the number of agents
    path_agents = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{population.name}.json"

    if os.path.exists(path_agents):
        with open(path_agents, "r") as f:
            agents = json.load(f)
    else:
        agents = None

    llms = []
    if agents is not None:
        for agent in agents["agents"]:
            # Skip page agents (is_page=1) as they don't have a type field
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)

    llms = ",".join(list(set(llms)))

    activity = config["simulation"]["hourly_activity"]

    data = []
    idx = []

    for x in range(0, 24):
        idx.append(str(x))
        data.append(activity[str(x)])

    models = get_llm_models()  # Use generic function for any LLM server

    llm_backend = llm_backend_status()

    # Get all recsys and filter by enabled field for Standard clients
    frecsys_all = Follow_Recsys.query.all()
    crecsys_all = Content_Recsys.query.all()

    # Filter recsys based on enabled field - Standard clients only get ones with "Standard" in enabled
    frecsys = [r for r in frecsys_all if r.enabled and "Standard" in r.enabled]
    crecsys = [r for r in crecsys_all if r.enabled and "Standard" in r.enabled]

    return render_template(
        "admin/client_details.html",
        data=data,
        idx=idx,
        activity=activity,
        client=client,
        experiment=experiment,
        population=population,
        pages=pages,
        models=models,
        llm_backend=llm_backend,
        frecsys=frecsys,
        crecsys=crecsys,
        llms=llms,
    )


@clientsr.route("/admin/client_details_hpc/<int:uid>")
@login_required
def client_details_hpc(uid):
    """Handle HPC client details operation."""
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.settings"))

    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    # get population for the client
    population = Population.query.filter_by(id=client.population_id).first()
    # get the pages included to the population
    pages = (
        db.session.query(Page, Page_Population)
        .join(Page_Population)
        .filter(Page_Population.population_id == client.population_id)
        .all()
    )

    # get the client configuration file
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    dbtype = get_db_type()

    if dbtype == "sqlite":
        exp_folder = experiment.db_name.split(os.sep)[1]
    else:
        exp_folder = experiment.db_name.removeprefix("experiments_")

    # HPC clients use the same file naming pattern: client_{name}-{population}.json
    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
    else:
        config = None
        flash("HPC client configuration file not found.", "warning")

    # open the agent population file to get the number of agents
    path_agents = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{population.name}.json"

    if os.path.exists(path_agents):
        with open(path_agents, "r") as f:
            agents = json.load(f)
    else:
        agents = None

    llms = []
    if agents is not None:
        for agent in agents["agents"]:
            # Skip page agents (is_page=1) as they don't have a type field
            if not agent.get("is_page", 0):
                agent_type = agent.get("type")
                if agent_type:
                    llms.append(agent_type)

    llms = ",".join(list(set(llms)))

    # Extract activity data from HPC config structure
    data = []
    idx = []
    activity = None

    if config and "simulation" in config and "hourly_activity" in config["simulation"]:
        activity = config["simulation"]["hourly_activity"]
        for x in range(0, 24):
            idx.append(str(x))
            data.append(activity.get(str(x), 0))
    elif (
        config
        and "simulation" in config
        and "activity_profiles" in config["simulation"]
    ):
        # If hourly_activity is not present but activity_profiles are, use first profile
        profiles = config["simulation"]["activity_profiles"]
        if profiles:
            first_profile = list(profiles.values())[0]
            activity = first_profile
            for x in range(0, 24):
                idx.append(str(x))
                data.append(activity.get(str(x), 0))

    if not activity:
        # Default to empty data
        for x in range(0, 24):
            idx.append(str(x))
            data.append(0)
        activity = {str(x): 0 for x in range(24)}

    models = get_llm_models()  # Use generic function for any LLM server

    llm_backend = llm_backend_status()

    # Get all recsys and filter by enabled field for HPC clients
    frecsys_all = Follow_Recsys.query.all()
    crecsys_all = Content_Recsys.query.all()

    # Filter recsys based on enabled field - HPC clients only get ones with "HPC" in enabled
    frecsys = [r for r in frecsys_all if r.enabled and "HPC" in r.enabled]
    crecsys = [r for r in crecsys_all if r.enabled and "HPC" in r.enabled]

    return render_template(
        "admin/client_details_hpc.html",
        data=data,
        idx=idx,
        activity=activity,
        client=client,
        experiment=experiment,
        population=population,
        pages=pages,
        models=models,
        llm_backend=llm_backend,
        frecsys=frecsys,
        crecsys=crecsys,
        llms=llms,
        config=config,
    )


@clientsr.route("/admin/progress/<int:client_id>")
def get_progress(client_id):
    """Return the current progress as JSON.

    For finite clients: returns progress percentage (0-100)
    For infinite clients (expected_duration_rounds = -1): returns elapsed time info
    """
    # get client_execution
    client_execution = Client_Execution.query.filter_by(client_id=client_id).first()

    if client_execution is None:
        return json.dumps({"progress": 0, "infinite": False})

    # Check if this is an infinite client (expected_duration_rounds = -1)
    if client_execution.expected_duration_rounds == -1:
        # Return elapsed time info for infinite clients
        elapsed_hours = client_execution.elapsed_time
        elapsed_days = elapsed_hours // 24
        remaining_hours = elapsed_hours % 24
        return json.dumps(
            {
                "progress": -1,
                "infinite": True,
                "elapsed_time": client_execution.elapsed_time,
                "elapsed_days": elapsed_days,
                "elapsed_hours": remaining_hours,
                "last_active_day": client_execution.last_active_day,
                "last_active_hour": client_execution.last_active_hour,
            }
        )

    # Calculate progress and cap at 100%
    if client_execution.expected_duration_rounds > 0:
        progress = int(
            100
            * float(client_execution.elapsed_time)
            / float(client_execution.expected_duration_rounds)
        )
        # Cap progress at 100% to prevent overflow
        progress = min(100, max(0, progress))
    else:
        progress = 0

    return json.dumps({"progress": progress, "infinite": False})


@clientsr.route("/admin/set_network/<int:uid>", methods=["POST"])
@login_required
def set_network(uid):
    """Handle set network operation."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations for client uid
    populations = Population.query.filter_by(id=client.population_id).all()
    # get agents for the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id for p in populations])
    ).all()
    # get agent ids for all agents in populations
    agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

    # get data from form
    network = request.form.get("network_model")

    # Extract parameters with defaults
    m = int(request.form.get("m")) if request.form.get("m") else 2
    p = float(request.form.get("p")) if request.form.get("p") else 0.1
    k = int(request.form.get("k")) if request.form.get("k") else 4
    ws_p = float(request.form.get("ws_p")) if request.form.get("ws_p") else 0.3
    plc_m = int(request.form.get("plc_m")) if request.form.get("plc_m") else 2
    plc_p = float(request.form.get("plc_p")) if request.form.get("plc_p") else 0.5
    blocks = int(request.form.get("blocks")) if request.form.get("blocks") else 3
    p_in = float(request.form.get("p_in")) if request.form.get("p_in") else 0.3
    p_out = float(request.form.get("p_out")) if request.form.get("p_out") else 0.05
    tau1 = float(request.form.get("tau1")) if request.form.get("tau1") else 2.5
    tau2 = float(request.form.get("tau2")) if request.form.get("tau2") else 1.5
    mu = float(request.form.get("mu")) if request.form.get("mu") else 0.1
    avg_degree = (
        int(request.form.get("avg_degree")) if request.form.get("avg_degree") else 5
    )

    n = len(agent_ids)

    # Generate network based on selected model
    if network == "BA":
        g = nx.barabasi_albert_graph(n, m=m)
    elif network == "ER":
        g = nx.erdos_renyi_graph(n, p=p)
    elif network == "WS":
        g = nx.watts_strogatz_graph(n, k=k, p=ws_p)
    elif network == "PLC":
        g = nx.powerlaw_cluster_graph(n, m=plc_m, p=plc_p)
    elif network == "C":
        g = nx.complete_graph(n)
    elif network == "SBM":
        # Divide nodes into blocks
        block_sizes = [n // blocks] * blocks
        # Add remaining nodes to last block
        block_sizes[-1] += n % blocks
        # Create probability matrix
        probs = [
            [p_in if i == j else p_out for j in range(blocks)] for i in range(blocks)
        ]
        g = nx.stochastic_block_model(block_sizes, probs)
    elif network == "LFR":
        # LFR benchmark with community structure
        # Calculate min_community: at least 5 nodes, at most n/3 to allow multiple communities
        min_community = min(max(5, n // 10), n // 3)
        g = nx.LFR_benchmark_graph(
            n=n,
            tau1=tau1,
            tau2=tau2,
            mu=mu,
            average_degree=avg_degree,
            min_community=min_community,
        )
    else:
        # Default to ER for backward compatibility if unrecognized model
        g = nx.erdos_renyi_graph(n, p=p)

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

    # since the network is undirected and Y assume directed relations we need to write the edges in both directions
    with open(path, "w") as f:
        for n in g.edges:
            f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
            f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
        f.flush()

    client.network_type = network
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/upload_network/<int:uid>", methods=["POST"])
@login_required
def upload_network(uid):
    """Upload network."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    network = request.files["network_file"]
    network.save(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network_temp.csv"
    )

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}"

    try:
        with open(f"{path}_network.csv", "w") as o:
            error, error2 = False, False
            with open(f"{path}_network_temp.csv", "r") as f:
                for l in f:
                    l = l.rstrip().split(",")

                    agent_1 = Agent.query.filter_by(name=l[0]).all()
                    aids = [a.id for a in agent_1]

                    if agent_1 is not None:
                        # check if in population
                        test = Agent_Population.query.filter(
                            Agent_Population.agent_id.in_(aids),
                            Agent_Population.population_id == client.population_id,
                        ).all()
                        error = len(test) == 0
                    else:
                        agent_1 = Page.query.filter_by(name=l[0]).all()
                        aids = [a.id for a in agent_1]

                        if agent_1 is not None:
                            # check if in population
                            test = Page_Population.query.filter(
                                Page_Population.page_id.in_(aids),
                                Page_Population.population_id == client.population_id,
                            ).all()
                            error = len(test) == 0
                        if agent_1 is None:
                            error = True

                    agent_2 = Agent.query.filter_by(name=l[1]).all()
                    aids = [a.id for a in agent_2]

                    if agent_2 is not None:
                        # check if in population
                        test = Agent_Population.query.filter(
                            Agent_Population.agent_id.in_(aids),
                            Agent_Population.population_id == client.population_id,
                        ).all()
                        error2 = len(test) == 0
                    else:
                        agent_2 = Page.query.filter_by(name=l[1]).all()
                        aids = [a.id for a in agent_2]

                        if agent_2 is not None:
                            # check if in population
                            test = Page_Population.query.filter(
                                Page_Population.page_id.in_(aids),
                                Page_Population.population_id == client.population_id,
                            ).all()
                            error2 = len(test) == 0

                        if agent_2 is None:
                            error2 = True

                    if not error and not error2:
                        o.write(f"{l[0]},{l[1]}\n")
                    else:
                        flash(f"Agent {l[0]} or {l[1]} not found.", "error")
                        os.remove(f"{path}_network_temp.csv")
                        os.remove(f"{path}_network.csv")
                        return redirect(request.referrer)
    except:
        flash(
            "File format error: provide a csv file containing two columns with agent names. No header required.",
            "error",
        )
        os.remove(f"{path}_network_temp.csv")
        os.remove(f"{path}_network.csv")
        return redirect(request.referrer)

    # delete the temp file
    os.remove(f"{path}_network_temp.csv")

    client.network_type = "Custom Network"
    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/download_agent_list/<int:uid>")
@login_required
def download_agent_list(uid):
    """Download agent list."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations associated to the client
    populations = Population_Experiment.query.filter_by(id_exp=client.id_exp).all()

    # get agents in the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id_population for p in populations])
    ).all()

    # get the experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()

    from y_web.utils.path_utils import get_writable_path

    # get the experiment folder
    BASE = get_writable_path()

    dbtypte = get_db_type()

    if dbtypte == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    with open(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv",
        "w",
    ) as f:
        for a in agents:
            agent = Agent.query.filter_by(id=a.agent_id).first()
            f.write(f"{agent.name}\n")
        f.flush()

    return send_file_desktop(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv",
        as_attachment=True,
    )


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

    from y_web.utils.path_utils import get_writable_path

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

    from y_web.utils.path_utils import get_writable_path

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

    from y_web.utils.path_utils import get_writable_path

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

    from y_web.utils.path_utils import get_writable_path

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


@clientsr.route("/admin/update_recsys/<int:uid>", methods=["POST"])
@login_required
def update_recsys(uid):
    """Update recsys."""
    check_privileges(current_user.username)

    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")

    client = Client.query.filter_by(id=uid).first()

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


@clientsr.route("/admin/update_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_llm(uid):
    """Update llm."""
    check_privileges(current_user.username)

    user_type = request.form.get("user_type")

    client = Client.query.filter_by(id=uid).first()

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


@clientsr.route("/admin/opinion_configuration/<int:idexp>")
@login_required
def opinion_configuration(idexp):
    """Display opinion configuration page for experiments with opinions annotation."""
    check_privileges(current_user.username)

    # Get client_id from query parameters
    client_id = request.args.get("client_id", type=int)
    if not client_id:
        flash("Client ID is required.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Get experiment details
    exp = Exps.query.filter_by(idexp=idexp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    # Get client details
    client = Client.query.filter_by(id=client_id).first()
    if not client or client.id_exp != idexp:
        flash("Client not found or does not belong to this experiment.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Verify that opinions annotation is present
    annotations = (
        {an.strip(): None for an in exp.annotations.split(",")}
        if exp.annotations and exp.annotations.strip()
        else {}
    )
    if "opinions" not in annotations:
        flash("This experiment does not have opinions annotation.", "warning")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics = db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    topics = [{"id": t.id, "name": t.name} for t in topics]

    # Get population and load population JSON file to get actual segment values
    population = Population.query.filter_by(id=client.population_id).first()
    if not population:
        flash("Population not found.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Load population JSON file to get actual segment values
    from y_web.utils import get_db_type
    from y_web.utils.path_utils import get_writable_path

    writable_base = get_writable_path()
    dbtype = get_db_type()

    if dbtype == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    # For HPC experiments, look for client_{client.name}-{population.name}.json
    # For standard experiments, look for {population.name}.json
    if exp.simulator_type == "HPC":
        population_file = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp_folder,
            f"{population.name.replace(' ', '')}.json",
        )
    else:
        population_file = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp_folder,
            f"{population.name.replace(' ', '')}.json",
        )

    # Load age classes from database to map individual ages to age groups
    age_classes = AgeClass.query.all()
    age_class_map = {}
    for ac in age_classes:
        age_class_map[ac.name] = (ac.age_start, ac.age_end)

    # Read population data to get actual segment values
    segment_values = {
        "age": set(),
        "political_leaning": set(),
        "gender": set(),
        "education_level": set(),
    }

    try:
        if os.path.exists(population_file):
            with open(population_file, "r") as f:
                pop_data = json.load(f)
                for agent in pop_data.get("agents", []):
                    if not agent.get("is_page", 0):  # Exclude pages
                        age = agent.get("age")
                        if age:
                            # Map individual age to age class
                            age_class_found = False
                            for class_name, (start, end) in age_class_map.items():
                                if start <= age <= end:
                                    segment_values["age"].add(class_name)
                                    age_class_found = True
                                    break
                            if not age_class_found:
                                # If no age class found, use the raw age
                                segment_values["age"].add(f"{age}")

                        leaning = agent.get("leaning")
                        if leaning:
                            segment_values["political_leaning"].add(str(leaning))

                        gender = agent.get("gender")
                        if gender:
                            segment_values["gender"].add(str(gender))

                        education = agent.get("education_level")
                        if education:
                            segment_values["education_level"].add(str(education))
            print(f"Successfully loaded population file: {population_file}")
        else:
            print(f"Population file does not exist: {population_file}")
            flash(
                "Warning: Population file not found. Segment values may be limited.",
                "warning",
            )
    except Exception as e:
        print(f"Error reading population file: {e}")
        flash(
            f"Warning: Error reading population file. Segment values may be limited.",
            "warning",
        )

    # Convert sets to sorted lists
    segment_values = {k: sorted(list(v)) for k, v in segment_values.items()}
    print(f"Extracted segment values: {segment_values}")

    # Fetch available distribution types from the OpinionDistribution table
    opinion_distributions = OpinionDistribution.query.all()

    # Create a list of distribution dictionaries with name, type, and parameters
    distributions = []
    for dist in opinion_distributions:
        try:
            params = json.loads(dist.parameters)
            distributions.append(
                {
                    "id": dist.id,
                    "name": dist.name,
                    "type": dist.distribution_type,
                    "parameters": params,
                }
            )
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON parameters for distribution {dist.name}")
            continue

    # Extract just the names for the dropdown
    distribution_names = [d["name"] for d in distributions]

    # Fetch opinion groups from the database
    opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()

    # Create bins and labels from opinion groups
    # If no groups exist, use default bins
    if opinion_groups:
        # Create bins from group boundaries
        bins = []
        labels = []
        for group in opinion_groups:
            bins.append(group.lower_bound)
            labels.append(group.name)
        # Add the upper bound of the last group
        bins.append(opinion_groups[-1].upper_bound)
    else:
        # Default to 5 bins if no groups defined
        bins = [0.0, 0.25, 0.5, 0.75, 1.0]
        labels = ["0.0", "0.25", "0.5", "0.75"]

    # Define available segmentation dimensions
    segmentation_options = [
        {"id": "age", "name": "Age Classes"},
        {"id": "political_leaning", "name": "Political Leaning"},
        {"id": "gender", "name": "Gender"},
        {"id": "education_level", "name": "Education Level"},
    ]

    return render_template(
        "admin/opinion_configuration.html",
        experiment=exp,
        client=client,
        topics=topics,
        distributions=distributions,
        distribution_names=distribution_names,
        opinion_groups=opinion_groups,
        bins=bins,
        labels=labels,
        segmentation_options=segmentation_options,
        segment_values=segment_values,
        llm_agents_enabled=(
            exp.llm_agents_enabled if hasattr(exp, "llm_agents_enabled") else False
        ),
    )


@clientsr.route("/admin/set_opinion_distributions", methods=["POST"])
@login_required
def set_opinion_distributions():
    """Handle opinion distribution configuration submission and update population JSON."""
    check_privileges(current_user.username)

    # Get experiment ID and client ID from form
    idexp = request.form.get("idexp")
    client_id = request.form.get("client_id")

    if not idexp:
        flash("Experiment ID is missing.", "error")
        return redirect(url_for("experiments.settings"))

    if not client_id:
        flash("Client ID is missing.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Get experiment and client details
    exp = Exps.query.filter_by(idexp=idexp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    client = Client.query.filter_by(id=client_id).first()
    if not client or client.id_exp != int(idexp):
        flash("Client not found or does not belong to this experiment.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Get population
    population = Population.query.filter_by(id=client.population_id).first()
    if not population:
        flash("Population not found.", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Get the selected segmentation dimensions
    segmentation = request.form.get("segmentation", "")
    selected_dimensions = [d.strip() for d in segmentation.split(",") if d.strip()]

    # Parse form data to extract topic-segment-distribution mappings
    # Form fields are named: dist_topic_{topic_id}_segment_{segment_index}
    # Each select also has data-segment-name attribute with the actual segment name
    topic_segment_distributions = {}

    for key, value in request.form.items():
        if key.startswith("dist_topic_"):
            # Parse the field name: dist_topic_{topic_id}_segment_{segment_index}
            parts = key.split("_")
            if len(parts) >= 4:
                topic_id = int(parts[2])
                segment_index = int(parts[4])
                distribution_name = value

                if topic_id not in topic_segment_distributions:
                    topic_segment_distributions[topic_id] = {}

                topic_segment_distributions[topic_id][segment_index] = distribution_name

    # Get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics_list = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topic_id_to_name = {t.id: t.name for t in topics_list}

    # Load age classes for segment identification
    age_classes = AgeClass.query.all()
    age_class_map = {}
    for ac in age_classes:
        age_class_map[ac.name] = (ac.age_start, ac.age_end)

    # Load population JSON file
    from y_web.utils import get_db_type
    from y_web.utils.path_utils import get_writable_path

    writable_base = get_writable_path()
    dbtype = get_db_type()

    if dbtype == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    population_file = os.path.join(
        writable_base,
        "y_web",
        "experiments",
        exp_folder,
        f"{population.name.replace(' ', '')}.json",
    )

    if not os.path.exists(population_file):
        flash(f"Population file not found: {population_file}", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Load population data
    try:
        with open(population_file, "r") as f:
            pop_data = json.load(f)
    except Exception as e:
        flash(f"Error loading population file: {str(e)}", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Get all opinion distributions from database
    opinion_distributions = OpinionDistribution.query.all()
    distributions_map = {}
    for dist in opinion_distributions:
        try:
            params = json.loads(dist.parameters)
            distributions_map[dist.name] = {
                "type": dist.distribution_type,
                "parameters": params,
            }
        except json.JSONDecodeError as e:
            error_msg = (
                f"Invalid JSON parameters for distribution '{dist.name}': {str(e)}"
            )
            print(f"Warning: {error_msg}")
            flash(error_msg, "warning")

    # Helper function to identify segment for an agent
    def get_agent_segment(agent_data, dimensions):
        """Determine the segment for an agent based on selected dimensions."""
        if not dimensions:
            return "All Population"

        segment_parts = []
        for dim in dimensions:
            if dim == "age":
                age = agent_data.get("age")
                if age:
                    # Map age to age class
                    age_class_found = False
                    for class_name, (start, end) in age_class_map.items():
                        if start <= age <= end:
                            segment_parts.append(class_name)
                            age_class_found = True
                            break
                    if not age_class_found:
                        # Use "Other" for ages that don't fit any defined class
                        segment_parts.append(f"Age-{age}")
            elif dim == "political_leaning":
                leaning = agent_data.get("leaning")
                if leaning:
                    segment_parts.append(str(leaning))
            elif dim == "gender":
                gender = agent_data.get("gender")
                if gender:
                    segment_parts.append(str(gender))
            elif dim == "education_level":
                education = agent_data.get("education_level")
                if education:
                    segment_parts.append(str(education))

        return " - ".join(segment_parts) if segment_parts else "All Population"

    # Helper function to get segment index
    def get_segment_index(segment_name, dimensions, pop_data_agents):
        """Get the segment index based on segment name and dimensions."""
        # Generate all possible segments in the same order as the frontend
        if not dimensions:
            return 0

        # Collect unique values for each dimension from the population
        dimension_values = {dim: set() for dim in dimensions}

        for agent in pop_data_agents:
            if agent.get("is_page", 0):
                continue

            for dim in dimensions:
                if dim == "age":
                    age = agent.get("age")
                    if age:
                        for class_name, (start, end) in age_class_map.items():
                            if start <= age <= end:
                                dimension_values[dim].add(class_name)
                                break
                elif dim == "political_leaning":
                    leaning = agent.get("leaning")
                    if leaning:
                        dimension_values[dim].add(str(leaning))
                elif dim == "gender":
                    gender = agent.get("gender")
                    if gender:
                        dimension_values[dim].add(str(gender))
                elif dim == "education_level":
                    education = agent.get("education_level")
                    if education:
                        dimension_values[dim].add(str(education))

        # Sort values for each dimension
        dimension_values = {k: sorted(list(v)) for k, v in dimension_values.items()}

        # Generate all segments in order
        segments = [""]
        for dim in dimensions:
            values = dimension_values.get(dim, [])
            if not values:
                continue

            new_segments = []
            for segment in segments:
                for value in values:
                    new_segments.append(segment + " - " + value if segment else value)
            segments = new_segments

        # Find the index of our segment
        try:
            return segments.index(segment_name)
        except ValueError:
            return 0

    # Helper function to sample from a distribution
    def sample_from_distribution(distribution_name):
        """Sample a value from the specified distribution."""
        if distribution_name not in distributions_map:
            # Default to uniform random if distribution not found
            return random.random()

        dist_info = distributions_map[distribution_name]
        dist_type = dist_info["type"]
        params = dist_info["parameters"]

        try:
            if dist_type == "uniform":
                return np.random.uniform(0, 1)
            elif dist_type == "normal":
                loc = params.get("loc", 0.5)
                scale = params.get("scale", 0.2)
                # Clip to [0, 1] range
                value = np.random.normal(loc, scale)
                return max(0.0, min(1.0, value))
            elif dist_type == "beta":
                a = params.get("a", 2)
                b = params.get("b", 5)
                return np.random.beta(a, b)
            elif dist_type == "exponential":
                scale = params.get("scale", 1)
                # Scale and clip to [0, 1]
                value = np.random.exponential(scale)
                return max(0.0, min(1.0, value))
            elif dist_type == "gamma":
                shape = params.get("shape", 2)
                scale = params.get("scale", 1)
                # Scale and clip to [0, 1] using DISTRIBUTION_SCALE_FACTOR
                value = np.random.gamma(shape, scale)
                return max(0.0, min(1.0, value / DISTRIBUTION_SCALE_FACTOR))
            elif dist_type == "lognormal":
                mean = params.get("mean", 0)
                sigma = params.get("sigma", 1)
                # Scale and clip to [0, 1] using DISTRIBUTION_SCALE_FACTOR
                value = np.random.lognormal(mean, sigma)
                return max(0.0, min(1.0, value / DISTRIBUTION_SCALE_FACTOR))
            elif dist_type == "bimodal":
                peak1 = params.get("peak1", 0.2)
                peak2 = params.get("peak2", 0.8)
                sigma = params.get("sigma", 0.15)
                # Randomly choose one of the two peaks
                if np.random.random() < 0.5:
                    value = np.random.normal(peak1, sigma)
                else:
                    value = np.random.normal(peak2, sigma)
                return max(0.0, min(1.0, value))
            elif dist_type == "polarized":
                # Sample from extremes (0 or 1 with some noise)
                if np.random.random() < 0.5:
                    value = np.random.normal(0.0, 0.1)
                else:
                    value = np.random.normal(1.0, 0.1)
                return max(0.0, min(1.0, value))
            else:
                # Default to uniform if type not recognized
                return np.random.uniform(0, 1)
        except Exception as e:
            error_msg = (
                f"Error sampling from distribution '{distribution_name}': {str(e)}"
            )
            print(f"Warning: {error_msg}")
            flash(error_msg, "warning")
            return random.random()

    # Process each agent in the population
    updated_count = 0
    for agent in pop_data.get("agents", []):
        # Skip pages
        if agent.get("is_page", 0):
            continue

        # Get agent's segment
        agent_segment = get_agent_segment(agent, selected_dimensions)
        segment_index = get_segment_index(
            agent_segment, selected_dimensions, pop_data["agents"]
        )

        # Get agent's interests (topics)
        interests = agent.get("interests", [])
        if isinstance(interests, list) and len(interests) > 0:
            topic_names = interests[0] if isinstance(interests[0], list) else interests
        else:
            topic_names = []

        # Initialize or update opinions for this agent
        if "opinions" not in agent or agent["opinions"] is None:
            agent["opinions"] = {}

        # For each topic the agent is interested in
        for topic_name in topic_names:
            # Find the topic ID
            topic_id = None
            for tid, tname in topic_id_to_name.items():
                if tname == topic_name:
                    topic_id = tid
                    break

            if topic_id is None:
                continue

            # Get the distribution for this topic-segment combination
            if topic_id in topic_segment_distributions:
                if segment_index in topic_segment_distributions[topic_id]:
                    distribution_name = topic_segment_distributions[topic_id][
                        segment_index
                    ]
                    # Sample a value from the distribution
                    opinion_value = sample_from_distribution(distribution_name)
                    agent["opinions"][topic_name] = opinion_value
                    updated_count += 1

    # Save the updated population JSON file
    try:
        with open(population_file, "w") as f:
            json.dump(pop_data, f, indent=4)
        flash(
            f"Successfully updated opinions for {updated_count} agent-topic pairs.",
            "success",
        )
    except Exception as e:
        flash(f"Error saving population file: {str(e)}", "error")
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    # Check if this is an HPC experiment
    is_hpc = exp.simulator_type == "HPC" if hasattr(exp, "simulator_type") else False

    # Check if opinions are enabled for the experiment
    annotations = (
        {an.strip(): None for an in exp.annotations.split(",")}
        if exp.annotations and exp.annotations.strip()
        else {}
    )
    opinions_enabled = "opinions" in annotations

    # Build opinion dynamics configuration for HPC clients
    if is_hpc:
        if opinions_enabled:
            # Get opinion update rule from form
            update_rule = request.form.get("update_rule", "bounded_confidence")

            # Build HPC-specific opinion dynamics configuration
            opinion_dynamics = {"enabled": True, "model_name": update_rule}

            if update_rule == "bounded_confidence":
                # Collect bounded confidence parameters
                bc_epsilon = request.form.get("bc_epsilon", "0.25")
                bc_mu = request.form.get("bc_mu", "0.5")
                bc_theta = request.form.get("bc_theta", "0.0")
                bc_cold_start = request.form.get("bc_cold_start", "neutral")

                opinion_dynamics["parameters"] = {
                    "epsilon": float(bc_epsilon),
                    "mu": float(bc_mu),
                    "theta": float(bc_theta),
                    "cold_start": bc_cold_start,
                }
            elif update_rule == "llm_evaluation":
                # Collect LLM evaluation parameters
                llm_cold_start = request.form.get("llm_cold_start", "neutral")
                llm_evaluation_scope = request.form.get(
                    "llm_evaluation_scope", "neighbors"
                )

                opinion_dynamics["note"] = (
                    "Uses LLM-based opinion evaluation with natural language reasoning. Requires LLM agents."
                )
                opinion_dynamics["parameters"] = {
                    "evaluation_scope": llm_evaluation_scope,
                    "cold_start": llm_cold_start,
                    "note": f"evaluation_scope='{llm_evaluation_scope}' considers opinions of followed users. cold_start='{llm_cold_start}' initializes new opinions at 0.5.",
                }

            # Add opinion groups from database
            opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()
            opinion_groups_dict = {}
            for group in opinion_groups:
                opinion_groups_dict[group.name.rstrip()] = [
                    group.lower_bound,
                    group.upper_bound,
                ]

            opinion_dynamics["opinion_groups"] = opinion_groups_dict
        else:
            # Opinion dynamics disabled for HPC
            opinion_dynamics = {
                "enabled": False,
                "note": "Opinion dynamics disabled for this experiment. No opinion evolution occurs during simulation.",
            }

        # Load and update HPC client configuration JSON file
        client_config_file = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp_folder,
            f"client_{client.name}-{population.name}.json",
        )

        if os.path.exists(client_config_file):
            try:
                with open(client_config_file, "r") as f:
                    client_config = json.load(f)

                # Add opinion_dynamics at root level for HPC clients
                client_config["opinion_dynamics"] = opinion_dynamics

                # Save updated configuration
                with open(client_config_file, "w") as f:
                    json.dump(client_config, f, indent=4)

                flash("Opinion dynamics configuration saved successfully.", "success")
            except Exception as e:
                flash(f"Error updating client configuration: {str(e)}", "warning")
        else:
            flash(
                f"Client configuration file not found: {client_config_file}", "warning"
            )
    else:
        # Standard client configuration (original behavior)
        # Get opinion update rule from form
        update_rule = request.form.get("update_rule", "bounded_confidence")

        # Build opinion dynamics configuration based on selected rule
        opinion_dynamics = {"model_name": update_rule, "parameters": {}}

        if update_rule == "bounded_confidence":
            # Collect bounded confidence parameters
            bc_epsilon = request.form.get("bc_epsilon", "0.25")
            bc_mu = request.form.get("bc_mu", "0.5")
            bc_theta = request.form.get("bc_theta", "0")
            bc_cold_start = request.form.get("bc_cold_start", "neutral")

            opinion_dynamics["parameters"] = {
                "epsilon": float(bc_epsilon),
                "mu": float(bc_mu),
                "theta": float(bc_theta),
                "cold_start": bc_cold_start,
            }
        elif update_rule == "llm_evaluation":
            # Collect LLM evaluation parameters
            llm_cold_start = request.form.get("llm_cold_start", "neutral")
            llm_evaluation_scope = request.form.get(
                "llm_evaluation_scope", "interlocutor_only"
            )

            opinion_dynamics["parameters"] = {
                "cold_start": llm_cold_start,
                "evaluation_scope": llm_evaluation_scope,
            }

        # Add opinion groups from database
        opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()
        opinion_groups_dict = {}
        for group in opinion_groups:
            opinion_groups_dict[group.name.rstrip()] = [
                group.lower_bound,
                group.upper_bound,
            ]

        opinion_dynamics["opinion_groups"] = opinion_groups_dict

        # Load and update client configuration JSON file
        client_config_file = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp_folder,
            f"client_{client.name}-{population.name}.json",
        )

        if os.path.exists(client_config_file):
            try:
                with open(client_config_file, "r") as f:
                    client_config = json.load(f)

                # Add opinion_dynamics to simulation section
                if "simulation" not in client_config:
                    client_config["simulation"] = {}

                client_config["simulation"]["opinion_dynamics"] = opinion_dynamics

                # Save updated configuration
                with open(client_config_file, "w") as f:
                    json.dump(client_config, f, indent=4)

                flash("Opinion dynamics configuration saved successfully.", "success")
            except Exception as e:
                flash(f"Error updating client configuration: {str(e)}", "warning")
        else:
            flash(
                f"Client configuration file not found: {client_config_file}", "warning"
            )

    return redirect(url_for("experiments.experiment_details", uid=idexp))
