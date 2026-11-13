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


def logged_user():
    from y_web.routes.social.helpers import _forum_logged_user as target

    return target()


def profile_pic_of(user):
    from y_web.routes.social.helpers import _forum_profile_pic as target

    return target(user)


def current_profile_pic(exp_id, forum_user=None):
    from y_web.routes.social.helpers import _forum_current_profile_pic as target

    return target(exp_id, forum_user)


def feed_memory_enabled(exp_id):
    from y_web.routes.social.helpers import _forum_memory_enabled as target

    return target(exp_id)


def resolve_back_url(exp_id):
    from y_web.routes.social.helpers import _forum_resolve_back_url as target

    return target(exp_id)


def get_discussions(posts, username, page, exp_id, exp_user_id=None):
    """Handle get discussions operation."""
    from y_web.routes.social.helpers import _get_discussions as target

    return target(posts, username, page, exp_id, exp_user_id)


def build_thread_tree(root_id, post_to_data, parent_lookup):
    """Build a thread tree without depending on row ordering."""
    from y_web.routes.social.helpers import build_thread_tree as target

    return target(root_id, post_to_data, parent_lookup)


def maybe_update_fb_interests(exp_id, exp_user, post_id, interaction_type):
    """If the user is using FilterBubble mode, update their topic interests."""
    from y_web.routes.interactions.common import _maybe_update_fb_interests as target

    return target(exp_id, exp_user, post_id, interaction_type)


def augment_text(text, exp_id):
    """Augment post text by adding HTML links to @mentions and #hashtags."""
    from y_web.src.data_access import augment_text as target

    return target(text, exp_id)


def get_elicited_emotions(post_id):
    """Get emotions elicited by a post."""
    from y_web.src.data_access import get_elicited_emotions as target

    return target(post_id)


def get_topics(post_id, user_id):
    """Get topics associated with a post and user sentiment."""
    from y_web.src.data_access import get_topics as target

    return target(post_id, user_id)


def get_trending_hashtags(limit=10, window=120):
    """Get the trending hashtags."""
    from y_web.src.data_access import get_trending_hashtags as target

    return target(limit, window)


def hidden_author_ids_for_viewer(exp_id, viewer_user_id):
    """Ask any installed frontend plugin (e.g. reactive_agents' Phase 6"""
    from y_web.src.data_access.posts import _hidden_author_ids_for_viewer as target

    return target(exp_id, viewer_user_id)


def hidden_post_ids_in_thread(post_records, hidden_author_ids):
    """Given *post_records* -- an iterable of ``(post_id, author_id,"""
    from y_web.src.data_access.posts import _hidden_post_ids_in_thread as target

    return target(post_records, hidden_author_ids)


def origin_community(source_id) -> str:
    """Slug of the community a cross-posted thread was copied from ('' when unknown): resolved like the community of a"""
    from y_web.src.data_access.posts import _origin_community as target

    return target(source_id)


def get_db_bind_key_for_exp(exp_id):
    """Get the database bind key for a specific experiment."""
    from y_web.src.experiment.context import get_db_bind_key_for_exp as target

    return target(exp_id)


def register_experiment_database(app, exp_id, db_name):
    """Register an experiment database in the app's SQLALCHEMY_BINDS."""
    from y_web.src.experiment.context import register_experiment_database as target

    return target(app, exp_id, db_name)


__all__ = [
    "augment_text",
    "build_thread_tree",
    "content_recsys_info",
    "current_profile_pic",
    "ensure_experiment_user",
    "experiment_memory_enabled",
    "feed_memory_enabled",
    "get_avatars_dir",
    "get_db_bind_key_for_exp",
    "get_discussions",
    "get_elicited_emotions",
    "get_experiment_engine_uri",
    "get_safe_profile_pic",
    "get_suggested_users",
    "get_topics",
    "get_trending_hashtags",
    "get_unanswered_mentions",
    "hidden_author_ids_for_viewer",
    "hidden_post_ids_in_thread",
    "is_admin",
    "logged_user",
    "maybe_update_fb_interests",
    "open_experiment_session",
    "origin_community",
    "profile_pic_of",
    "register_experiment_database",
    "resolve_back_url",
]
