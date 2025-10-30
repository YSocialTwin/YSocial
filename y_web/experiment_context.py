"""
Experiment Context Management.

This module handles dynamic database binding for multiple active experiments.
It provides utilities to register, access, and switch between experiment databases.
"""

import os
from flask import g, current_app, request
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
        db_name: Database name or path
    """
    bind_key = get_db_bind_key_for_exp(exp_id)
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # Check database type
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        # PostgreSQL: construct full URI
        base_uri = app.config["SQLALCHEMY_DATABASE_URI"].rsplit("/", 1)[0]
        db_uri = f"{base_uri}/{db_name}"
    elif app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        # SQLite: construct file path
        db_uri = f"sqlite:///{BASE_DIR}/{db_name}"
    else:
        raise ValueError("Unsupported database type")
    
    # Add to binds
    app.config["SQLALCHEMY_BINDS"][bind_key] = db_uri
    
    # Also update the legacy db_exp bind to point to this experiment
    # This maintains backward compatibility with existing code
    app.config["SQLALCHEMY_BINDS"]["db_exp"] = db_uri


def get_active_experiments():
    """
    Get all currently active experiments.

    Returns:
        List of Exps objects with status=1
    """
    from y_web.models import Exps
    return Exps.query.filter_by(status=1).all()


def setup_experiment_context():
    """
    Setup experiment context from the current request URL.
    
    This should be called in a before_request handler to extract
    the exp_id from the URL and set up the appropriate database binding.
    """
    # Extract exp_id from URL if present
    exp_id = request.view_args.get('exp_id') if request.view_args else None
    
    if exp_id:
        g.current_exp_id = exp_id
        bind_key = get_db_bind_key_for_exp(exp_id)
        
        # Verify the bind exists
        if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
            # Bind doesn't exist, need to register it
            from y_web.models import Exps
            exp = Exps.query.filter_by(idexp=exp_id, status=1).first()
            if exp:
                register_experiment_database(current_app, exp_id, exp.db_name)
        
        g.current_db_bind = bind_key
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
    return getattr(g, 'current_db_bind', 'db_exp')


def get_current_experiment_id():
    """
    Get the experiment ID for the current request context.

    Returns:
        Experiment ID or None
    """
    return getattr(g, 'current_exp_id', None)


def initialize_active_experiment_databases(app):
    """
    Initialize database bindings for all currently active experiments.
    
    This should be called during application startup to register
    all active experiment databases.

    Args:
        app: Flask application instance
    """
    with app.app_context():
        from y_web.models import Exps
        active_experiments = Exps.query.filter_by(status=1).all()
        
        for exp in active_experiments:
            register_experiment_database(app, exp.idexp, exp.db_name)
