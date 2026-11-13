"""What a platform's views share with the rest of the web application: who may do what, and the page settings.

The functions look the core up when called, so what the core (or a test) replaces is what a platform gets.
"""

from __future__ import annotations


def build_client_creation_context(idexp, recsys_mode):
    """Build the shared context used by client creation pages."""
    from y_web.routes.admin.sub.clients._crud import (
        _build_client_creation_context as target,
    )

    return target(idexp, recsys_mode)


def check_privileges(username):
    """Verify if a user has admin or researcher privileges."""
    from y_web.src.system.miscellanea import check_privileges as target

    return target(username)


def redirect_to_clients_page(experiment, current_endpoint):
    """Redirect to the creation page of the experiment when ``current_endpoint`` is not it; ``None`` when it is."""
    from y_web.routes.admin.sub.clients._crud import _redirect_to_clients_page as target

    return target(experiment, current_endpoint)


def allocate_topics_by_percentage(topics, topic_percentages):
    """Allocate topics to an agent based on specified interest percentages."""
    from y_web.routes.admin.sub.clients._helpers import (
        allocate_topics_by_percentage as target,
    )

    return target(topics, topic_percentages)


def client_config_path_for_platform(
    exp_dir: "str", exp, client_name: "str", population_name: "str"
) -> "str":
    from y_web.routes.admin.sub.clients._crud import (
        _client_config_path_for_platform as target,
    )

    return target(exp_dir, exp, client_name, population_name)


def current_admin_user_or_none():
    """Resolve current admin user or None if unavailable."""
    from y_web.routes.admin.sub.experiments._helpers import (
        _current_admin_user_or_none as target,
    )

    return target()


def experiment_configuration_update_required(experiment):
    """Return whether experiment workflows must stay locked until config is acknowledged."""
    from y_web.routes.admin.sub.experiments._helpers import (
        _experiment_configuration_update_required as target,
    )

    return target(experiment)


def experiment_uses_llm_agents(experiment):
    """Resolve whether an experiment is configured to use LLM agents."""
    from y_web.routes.admin.sub.experiments._helpers import (
        _experiment_uses_llm_agents as target,
    )

    return target(experiment)


def get_database_type():
    """Get active admin database backend type."""
    from y_web.routes.admin.sub.experiments._helpers import _get_database_type as target

    return target()


def get_experiment_folder(base_dir, experiment, db_type):
    """Resolve experiment folder path for sqlite/postgresql layouts."""
    from y_web.routes.admin.sub.experiments._helpers import (
        _get_experiment_folder as target,
    )

    return target(base_dir, experiment, db_type)


def get_experiment_folder_name(experiment):
    """Return the experiment folder name used under y_web/experiments."""
    from y_web.routes.admin.sub.clients._crud import (
        _get_experiment_folder_name as target,
    )

    return target(experiment)


def load_ui_settings(exp_id: int) -> dict:
    """Return the frontend settings dict for *exp_id*, merged with defaults."""
    from y_web.routes.social.helpers import _load_ui_settings as target

    return target(exp_id)


def load_feed_experiment_context(uid, require_manage=True):
    """Load an experiment with news-page feeds and its writable directory."""
    from y_web.routes.admin.sub.experiments._helpers import (
        _load_forum_experiment_context as target,
    )

    return target(uid, require_manage)


def read_json_if_exists(path):
    """Load a JSON file if it exists, otherwise return None."""
    from y_web.routes.admin.sub.clients._crud import _read_json_if_exists as target

    return target(path)


def get_client_population_pages(client):
    """Fetch pages associated with the client's population."""
    from y_web.routes.admin.sub.clients._crud import (
        _get_client_population_pages as target,
    )

    return target(client)


def extract_llm_names_from_population_payload(agents_payload):
    """Collect unique non-page LLM names from a population payload."""
    from y_web.routes.admin.sub.clients._crud import (
        _extract_llm_names_from_population_payload as target,
    )

    return target(agents_payload)


def build_hourly_activity_chart_series(activity):
    """Convert hourly activity (dict, CSV string or list of hours) to plotting arrays."""
    from y_web.routes.admin.sub.clients._crud import (
        _build_hourly_activity_chart_series as target,
    )

    return target(activity)


def hpc_prompts_filename(experiment) -> str:
    from y_web.routes.admin.sub.experiments._crud import _hpc_prompts_filename as target

    return target(experiment)


def redirect_to_details_page(experiment, current_endpoint, uid):
    """Redirect to the details page of the clients of this experiment when ``current_endpoint`` is not it."""
    from y_web.routes.admin.sub.clients._details import (
        _redirect_to_details_page as target,
    )

    return target(experiment, current_endpoint, uid)


def opinion_configuration_internal(idexp, expected_mode):
    """Display opinion configuration page for the expected experiment modality."""
    from y_web.routes.admin.sub.clients._opinion import (
        _opinion_configuration_internal as target,
    )

    return target(idexp, expected_mode)


def resolve_opinion_submission_context(expected_mode):
    """Validate the submission and load common opinion-distribution state."""
    from y_web.routes.admin.sub.clients._opinion import (
        _resolve_opinion_submission_context as target,
    )

    return target(expected_mode)


def apply_opinion_distributions_to_population(context):
    """Update the population payload according to the submitted distributions."""
    from y_web.routes.admin.sub.clients._opinion import (
        _apply_opinion_distributions_to_population as target,
    )

    return target(context)


