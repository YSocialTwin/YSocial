"""Database migrations and startup checks (Alembic, with fallbacks), moved out of ``y_web/__init__.py``.

Behaviour unchanged: stamp every bound database, upgrade the primary schema to HEAD, bring the active
experiment databases up to date; without Flask-Migrate use standalone Alembic, and without Alembic the legacy
runner.
"""

import os

import y_web
from y_web import db


def sync_missing_model_columns(engine, metadata):
    """Add model columns that a legacy table lacks (idempotent, every startup).

    Databases created by older releases may already be stamped at an Alembic head
    while missing columns later added to the models (e.g. ``exps.simulator_type``),
    so a revision file cannot repair them. Columns that need a default to be
    NOT NULL are added as nullable. Returns the list of ``(table, column)`` added.
    """
    from sqlalchemy import inspect, text

    added = []
    with engine.begin() as conn:
        inspector = inspect(conn)
        existing = set(inspector.get_table_names())
        for table in metadata.sorted_tables:
            if table.name not in existing:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in have or col.primary_key:
                    continue
                ddl = col.type.compile(dialect=conn.dialect)
                if col.server_default is not None:
                    arg = col.server_default.arg
                    ddl += f" DEFAULT {getattr(arg, 'text', arg)}"
                    if not col.nullable:
                        ddl += " NOT NULL"
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}')
                )
                added.append((table.name, col.name))
    return added


def _repair_legacy_columns(app):
    try:
        import y_web.src.models  # noqa: F401  (registers every model)

        engine = db.engines["db_admin"]
        added = sync_missing_model_columns(engine, db.metadatas["db_admin"])
        if added:
            print(
                "✓ Added missing columns to legacy tables: "
                + ", ".join(f"{t}.{c}" for t, c in added)
            )
    except Exception as exc:  # never block startup on a repair attempt
        print(f"⚠ Warning: legacy column sync failed: {exc}")


def run_startup_migrations(app, db_type):
    """Migrate the databases of ``app`` at startup."""
    # ------------------------------------------------------------------ #
    # Database migrations + startup checks                                 #
    # ------------------------------------------------------------------ #
    _alembic_dir = os.path.join(os.path.dirname(y_web.__file__), "alembic")
    try:
        from alembic.config import Config as AlembicConfig
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from flask_migrate import Migrate
        from flask_migrate import upgrade as alembic_upgrade

        migrate_ext = Migrate(app, db, directory=_alembic_dir)
        with app.app_context():
            # Build a minimal Alembic config pointing at our script directory.
            # This lets us stamp arbitrary engines directly — not just the default
            # bind that flask_migrate.stamp() targets.
            _alembic_cfg = AlembicConfig()
            _alembic_cfg.set_main_option("script_location", _alembic_dir)
            _alembic_script = ScriptDirectory.from_config(_alembic_cfg)

            def _stamp_engine_if_needed(engine, bind_key):
                """Stamp *engine* with 0001_baseline if it has no alembic_version row."""
                with engine.begin() as conn:
                    ctx = MigrationContext.configure(conn)
                    if not ctx.get_current_heads():
                        print(
                            f"  ↳ [{bind_key}] no alembic_version found — stamping 0001_baseline"
                        )
                        ctx.stamp(_alembic_script, "0001_baseline")
                    else:
                        print(
                            f"  ↳ [{bind_key}] alembic_version OK ({', '.join(ctx.get_current_heads())})"
                        )

            # Check every bound engine at startup (db_admin = dashboard.db,
            # db_exp = dummy.db placeholder).  De-duplicate by engine identity
            # because the default URI and "db_admin" can resolve to the same file.
            print("✦ Alembic: checking bound databases…")
            _seen_engine_ids: set = set()
            for _bind_key, _engine in db.engines.items():
                if id(_engine) not in _seen_engine_ids:
                    _seen_engine_ids.add(id(_engine))
                    _stamp_engine_if_needed(_engine, _bind_key)

            # Upgrade the primary (db_admin) schema to HEAD.
            print("✦ Alembic: upgrading primary schema (db_admin) to HEAD…")
            alembic_upgrade()
            print("✓ Alembic: primary schema up to date")
            _repair_legacy_columns(app)

            # Bring every active experiment database up to date.
            # Experiment DBs (experiments/<UUID>/database_server.db) are NOT
            # managed through Alembic revision files — their schema is kept
            # current by ensure_experiment_schema_for_uri(), which creates
            # missing tables and adds new columns via ALTER TABLE ADD COLUMN.
            # initialize_active_experiment_databases() iterates the Exps table,
            # re-registers each active experiment's DB URI and runs that function
            # against it, exactly as the old manual migration runner did.
            print("✦ Alembic: migrating active experiment databases…")
            try:
                from y_web.src.experiment.context import (
                    initialize_active_experiment_databases,
                )

                initialize_active_experiment_databases(app)
                print("✓ Alembic: experiment databases up to date")
            except Exception as _exp_err:
                print(f"⚠ Warning: failed to migrate experiment databases: {_exp_err}")
    except ImportError:
        # Flask-Migrate not installed — try standalone Alembic, then legacy runner.
        try:
            from alembic import command as _alembic_cmd
            from alembic.config import Config as _AlembicConfig
            from alembic.runtime.migration import MigrationContext as _MigCtx
            from alembic.script import ScriptDirectory as _AlembicScript

            with app.app_context():
                _sa_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
                _sa_cfg = _AlembicConfig()
                _sa_cfg.set_main_option("script_location", _alembic_dir)
                _sa_cfg.set_main_option("sqlalchemy.url", _sa_url)
                _sa_script = _AlembicScript.from_config(_sa_cfg)

                def _stamp_if_needed(engine, bind_key):
                    with engine.begin() as _conn:
                        _ctx = _MigCtx.configure(_conn)
                        if not _ctx.get_current_heads():
                            print(
                                f"  ↳ [{bind_key}] no alembic_version — stamping 0001_baseline"
                            )
                            _ctx.stamp(_sa_script, "0001_baseline")
                        else:
                            print(
                                f"  ↳ [{bind_key}] alembic_version OK ({', '.join(_ctx.get_current_heads())})"
                            )

                print("✦ Alembic (standalone): checking bound databases…")
                _seen: set = set()
                for _bk, _eng in db.engines.items():
                    if id(_eng) not in _seen:
                        _seen.add(id(_eng))
                        _stamp_if_needed(_eng, _bk)

                print("✦ Alembic (standalone): upgrading primary schema to HEAD…")
                _alembic_cmd.upgrade(_sa_cfg, "head")
                print("✓ Alembic (standalone): primary schema up to date")
                _repair_legacy_columns(app)

                try:
                    from y_web.src.experiment.context import (
                        initialize_active_experiment_databases,
                    )

                    initialize_active_experiment_databases(app)
                    print("✓ Alembic (standalone): experiment databases up to date")
                except Exception as _exp_err:
                    print(
                        f"⚠ Warning: failed to migrate experiment databases: {_exp_err}"
                    )

        except ImportError:
            # Neither Flask-Migrate nor standalone Alembic available.
            # Fall back to manual migration runner.
            # Install with: pip install Flask-Migrate>=4.0.0
            from y_web.db_init.migrations import run_migrations

            run_migrations(app, db_type, db)
