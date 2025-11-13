"""
Desktop File Handler - Utility for handling file downloads in desktop mode.

This module provides utilities for handling file downloads when running in
PyInstaller desktop mode with PyWebview. PyWebview automatically handles
file downloads with native save dialogs when Flask sends files with
Content-Disposition: attachment headers.
"""

import os
from functools import wraps
from typing import Optional

from flask import Response, current_app, send_file


def is_desktop_mode() -> bool:
    """
    Check if the application is running in desktop mode.

    Returns:
        True if running in desktop mode with PyWebview, False otherwise
    """
    return current_app.config.get("DESKTOP_MODE", False)


def get_webview_window():
    """
    Get the PyWebview window instance if available.

    Returns:
        PyWebview Window instance or None
    """
    # First try to get from app config (set in before_request)
    window = current_app.config.get("WEBVIEW_WINDOW", None)
    if window:
        return window

    # If not in config, try to get directly from desktop module
    try:
        from y_web.pyinstaller_utils.y_social_desktop import get_desktop_window

        return get_desktop_window()
    except ImportError:
        return None


def send_file_desktop(
    path_or_file,
    mimetype=None,
    as_attachment=False,
    download_name=None,
    conditional=True,
    etag=True,
    last_modified=None,
    max_age=None,
    **kwargs,
):
    """
    Enhanced send_file function that handles desktop mode file downloads.

    This function wraps Flask's send_file. In desktop mode, it uses standard
    Flask send_file with proper headers so PyWebview can handle the download
    naturally. In browser mode, it behaves exactly like send_file.

    Args:
        Same as Flask's send_file function

    Returns:
        Flask Response object
    """
    # In desktop mode, still use standard send_file but ensure proper headers
    # PyWebview will handle the download dialog based on Content-Disposition header
    return send_file(
        path_or_file,
        mimetype=mimetype,
        as_attachment=as_attachment,
        download_name=download_name,
        conditional=conditional,
        etag=etag,
        last_modified=last_modified,
        max_age=max_age,
        **kwargs,
    )


def desktop_aware_route(f):
    """
    Decorator to make download routes desktop-aware.

    This decorator can be used on Flask routes that return send_file responses
    to automatically handle desktop mode save dialogs.

    Usage:
        @app.route('/download')
        @desktop_aware_route
        def download():
            return send_file(path, as_attachment=True)
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = f(*args, **kwargs)
        # The route should already use send_file_desktop instead of send_file
        # This decorator is here for future extensibility
        return response

    return decorated_function
