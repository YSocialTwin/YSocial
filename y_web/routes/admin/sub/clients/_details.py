"""Client detail view routes."""
import json
import os

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.src.models import (
    Agent,
    Agent_Population,
    Client,
    Client_Execution,
    Content_Recsys,
    Exps,
    Follow_Recsys,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
)
from y_web.src.llm.vllm_manager import get_llm_models
from y_web.src.system.desktop_file_handler import send_file_desktop
from y_web.src.system.miscellanea import check_privileges, get_db_type, llm_backend_status

from ._blueprint import clientsr
from ._crud import (
    _build_client_creation_context,
    _build_hourly_activity_chart_series,
    _extract_llm_names_from_population_payload,
    _get_client_population_pages,
    _get_experiment_folder_name,
    _get_experiment_mode,
    _read_json_if_exists,
)
from ._helpers import _forum_effective_link_share

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
    if experiment and experiment.platform_type == "forum":
        return redirect(url_for("clientsr.client_details_forum", uid=uid))

    population = Population.query.filter_by(id=client.population_id).first()
    pages = _get_client_population_pages(client)

    from y_web.src.system.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = _get_experiment_folder_name(experiment)
    config_path = os.path.join(
        base_dir,
        "y_web",
        "experiments",
        exp_folder,
        f"client_{client.name}-{population.name}.json",
    )
    population_path = os.path.join(
        base_dir,
        "y_web",
        "experiments",
        exp_folder,
        f"{population.name}.json",
    )

    config = _read_json_if_exists(config_path)
    agents = _read_json_if_exists(population_path)
    llms = _extract_llm_names_from_population_payload(agents)

    activity = ((config or {}).get("simulation") or {}).get("hourly_activity") or {
        str(hour): 0 for hour in range(24)
    }
    idx, data = _build_hourly_activity_chart_series(activity)

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


@clientsr.route("/admin/client_details_forum/<int:uid>")
@login_required
def client_details_forum(uid):
    """Handle forum client details operation."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.settings"))

    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    if not experiment:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    if experiment.simulator_type == "HPC":
        return redirect(url_for("clientsr.client_details_hpc", uid=uid))
    if experiment.platform_type != "forum":
        return redirect(url_for("clientsr.client_details", uid=uid))

    population = Population.query.filter_by(id=client.population_id).first()
    pages = _get_client_population_pages(client)

    from y_web.src.system.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = _get_experiment_folder_name(experiment)
    config_path = os.path.join(
        base_dir,
        "y_web",
        "experiments",
        exp_folder,
        f"client_{client.name}-{population.name}.json",
    )
    population_path = os.path.join(
        base_dir,
        "y_web",
        "experiments",
        exp_folder,
        f"{population.name}.json",
    )

    config = _read_json_if_exists(config_path)
    agents = _read_json_if_exists(population_path)
    llms = _extract_llm_names_from_population_payload(agents)

    activity = ((config or {}).get("simulation") or {}).get("hourly_activity") or {
        str(hour): 0 for hour in range(24)
    }
    idx, data = _build_hourly_activity_chart_series(activity)

    models = get_llm_models()
    llm_backend = llm_backend_status()

    frecsys_all = Follow_Recsys.query.all()
    crecsys_all = Content_Recsys.query.all()
    frecsys = [r for r in frecsys_all if r.enabled and "Standard" in r.enabled]
    crecsys = [r for r in crecsys_all if r.enabled and "Standard" in r.enabled]

    forum_action_weights = {
        "post": client.post,
        "comment": client.comment,
        "read": client.read,
        "search": client.search,
        "share_link": _forum_effective_link_share(client.news, client.share_link),
        "share_image": ((config or {}).get("simulation") or {})
        .get("actions_likelihood", {})
        .get("share_image", 0.0),
    }

    return render_template(
        "admin/client_details_forum.html",
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
        forum_action_weights=forum_action_weights,
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

    population = Population.query.filter_by(id=client.population_id).first()
    pages = _get_client_population_pages(client)

    from y_web.src.system.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = _get_experiment_folder_name(experiment)
    config_path = os.path.join(
        base_dir,
        "y_web",
        "experiments",
        exp_folder,
        f"client_{client.name}-{population.name}.json",
    )
    population_path = os.path.join(
        base_dir,
        "y_web",
        "experiments",
        exp_folder,
        f"{population.name}.json",
    )

    config = _read_json_if_exists(config_path)
    if config is None:
        flash("HPC client configuration file not found.", "warning")

    agents = _read_json_if_exists(population_path)
    llms = _extract_llm_names_from_population_payload(agents)

    # Extract activity data from HPC config structure
    data = []
    idx = []
    activity = None

    if config and "simulation" in config and "hourly_activity" in config["simulation"]:
        activity = config["simulation"]["hourly_activity"]
        idx, data = _build_hourly_activity_chart_series(activity)
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
            idx, data = _build_hourly_activity_chart_series(activity)

    if not activity:
        activity = {str(x): 0 for x in range(24)}
        idx, data = _build_hourly_activity_chart_series(activity)

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
    from y_web.src.system.path_utils import get_writable_path

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
    from y_web.src.system.path_utils import get_writable_path

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

    from y_web.src.system.path_utils import get_writable_path

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
