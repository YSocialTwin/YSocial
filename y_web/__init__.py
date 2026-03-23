"""
YSocial Web Application Initialization.

This module initializes the Flask application and configures database connections
for the YSocial platform. It supports both SQLite and PostgreSQL databases and
manages application lifecycle including subprocess cleanup on shutdown.

Key components:
- Flask app factory pattern (create_app)
- Database initialization and schema management via y_web.db_init
- Flask-Login user session management
- Blueprint registration for all routes
- Subprocess management for simulation clients
"""

import atexit
import json
import os
import sys

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def cleanup_db_jupyter_with_new_app():
    """
    Create a fresh app instance to get a valid app context, then run DB cleanup.
    Call this from the main runner's shutdown handler or as final step in atexit.
    """
    print("Cleaning up db...")

    # Stop the log sync scheduler
    try:
        from y_web.src.hpc.log_sync_scheduler import stop_log_sync_scheduler

        stop_log_sync_scheduler()
        print("Log sync scheduler stopped")
    except Exception as e:
        print(f"Failed to stop log sync scheduler: {e}")

    # Log service stop event
    try:
        from y_web.src.telemetry import Telemetry

        telemetry = Telemetry()
        telemetry.log_event({"action": "stop"})
    except Exception as e:
        print(f"Failed to log stop event: {e}")

    try:
        # Try to use existing app context first
        from flask import current_app

        try:
            # Check if we're already in an app context
            _ = current_app.name
            app_context_exists = True
            print("Using existing app context for cleanup")
        except RuntimeError:
            # No app context exists
            app_context_exists = False
            print("No existing app context, creating new app for cleanup")

        if app_context_exists:
            # Use existing context
            from y_web import db
            from y_web.src.simulation.process_registry import stop_all_exps
            from y_web.src.system.jupyter_utils import stop_all_jupyter_instances

            stop_all_jupyter_instances()
            stop_all_exps()

            # Ensure changes are committed
            db.session.commit()
            db.session.close()
            print(
                "Database session committed and closed successfully (existing context)"
            )
        else:
            # Create a fresh app instance (use same DB_TYPE env var)
            from y_web import create_app

            # close both
            for dbms in ["sqlite", "postgresql"]:
                try:
                    app = create_app(dbms)
                    with app.app_context():
                        from y_web import db
                        from y_web.src.simulation.process_registry import stop_all_exps
                        from y_web.src.system.jupyter_utils import (
                            stop_all_jupyter_instances,
                        )

                        stop_all_jupyter_instances()
                        stop_all_exps()
                        # For PostgreSQL, ensure changes are committed by explicitly closing the session
                        db.session.commit()
                        db.session.close()
                        print(
                            "Database session committed and closed successfully (new context)"
                        )
                except Exception:  # as e1:
                    # print(f"Error during DB cleanup with {dbms} app:", e1)
                    pass

    except Exception as e:
        print("Error during DB cleanup with fresh app:", e)
        import traceback

        traceback.print_exc()


# Only register atexit handler for the main application process, not subprocesses
# Client subprocesses set Y_CLIENT_SUBPROCESS=1 to indicate they should not run cleanup
if os.environ.get("Y_CLIENT_SUBPROCESS") != "1":
    atexit.register(cleanup_db_jupyter_with_new_app)


