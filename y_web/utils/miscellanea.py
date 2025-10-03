"""
Miscellaneous utility functions.

Provides helper functions for privilege checking, user session management,
database connection testing, and Ollama LLM service status checking.
"""

from flask import redirect, url_for
from flask_login import login_user

from y_web import db
from y_web.models import (
    Admin_users,
    User_mgmt,
)
from y_web.utils import (
    is_ollama_installed,
    is_ollama_running,
    is_vllm_installed,
    is_vllm_running,
)


def check_privileges(username):
    """
    Verify if a user has admin privileges.

    Args:
        username: Username to check privileges for

    Returns:
        Redirect to main.index if not admin, None if admin
    """
    user = Admin_users.query.filter_by(username=username).first()

    if user.role != "admin":
        return redirect(url_for("main.index"))
    return


def reload_current_user(username):
    """
    Reload and re-authenticate the current user session.

    Args:
        username: Username to reload session for
    """
    user = db.session.query(User_mgmt).filter_by(username=username).first()
    login_user(user, remember=True, force=True)


def ollama_status():
    """
    Check Ollama LLM service status.

    Returns:
        Dictionary with 'status' (running) and 'installed' boolean flags
    """
    return {
        "status": is_ollama_running(),
        "installed": is_ollama_installed(),
    }


def llm_backend_status():
    """
    Check LLM backend service status based on LLM_BACKEND environment variable.

    Returns:
        Dictionary with 'backend' (ollama/vllm), 'status' (running), and 'installed' boolean flags
    """
    import os
    
    backend = os.getenv("LLM_BACKEND", "ollama")
    
    if backend == "vllm":
        return {
            "backend": "vllm",
            "status": is_vllm_running(),
            "installed": is_vllm_installed(),
        }
    else:  # ollama
        return {
            "backend": "ollama",
            "status": is_ollama_running(),
            "installed": is_ollama_installed(),
        }


def check_connection():
    """
    Test database connection.

    Returns:
        True if database is accessible, False otherwise
    """
    try:
        db.engine.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        return False


def get_db_type():
    """
    Get the type of database being used.

    Returns:
        String: "postgresql" or "sqlite"

    Raises:
        ValueError: If database type is not supported
    """
    db_uri = db.get_engine().url
    if db_uri.drivername == "postgresql":
        return "postgresql"
    elif db_uri.drivername == "sqlite":
        return "sqlite"
    else:
        raise ValueError(f"Unsupported database type: {db_uri.drivername}")


def get_db_port():
    """
    Get the database server port.

    Returns:
        Integer port number for PostgreSQL (default 5432), None for SQLite

    Raises:
        ValueError: If database type is not supported
    """
    db_uri = db.get_engine().url
    if db_uri.drivername == "postgresql":
        return db_uri.port or 5432  # Default PostgreSQL port
    elif db_uri.drivername == "sqlite":
        return None  # SQLite does not use a port
    else:
        raise ValueError(f"Unsupported database type: {db_uri.drivername}")


def get_db_server():
    """
    Get the database server hostname.

    Returns:
        String hostname for PostgreSQL (default "localhost"), None for SQLite

    Raises:
        ValueError: If database type is not supported
    """
    db_uri = db.get_engine().url
    if db_uri.drivername == "postgresql":
        return (
            db_uri.host or "localhost"
        )  # Default to localhost if no host is specified
    elif db_uri.drivername == "sqlite":
        return None  # SQLite does not use a server
    else:
        raise ValueError(f"Unsupported database type: {db_uri.drivername}")
