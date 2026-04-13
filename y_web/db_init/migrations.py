"""
Database migration runner for YSocial.

Provides :func:`run_migrations` which applies all incremental schema migrations
to both SQLite and PostgreSQL databases.  Called once during :func:`create_app`
after the database engine has been configured.
"""

import os


def _get_pg_params():
    """Return a dict of PostgreSQL connection parameters from environment variables."""
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": os.getenv("PG_PORT", "5432"),
        "database": os.getenv("PG_DBNAME", "dashboard"),
        "user": os.getenv("PG_USER", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
    }


def run_migrations(app, db_type, db):
    """
    Run all pending database migrations against the configured database.

    This function is idempotent: each migration module checks whether the
    target schema change already exists before applying it.

    Args:
        app:     Configured Flask application instance (used for app context).
        db_type: ``"sqlite"`` or ``"postgresql"``.
        db:      The Flask-SQLAlchemy :class:`~flask_sqlalchemy.SQLAlchemy` instance.
    """
    with app.app_context():
        _run_all_migrations(app, db_type, db)

    # Check for updates at startup (outside the migrations context so it can
    # use a clean session)
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


def _run_all_migrations(app, db_type, db):
    """Execute every migration inside a single app context."""
    from y_web.src.experiment.context import initialize_active_experiment_databases

    dashboard_db_path = app.config.get("DASHBOARD_DB_PATH")
    dummy_db_path = app.config.get("DUMMY_DB_PATH")
    pg = _get_pg_params() if db_type == "postgresql" else {}

    # ------------------------------------------------------------------
    # blog_posts table
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_blog_posts_table import migrate_dashboard_db

            migrate_dashboard_db()
        # For PostgreSQL, the table is created via the schema file
    except Exception as e:
        print(f"Failed to run blog_posts table migration: {e}")

    # ------------------------------------------------------------------
    # telemetry columns
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_telemetry_columns import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_telemetry_columns import migrate_postgresql

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run telemetry columns migration: {e}")

    # ------------------------------------------------------------------
    # log metrics tables
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_log_metrics_tables import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_log_metrics_tables import migrate_postgresql

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run log metrics tables migration: {e}")

    # ------------------------------------------------------------------
    # HPC monitor settings
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_hpc_monitor_settings import (
                migrate_sqlite as migrate_hpc_monitor_sqlite,
            )

            if dashboard_db_path:
                migrate_hpc_monitor_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_hpc_monitor_settings import (
                migrate_postgresql as migrate_hpc_monitor_postgresql,
            )

            if pg["password"]:
                migrate_hpc_monitor_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run HPC monitor settings migration: {e}")

    # ------------------------------------------------------------------
    # exp_status column
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_exp_status_column import (
                migrate_sqlite as migrate_exp_status_sqlite,
            )

            if dashboard_db_path:
                migrate_exp_status_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_exp_status_column import (
                migrate_postgresql as migrate_exp_status_postgresql,
            )

            if pg["password"]:
                migrate_exp_status_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run exp_status column migration: {e}")

    # ------------------------------------------------------------------
    # experiment schedule tables
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_experiment_schedule_tables import (
                migrate_sqlite as migrate_schedule_sqlite,
            )

            if dashboard_db_path:
                migrate_schedule_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_experiment_schedule_tables import (
                migrate_postgresql as migrate_schedule_postgresql,
            )

            if pg["password"]:
                migrate_schedule_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run experiment schedule tables migration: {e}")

    # ------------------------------------------------------------------
    # watchdog settings
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_watchdog_settings import (
                migrate_sqlite as migrate_watchdog_sqlite,
            )

            if dashboard_db_path:
                migrate_watchdog_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_watchdog_settings import (
                migrate_postgresql as migrate_watchdog_postgresql,
            )

            if pg["password"]:
                migrate_watchdog_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run watchdog settings migration: {e}")

    # ------------------------------------------------------------------
    # tutorial_shown column
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_tutorial_shown_column import (
                migrate_sqlite as migrate_tutorial_sqlite,
            )

            if dashboard_db_path:
                migrate_tutorial_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_tutorial_shown_column import (
                migrate_postgresql as migrate_tutorial_postgresql,
            )

            if pg["password"]:
                migrate_tutorial_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run tutorial_shown column migration: {e}")

    # ------------------------------------------------------------------
    # exp_details_tutorial_shown column
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_exp_details_tutorial_column import (
                migrate_sqlite as migrate_exp_details_tutorial_sqlite,
            )

            if dashboard_db_path:
                migrate_exp_details_tutorial_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_exp_details_tutorial_column import (
                migrate_postgresql as migrate_exp_details_tutorial_postgresql,
            )

            if pg["password"]:
                migrate_exp_details_tutorial_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run exp_details_tutorial_shown column migration: {e}")

    # ------------------------------------------------------------------
    # exp_group column
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_exp_group_column import (
                migrate_sqlite as migrate_exp_group_sqlite,
            )

            if dashboard_db_path:
                migrate_exp_group_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_exp_group_column import (
                migrate_postgresql as migrate_exp_group_postgresql,
            )

            if pg["password"]:
                migrate_exp_group_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run exp_group column migration: {e}")

    # ------------------------------------------------------------------
    # agent archetypes
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_agent_archetypes import (
                migrate_sqlite as migrate_agent_archetypes_sqlite,
            )

            if dashboard_db_path:
                migrate_agent_archetypes_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_agent_archetypes import (
                migrate_postgresql as migrate_agent_archetypes_postgresql,
            )

            if pg["password"]:
                migrate_agent_archetypes_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run agent archetypes migration: {e}")

    # ------------------------------------------------------------------
    # agent archetype field (agents + user_mgmt tables)
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_agent_archetype_field import (
                migrate_experiment_databases,
                migrate_sqlite_dashboard,
                migrate_sqlite_server,
            )

            if dashboard_db_path:
                migrate_sqlite_dashboard(dashboard_db_path)

            if dummy_db_path:
                migrate_sqlite_server(dummy_db_path, quiet=True)

            # Migrate all existing experiment databases
            from y_web.src.system.path_utils import get_writable_path

            experiments_dir = os.path.join(get_writable_path(), "y_web", "experiments")
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
            )

            if pg["password"]:
                migrate_postgresql_dashboard(pg)
            # Note: Server database migration will happen per experiment
    except Exception as e:
        print(f"Failed to run agent archetype field migration: {e}")

    # ------------------------------------------------------------------
    # moderation schema in experiment databases
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_moderation_schema import (
                migrate_experiment_databases as migrate_moderation_experiment_databases,
            )
            from y_web.migrations.add_moderation_schema import (
                migrate_sqlite_server as migrate_moderation_sqlite_server,
            )

            if dummy_db_path:
                migrate_moderation_sqlite_server(dummy_db_path, quiet=True)

            from y_web.src.system.path_utils import get_writable_path

            experiments_dir = os.path.join(get_writable_path(), "y_web", "experiments")
            if os.path.exists(experiments_dir):
                print("Migrating moderation schema for experiment databases...")
                success, total = migrate_moderation_experiment_databases(
                    experiments_dir, quiet=False
                )
                if total > 0:
                    print(f"✓ Migrated {success}/{total} experiment databases")
        elif db_type == "postgresql":
            from y_web.migrations.add_moderation_schema import (
                migrate_postgresql_server as migrate_moderation_postgresql_server,
            )

            if pg["password"]:
                pg_dummy_db = os.getenv("PG_DBNAME_DUMMY", "dummy")
                migrate_moderation_postgresql_server(
                    pg["host"], pg["port"], pg_dummy_db, pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run moderation schema migration: {e}")

    # ------------------------------------------------------------------
    # opinion evolution cache tables
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_opinion_evolution_cache import (
                migrate_sqlite as migrate_cache_sqlite,
            )

            if dashboard_db_path:
                migrate_cache_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_opinion_evolution_cache import (
                migrate_postgresql as migrate_cache_postgresql,
            )

            if pg["password"]:
                migrate_cache_postgresql(
                    pg["user"], pg["password"], pg["host"], pg["port"], pg["database"]
                )
    except Exception as e:
        print(f"Failed to run opinion evolution cache migration: {e}")

    # ------------------------------------------------------------------
    # remote experiment fields
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_remote_experiment_fields import (
                migrate_sqlite as migrate_remote_fields_sqlite,
            )

            if dashboard_db_path:
                migrate_remote_fields_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_remote_experiment_fields import (
                migrate_postgresql as migrate_remote_fields_postgresql,
            )

            if pg["password"]:
                migrate_remote_fields_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run remote experiment fields migration: {e}")

    # ------------------------------------------------------------------
    # follow action column
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_follow_action_column import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_follow_action_column import migrate_postgresql

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run follow action column migration: {e}")

    # ------------------------------------------------------------------
    # recsys columns (group + enabled)
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_recsys_columns import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_recsys_columns import migrate_postgresql

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run recsys columns migration: {e}")

    # ------------------------------------------------------------------
    # async download notifications table
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_download_notifications_table import (
                migrate_sqlite,
            )

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_download_notifications_table import (
                migrate_postgresql,
            )

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run download notifications migration: {e}")

    # ------------------------------------------------------------------
    # plugin agent extension table
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_agent_ext_table import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_agent_ext_table import migrate_postgresql

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run agent_ext table migration: {e}")

    # ------------------------------------------------------------------
    # reusable forum feed resource tables
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_forum_feed_resource_tables import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_forum_feed_resource_tables import (
                migrate_postgresql,
            )

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run forum feed resource migration: {e}")

    # ------------------------------------------------------------------
    # structured agent custom features table
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_agents_custom_features_table import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_agents_custom_features_table import (
                migrate_postgresql,
            )

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run agents_custom_features table migration: {e}")

    # ------------------------------------------------------------------
    # population pop_type column
    # ------------------------------------------------------------------
    try:
        if db_type == "sqlite":
            from y_web.migrations.add_population_pop_type import migrate_sqlite

            if dashboard_db_path:
                migrate_sqlite(dashboard_db_path)
        elif db_type == "postgresql":
            from y_web.migrations.add_population_pop_type import migrate_postgresql

            if pg["password"]:
                migrate_postgresql(
                    pg["host"], pg["port"], pg["database"], pg["user"], pg["password"]
                )
    except Exception as e:
        print(f"Failed to run population pop_type migration: {e}")

    # ------------------------------------------------------------------
    # Ensure all tables defined in models exist (including release_info)
    # ------------------------------------------------------------------
    try:
        db.create_all()
        print("✓ Database tables verified/created")
    except Exception as e:
        print(f"Failed to create database tables: {e}")

    # Initialize database bindings for all active experiments.
    # NOTE: Must run AFTER all migrations (especially add_exp_status_column)
    # to ensure the exp_status column exists in the exps table before querying.
    try:
        initialize_active_experiment_databases(app)
    except Exception as e:
        print(f"Failed to initialize active experiment databases: {e}")
