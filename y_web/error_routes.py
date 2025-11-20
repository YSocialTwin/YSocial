"""
Error handling routes and handlers.

Provides centralized error handling for the Y Social application,
including custom error pages for common HTTP errors (400, 403, 404, 500).
"""

import traceback

from flask import Blueprint, render_template, request
from flask_login import current_user

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
    error_details = {
        "status_code": 400,
        "error_name": "Bad Request",
        "error_description": (
            str(e)
            if str(e)
            != "400 Bad Request: The browser (or proxy) sent a request that this server could not understand."
            else "The server could not understand the request due to invalid syntax."
        ),
        "requested_url": request.url if request else None,
        "method": request.method if request else None,
    }

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)

    # Capture full traceback as string
    full_trace = traceback.format_exc()
    telemetry.log_stack_trace(
        {
            "error_type": "400 Bad Request",
            "stacktrace": full_trace,
            "url": request.url,
            "method": request.method,
        }
    )

    return render_template("error_pages/400.html", error=error_details), 400


@errors.app_errorhandler(403)
def forbidden(e):
    """
    Handle 403 Forbidden errors.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 403 template, 403 status code)
    """
    error_details = {
        "status_code": 403,
        "error_name": "Forbidden",
        "error_description": (
            str(e)
            if str(e)
            != "403 Forbidden: You don't have the permission to access the requested resource. It is either read-protected or not readable by the server."
            else "You don't have permission to access this resource."
        ),
        "requested_url": request.url if request else None,
        "method": request.method if request else None,
    }

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)

    # Capture full traceback as string
    full_trace = traceback.format_exc()
    telemetry.log_stack_trace(
        {
            "error_type": "403 Forbidden",
            "stacktrace": full_trace,
            "url": request.url,
            "method": request.method,
        }
    )

    return render_template("error_pages/403.html", error=error_details), 403


@errors.app_errorhandler(404)
def not_found(e):
    """
    Handle 404 Not Found errors.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 404 template, 404 status code)
    """
    error_details = {
        "status_code": 404,
        "error_name": "Not Found",
        "error_description": (
            str(e)
            if str(e)
            != "404 Not Found: The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again."
            else "The requested page could not be found."
        ),
        "requested_url": request.url if request else None,
        "method": request.method if request else None,
    }

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)

    # Capture full traceback as string
    full_trace = traceback.format_exc()
    telemetry.log_stack_trace(
        {
            "error_type": "404 Not Found",
            "stacktrace": full_trace,
            "url": request.url,
            "method": request.method,
        }
    )

    return render_template("error_pages/404.html", error=error_details), 404


@errors.app_errorhandler(500)
def internal_server_error(e):
    """
    Handle 500 Internal Server Error.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 500 template, 500 status code)
    """
    error_details = {
        "status_code": 500,
        "error_name": "Internal Server Error",
        "error_description": (
            str(e)
            if str(e)
            != "500 Internal Server Error: The server encountered an internal error and was unable to complete your request. Either the server is overloaded or there is an error in the application."
            else "The server encountered an unexpected condition."
        ),
        "requested_url": request.url if request else None,
        "method": request.method if request else None,
    }

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)

    # Capture full traceback as string
    full_trace = traceback.format_exc()
    telemetry.log_stack_trace(
        {
            "error_type": "500 Internal Server Error",
            "stacktrace": full_trace,
            "url": request.url,
            "method": request.method,
        }
    )
    return render_template("error_pages/500.html", error=error_details), 500
