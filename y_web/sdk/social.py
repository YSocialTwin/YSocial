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


def get_adhoc_agent_badge(user) -> Optional[str]:
    from y_web.routes.social.helpers import get_adhoc_agent_badge as target

    return target(user)


def get_author_type_badge(user) -> str:
    """Return a badge label identifying whether the author is an AI agent or a human."""
    from y_web.routes.social.helpers import get_author_type_badge as target

    return target(user)


def get_posts_associated_to_emotion(
    emotion_id, page, per_page=10, current_user=None, exp_id=None
):
    """Get the posts associated to the given emotion."""
    from y_web.src.data_access import get_posts_associated_to_emotion as target

    return target(emotion_id, page, per_page, current_user, exp_id)


def get_posts_associated_to_hashtags(
    hashtag_id, page, per_page=10, current_user=None, exp_id=None
):
    """Get the posts associated to the given hashtag."""
    from y_web.src.data_access import get_posts_associated_to_hashtags as target

    return target(hashtag_id, page, per_page, current_user, exp_id)


def get_posts_associated_to_interest(
    interest_id, page, per_page=10, current_user=None, exp_id=None
):
    """Get the posts associated to the given interest/topic."""
    from y_web.src.data_access import get_posts_associated_to_interest as target

    return target(interest_id, page, per_page, current_user, exp_id)


def get_report_count(post_id):
    """Return how many report records exist for a given post or comment."""
    from y_web.src.data_access import get_report_count as target

    return target(post_id)


def get_trending_emotions(limit=10, window=120):
    """Get the trending emotions."""
    from y_web.src.data_access import get_trending_emotions as target

    return target(limit, window)


def get_trending_topics(limit=10, window=120):
    """Get currently trending topics based on recent post activity."""
    from y_web.src.data_access import get_trending_topics as target

    return target(limit, window)


def get_user_friends(user_id, limit=12, page=1):
    """Get the followers and followees of the user with pagination."""
    from y_web.src.data_access import get_user_friends as target

    return target(user_id, limit, page)


def get_user_recent_posts(
    user_id, page, per_page=10, mode="rf", current_user=None, exp_id=None
):
    """Retrieve paginated posts for a specific user based on filter mode."""
    from y_web.src.data_access import get_user_recent_posts as target

    return target(user_id, page, per_page, mode, current_user, exp_id)


def experiment_db_bind(exp_id):
    """Temporarily point ``db_exp`` at the database for ``exp_id``."""
    from y_web.src.experiment.context import experiment_db_bind as target

    return target(exp_id)


def active_modules_context(exp_id: "int") -> "list[dict]":
    """Build the per-request context consumed by the frontend loader template."""
    from y_web.src.external_runtime.plugin_loader import (
        active_modules_context as target,
    )

    return target(exp_id)


def get_suggested_posts(
    uid,
    mode,
    page=1,
    per_page=10,
    follower_ratio=0.6,
    exp_engine=None,
    fb_settings=None,
):
    """Get recommended posts for a user based on specified algorithm."""
    from y_web.src.recsys import get_suggested_posts as target

    return target(uid, mode, page, per_page, follower_ratio, exp_engine, fb_settings)


def get_db_bind_key_for_exp(exp_id):
    """Get the database bind key for a specific experiment."""
    from y_web.src.experiment.context import get_db_bind_key_for_exp as target

    return target(exp_id)


def register_experiment_database(app, exp_id, db_name):
    """Register an experiment database in the app's SQLALCHEMY_BINDS."""
    from y_web.src.experiment.context import register_experiment_database as target

    return target(app, exp_id, db_name)


__all__ = [
    "active_modules_context",
    "augment_text",
    "build_thread_tree",
    "content_recsys_info",
    "current_profile_pic",
    "ensure_experiment_user",
    "experiment_db_bind",
    "experiment_memory_enabled",
    "feed_memory_enabled",
    "get_adhoc_agent_badge",
    "get_author_type_badge",
    "get_avatars_dir",
    "get_db_bind_key_for_exp",
    "get_discussions",
    "get_elicited_emotions",
    "get_experiment_engine_uri",
    "get_posts_associated_to_emotion",
    "get_posts_associated_to_hashtags",
    "get_posts_associated_to_interest",
    "get_report_count",
    "get_safe_profile_pic",
    "get_suggested_posts",
    "get_suggested_users",
    "get_topics",
    "get_trending_emotions",
    "get_trending_hashtags",
    "get_trending_topics",
    "get_unanswered_mentions",
    "get_user_friends",
    "get_user_recent_posts",
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
