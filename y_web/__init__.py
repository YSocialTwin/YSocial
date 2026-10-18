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
from sqlalchemy import select

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
            # Use existing context — db is the module-level SQLAlchemy instance
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


def _is_simulation_subprocess():
    """Return True when running in a spawned simulation subprocess."""
    return (
        os.environ.get("Y_CLIENT_SUBPROCESS") == "1"
        or os.environ.get("Y_SERVER_SUBPROCESS") == "1"
        or os.environ.get("Y_SOCIAL_SUBPROCESS") == "1"
    )


def _should_register_cleanup_handler():
    """
    Register shutdown cleanup only for the real top-level YSocial app process.

    Importing ``y_web`` from tests, maintenance scripts, or ad hoc validation
    helpers must not implicitly arm a global atexit hook that stops active
    experiments.
    """
    return (
        os.environ.get("YSOCIAL_REGISTER_ATEXIT_CLEANUP") == "1"
        and not _is_simulation_subprocess()
    )


# Only register atexit handler for the opted-in main application process.
if _should_register_cleanup_handler():
    atexit.register(cleanup_db_jupyter_with_new_app)


def create_app(db_type="sqlite", desktop_mode=False, config_class=None):
    """
    Create and configure the Flask application (factory pattern).

    Initializes the application with database connections, authentication,
    and all route blueprints. Supports both SQLite and PostgreSQL backends.

    Args:
        db_type: Database type to use, either "sqlite" or "postgresql"
        desktop_mode: Whether the app is running in desktop mode with PyWebview
        config_class: Optional config class from y_web.config (auto-detected from
            FLASK_ENV if not provided)

    Returns:
        Configured Flask application instance

    Raises:
        ValueError: If unsupported db_type is provided
    """
    app = Flask(__name__, static_url_path="/static")

    # ------------------------------------------------------------------ #
    # Centralized configuration (y_web/config.py)                         #
    # ------------------------------------------------------------------ #
    from dotenv import load_dotenv

    from y_web.config import get_config

    load_dotenv()

    if config_class is None:
        config_class = get_config()

    app.config.from_object(config_class)

    # Runtime-only settings (not part of static config classes)
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

    db.init_app(app)
    login_manager.init_app(app)

    __import__("y_web.i18n", fromlist=["init_i18n"]).init_i18n(app)
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
            return db.session.get(Admin_users, admin_id)
        else:
            # Regular experiment participant
            return db.session.get(User_mgmt, user_id)

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
        from y_web.src.system.role_gate import teacher_gate

        denied = (
            setup_experiment_context() or teacher_gate()
        )  # the gate runs after the context (see role_gate)
        if denied is not None:
            return denied

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

    __import__("y_web.src.system.prompt_packs", fromlist=["x"]).register_context(app)

    from y_web.src.system.template_context import register_template_context

    register_template_context(app)

    from y_web.routes import register_blueprints

    register_blueprints(app)

    # ------------------------------------------------------------------
    # Frontend plugin suites (e.g. Frontend Adds-on) — registered ONLY for suites
    # that are installed under external/<repo> AND pass manifest validation.
    # A suite that is absent, partially installed, or fails validation
    # contributes zero routes/blueprints: this is the app-startup half of
    # the "zero impact when not installed" guarantee (the per-experiment
    # enable/disable half is enforced per-request inside each module's own
    # blueprint — see external/frontend_adds-on/modules/*/backend).
    # ------------------------------------------------------------------
    try:
        from y_web.src.external_runtime.plugin_loader import (
            register_frontend_plugin_suites,
        )

        _frontend_plugin_report = register_frontend_plugin_suites(app)
        for _repo_key, _suite_report in _frontend_plugin_report.get(
            "suites", {}
        ).items():
            if _suite_report.get("installed"):
                if _suite_report.get("valid"):
                    print(
                        f"✓ Frontend plugin suite '{_repo_key}': "
                        f"{len(_suite_report.get('registered_modules', []))} module(s) registered"
                    )
                else:
                    print(
                        f"⚠ Frontend plugin suite '{_repo_key}' is installed but failed validation: "
                        f"{_suite_report.get('errors')}"
                    )
    except Exception as e:
        print(f"Failed to load frontend plugin suites: {e}")

    # ------------------------------------------------------------------
    # Backend settings plugin suites (e.g. Scenario Design) — structurally
    # parallel to the frontend plugin suites above, but admin-only authoring
    # tools that are always active once installed and valid (no per-
    # experiment enable/disable, no entry in /admin/frontend_settings).
    # ------------------------------------------------------------------
    try:
        from y_web.src.external_runtime.backend_plugins import (
            print_backend_plugin_report,
            register_backend_plugin_suites,
        )

        print_backend_plugin_report(register_backend_plugin_suites(app))
    except Exception as e:
        print(f"Failed to load backend settings plugin suites: {e}")

    # Backend settings suite sidebar visibility (e.g. Scenario Design):
    # body lives in src/external_runtime/backend_plugins.py, not inline
    # here, to keep this factory function's line count down (see
    # y_web/tests/test_phase11_db_init_package.py::
    # test_y_web_init_line_count_reduced).
    from y_web.src.external_runtime.backend_plugins import (
        inject_backend_plugin_visibility,
    )

    app.context_processor(inject_backend_plugin_visibility)

    from y_web.src.system.startup_migrations import run_startup_migrations

    run_startup_migrations(app, db_type)

    # Optional per-suite schema migrations (manifest key "schema_module"),
    # run after the core Alembic upgrade. Never raises.
    from y_web.src.external_runtime.backend_plugins import (
        run_backend_plugin_schema_migrations,
    )

    run_backend_plugin_schema_migrations(app)

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
