"""What the pages a platform shows to its participants take from the core: the experiment database, the participant, mentions, suggestions and avatars.

The functions look the core up when called, so what the core (or a test) replaces is what a platform gets.
"""

from __future__ import annotations


def content_recsys_info(recsys_type, ui=None):
    """``{"name", "label", "description"}`` of a user's content recommender system, or ``None``."""
    from y_web.routes.social.helpers import _content_recsys_info as target

    return target(recsys_type, ui)


def experiment_memory_enabled(exp_id):
    from y_web.routes.social.helpers import _experiment_memory_enabled as target

    return target(exp_id)


def get_safe_profile_pic(username, is_page=0):
    """Safely retrieve profile picture URL for a user or page."""
    from y_web.routes.social.helpers import get_safe_profile_pic as target

    return target(username, is_page)


def is_admin(username):
    """Check if a user has admin role."""
    from y_web.routes.social.helpers import is_admin as target

    return target(username)


def get_unanswered_mentions(username, exp_id=None):
    """Get unanswered @-mention notifications for a user."""
    from y_web.src.data_access import get_unanswered_mentions as target

    return target(username, exp_id)


def ensure_experiment_user(experiment: "Exps", *, account_id=None, **kwargs):
    """Ensure a participant row exists in the experiment database."""
    from y_web.src.experiment.helpers import ensure_experiment_user as target

    return target(experiment, account_id=account_id, **kwargs)


def get_experiment_engine_uri(experiment: "Exps") -> "Optional[str]":
    """Public wrapper returning the database URI for an experiment."""
    from y_web.src.experiment.helpers import get_experiment_engine_uri as target

    return target(experiment)


def open_experiment_session(experiment: "Exps"):
    """Open an isolated SQLAlchemy session bound to the experiment database."""
    from y_web.src.experiment.helpers import open_experiment_session as target

    return target(experiment)


def get_suggested_users(username, pages=False):
    """Get follow recommendations for a user."""
    from y_web.src.recsys.follow_recsys import get_suggested_users as target

    return target(username, pages)


def get_avatars_dir() -> str:
    """Bundled folder when populated, otherwise the downloaded one."""
    from y_web.src.system.avatars_store import get_avatars_dir as target

    return target()


__all__ = [
    "content_recsys_info",
    "ensure_experiment_user",
    "experiment_memory_enabled",
    "get_avatars_dir",
    "get_experiment_engine_uri",
    "get_safe_profile_pic",
    "get_suggested_users",
    "get_unanswered_mentions",
    "is_admin",
    "open_experiment_session",
]
