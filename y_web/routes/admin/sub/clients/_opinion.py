"""Opinion configuration and distribution routes."""
import json
import os
import random

import numpy as np
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.src.models import (
    AgeClass,
    Client,
    Exp_Topic,
    Exps,
    OpinionDistribution,
    OpinionGroup,
    Population,
    Topic_List,
)
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import DISTRIBUTION_SCALE_FACTOR, clientsr
from ._crud import _get_experiment_folder_name, _get_experiment_mode

def _opinion_configuration_internal(idexp, expected_mode):
    """Display opinion configuration page for the expected experiment modality."""
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

    actual_mode = (
        "hpc"
        if getattr(exp, "simulator_type", "Standard") == "HPC"
        else ("forum" if exp.platform_type == "forum" else "standard")
    )
    if actual_mode != expected_mode:
        flash(
            "Opinion configuration route does not match the experiment modality.",
            "error",
        )
        if actual_mode == "hpc":
            return redirect(
                url_for(
                    "clientsr.opinion_configuration_hpc",
                    idexp=idexp,
                    client_id=client_id,
                )
            )
        if actual_mode == "forum":
            return redirect(
                url_for(
                    "clientsr.opinion_configuration_forum",
                    idexp=idexp,
                    client_id=client_id,
                )
            )
        return redirect(
            url_for(
                "clientsr.opinion_configuration_standard",
                idexp=idexp,
                client_id=client_id,
            )
        )

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
    from y_web.src.system.miscellanea import get_db_type
    from y_web.src.system.path_utils import get_writable_path

    writable_base = get_writable_path()
    dbtype = get_db_type()

    if dbtype == "sqlite":
        exp_folder = exp.db_name.split(os.sep)[1]
    else:
        exp_folder = exp.db_name.removeprefix("experiments_")

    # Read server config to resolve opinion dynamics global toggle.
    server_cfg = os.path.join(
        writable_base,
        "y_web",
        "experiments",
        exp_folder,
        "server_config.json" if exp.simulator_type == "HPC" else "config_server.json",
    )
    opinion_dynamics_global_enabled = False
    if os.path.exists(server_cfg):
        try:
            with open(server_cfg, "r") as sf:
                scfg = json.load(sf)
            opinion_dynamics_global_enabled = bool(
                scfg.get(
                    "opinion_dynamics_enabled",
                    bool(exp.annotations and "opinions" in exp.annotations),
                )
            )
        except Exception:
            opinion_dynamics_global_enabled = bool(
                exp.annotations and "opinions" in exp.annotations
            )
    else:
        opinion_dynamics_global_enabled = bool(
            exp.annotations and "opinions" in exp.annotations
        )

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

    template_name = {
        "standard": "admin/opinion_configuration.html",
        "forum": "admin/opinion_configuration_forum.html",
        "hpc": "admin/opinion_configuration_hpc.html",
    }[expected_mode]

    return render_template(
        template_name,
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


@clientsr.route("/admin/opinion_configuration_standard/<int:idexp>")
@login_required
def opinion_configuration_standard(idexp):
    """Display opinion configuration for a standard microblogging experiment."""
    return _opinion_configuration_internal(idexp, "standard")


@clientsr.route("/admin/opinion_configuration_forum/<int:idexp>")
@login_required
def opinion_configuration_forum(idexp):
    """Display opinion configuration for a forum experiment."""
    return _opinion_configuration_internal(idexp, "forum")


@clientsr.route("/admin/opinion_configuration_hpc/<int:idexp>")
@login_required
def opinion_configuration_hpc(idexp):
    """Display opinion configuration for an HPC experiment."""
    return _opinion_configuration_internal(idexp, "hpc")


@clientsr.route("/admin/opinion_configuration/<int:idexp>")
@login_required
def opinion_configuration(idexp):
    """Backward-compatible dispatcher for opinion configuration routes."""
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=idexp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    client_id = request.args.get("client_id", type=int)
    experiment_mode = _get_experiment_mode(exp)
    if experiment_mode == "hpc":
        return redirect(
            url_for(
                "clientsr.opinion_configuration_hpc", idexp=idexp, client_id=client_id
            )
        )
    if experiment_mode == "forum":
        return redirect(
            url_for(
                "clientsr.opinion_configuration_forum", idexp=idexp, client_id=client_id
            )
        )
    return redirect(
        url_for(
            "clientsr.opinion_configuration_standard", idexp=idexp, client_id=client_id
        )
    )


def _build_topic_segment_distributions():
    """Parse topic/segment distribution selections from the submitted form."""
    topic_segment_distributions = {}
    for key, value in request.form.items():
        if key.startswith("dist_topic_"):
            parts = key.split("_")
            if len(parts) >= 4:
                topic_id = int(parts[2])
                segment_index = int(parts[4])
                topic_segment_distributions.setdefault(topic_id, {})[
                    segment_index
                ] = value
    return topic_segment_distributions


def _sample_opinion_from_distribution(distribution_name, distributions_map):
    """Sample a value from the named opinion distribution."""
    if distribution_name not in distributions_map:
        return random.random()

    dist_info = distributions_map[distribution_name]
    dist_type = dist_info["type"]
    params = dist_info["parameters"]

    try:
        if dist_type == "uniform":
            return np.random.uniform(0, 1)
        if dist_type == "normal":
            value = np.random.normal(params.get("loc", 0.5), params.get("scale", 0.2))
            return max(0.0, min(1.0, value))
        if dist_type == "beta":
            return np.random.beta(params.get("a", 2), params.get("b", 5))
        if dist_type == "exponential":
            value = np.random.exponential(params.get("scale", 1))
            return max(0.0, min(1.0, value))
        if dist_type == "gamma":
            value = np.random.gamma(params.get("shape", 2), params.get("scale", 1))
            return max(0.0, min(1.0, value / DISTRIBUTION_SCALE_FACTOR))
        if dist_type == "lognormal":
            value = np.random.lognormal(params.get("mean", 0), params.get("sigma", 1))
            return max(0.0, min(1.0, value / DISTRIBUTION_SCALE_FACTOR))
        if dist_type == "bimodal":
            peak = params.get("peak1", 0.2)
            if np.random.random() >= 0.5:
                peak = params.get("peak2", 0.8)
            value = np.random.normal(peak, params.get("sigma", 0.15))
            return max(0.0, min(1.0, value))
        if dist_type == "polarized":
            value = np.random.normal(0.0, 0.1)
            if np.random.random() >= 0.5:
                value = np.random.normal(1.0, 0.1)
            return max(0.0, min(1.0, value))
        return np.random.uniform(0, 1)
    except Exception as e:
        flash(
            f"Error sampling from distribution '{distribution_name}': {str(e)}",
            "warning",
        )
        return random.random()


def _get_agent_segment(agent_data, dimensions, age_class_map):
    """Determine the segment label for an agent."""
    if not dimensions:
        return "All Population"

    segment_parts = []
    for dim in dimensions:
        if dim == "age":
            age = agent_data.get("age")
            if age:
                matched = False
                for class_name, (start, end) in age_class_map.items():
                    if start <= age <= end:
                        segment_parts.append(class_name)
                        matched = True
                        break
                if not matched:
                    segment_parts.append(f"Age-{age}")
        elif dim == "political_leaning" and agent_data.get("leaning"):
            segment_parts.append(str(agent_data.get("leaning")))
        elif dim == "gender" and agent_data.get("gender"):
            segment_parts.append(str(agent_data.get("gender")))
        elif dim == "education_level" and agent_data.get("education_level"):
            segment_parts.append(str(agent_data.get("education_level")))

    return " - ".join(segment_parts) if segment_parts else "All Population"


def _get_segment_index(segment_name, dimensions, pop_data_agents, age_class_map):
    """Map a segment label to the index used by the frontend."""
    if not dimensions:
        return 0

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
            elif dim == "political_leaning" and agent.get("leaning"):
                dimension_values[dim].add(str(agent.get("leaning")))
            elif dim == "gender" and agent.get("gender"):
                dimension_values[dim].add(str(agent.get("gender")))
            elif dim == "education_level" and agent.get("education_level"):
                dimension_values[dim].add(str(agent.get("education_level")))

    dimension_values = {
        key: sorted(list(values)) for key, values in dimension_values.items()
    }
    segments = [""]
    for dim in dimensions:
        values = dimension_values.get(dim, [])
        if not values:
            continue
        next_segments = []
        for segment in segments:
            for value in values:
                next_segments.append(segment + " - " + value if segment else value)
        segments = next_segments

    try:
        return segments.index(segment_name)
    except ValueError:
        return 0


def _build_opinion_groups_dict():
    """Load opinion groups as config-friendly bounds."""
    opinion_groups = OpinionGroup.query.order_by(OpinionGroup.lower_bound).all()
    opinion_groups_dict = {}
    for group in opinion_groups:
        opinion_groups_dict[group.name.rstrip()] = [
            group.lower_bound,
            group.upper_bound,
        ]
    return opinion_groups_dict


def _resolve_opinion_submission_context(expected_mode):
    """Validate the submission and load common opinion-distribution state."""
    check_privileges(current_user.username)

    idexp = request.form.get("idexp")
    client_id = request.form.get("client_id")
    if not idexp:
        return None, redirect(url_for("experiments.settings"))
    if not client_id:
        flash("Client ID is missing.", "error")
        return None, redirect(url_for("experiments.experiment_details", uid=idexp))

    exp = Exps.query.filter_by(idexp=idexp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return None, redirect(url_for("experiments.settings"))

    actual_mode = (
        "hpc"
        if getattr(exp, "simulator_type", "Standard") == "HPC"
        else ("forum" if exp.platform_type == "forum" else "standard")
    )
    if actual_mode != expected_mode:
        flash(
            "Opinion distribution update route does not match the experiment modality.",
            "error",
        )
        if actual_mode == "hpc":
            return None, redirect(
                url_for(
                    "clientsr.opinion_configuration_hpc",
                    idexp=idexp,
                    client_id=client_id,
                )
            )
        if actual_mode == "forum":
            return None, redirect(
                url_for(
                    "clientsr.opinion_configuration_forum",
                    idexp=idexp,
                    client_id=client_id,
                )
            )
        return None, redirect(
            url_for(
                "clientsr.opinion_configuration_standard",
                idexp=idexp,
                client_id=client_id,
            )
        )

    client = Client.query.filter_by(id=client_id).first()
    if not client or client.id_exp != int(idexp):
        flash("Client not found or does not belong to this experiment.", "error")
        return None, redirect(url_for("experiments.experiment_details", uid=idexp))

    population = Population.query.filter_by(id=client.population_id).first()
    if not population:
        flash("Population not found.", "error")
        return None, redirect(url_for("experiments.experiment_details", uid=idexp))

    selected_dimensions = [
        value.strip()
        for value in (request.form.get("segmentation", "")).split(",")
        if value.strip()
    ]
    topic_segment_distributions = _build_topic_segment_distributions()

    topics = Exp_Topic.query.filter_by(exp_id=idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics_list = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topic_id_to_name = {t.id: t.name for t in topics_list}

    age_class_map = {ac.name: (ac.age_start, ac.age_end) for ac in AgeClass.query.all()}

    from y_web.src.system.path_utils import get_writable_path

    writable_base = get_writable_path()
    exp_folder = _get_experiment_folder_name(exp)
    population_file = os.path.join(
        writable_base,
        "y_web",
        "experiments",
        exp_folder,
        f"{population.name.replace(' ', '')}.json",
    )
    if not os.path.exists(population_file):
        flash(f"Population file not found: {population_file}", "error")
        return None, redirect(url_for("experiments.experiment_details", uid=idexp))

    try:
        with open(population_file, "r") as handle:
            pop_data = json.load(handle)
    except Exception as e:
        flash(f"Error loading population file: {str(e)}", "error")
        return None, redirect(url_for("experiments.experiment_details", uid=idexp))

    distributions_map = {}
    for dist in OpinionDistribution.query.all():
        try:
            distributions_map[dist.name] = {
                "type": dist.distribution_type,
                "parameters": json.loads(dist.parameters),
            }
        except json.JSONDecodeError as e:
            flash(
                f"Invalid JSON parameters for distribution '{dist.name}': {str(e)}",
                "warning",
            )

    server_cfg = os.path.join(
        writable_base,
        "y_web",
        "experiments",
        exp_folder,
        "server_config.json" if actual_mode == "hpc" else "config_server.json",
    )
    opinion_dynamics_global_enabled = False
    if os.path.exists(server_cfg):
        try:
            with open(server_cfg, "r") as handle:
                scfg = json.load(handle)
            opinion_dynamics_global_enabled = bool(
                scfg.get(
                    "opinion_dynamics_enabled",
                    scfg.get(
                        "opinions_enabled",
                        bool(exp.annotations and "opinions" in exp.annotations),
                    ),
                )
            )
        except Exception:
            opinion_dynamics_global_enabled = bool(
                exp.annotations and "opinions" in exp.annotations
            )
    else:
        opinion_dynamics_global_enabled = bool(
            exp.annotations and "opinions" in exp.annotations
        )

    annotations = (
        {an.strip(): None for an in exp.annotations.split(",")}
        if exp.annotations and exp.annotations.strip()
        else {}
    )
    opinion_dynamics_enabled = (
        "opinions" in annotations and opinion_dynamics_global_enabled
    )

    client_config_file = os.path.join(
        writable_base,
        "y_web",
        "experiments",
        exp_folder,
        f"client_{client.name}-{population.name}.json",
    )

    return {
        "idexp": idexp,
        "client_id": client_id,
        "exp": exp,
        "client": client,
        "population": population,
        "selected_dimensions": selected_dimensions,
        "topic_segment_distributions": topic_segment_distributions,
        "topic_id_to_name": topic_id_to_name,
        "age_class_map": age_class_map,
        "pop_data": pop_data,
        "population_file": population_file,
        "distributions_map": distributions_map,
        "opinion_dynamics_enabled": opinion_dynamics_enabled,
        "client_config_file": client_config_file,
    }, None


def _apply_opinion_distributions_to_population(context):
    """Update the population payload according to the submitted distributions."""
    updated_count = 0
    pop_data = context["pop_data"]
    for agent in pop_data.get("agents", []):
        if agent.get("is_page", 0):
            continue

        agent_segment = _get_agent_segment(
            agent, context["selected_dimensions"], context["age_class_map"]
        )
        segment_index = _get_segment_index(
            agent_segment,
            context["selected_dimensions"],
            pop_data["agents"],
            context["age_class_map"],
        )

        interests = agent.get("interests", [])
        topic_names = (
            interests[0]
            if isinstance(interests, list)
            and interests
            and isinstance(interests[0], list)
            else interests
        )
        if "opinions" not in agent or agent["opinions"] is None:
            agent["opinions"] = {}

        for topic_name in topic_names or []:
            topic_id = None
            for tid, tname in context["topic_id_to_name"].items():
                if tname == topic_name:
                    topic_id = tid
                    break
            if topic_id is None:
                continue
            selected = context["topic_segment_distributions"].get(topic_id, {})
            if segment_index in selected:
                agent["opinions"][topic_name] = _sample_opinion_from_distribution(
                    selected[segment_index], context["distributions_map"]
                )
                updated_count += 1

    try:
        with open(context["population_file"], "w") as handle:
            json.dump(pop_data, handle, indent=4)
        flash(
            f"Successfully updated opinions for {updated_count} agent-topic pairs.",
            "success",
        )
    except Exception as e:
        flash(f"Error saving population file: {str(e)}", "error")
        return redirect(url_for("experiments.experiment_details", uid=context["idexp"]))
    return None


def _persist_non_hpc_opinion_dynamics(context):
    """Persist standard/forum opinion dynamics configuration to client config."""
    update_rule = request.form.get("update_rule", "bounded_confidence")
    opinion_dynamics = {
        "enabled": context["opinion_dynamics_enabled"],
        "model_name": update_rule,
        "parameters": {},
        "opinion_groups": _build_opinion_groups_dict(),
    }

    if update_rule == "bounded_confidence":
        opinion_dynamics["parameters"] = {
            "epsilon": float(request.form.get("bc_epsilon", "0.25")),
            "mu": float(request.form.get("bc_mu", "0.5")),
            "theta": float(request.form.get("bc_theta", "0")),
            "cold_start": request.form.get("bc_cold_start", "neutral"),
        }
    elif update_rule == "llm_evaluation":
        opinion_dynamics["parameters"] = {
            "cold_start": request.form.get("llm_cold_start", "neutral"),
            "evaluation_scope": request.form.get(
                "llm_evaluation_scope", "interlocutor_only"
            ),
        }

    if os.path.exists(context["client_config_file"]):
        try:
            with open(context["client_config_file"], "r") as handle:
                client_config = json.load(handle)
            client_config.setdefault("simulation", {})[
                "opinion_dynamics"
            ] = opinion_dynamics
            with open(context["client_config_file"], "w") as handle:
                json.dump(client_config, handle, indent=4)
            flash("Opinion dynamics configuration saved successfully.", "success")
        except Exception as e:
            flash(f"Error updating client configuration: {str(e)}", "warning")
    else:
        flash(
            f"Client configuration file not found: {context['client_config_file']}",
            "warning",
        )


def _persist_hpc_opinion_dynamics(context):
    """Persist HPC opinion dynamics configuration to client config."""
    if context["opinion_dynamics_enabled"]:
        update_rule = request.form.get("update_rule", "bounded_confidence")
        opinion_dynamics = {
            "enabled": True,
            "model_name": update_rule,
            "opinion_groups": _build_opinion_groups_dict(),
        }
        if update_rule == "bounded_confidence":
            opinion_dynamics["parameters"] = {
                "epsilon": float(request.form.get("bc_epsilon", "0.25")),
                "mu": float(request.form.get("bc_mu", "0.5")),
                "theta": float(request.form.get("bc_theta", "0.0")),
                "cold_start": request.form.get("bc_cold_start", "neutral"),
            }
        elif update_rule == "llm_evaluation":
            llm_cold_start = request.form.get("llm_cold_start", "neutral")
            llm_evaluation_scope = request.form.get("llm_evaluation_scope", "neighbors")
            opinion_dynamics["note"] = (
                "Uses LLM-based opinion evaluation with natural language reasoning. Requires LLM agents."
            )
            opinion_dynamics["parameters"] = {
                "evaluation_scope": llm_evaluation_scope,
                "cold_start": llm_cold_start,
                "note": f"evaluation_scope='{llm_evaluation_scope}' considers opinions of followed users. cold_start='{llm_cold_start}' initializes new opinions at 0.5.",
            }
    else:
        opinion_dynamics = {
            "enabled": False,
            "note": "Opinion dynamics disabled for this experiment. No opinion evolution occurs during simulation.",
        }

    if os.path.exists(context["client_config_file"]):
        try:
            with open(context["client_config_file"], "r") as handle:
                client_config = json.load(handle)
            client_config["opinion_dynamics"] = opinion_dynamics
            with open(context["client_config_file"], "w") as handle:
                json.dump(client_config, handle, indent=4)
            flash("Opinion dynamics configuration saved successfully.", "success")
        except Exception as e:
            flash(f"Error updating client configuration: {str(e)}", "warning")
    else:
        flash(
            f"Client configuration file not found: {context['client_config_file']}",
            "warning",
        )


def _set_standard_opinion_distributions_internal():
    """Persist opinion distributions for standard microblogging experiments."""
    context, error_response = _resolve_opinion_submission_context("standard")
    if error_response is not None:
        return error_response
    save_error = _apply_opinion_distributions_to_population(context)
    if save_error is not None:
        return save_error
    _persist_non_hpc_opinion_dynamics(context)
    return redirect(url_for("experiments.experiment_details", uid=context["idexp"]))


def _set_forum_opinion_distributions_internal():
    """Persist opinion distributions for forum experiments."""
    context, error_response = _resolve_opinion_submission_context("forum")
    if error_response is not None:
        return error_response
    save_error = _apply_opinion_distributions_to_population(context)
    if save_error is not None:
        return save_error
    _persist_non_hpc_opinion_dynamics(context)
    return redirect(url_for("experiments.experiment_details", uid=context["idexp"]))


def _set_hpc_opinion_distributions_internal():
    """Persist opinion distributions for HPC experiments."""
    context, error_response = _resolve_opinion_submission_context("hpc")
    if error_response is not None:
        return error_response
    save_error = _apply_opinion_distributions_to_population(context)
    if save_error is not None:
        return save_error
    _persist_hpc_opinion_dynamics(context)
    return redirect(url_for("experiments.experiment_details", uid=context["idexp"]))


@clientsr.route("/admin/set_standard_opinion_distributions", methods=["POST"])
@login_required
def set_standard_opinion_distributions():
    """Persist opinion distributions for a standard microblogging experiment."""
    return _set_standard_opinion_distributions_internal()


@clientsr.route("/admin/set_forum_opinion_distributions", methods=["POST"])
@login_required
def set_forum_opinion_distributions():
    """Persist opinion distributions for a forum experiment."""
    return _set_forum_opinion_distributions_internal()


@clientsr.route("/admin/set_hpc_opinion_distributions", methods=["POST"])
@login_required
def set_hpc_opinion_distributions():
    """Persist opinion distributions for an HPC experiment."""
    return _set_hpc_opinion_distributions_internal()


@clientsr.route("/admin/set_opinion_distributions", methods=["POST"])
@login_required
def set_opinion_distributions():
    """Backward-compatible dispatcher for opinion distribution persistence."""
    check_privileges(current_user.username)

    idexp = request.form.get("idexp")
    exp = Exps.query.filter_by(idexp=idexp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    experiment_mode = _get_experiment_mode(exp)
    if experiment_mode == "hpc":
        return set_hpc_opinion_distributions()
    if experiment_mode == "forum":
        return set_forum_opinion_distributions()
    return set_standard_opinion_distributions()
