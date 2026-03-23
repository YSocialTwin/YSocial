"""
SQLite database initialisation for YSocial.

Provides :func:`create_sqlite_db` which configures SQLAlchemy on *app*
to use SQLite databases (dashboard + dummy), creating them from bundled
seed files the first time the application runs.
"""

import os
import shutil
import sys


def create_sqlite_db(app):
    """
    Create and initialize SQLite database for the application.

    Determines the correct database directory, copies seed databases if they
    do not yet exist, and sets all required SQLAlchemy config keys on *app*.

    Args:
        app: Flask application instance to configure
    """
    # app.root_path is the y_web package directory (same as BASE_DIR in __init__.py)
    BASE_DIR = app.root_path

    # Determine the database directory based on execution mode
    if getattr(sys, "frozen", False):
        # Running from PyInstaller - use writable location for database
        from y_web.src.system.path_utils import get_writable_path

        db_dir = os.path.join(get_writable_path(), "y_web", "db")
    else:
        # Running from source - use BASE_DIR
        db_dir = os.path.join(BASE_DIR, "db")

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
