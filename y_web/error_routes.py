"""
Error handling routes and handlers.

Provides centralized error handling for the Y Social application,
including custom error pages for common HTTP errors (400, 403, 404, 500).
"""

from flask import Blueprint, render_template

errors = Blueprint("errors", __name__)


@errors.app_errorhandler(400)
def bad_request(e):
    """
    Handle 400 Bad Request errors.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 400 template, 400 status code)
    """
    return render_template("error_pages/400.html"), 400


@errors.app_errorhandler(403)
def forbidden(e):
    """
    Handle 403 Forbidden errors.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 403 template, 403 status code)
    """
    return render_template("error_pages/403.html"), 403


@errors.app_errorhandler(404)
def not_found(e):
    """
    Handle 404 Not Found errors.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 404 template, 404 status code)
    """
    return render_template("error_pages/404.html"), 404


@errors.app_errorhandler(500)
def internal_server_error(e):
    """
    Handle 500 Internal Server Error.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 500 template, 500 status code)
    """
    return render_template("error_pages/500.html"), 500
