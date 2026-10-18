"""Template context processors and Jinja filters of the YWeb application.

Moved out of ``y_web/__init__.py`` (behaviour unchanged): every function keeps its name, so tests and tools can
still find them in ``app.template_context_processors``.
"""

from flask import Flask
from sqlalchemy import select

from y_web import db


def register_template_context(app: Flask) -> None:
    """Register the context processors and the ``user_image_id`` filter on ``app``."""
    # imported here, as in the factory, so that a patched ``get_current_experiment_id`` is the one used
    from y_web.src.experiment.context import get_current_experiment_id

    @app.context_processor
    def inject_exp_id():
        """Inject exp_id into all templates."""
        return dict(exp_id=get_current_experiment_id())

    @app.context_processor
    def inject_feed_home_url():
        """Inject the canonical home URL for the active experiment feed."""
        from flask_login import current_user

        from y_web.src.models import Exps, User_mgmt

        try:
            if not current_user.is_authenticated:
                return dict(feed_home_url="/")

            exp = None
            exp_id = get_current_experiment_id()
            if exp_id is not None:
                exp = db.session.scalars(
                    select(Exps).filter_by(idexp=int(exp_id))
                ).first()

            if exp is None:
                active_exps = db.session.scalars(
                    select(Exps).filter(Exps.status != 0)
                ).all()
                if not active_exps:
                    return dict(feed_home_url="/")
                if len(active_exps) > 1:
                    return dict(feed_home_url="/admin/join_simulation")
                exp = active_exps[0]

            if exp.platform_type == "forum":
                return dict(
                    feed_home_url=f"/{exp.idexp}/rfeed/all/feed/rf/1?feed_type=new"
                )

            feed_user_id = None
            user_id_str = str(current_user.get_id() or "")
            if user_id_str.isdigit():
                feed_user_id = int(user_id_str)
            else:
                exp_user = db.session.scalars(
                    select(User_mgmt).filter_by(
                        username=getattr(current_user, "username", None)
                    )
                ).first()
                if exp_user is not None:
                    feed_user_id = int(exp_user.id)

            if feed_user_id is None:
                return dict(feed_home_url=f"/{exp.idexp}/feed/all/feed/rf/1")
            return dict(feed_home_url=f"/{exp.idexp}/feed/{feed_user_id}/feed/rf/1")
        except Exception:
            return dict(feed_home_url="/feed")

    @app.context_processor
    def inject_memory_plugin_installed():
        """Memory settings are shown only while the Agent Memory plugin is installed."""
        from y_web.src.system.memory_plugin import agent_memory_plugin_installed

        return dict(memory_plugin_installed=agent_memory_plugin_installed())

    @app.context_processor
    def inject_experiment_memory_enabled():
        """Inject whether the active experiment has memory-enabled chat."""
        from y_web.routes.social.helpers import _experiment_memory_enabled

        try:
            exp_id = get_current_experiment_id()
            if exp_id is None:
                return dict(experiment_memory_enabled=False)

            return dict(
                experiment_memory_enabled=bool(_experiment_memory_enabled(exp_id))
            )
        except Exception:
            return dict(experiment_memory_enabled=False)

    @app.context_processor
    def inject_active_experiments():
        """Inject active experiments into all admin templates."""
        from flask_login import current_user

        from y_web.src.experiment.access import get_visible_experiment_query
        from y_web.src.models import Admin_users, Exps

        try:
            if not current_user.is_authenticated:
                return dict(active_experiments=[])
            admin_user = db.session.scalars(
                select(Admin_users).filter_by(username=current_user.username)
            ).first()
            if not admin_user or admin_user.role == "teacher":  # a teacher sees none
                return dict(active_experiments=[])
            if admin_user.role in ("admin", "researcher"):
                active_exps = (
                    get_visible_experiment_query(admin_user).filter_by(status=1).all()
                )
            else:
                active_exps = db.session.scalars(select(Exps).filter_by(status=1)).all()
            return dict(active_experiments=active_exps)
        except Exception:
            return dict(active_experiments=[])

    @app.context_processor
    def inject_user_info():
        """Inject current user role information into templates."""
        from flask_login import current_user

        from y_web.src.models import Admin_users

        if current_user.is_authenticated:
            try:
                admin_user = db.session.scalars(
                    select(Admin_users).filter_by(username=current_user.username)
                ).first()
                if admin_user:
                    return dict(
                        current_user_role=admin_user.role, current_user_id=admin_user.id
                    )
            except Exception:
                pass
        return dict(current_user_role=None, current_user_id=None)

    @app.context_processor
    def inject_release_info():
        """Inject release update information for admin users."""
        from flask_login import current_user

        from y_web.src.models import Admin_users, ReleaseInfo

        if current_user.is_authenticated:
            try:
                admin_user = db.session.scalars(
                    select(Admin_users).filter_by(username=current_user.username)
                ).first()
                if admin_user and admin_user.role == "admin":
                    # Get release info
                    release_info = db.session.scalars(select(ReleaseInfo)).first()
                    if release_info and release_info.latest_version_tag:
                        return dict(
                            new_release_available=True, release_info=release_info
                        )
            except Exception:
                pass
        return dict(new_release_available=False, release_info=None)

    @app.context_processor
    def inject_blog_post_info():
        """Inject latest blog post information for admin users."""
        from flask_login import current_user

        from y_web.src.models import Admin_users, BlogPost

        if current_user.is_authenticated:
            try:
                admin_user = db.session.scalars(
                    select(Admin_users).filter_by(username=current_user.username)
                ).first()
                if admin_user and admin_user.role == "admin":
                    # Get unread blog posts
                    latest_post = (
                        BlogPost.query.filter(BlogPost.is_read == False)
                        .order_by(BlogPost.id.desc())
                        .first()
                    )
                    if latest_post:
                        return dict(new_blog_post_available=True, blog_post=latest_post)
            except Exception as e:
                print(f"Error injecting blog post info: {e}")
        return dict(new_blog_post_available=False, blog_post=None)

    # Add custom Jinja filter for user ID to image mapping
    # This supports both int IDs (Standard experiments) and UUID IDs (HPC experiments)
    from y_web.src.system.display_names import display_name

    app.add_template_filter(display_name, "display_name")

    @app.template_filter("user_image_id")
    def user_image_id_filter(user_id):
        """
        Convert user ID to a consistent image ID for profile pictures.

        For integer IDs (Standard experiments): returns the ID as string
        For UUID strings (HPC experiments): returns a hash-based consistent numeric ID as string

        Args:
            user_id: User ID (int or UUID string)

        Returns:
            String numeric ID for image filename (1-1000 range for UUIDs)
        """
        if user_id is None:
            return "1"  # Default fallback

        # Try to use as integer (Standard experiments)
        try:
            return str(int(user_id))
        except (ValueError, TypeError):
            # UUID string (HPC experiments) - create consistent hash
            import hashlib

            # Use MD5 hash for consistent mapping
            hash_value = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16)
            # Map to range 1-1000 for available profile images
            return str((hash_value % 1000) + 1)

    # Detect PyInstaller mode
    @app.context_processor
    def inject_pyinstaller_mode():
        """Inject PyInstaller mode detection into all templates."""
        import sys

        return dict(is_pyinstaller=getattr(sys, "frozen", False))
