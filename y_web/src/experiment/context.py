"""
Experiment Context Management.

This module handles dynamic database binding for multiple active experiments.
It provides utilities to register, access, and switch between experiment databases.
"""

import os
from contextlib import contextmanager

from flask import current_app, g, request

from y_web import db


def get_db_bind_key_for_exp(exp_id):
    """
    Get the database bind key for a specific experiment.

    Args:
        exp_id: Experiment ID

    Returns:
        Database bind key string (e.g., 'db_exp_5')
    """
    if exp_id is None:
        return "db_exp"  # Fallback to legacy single experiment bind
    return f"db_exp_{exp_id}"


def register_experiment_database(app, exp_id, db_name):
    """
    Register an experiment database in the app's SQLALCHEMY_BINDS.

    Args:
        app: Flask application instance
        exp_id: Experiment ID
        db_name: Database name or path (e.g., "experiments/uid/database_server.db")
    """
    bind_key = get_db_bind_key_for_exp(exp_id)

    # Use get_writable_path to handle both development and PyInstaller modes
    from y_web.src.system.path_utils import get_writable_path

    # Check database type
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        # PostgreSQL: construct full URI
        base_uri = app.config["SQLALCHEMY_DATABASE_URI"].rsplit("/", 1)[0]
        db_uri = f"{base_uri}/{db_name}"
    elif app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        # SQLite: construct file path
        # db_name is stored as "experiments/uid/database_server.db"
        # but actual file is in "y_web/experiments/uid/database_server.db"
        # Prepend y_web/ to match actual file location
        db_path = get_writable_path(os.path.join("y_web", db_name))
        db_uri = f"sqlite:///{db_path}"
    else:
        raise ValueError("Unsupported database type")

    from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

    ensure_experiment_schema_for_uri(db_uri)

    # Add to binds with experiment-specific key
    app.config["SQLALCHEMY_BINDS"][bind_key] = db_uri


def _activate_db_exp_bind(exp_id):
    """Point the shared ``db_exp`` bind at the database for ``exp_id``.

    Flask-SQLAlchemy caches engines per bind key. Updating only
    ``SQLALCHEMY_BINDS`` is not enough because the already-created ``db_exp``
    engine may still reference the legacy dummy database. This helper refreshes
    both the bind URI and the cached engine so experiment-scoped ORM queries are
    executed against the selected experiment database.
    """

    from y_web.src.models import Exps

    bind_key = get_db_bind_key_for_exp(exp_id)
    if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
        exp = Exps.query.filter_by(idexp=exp_id).first()
        if exp is not None:
            register_experiment_database(current_app, exp_id, exp.db_name)

    binds = current_app.config["SQLALCHEMY_BINDS"]
    target_uri = binds.get(bind_key)
    original_bind = binds.get("db_exp")
    original_engine = db.engines.get("db_exp")

    if not target_uri:
        return original_bind, original_engine, None

    from y_web.src.experiment.schema import ensure_experiment_schema_for_uri

    ensure_experiment_schema_for_uri(target_uri)

    binds["db_exp"] = target_uri
    db.session.remove()
    engine_options = dict(db._engine_options)
    engine_options["url"] = target_uri
    refreshed_engine = db._make_engine("db_exp", engine_options, current_app)
    db.engines["db_exp"] = refreshed_engine
    return original_bind, original_engine, refreshed_engine


def _restore_db_exp_bind(original_bind, original_engine, refreshed_engine=None):
    """Restore the shared ``db_exp`` bind after a temporary override."""

    binds = current_app.config["SQLALCHEMY_BINDS"]
    if original_bind is not None:
        binds["db_exp"] = original_bind
    else:
        binds.pop("db_exp", None)

    db.session.remove()
    if original_engine is not None:
        db.engines["db_exp"] = original_engine
    else:
        db.engines.pop("db_exp", None)

    if refreshed_engine is not None and refreshed_engine is not original_engine:
        refreshed_engine.dispose()


def get_active_experiments():
    """
    Get all currently active experiments.

    Returns:
        List of Exps objects with status=1
    """
    from y_web.src.models import Exps

    return Exps.query.filter_by(status=1).all()


