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

import os
import shutil
import signal
import atexit
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

client_processes = {}

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

    app.config[
        "SQLALCHEMY_DATABASE_URI"
    ] = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

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
    from sqlalchemy import create_engine
    from sqlalchemy import text
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
            schema_sql = open(
                f"{BASE_DIR}{os.sep}..{os.sep}data_schema{os.sep}postgre_dashboard.sql",
                "r",
            ).read()
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
            schema_sql = open(
                f"{BASE_DIR}{os.sep}..{os.sep}data_schema{os.sep}postgre_server.sql",
                "r",
            ).read()
            dummy_conn.execute(text(schema_sql))

            # Generate hashed password
            hashed_pw = generate_password_hash("test", method="pbkdf2:sha256")

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
                }
            )

        dummy_engine.dispose()

    admin_engine.dispose()


def cleanup_subprocesses():
    """Terminate all running simulation client subprocesses on shutdown."""
    print("Cleaning up subprocesses...")
    for _, proc in client_processes.items():
        print(f"Terminating subprocess {proc.pid}...")
        proc.terminate()
        proc.join()
    print("All subprocesses terminated.")


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) by cleaning up subprocesses and exiting gracefully."""
    print("Ctrl+C detected, shutting down...")
    cleanup_subprocesses()
    exit(0)


signal.signal(signal.SIGINT, signal_handler)
atexit.register(cleanup_subprocesses)


def create_app(db_type="sqlite"):
    """
    Create and configure the Flask application (factory pattern).
    
    Initializes the application with database connections, authentication,
    and all route blueprints. Supports both SQLite and PostgreSQL backends.
    
    Args:
        db_type: Database type to use, either "sqlite" or "postgresql"
        
    Returns:
        Configured Flask application instance
        
    Raises:
        ValueError: If unsupported db_type is provided
    """
    app = Flask(__name__, static_url_path="/static")

    # Copy databases if missing (keep your existing logic)
    if not os.path.exists(f"{BASE_DIR}{os.sep}db{os.sep}dashboard.db"):
        shutil.copyfile(
            f"{BASE_DIR}{os.sep}..{os.sep}data_schema{os.sep}database_dashboard.db",
            f"{BASE_DIR}{os.sep}db{os.sep}dashboard.db",
        )
        shutil.copyfile(
            f"{BASE_DIR}{os.sep}..{os.sep}data_schema{os.sep}database_clean_server.db",
            f"{BASE_DIR}{os.sep}db{os.sep}dummy.db",
        )

    app.config["SECRET_KEY"] = "4323432nldsf"

    if db_type == "sqlite":
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

    db.init_app(app)
    login_manager.init_app(app)

    from .models import User_mgmt as User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

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

    return app
