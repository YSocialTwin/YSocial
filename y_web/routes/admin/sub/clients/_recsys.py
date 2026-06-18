"""Recommender system and LLM update routes for clients."""

import json
import os

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from y_web import db
from y_web.src.models import (
    Agent,
    Agent_Population,
    Client,
    Exp_Topic,
    Exps,
    Population,
    Topic_List,
    User_mgmt,
)
from y_web.src.system.miscellanea import check_privileges

from ._blueprint import clientsr
from ._crud import _get_experiment_folder_name, _get_experiment_mode


def _update_client_simulation_internal(uid, expected_mode):
    """Update visible simulation parameters and action likelihoods."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.settings"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    actual_mode = _get_experiment_mode(exp)
    if actual_mode != expected_mode:
        flash("Update route does not match the experiment modality.", "error")
        if actual_mode == "hpc":
            return redirect(url_for("clientsr.client_details_hpc", uid=uid))
        if actual_mode == "forum":
            return redirect(url_for("clientsr.client_details_forum", uid=uid))
        return redirect(url_for("clientsr.client_details", uid=uid))

    def _float(name, default):
        return float(request.form.get(name, default))

    def _int(name, default):
        return int(request.form.get(name, default))

    client.days = _int("days", client.days)
    client.percentage_new_agents_iteration = _float(
        "percentage_new_agents_iteration", client.percentage_new_agents_iteration
    )
    client.percentage_removed_agents_iteration = _float(
        "percentage_removed_agents_iteration",
        client.percentage_removed_agents_iteration,
    )
    client.max_length_thread_reading = _int(
        "max_length_thread_reading", client.max_length_thread_reading
    )
    client.reading_from_follower_ratio = _float(
        "reading_from_follower_ratio", client.reading_from_follower_ratio
    )
    client.probability_of_daily_follow = _float(
        "probability_of_daily_follow", client.probability_of_daily_follow
    )
    client.attention_window = _int("attention_window", client.attention_window)
    client.visibility_rounds = _int("visibility_rounds", client.visibility_rounds)

    client.post = _float("post", client.post)
    client.image = _float("image", client.image)
    client.news = _float("news", client.news)
    client.comment = _float("comment", client.comment)
    client.read = _float("read", client.read)
    client.share = _float("share", client.share)
    client.search = _float("search", client.search)
    client.vote = _float("vote", client.vote)

    memory_enabled = request.form.get("memory_enabled") in {"on", "true", "1", "yes"}
    memory_semantic_enabled = request.form.get("memory_semantic_enabled") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_pair_limit = _int("memory_pair_limit", 5)
    memory_prompt_max_chars = _int("memory_prompt_max_chars", 1600)
    memory_social_decay_lambda = _float("memory_social_decay_lambda", 0.05)
    memory_social_corruption_rate = _float("memory_social_corruption_rate", 0.02)
    memory_social_resummarize_every_events = _int(
        "memory_social_resummarize_every_events", 4
    )
    memory_thread_decay_lambda = _float("memory_thread_decay_lambda", 0.03)
    memory_thread_corruption_rate = _float("memory_thread_corruption_rate", 0.01)
    memory_thread_resummarize_every_events = _int(
        "memory_thread_resummarize_every_events", 4
    )
    memory_evidence_tail_max = _int("memory_evidence_tail_max", 8)
    memory_digest_update_cadence_rounds = _int("memory_digest_update_cadence_rounds", 3)
    memory_digest_events_limit = _int("memory_digest_events_limit", 80)
    memory_cold_start_window = _int("memory_cold_start_window", 5)
    memory_search_k = _int("memory_search_k", 8)
    memory_search_max_chars = _int("memory_search_max_chars", 900)
    memory_search_time_window_rounds = _int("memory_search_time_window_rounds", 40)
    memory_tier_a_max_chars = _int("memory_tier_a_max_chars", 350)
    memory_tier_b_max_chars = _int("memory_tier_b_max_chars", 900)
    memory_tier_c_max_chars = _int("memory_tier_c_max_chars", 900)
    memory_total_max_chars = _int("memory_total_max_chars", 2200)
    memory_tier_c_uncertainty_threshold = _float(
        "memory_tier_c_uncertainty_threshold", 0.45
    )
    memory_reflection_cadence_rounds = _int("memory_reflection_cadence_rounds", 3)
    memory_reflection_min_events = _int("memory_reflection_min_events", 12)
    memory_reflection_trigger_importance_sum = _float(
        "memory_reflection_trigger_importance_sum", 3.5
    )
    memory_reflection_max_items_per_run = _int(
        "memory_reflection_max_items_per_run", 60
    )
    memory_embedding_model = str(
        request.form.get("memory_embedding_model", "snowflake-arctic-embed:110m")
    ).strip()
    memory_embedding_async = request.form.get("memory_embedding_async") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_importance_mode = str(
        request.form.get("memory_importance_mode", "heuristic_then_batch_llm")
    ).strip()

    enable_archetypes = request.form.get("enable_archetypes") == "on"
    agent_downcast = request.form.get("agent_downcast") == "on"
    archetype_validator = _float("archetype_validator", 52) / 100.0
    archetype_broadcaster = _float("archetype_broadcaster", 20) / 100.0
    archetype_explorer = _float("archetype_explorer", 28) / 100.0
    trans_val_val = _float("trans_val_val", 85.3) / 100.0
    trans_val_broad = _float("trans_val_broad", 8.1) / 100.0
    trans_val_expl = _float("trans_val_expl", 6.6) / 100.0
    trans_broad_val = _float("trans_broad_val", 19.5) / 100.0
    trans_broad_broad = _float("trans_broad_broad", 72.9) / 100.0
    trans_broad_expl = _float("trans_broad_expl", 7.5) / 100.0
    trans_expl_val = _float("trans_expl_val", 36.4) / 100.0
    trans_expl_broad = _float("trans_expl_broad", 14.6) / 100.0
    trans_expl_expl = _float("trans_expl_expl", 49.0) / 100.0

    db.session.commit()

    topics = Exp_Topic.query.filter_by(exp_id=exp.idexp).all()
    topics_ids = [t.topic_id for t in topics]
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topics_by_name = {str(t.name): t for t in topics_objs}
    topics_by_id = {str(t.id): t for t in topics_objs}
    topic_percentages = {}
    for topic_obj in topics_objs:
        key = f"topic_interest_{topic_obj.id}"
        try:
            raw = request.form.get(key)
            if raw is None:
                raw = request.form.get(f"topic_interest_{topic_obj.name}")
            topic_percentages[topic_obj.name] = float(raw if raw is not None else "100")
        except (ValueError, TypeError):
            topic_percentages[topic_obj.name] = 100.0

    from y_web.src.system.path_utils import get_writable_path

    base_dir = get_writable_path()
    exp_folder = _get_experiment_folder_name(exp)
    population = Population.query.filter_by(id=client.population_id).first()
    if not population:
        flash("Population not found.", "warning")
        return redirect(request.referrer)

    config_path = (
        f"{base_dir}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}"
        f"client_{client.name}-{population.name}.json"
    )

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
        config.setdefault("simulation", {})
        config.setdefault("agents", {})
        config.setdefault("posts", {})
        config.setdefault("topics", [])
        config["simulation"]["num_days"] = client.days
        config["simulation"][
            "percentage_new_agents_iteration"
        ] = client.percentage_new_agents_iteration
        config["simulation"][
            "percentage_removed_agents_iteration"
        ] = client.percentage_removed_agents_iteration
        config["simulation"]["visibility_rounds"] = client.visibility_rounds
        config["agents"]["max_length_thread_reading"] = client.max_length_thread_reading
        config["agents"][
            "reading_from_follower_ratio"
        ] = client.reading_from_follower_ratio
        config["agents"][
            "probability_of_daily_follow"
        ] = client.probability_of_daily_follow
        config["agents"]["attention_window"] = client.attention_window
        actions = config["simulation"].setdefault("actions_likelihood", {})
        actions.update(
            {
                "post": client.post,
                "image": client.image,
                "news": client.news,
                "comment": client.comment,
                "read": client.read,
                "share": client.share,
                "search": client.search,
                "vote": client.vote,
            }
        )
        config["agents"].update(
            {
                "memory_enabled": bool(memory_enabled),
                "memory_pair_limit": memory_pair_limit,
                "memory_prompt_max_chars": memory_prompt_max_chars,
                "memory_social_decay_lambda": memory_social_decay_lambda,
                "memory_social_corruption_rate": memory_social_corruption_rate,
                "memory_social_resummarize_every_events": memory_social_resummarize_every_events,
                "memory_thread_decay_lambda": memory_thread_decay_lambda,
                "memory_thread_corruption_rate": memory_thread_corruption_rate,
                "memory_thread_resummarize_every_events": memory_thread_resummarize_every_events,
                "memory_evidence_tail_max": memory_evidence_tail_max,
                "memory_digest_update_cadence_rounds": memory_digest_update_cadence_rounds,
                "memory_digest_events_limit": memory_digest_events_limit,
                "memory_cold_start_window": memory_cold_start_window,
                "memory_semantic_enabled": bool(memory_semantic_enabled),
                "memory_search_k": memory_search_k,
                "memory_search_max_chars": memory_search_max_chars,
                "memory_search_time_window_rounds": memory_search_time_window_rounds,
                "memory_tier_a_max_chars": memory_tier_a_max_chars,
                "memory_tier_b_max_chars": memory_tier_b_max_chars,
                "memory_tier_c_max_chars": memory_tier_c_max_chars,
                "memory_total_max_chars": memory_total_max_chars,
                "memory_tier_c_uncertainty_threshold": memory_tier_c_uncertainty_threshold,
                "memory_reflection_cadence_rounds": memory_reflection_cadence_rounds,
                "memory_reflection_min_events": memory_reflection_min_events,
                "memory_reflection_trigger_importance_sum": memory_reflection_trigger_importance_sum,
                "memory_reflection_max_items_per_run": memory_reflection_max_items_per_run,
                "memory_embedding_model": memory_embedding_model,
                "memory_embedding_async": bool(memory_embedding_async),
                "memory_importance_mode": memory_importance_mode,
            }
        )
        config["simulation"]["agent_archetypes"] = {
            "enabled": enable_archetypes,
            "agent_downcast": agent_downcast,
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
        config["topic_interest_weights"] = topic_percentages or config.get(
            "topic_interest_weights", {}
        )
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
    else:
        flash("Configuration file not found.", "warning")

    flash("Client simulation parameters updated.", "success")
    return redirect(request.referrer)


def _update_recsys_internal(uid, expected_mode):
    """Update recsys using the modality-specific route."""
    check_privileges(current_user.username)

    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("experiments.settings"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

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
        return redirect(url_for("experiments.settings"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

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
        return redirect(url_for("experiments.settings"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

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


@clientsr.route("/admin/update_standard_client_settings/<int:uid>", methods=["POST"])
@login_required
def update_standard_client_settings(uid):
    return _update_client_simulation_internal(uid, "standard")


@clientsr.route("/admin/update_forum_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_forum_client_llm(uid):
    """Update LLM for a forum client."""
    return _update_client_llm_internal(uid, "forum")


@clientsr.route("/admin/update_forum_client_settings/<int:uid>", methods=["POST"])
@login_required
def update_forum_client_settings(uid):
    return _update_client_simulation_internal(uid, "forum")


@clientsr.route("/admin/update_hpc_client_settings/<int:uid>", methods=["POST"])
@login_required
def update_hpc_client_settings(uid):
    return _update_client_simulation_internal(uid, "hpc")


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
        return redirect(url_for("experiments.settings"))

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found.", "error")
        return redirect(url_for("experiments.settings"))

    if getattr(exp, "simulator_type", "Standard") == "HPC":
        return update_hpc_client_llm(uid)
    if exp.platform_type == "forum":
        return update_forum_client_llm(uid)
    return update_standard_client_llm(uid)
