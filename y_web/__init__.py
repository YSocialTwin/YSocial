"""
YSocial Web Application Initialization.

This module initializes the Flask application and configures database connections
for the YSocial platform. It supports both SQLite and PostgreSQL databases and
manages application lifecycle including subprocess cleanup on shutdown.

Key components:
- Flask app factory pattern (create_app)
- Database initialization and schema management
- Flask-Login user session management
- Blueprint registration for all routes
- Subprocess management for simulation clients
"""

import atexit
import json
import os
import shutil
import sys

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_postgresql_db(app):
    """
    Create and initialize PostgreSQL database for the application.

    Sets up PostgreSQL connection, creates databases if they don't exist,
    and loads initial schema and admin user data.

    Args:
        app: Flask application instance to configure

    Raises:
        RuntimeError: If PostgreSQL is not installed or not running
    """
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "password")
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    dbname = os.getenv("PG_DBNAME", "dashboard")
    dbname_dummy = os.getenv("PG_DBNAME_DUMMY", "dummy")

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    )

    app.config["SQLALCHEMY_BINDS"] = {
        "db_admin": app.config["SQLALCHEMY_DATABASE_URI"],
        "db_exp": f"postgresql://{user}:{password}@{host}:{port}/{dbname_dummy}",  # change if needed
    }
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

    # is postgresql installed and running?
    try:
        from sqlalchemy import create_engine

        engine = create_engine(
            app.config["SQLALCHEMY_DATABASE_URI"].replace("dashboard", "postgres")
        )
        engine.connect()
    except Exception as e:
        raise RuntimeError(
            "PostgreSQL is not installed or running. Please check your configuration."
        ) from e

    # does dbname exist? if not, create it and load schema
    from sqlalchemy import create_engine, text
    from werkzeug.security import generate_password_hash

    # Connect to a default admin DB (typically 'postgres') to check for existence of target DBs
    admin_engine = create_engine(
        f"postgresql://{user}:{password}@{host}:{port}/postgres"
    )

    # --- Check and create dashboard DB if needed ---
    with admin_engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{dbname}'")
        )
        db_exists = result.scalar() is not None

    if not db_exists:
        # Create the database (requires AUTOCOMMIT mode)
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            conn.execute(text(f"CREATE DATABASE {dbname}"))

        # Connect to the new DB and load schema
        dashboard_engine = create_engine(app.config["SQLALCHEMY_BINDS"]["db_admin"])
        with dashboard_engine.connect() as db_conn:
            # Load SQL schema
            from y_web.src.system.path_utils import get_resource_path

            schema_path = get_resource_path(
                os.path.join("data_schema", "postgre_dashboard.sql")
            )
            schema_sql = open(schema_path, "r").read()
            db_conn.execute(text(schema_sql))

            # Generate hashed password
            hashed_pw = generate_password_hash("admin", method="pbkdf2:sha256")

            # Insert initial admin user
            db_conn.execute(
                text("""
                     INSERT INTO admin_users (username, email, password, role)
                     VALUES (:username, :email, :password, :role)
                     """),
                {
                    "username": "Admin",
                    "email": "admin@y-not.social",
                    "password": hashed_pw,
                    "role": "admin",
                },
            )

        dashboard_engine.dispose()

    # --- Check and create dummy DB if needed ---
    with admin_engine.connect() as conn:
        result = conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{dbname_dummy}'")
        )
        dummy_exists = result.scalar() is not None

    if not dummy_exists:
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            conn.execute(text(f"CREATE DATABASE {dbname_dummy}"))

        dummy_engine = create_engine(app.config["SQLALCHEMY_BINDS"]["db_exp"])
        with dummy_engine.connect() as dummy_conn:
            from y_web.src.system.path_utils import get_resource_path

            schema_path = get_resource_path(
                os.path.join("data_schema", "postgre_server.sql")
            )
            schema_sql = open(schema_path, "r").read()
            dummy_conn.execute(text(schema_sql))

            # Generate hashed password
            hashed_pw = generate_password_hash("admin", method="pbkdf2:sha256")

            # Insert initial admin user
            stmt = text("""
                        INSERT INTO user_mgmt (username, email, password, user_type, leaning, age,
                                               language, owner, joined_on, frecsys_type,
                                               round_actions, toxicity, is_page, daily_activity_level)
                        VALUES (:username, :email, :password, :user_type, :leaning, :age,
                                :language, :owner, :joined_on, :frecsys_type,
                                :round_actions, :toxicity, :is_page, :daily_activity_level)
                        """)

            dummy_conn.execute(
                stmt,
                {
                    "username": "Admin",
                    "email": "admin@y-not.social",
                    "password": hashed_pw,
                    "user_type": "user",
                    "leaning": "none",
                    "age": 0,
                    "language": "en",
                    "owner": "admin",
                    "joined_on": 0,
                    "frecsys_type": "default",
                    "round_actions": 3,
                    "toxicity": "none",
                    "is_page": 0,
                    "daily_activity_level": 1,
                },
            )

        dummy_engine.dispose()

    admin_engine.dispose()


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
    import os

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    app = Flask(__name__, static_url_path="/static")

    app.config["SECRET_KEY"] = "4323432nldsf"
    app.config["DESKTOP_MODE"] = desktop_mode

    if db_type == "sqlite":
        # Determine the database directory based on execution mode
        if getattr(sys, "frozen", False):
            # Running from PyInstaller - use writable location for database
            from y_web.src.system.path_utils import get_writable_path

            db_dir = os.path.join(get_writable_path(), "y_web", "db")
        else:
            # Running from source - use BASE_DIR
            db_dir = f"{BASE_DIR}{os.sep}db"

        # Ensure db directory exists
        os.makedirs(db_dir, exist_ok=True)

        # Copy databases if missing in the target location
        dashboard_db_path = os.path.join(db_dir, "dashboard.db")
        dummy_db_path = os.path.join(db_dir, "dummy.db")

        if not os.path.exists(dashboard_db_path):
            from y_web.src.system.path_utils import get_resource_path

            dashboard_src = get_resource_path(
                os.path.join("data_schema", "database_dashboard.db")
            )
            server_src = get_resource_path(
                os.path.join("data_schema", "database_clean_server.db")
            )
            shutil.copyfile(dashboard_src, dashboard_db_path)
            shutil.copyfile(server_src, dummy_db_path)

        # Use the database paths in the appropriate location
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{dashboard_db_path}"
        app.config["SQLALCHEMY_BINDS"] = {
            "db_admin": f"sqlite:///{dashboard_db_path}",
            "db_exp": f"sqlite:///{dummy_db_path}",
        }

        # Use NullPool for SQLite to avoid connection pooling issues
        # This ensures each request gets a fresh connection and prevents hangs
        from sqlalchemy.pool import NullPool

        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False, "timeout": 10},
            "pool_pre_ping": True,
            "poolclass": NullPool,
        }

        # Store the database paths for migrations
        app.config["DASHBOARD_DB_PATH"] = dashboard_db_path
        app.config["DUMMY_DB_PATH"] = dummy_db_path

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

    # Run database migrations at startup
    with app.app_context():
        try:
            # Run migration to add blog_posts table if needed
            if db_type == "sqlite":
                from y_web.migrations.add_blog_posts_table import migrate_dashboard_db

                migrate_dashboard_db()
            # For PostgreSQL, the table is created via the schema file
        except Exception as e:
            print(f"Failed to run blog_posts table migration: {e}")

        try:
            # Run migration to add telemetry columns if needed
            if db_type == "sqlite":
                from y_web.migrations.add_telemetry_columns import migrate_sqlite

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_telemetry_columns import migrate_postgresql

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run telemetry columns migration: {e}")

        try:
            # Run migration to add log metrics tables if needed
            if db_type == "sqlite":
                from y_web.migrations.add_log_metrics_tables import migrate_sqlite

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_log_metrics_tables import migrate_postgresql

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run log metrics tables migration: {e}")

        try:
            # Run migration to add HPC monitor settings table and remove log sync settings
            if db_type == "sqlite":
                from y_web.migrations.add_hpc_monitor_settings import (
                    migrate_sqlite as migrate_hpc_monitor_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_hpc_monitor_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_hpc_monitor_settings import (
                    migrate_postgresql as migrate_hpc_monitor_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_hpc_monitor_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run HPC monitor settings migration: {e}")

        try:
            # Run migration to add exp_status column to exps table if needed
            if db_type == "sqlite":
                from y_web.migrations.add_exp_status_column import (
                    migrate_sqlite as migrate_exp_status_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_exp_status_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_exp_status_column import (
                    migrate_postgresql as migrate_exp_status_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_exp_status_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run exp_status column migration: {e}")

        try:
            # Run migration to add experiment schedule tables if needed
            if db_type == "sqlite":
                from y_web.migrations.add_experiment_schedule_tables import (
                    migrate_sqlite as migrate_schedule_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_schedule_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_experiment_schedule_tables import (
                    migrate_postgresql as migrate_schedule_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_schedule_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run experiment schedule tables migration: {e}")

        # Run watchdog settings migration
        try:
            if db_type == "sqlite":
                from y_web.migrations.add_watchdog_settings import (
                    migrate_sqlite as migrate_watchdog_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_watchdog_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_watchdog_settings import (
                    migrate_postgresql as migrate_watchdog_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_watchdog_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run watchdog settings migration: {e}")

        # Run tutorial_shown column migration
        try:
            if db_type == "sqlite":
                from y_web.migrations.add_tutorial_shown_column import (
                    migrate_sqlite as migrate_tutorial_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_tutorial_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_tutorial_shown_column import (
                    migrate_postgresql as migrate_tutorial_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_tutorial_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run tutorial_shown column migration: {e}")

        # Run exp_details_tutorial_shown column migration
        try:
            if db_type == "sqlite":
                from y_web.migrations.add_exp_details_tutorial_column import (
                    migrate_sqlite as migrate_exp_details_tutorial_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_exp_details_tutorial_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_exp_details_tutorial_column import (
                    migrate_postgresql as migrate_exp_details_tutorial_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_exp_details_tutorial_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run exp_details_tutorial_shown column migration: {e}")

        try:
            # Run migration to add exp_group column to exps table if needed
            if db_type == "sqlite":
                from y_web.migrations.add_exp_group_column import (
                    migrate_sqlite as migrate_exp_group_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_exp_group_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_exp_group_column import (
                    migrate_postgresql as migrate_exp_group_postgresql,
                )

                # Get PostgreSQL connection details from environment variables
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_exp_group_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run exp_group column migration: {e}")

        # Run agent archetypes migration
        try:
            if db_type == "sqlite":
                from y_web.migrations.add_agent_archetypes import (
                    migrate_sqlite as migrate_agent_archetypes_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_agent_archetypes_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_agent_archetypes import (
                    migrate_postgresql as migrate_agent_archetypes_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_agent_archetypes_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run agent archetypes migration: {e}")

        # Run agent archetype field migration (for agents and user_mgmt tables)
        try:
            if db_type == "sqlite":
                from y_web.migrations.add_agent_archetype_field import (
                    migrate_experiment_databases,
                    migrate_sqlite_dashboard,
                    migrate_sqlite_server,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_sqlite_dashboard(dashboard_db_path)

                # Migrate the dummy server database
                dummy_db_path = app.config.get("DUMMY_DB_PATH")
                if dummy_db_path:
                    migrate_sqlite_server(dummy_db_path, quiet=True)

                # Migrate all existing experiment databases
                from y_web.src.system.path_utils import get_writable_path

                BASE_DIR = get_writable_path()
                experiments_dir = os.path.join(BASE_DIR, "y_web", "experiments")
                if os.path.exists(experiments_dir):
                    print("Migrating existing experiment databases...")
                    success, total = migrate_experiment_databases(
                        experiments_dir, quiet=False
                    )
                    if total > 0:
                        print(f"✓ Migrated {success}/{total} experiment databases")

            elif db_type == "postgresql":
                from y_web.migrations.add_agent_archetype_field import (
                    migrate_postgresql_dashboard,
                    migrate_postgresql_server,
                )

                # Get PostgreSQL connection details for dashboard
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")

                if pg_password:
                    dashboard_config = {
                        "host": pg_host,
                        "port": pg_port,
                        "database": pg_database,
                        "user": pg_user,
                        "password": pg_password,
                    }
                    migrate_postgresql_dashboard(dashboard_config)

                    # Note: Server database migration will happen per experiment
                    # The schema files are already updated for new installations
        except Exception as e:
            print(f"Failed to run agent archetype field migration: {e}")

        # Run opinion evolution cache tables migration
        try:
            if db_type == "sqlite":
                from y_web.migrations.add_opinion_evolution_cache import (
                    migrate_sqlite as migrate_cache_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_cache_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_opinion_evolution_cache import (
                    migrate_postgresql as migrate_cache_postgresql,
                )

                # Get PostgreSQL connection details from environment variables
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_cache_postgresql(
                        pg_user, pg_password, pg_host, pg_port, pg_database
                    )
        except Exception as e:
            print(f"Failed to run opinion evolution cache migration: {e}")

        # Run remote experiment fields migration
        try:
            if db_type == "sqlite":
                from y_web.migrations.add_remote_experiment_fields import (
                    migrate_sqlite as migrate_remote_fields_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_remote_fields_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_remote_experiment_fields import (
                    migrate_postgresql as migrate_remote_fields_postgresql,
                )

                # Get PostgreSQL connection details from environment variables
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_remote_fields_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run remote experiment fields migration: {e}")

        try:
            # Run migration to add follow action column if needed
            if db_type == "sqlite":
                from y_web.migrations.add_follow_action_column import migrate_sqlite

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_follow_action_column import (
                    migrate_postgresql,
                )

                # Get PostgreSQL connection details from environment variables (same as create_postgresql_db)
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run follow action column migration: {e}")

        try:
            # Run migration to add group and enabled columns to recsys tables
            if db_type == "sqlite":
                from y_web.migrations.add_recsys_columns import migrate_sqlite

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_recsys_columns import migrate_postgresql

                # Get PostgreSQL connection details from environment variables
                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run recsys columns migration: {e}")

        try:
            # Run migration to add async download notifications table
            if db_type == "sqlite":
                from y_web.migrations.add_download_notifications_table import (
                    migrate_sqlite,
                )

                dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
                if dashboard_db_path:
                    migrate_sqlite(dashboard_db_path)
            elif db_type == "postgresql":
                from y_web.migrations.add_download_notifications_table import (
                    migrate_postgresql,
                )

                pg_host = os.getenv("PG_HOST", "localhost")
                pg_port = os.getenv("PG_PORT", "5432")
                pg_database = os.getenv("PG_DBNAME", "dashboard")
                pg_user = os.getenv("PG_USER", "postgres")
                pg_password = os.getenv("PG_PASSWORD", "")
                if pg_password:
                    migrate_postgresql(
                        pg_host, pg_port, pg_database, pg_user, pg_password
                    )
        except Exception as e:
            print(f"Failed to run download notifications migration: {e}")

        # Ensure all tables defined in models exist (including release_info)
        # This creates any missing tables that are defined in models.py
        try:
            db.create_all()
            print("✓ Database tables verified/created")
        except Exception as e:
            print(f"Failed to create database tables: {e}")

        # Initialize database bindings for all active experiments
        # NOTE: This must run AFTER all migrations (especially add_exp_status_column)
        # to ensure the exp_status column exists in the exps table before querying
        try:
            initialize_active_experiment_databases(app)
        except Exception as e:
            print(f"Failed to initialize active experiment databases: {e}")

    # Check for updates at startup
    with app.app_context():
        try:
            from y_web.src.system.check_release import update_release_info_in_db

            update_release_info_in_db()
        except Exception as e:
            print(f"Failed to check for updates at startup: {e}")

        try:
            from y_web.src.system.check_blog import update_blog_info_in_db

            update_blog_info_in_db()
        except Exception as e:
            print(f"Failed to check for blog posts at startup: {e}")

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