def persist_non_hpc_opinion_dynamics(context):
    """Persist standard/forum opinion dynamics configuration to client config."""
    from y_web.routes.admin.sub.clients._opinion import (
        _persist_non_hpc_opinion_dynamics as target,
    )

    return target(context)


def invalidate_opinion_evolution_cache_for_experiment(exp_id):
    """Clear opinion-evolution cache and stable samples for an experiment."""
    from y_web.routes.admin.sub.clients._opinion import (
        _invalidate_opinion_evolution_cache_for_experiment as target,
    )

    return target(exp_id)


def sync_initial_standard_opinions_to_experiment_db(context):
    """Sync configured initial opinions from the population JSON into the experiment DB."""
    from y_web.routes.admin.sub.clients._opinion import (
        _sync_initial_standard_opinions_to_experiment_db as target,
    )

    return target(context)


def update_client_simulation_internal(uid, expected_mode):
    """Update visible simulation parameters and action likelihoods."""
    from y_web.routes.admin.sub.clients._recsys import (
        _update_client_simulation_internal as target,
    )

    return target(uid, expected_mode)


def update_recsys_internal(uid, expected_mode):
    """Update recsys using the modality-specific route."""
    from y_web.routes.admin.sub.clients._recsys import _update_recsys_internal as target

    return target(uid, expected_mode)


def update_client_llm_internal(uid, expected_mode):
    """Update client LLM using the modality-specific route."""
    from y_web.routes.admin.sub.clients._recsys import (
        _update_client_llm_internal as target,
    )

    return target(uid, expected_mode)


def apply_population_attributes_to_client_config(config, population_id):
    from y_web.routes.admin.sub.clients._crud import (
        _apply_population_attributes_to_client_config as target,
    )

    return target(config, population_id)


def provider_of(experiment):
    from y_web.routes.admin.sub.clients._crud import _provider_of as target

    return target(experiment)


def opinion_dynamics_enabled_for_client_creation(experiment):
    """Resolve whether opinion dynamics are active for client creation flows."""
    from y_web.routes.admin.sub.clients._crud import (
        _opinion_dynamics_enabled_for_client_creation as target,
    )

    return target(experiment)


def memory_enabled_for_client_creation(experiment):
    """Resolve whether experiment-level memory is enabled for client creation flows."""
    from y_web.routes.admin.sub.clients._crud import (
        _memory_enabled_for_client_creation as target,
    )

    return target(experiment)


def get_llm_models(llm_url=None, api_key=None, raise_on_auth_error=False):
    """Get list of models from any OpenAI-compatible LLM server."""
    from y_web.src.llm.vllm_manager import get_llm_models as target

    return target(llm_url, api_key, raise_on_auth_error)


def llm_backend_status():
    """Check LLM backend service status based on LLM_BACKEND environment variable."""
    from y_web.src.system.miscellanea import llm_backend_status as target

    return target()


def get_db_type():
    """Get the type of database being used."""
    from y_web.src.system.miscellanea import get_db_type as target

    return target()


def read_feed_health(experiment, experiment_dir):
    """Return configured and loaded forum feed counts for the experiment."""
    from y_web.routes.admin.sub.experiments._helpers import (
        _read_forum_feed_health as target,
    )

    return target(experiment, experiment_dir)


def apply_structured_features_to_agent_payload(
    agent_payload: "dict", structured: "dict"
):
    from y_web.routes.admin.sub.clients._crud import (
        _apply_structured_features_to_agent_payload as target,
    )

    return target(agent_payload, structured)


def collect_population_agent_attributes(population_id):
    """Return normalized per-agent attributes for a population, skipping broken rows."""
    from y_web.routes.admin.sub.clients._crud import (
        _collect_population_agent_attributes as target,
    )

    return target(population_id)


def user_can_manage_experiment(admin_user, experiment):
    """Check if user can stop/delete an experiment."""
    from y_web.src.experiment.access import user_can_manage_experiment as target

    return target(admin_user, experiment)


def user_can_view_experiment(admin_user, experiment):
    """Check if admin/researcher can view an experiment."""
    from y_web.src.experiment.access import user_can_view_experiment as target

    return target(admin_user, experiment)


__all__ = [
    "allocate_topics_by_percentage",
    "apply_opinion_distributions_to_population",
    "apply_population_attributes_to_client_config",
    "apply_structured_features_to_agent_payload",
    "build_client_creation_context",
    "build_hourly_activity_chart_series",
    "check_privileges",
    "client_config_path_for_platform",
    "collect_population_agent_attributes",
    "current_admin_user_or_none",
    "experiment_configuration_update_required",
    "experiment_uses_llm_agents",
    "extract_llm_names_from_population_payload",
    "get_client_population_pages",
    "get_database_type",
    "get_db_type",
    "get_experiment_folder",
    "get_experiment_folder_name",
    "get_llm_models",
    "hpc_prompts_filename",
    "invalidate_opinion_evolution_cache_for_experiment",
    "llm_backend_status",
    "load_feed_experiment_context",
    "load_ui_settings",
    "memory_enabled_for_client_creation",
    "opinion_configuration_internal",
    "opinion_dynamics_enabled_for_client_creation",
    "persist_non_hpc_opinion_dynamics",
    "provider_of",
    "read_feed_health",
    "read_json_if_exists",
    "redirect_to_clients_page",
    "redirect_to_details_page",
    "resolve_opinion_submission_context",
    "sync_initial_standard_opinions_to_experiment_db",
    "update_client_llm_internal",
    "update_client_simulation_internal",
    "update_recsys_internal",
    "user_can_manage_experiment",
    "user_can_view_experiment",
]
