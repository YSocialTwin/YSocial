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


def user_can_manage_experiment(admin_user, experiment):
    """Check if user can stop/delete an experiment."""
    from y_web.src.experiment.access import user_can_manage_experiment as target

    return target(admin_user, experiment)


def user_can_view_experiment(admin_user, experiment):
    """Check if admin/researcher can view an experiment."""
    from y_web.src.experiment.access import user_can_view_experiment as target

    return target(admin_user, experiment)


__all__ = [
    "build_client_creation_context",
    "check_privileges",
    "current_admin_user_or_none",
    "experiment_configuration_update_required",
    "experiment_uses_llm_agents",
    "get_database_type",
    "get_experiment_folder",
    "get_experiment_folder_name",
    "load_ui_settings",
    "user_can_manage_experiment",
    "user_can_view_experiment",
]
