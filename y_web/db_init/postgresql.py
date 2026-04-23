"""
PostgreSQL database initialisation for YSocial.

Provides :func:`create_postgresql_db` which configures SQLAlchemy on *app*
and creates both the dashboard and dummy databases (with schema + seed data)
the first time the application runs against a fresh PostgreSQL server.
"""

import os

from y_web.src.content.cover_images import random_cover_image_url


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
                                       round_actions, toxicity, is_page, daily_activity_level, cover_image)
                VALUES (:username, :email, :password, :user_type, :leaning, :age,
                        :language, :owner, :joined_on, :frecsys_type,
                        :round_actions, :toxicity, :is_page, :daily_activity_level, :cover_image)
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
                    "cover_image": random_cover_image_url(),
                },
            )

        dummy_engine.dispose()

    admin_engine.dispose()