def setup_experiment_context():
    """
    Setup experiment context from the current request URL.

    This should be called in a before_request handler to extract
    the exp_id from the URL and set up the appropriate database binding.

    Dynamically routes queries to the correct experiment database by
    temporarily overriding the db_exp bind for this request.
    """
    # Extract exp_id from URL if present
    exp_id = request.view_args.get("exp_id") if request.view_args else None

    if exp_id:
        g.current_exp_id = exp_id
        bind_key = get_db_bind_key_for_exp(exp_id)

        # Verify the bind exists
        if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
            # Bind doesn't exist, need to register it
            from y_web.src.models import Exps

            # Bind the explicit experiment referenced by the route even if it is not
            # currently active, so direct admin/forum routes never fall back to the
            # legacy dummy bind.
            exp = Exps.query.filter_by(idexp=exp_id).first()
            if exp:
                register_experiment_database(current_app, exp_id, exp.db_name)

        g.current_db_bind = bind_key

        # Store the original db_exp bind so we can restore it later.
        if not hasattr(g, "original_db_exp_bind"):
            g.original_db_exp_bind = current_app.config["SQLALCHEMY_BINDS"].get(
                "db_exp"
            )
        if not hasattr(g, "original_db_exp_engine"):
            g.original_db_exp_engine = db.engines.get("db_exp")

        # Dynamically override db_exp bind and cached engine to point to the
        # current experiment's database.
        original_bind, original_engine, refreshed_engine = _activate_db_exp_bind(
            exp_id
        )
        if not hasattr(g, "original_db_exp_bind"):
            g.original_db_exp_bind = original_bind
        if not hasattr(g, "original_db_exp_engine"):
            g.original_db_exp_engine = original_engine
        g.current_db_exp_engine = refreshed_engine
    else:
        # No exp_id in URL, fall back to legacy behavior
        g.current_exp_id = None
        g.current_db_bind = "db_exp"


def get_current_experiment_bind():
    """
    Get the database bind key for the current request context.

    Returns:
        Database bind key string
    """
    return getattr(g, "current_db_bind", "db_exp")


def get_current_experiment_id():
    """
    Get the experiment ID for the current request context.

    Returns:
        Experiment ID or None
    """
    return getattr(g, "current_exp_id", None)


def teardown_experiment_context(exception=None):
    """
    Restore the original db_exp bind after the request completes.

    This should be called in a teardown_request handler to ensure
    the db_exp bind is restored to its original state after each request.

    Args:
        exception: Exception that occurred during request processing, if any
    """
    # Restore original db_exp bind if it was modified
    if hasattr(g, "original_db_exp_bind") or hasattr(g, "original_db_exp_engine"):
        _restore_db_exp_bind(
            getattr(g, "original_db_exp_bind", None),
            getattr(g, "original_db_exp_engine", None),
            getattr(g, "current_db_exp_engine", None),
        )


@contextmanager
def experiment_db_bind(exp_id):
    """Temporarily point ``db_exp`` at the database for ``exp_id``.

    The application already keeps a request-level bind through
    ``setup_experiment_context()``, but some feed paths build multiple query
    batches and can observe the wrong bind when other requests are active in
    parallel.  Wrapping the full rendering path keeps the feed data source
    stable for the duration of the request without changing callers.
    """

    if exp_id is None:
        yield
        return

    original_bind, original_engine, refreshed_engine = _activate_db_exp_bind(exp_id)

    try:
        yield
    finally:
        _restore_db_exp_bind(original_bind, original_engine, refreshed_engine)


def initialize_active_experiment_databases(app):
    """
    Initialize database bindings for all currently active experiments.

    This should be called during application startup to register
    all active experiment databases.

    Args:
        app: Flask application instance
    """
    with app.app_context():
        from y_web.src.models import Exps

        active_experiments = Exps.query.filter_by(status=1).all()

        for exp in active_experiments:
            register_experiment_database(app, exp.idexp, exp.db_name)
