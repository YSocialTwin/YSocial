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
import os
import shutil
import sys

from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

# Set BASE_DIR to a writable location when running from PyInstaller
# In PyInstaller mode, __file__ points to temp extraction folder which is recreated each run
# Use get_writable_path() to ensure database persistence across runs
if getattr(sys, "frozen", False):
    # Running in PyInstaller bundle - use persistent writable directory
    from y_web.utils.path_utils import get_writable_path
    BASE_DIR = get_writable_path("y_web")
else:
    # Running from source - use y_web directory
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
            from y_web.utils.path_utils import get_resource_path

            schema_path = get_resource_path(
                os.path.join("data_schema", "postgre_dashboard.sql")
            )
            schema_sql = open(schema_path, "r").read()
            db_conn.execute(text(schema_sql))

            # Generate hashed password
            hashed_pw = generate_password_hash("test", method="pbkdf2:sha256")

            # Insert initial admin user
            db_conn.execute(
                text(
                    """
                     INSERT INTO admin_users (username, email, password, role)
                     VALUES (:username, :email, :password, :role)
                     """
                ),
                {
                    "username": "admin",
                    "email": "admin@ysocial.com",
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
            from y_web.utils.path_utils import get_resource_path

            schema_path = get_resource_path(
                os.path.join("data_schema", "postgre_server.sql")
            )
            schema_sql = open(schema_path, "r").read()
            dummy_conn.execute(text(schema_sql))

            # Generate hashed password
            hashed_pw = generate_password_hash("test", method="pbkdf2:sha256")

            # Insert initial admin user
            stmt = text(
                """
                        INSERT INTO user_mgmt (username, email, password, user_type, leaning, age,
                                               language, owner, joined_on, frecsys_type,
                                               round_actions, toxicity, is_page, daily_activity_level)
                        VALUES (:username, :email, :password, :user_type, :leaning, :age,
                                :language, :owner, :joined_on, :frecsys_type,
                                :round_actions, :toxicity, :is_page, :daily_activity_level)
                        """
            )

            dummy_conn.execute(
                stmt,
                {
                    "username": "admin",
                    "email": "admin@ysocial.com",
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
            from y_web.utils.external_processes import stop_all_exps
            from y_web.utils.jupyter_utils import stop_all_jupyter_instances

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
                        from y_web.utils.external_processes import stop_all_exps
                        from y_web.utils.jupyter_utils import stop_all_jupyter_instances

                        stop_all_jupyter_instances()
                        stop_all_exps()
                        # For PostgreSQL, ensure changes are committed by explicitly closing the session
                        db.session.commit()
                        db.session.close()
                        print(
                            "Database session committed and closed successfully (new context)"
                        )
                except Exception as e1:
                    print(f"Error during DB cleanup with {dbms} app:", e1)
                    pass

    except Exception as e:
        print("Error during DB cleanup with fresh app:", e)
        import traceback

        traceback.print_exc()


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

    if db_type == "sqlite":
        # Ensure db directory exists (important for PyInstaller where BASE_DIR is in writable location)
        db_dir = f"{BASE_DIR}{os.sep}db"
        os.makedirs(db_dir, exist_ok=True)
        
        # Copy databases if missing
        if not os.path.exists(f"{BASE_DIR}{os.sep}db{os.sep}dashboard.db"):
            from y_web.utils.path_utils import get_resource_path

            dashboard_src = get_resource_path(
                os.path.join("data_schema", "database_dashboard.db")
            )
            server_src = get_resource_path(
                os.path.join("data_schema", "database_clean_server.db")
            )
            shutil.copyfile(
                dashboard_src,
                f"{BASE_DIR}{os.sep}db{os.sep}dashboard.db",
            )
            shutil.copyfile(
                server_src,
                f"{BASE_DIR}{os.sep}db{os.sep}dummy.db",
            )

        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR}/db/dashboard.db"
        app.config["SQLALCHEMY_BINDS"] = {
            "db_admin": f"sqlite:///{BASE_DIR}/db/dashboard.db",
            "db_exp": f"sqlite:///{BASE_DIR}/db/dummy.db",
        }
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False}
        }

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

    from .models import User_mgmt as User

    @login_manager.user_loader
    def load_user(user_id):
        """
        Load user by ID for Flask-Login session management.

        Args:
            user_id: User ID string to load

        Returns:
            User_mgmt object if found, None otherwise
        """
        return User.query.get(int(user_id))

    # Setup experiment context handler
    from .experiment_context import (
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
        """Restore experiment context after each request."""
        teardown_experiment_context(exception)

    @app.context_processor
    def inject_exp_id():
        """Inject exp_id into all templates."""
        return dict(exp_id=get_current_experiment_id())

    @app.context_processor
    def inject_active_experiments():
        """Inject active experiments into all admin templates."""
        from .models import Exps

        try:
            active_exps = Exps.query.filter_by(status=1).all()
            return dict(active_experiments=active_exps)
        except Exception:
            return dict(active_experiments=[])

    @app.context_processor
    def inject_user_info():
        """Inject current user role information into templates."""
        from flask_login import current_user

        from .models import Admin_users

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

    # Initialize database bindings for all active experiments
    initialize_active_experiment_databases(app)

    # Register your blueprints here as before
    from .auth import auth as auth_blueprint

    app.register_blueprint(auth_blueprint)
    from .main import main as main_blueprint

    app.register_blueprint(main_blueprint)
    from .user_interaction import user as user_blueprint

    app.register_blueprint(user_blueprint)
    from .admin_dashboard import admin as admin_blueprint

    app.register_blueprint(admin_blueprint)
    from .routes_admin.ollama_routes import ollama as ollama_blueprint

    app.register_blueprint(ollama_blueprint)
    from .routes_admin.populations_routes import population as population_blueprint

    app.register_blueprint(population_blueprint)
    from .routes_admin.pages_routes import pages as pages_blueprint

    app.register_blueprint(pages_blueprint)
    from .routes_admin.agents_routes import agents as agents_blueprint

    app.register_blueprint(agents_blueprint)
    from .routes_admin.users_routes import users as users_blueprint

    app.register_blueprint(users_blueprint)
    from .routes_admin.experiments_routes import experiments as experiments_blueprint

    app.register_blueprint(experiments_blueprint)
    from .routes_admin.clients_routes import clientsr as clients_blueprint

    app.register_blueprint(clients_blueprint)
    from .error_routes import errors as errors_blueprint

    app.register_blueprint(errors_blueprint)

    from .routes_admin.jupyterlab_routes import lab as lab_blueprint

    app.register_blueprint(lab_blueprint)

    # Add context processor to detect PyInstaller mode
    @app.context_processor
    def inject_pyinstaller_mode():
        """Inject PyInstaller mode detection into all templates."""
        import sys

        return dict(is_pyinstaller=getattr(sys, "frozen", False))

    return app
