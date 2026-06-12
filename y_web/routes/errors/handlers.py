"""
Error handling routes and handlers.

Provides centralized error handling for the Y Social application,
including custom error pages for common HTTP errors (400, 403, 404, 500).
"""

import traceback

from flask import render_template, request
from flask_login import current_user

from y_web.routes.errors._blueprint import errors


def _build_error_details(status_code: int, error_name: str, e):
    raw_description = str(e) if e is not None else ""
    default_messages = {
        400: "The server could not understand the request due to invalid syntax.",
        403: "You don't have permission to access this resource.",
        404: "The requested page could not be found.",
        500: "The server encountered an unexpected condition.",
    }
    generic_message = default_messages.get(status_code, "Unexpected error.")
    if raw_description and raw_description not in {
        "400 Bad Request: The browser (or proxy) sent a request that this server could not understand.",
        "403 Forbidden: You don't have the permission to access the requested resource. It is either read-protected or not readable by the server.",
        "404 Not Found: The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.",
        "500 Internal Server Error: The server encountered an internal error and was unable to complete your request. Either the server is overloaded or there is an error in the application.",
    }:
        description = raw_description
    else:
        description = generic_message

    traceback_lines = []
    try:
        traceback_lines = traceback.format_exception(
            type(e), e, getattr(e, "__traceback__", None)
        )
    except Exception:
        traceback_lines = []
    traceback_text = "".join(traceback_lines).strip() or traceback.format_exc().strip()
    traceback_excerpt = "\n".join(traceback_text.splitlines()[-12:]) if traceback_text else ""

    return {
        "status_code": status_code,
        "error_name": error_name,
        "error_description": description,
        "requested_url": request.url if request else None,
        "method": request.method if request else None,
        "path": request.path if request else None,
        "endpoint": request.endpoint if request else None,
        "view_args": dict(request.view_args or {}) if request and request.view_args else {},
        "exception_class": type(e).__name__ if e is not None else None,
        "traceback_excerpt": traceback_excerpt,
    }


@errors.app_errorhandler(400)
def bad_request(e):
    """
    Handle 400 Bad Request errors.

    Args:
        e: Error object

    Returns:
        Tuple of (rendered 400 template, 400 status code)
    """
    error_details = _build_error_details(400, "Bad Request", e)

    from y_web.src.telemetry import Telemetry

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
    error_details = _build_error_details(403, "Forbidden", e)

    from y_web.src.telemetry import Telemetry

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
    error_details = _build_error_details(404, "Not Found", e)

    from y_web.src.telemetry import Telemetry

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
    error_details = _build_error_details(500, "Internal Server Error", e)

    from y_web.src.telemetry import Telemetry

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