def create_app(db_type="sqlite", desktop_mode=False):
    """
    Create and configure the Flask application (factory pattern).

    Initializes the application with database connections, authentication,
    and all route blueprints. Supports both SQLite and PostgreSQL backends.

    Args:
        db_type: Database type to use, either "sqlite" or "postgresql"
        desktop_mode: Whether the app is running in desktop mode with PyWebview

    Returns:
        Configured Flask application instance

    Raises:
        ValueError: If unsupported db_type is provided
    """
    app = Flask(__name__, static_url_path="/static")

    app.config["SECRET_KEY"] = "4323432nldsf"
    app.config["DESKTOP_MODE"] = desktop_mode

    # ------------------------------------------------------------------ #
    # Database engine configuration                                        #
    # ------------------------------------------------------------------ #
    from y_web.db_init import create_postgresql_db, create_sqlite_db

    if db_type == "sqlite":
        create_sqlite_db(app)
    elif db_type == "postgresql":
        create_postgresql_db(app)
    else:
        raise ValueError("Unsupported db_type, use 'sqlite' or 'postgresql'")

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Disable static file caching for development mode to ensure JS/CSS updates are loaded
    # This ensures loading indicators and other static assets work in development mode
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    # Enable template auto-reload in development mode
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    db.init_app(app)
    login_manager.init_app(app)

    app.config["SESSION_COOKIE_NAME"] = "YSocial_session"

    from y_web.src.agents.platform import ensure_population_username_type_column

    from y_web.src.models import Admin_users, User_mgmt

    with app.app_context():
        ensure_population_username_type_column()

    @login_manager.user_loader
    def load_user(user_id):
        """
        Load user by ID for Flask-Login session management.

        Supports both Admin_users (for admin/researcher) and User_mgmt (for regular users).
        Admin users are identified by 'admin_' prefix in the user_id.

        Args:
            user_id: User ID string to load (format: 'admin_<id>' for admins, '<id>' for regular users)

        Returns:
            Admin_users or User_mgmt object if found, None otherwise
        """
        user_id_str = user_id
        if user_id_str.startswith("admin_"):
            # Admin or researcher user
            admin_id = user_id_str.replace("admin_", "")
            return Admin_users.query.get(admin_id)
        else:
            # Regular experiment participant
            return User_mgmt.query.get(user_id)

    # Setup experiment context handler
    from y_web.src.experiment.context import (
        get_current_experiment_id,
        initialize_active_experiment_databases,
        setup_experiment_context,
        teardown_experiment_context,
    )

    @app.before_request
    def before_request_handler():
        """Setup experiment context and desktop mode for each request."""
        setup_experiment_context()

        # If in desktop mode, ensure webview window is accessible
        if app.config.get("DESKTOP_MODE"):
            try:
                from y_web.pyinstaller_utils.y_social_desktop import get_desktop_window

                window = get_desktop_window()
                if window:
                    app.config["WEBVIEW_WINDOW"] = window
            except ImportError:
                pass  # Desktop module not available

    @app.teardown_request
    def teardown_request_handler(exception=None):
        """Clean up database session and restore experiment context after each request."""
        # Explicitly remove the database session to ensure proper cleanup
        # This prevents session leaks and connection hangs, especially with SQLite
        db.session.remove()
        teardown_experiment_context(exception)

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
                exp = Exps.query.filter_by(idexp=int(exp_id)).first()

            if exp is None:
                active_exps = Exps.query.filter(Exps.status != 0).all()
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
                exp_user = User_mgmt.query.filter_by(
                    username=getattr(current_user, "username", None)
                ).first()
                if exp_user is not None:
                    feed_user_id = int(exp_user.id)

            if feed_user_id is None:
                return dict(feed_home_url=f"/{exp.idexp}/feed/all/feed/rf/1")
            return dict(feed_home_url=f"/{exp.idexp}/feed/{feed_user_id}/feed/rf/1")
        except Exception:
            return dict(feed_home_url="/feed")

    @app.context_processor
    def inject_experiment_memory_enabled():
        """Inject whether the active Standard/Forum experiment has memory enabled."""
        from y_web.src.models import Exps
        from y_web.src.experiment.helpers import get_experiment_uid_from_db_name
        from y_web.src.system.path_utils import get_writable_path

        try:
            exp_id = get_current_experiment_id()
            if exp_id is None:
                return dict(experiment_memory_enabled=False)

            exp = Exps.query.filter_by(idexp=int(exp_id)).first()
            if not exp or getattr(exp, "platform_type", "") not in {
                "forum",
                "microblogging",
            }:
                return dict(experiment_memory_enabled=False)

            uid = get_experiment_uid_from_db_name(
                str(getattr(exp, "db_name", "") or "")
            )
            if not uid:
                return dict(experiment_memory_enabled=False)

            config_path = os.path.join(
                get_writable_path(),
                "y_web",
                "experiments",
                str(uid),
                "config_server.json",
            )
            if not os.path.exists(config_path):
                return dict(experiment_memory_enabled=False)

            with open(config_path, "r", encoding="utf-8") as handle:
                config = json.load(handle) or {}
            memory_cfg = config.get("memory")
            enabled = (
                bool(memory_cfg.get("enabled"))
                if isinstance(memory_cfg, dict)
                else False
            )
            if enabled:
                return dict(experiment_memory_enabled=True)

            # Also handle flat format written by client config routes: {"memory_enabled": true, ...}
            if bool(config.get("memory_enabled", False)):
                return dict(experiment_memory_enabled=True)

            platform_type = getattr(exp, "platform_type", "")
            if platform_type in {"microblogging", "forum"}:
                exp_dir = os.path.dirname(config_path)
                for entry in os.listdir(exp_dir):
                    if not entry.startswith("client_") or not entry.endswith(".json"):
                        continue
                    client_path = os.path.join(exp_dir, entry)
                    try:
                        with open(client_path, "r", encoding="utf-8") as client_handle:
                            client_config = json.load(client_handle) or {}
                        # Microblogging client configs nest under "agents"
                        agents_cfg = client_config.get("agents")
                        if isinstance(agents_cfg, dict) and bool(
                            agents_cfg.get("memory_enabled")
                        ):
                            return dict(experiment_memory_enabled=True)
                        # Forum client configs use a flat "memory_enabled" key
                        if bool(client_config.get("memory_enabled", False)):
                            return dict(experiment_memory_enabled=True)
                    except Exception:
                        continue
            return dict(experiment_memory_enabled=False)
        except Exception:
            return dict(experiment_memory_enabled=False)

    @app.context_processor
    def inject_active_experiments():
        """Inject active experiments into all admin templates."""
        from flask_login import current_user

        from y_web.src.models import Admin_users, Exps
        from y_web.src.experiment.access import get_visible_experiment_query

        try:
            if not current_user.is_authenticated:
                return dict(active_experiments=[])
            admin_user = Admin_users.query.filter_by(
                username=current_user.username
            ).first()
            if not admin_user:
                return dict(active_experiments=[])
            if admin_user.role in ("admin", "researcher"):
                active_exps = (
                    get_visible_experiment_query(admin_user).filter_by(status=1).all()
                )
            else:
                active_exps = Exps.query.filter_by(status=1).all()
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
                admin_user = Admin_users.query.filter_by(
                    username=current_user.username
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
                admin_user = Admin_users.query.filter_by(
                    username=current_user.username
                ).first()
                if admin_user and admin_user.role == "admin":
                    # Get release info
                    release_info = ReleaseInfo.query.first()
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
                admin_user = Admin_users.query.filter_by(
                    username=current_user.username
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

    from y_web.routes import register_blueprints

    register_blueprints(app)

    # Add context processor to detect PyInstaller mode
    @app.context_processor
    def inject_pyinstaller_mode():
        """Inject PyInstaller mode detection into all templates."""
        import sys

        return dict(is_pyinstaller=getattr(sys, "frozen", False))

    # ------------------------------------------------------------------ #
    # Database migrations + startup checks                                 #
    # ------------------------------------------------------------------ #
    from y_web.db_init.migrations import run_migrations

    run_migrations(app, db_type, db)

    # Log service start event
    try:
        from y_web.src.telemetry import Telemetry

        telemetry = Telemetry()
        telemetry.log_event({"action": "start"})
    except Exception as e:
        print(f"Failed to log start event: {e}")

    # Start the log sync scheduler for automatic periodic log reading
    try:
        from y_web.src.hpc.log_sync_scheduler import init_log_sync_scheduler

        init_log_sync_scheduler(app)
        print("✓ Log sync scheduler started")
    except Exception as e:
        print(f"Failed to start log sync scheduler: {e}")

    # Start the experiment schedule monitor for automatic group advancement
    try:
        from y_web.src.experiment.schedule_monitor import (
            init_experiment_schedule_monitor,
        )

        init_experiment_schedule_monitor(app)
        print("✓ Experiment schedule monitor started")
    except Exception as e:
        print(f"Failed to start experiment schedule monitor: {e}")

    return app
