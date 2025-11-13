"""
Desktop File Handler - Utility for handling file downloads in desktop mode.

This module provides utilities for handling file downloads when running in
PyInstaller desktop mode with PyWebview. It integrates with Flask's send_file
to provide native save dialogs instead of browser downloads.
"""

import os
import shutil
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


def desktop_save_file(
    file_path: str, default_filename: Optional[str] = None, file_types: tuple = ()
) -> bool:
    """
    Open a system save dialog and save the file to the selected location.

    This function uses PyWebview's create_file_dialog to show a native save dialog,
    allowing the user to choose where to save the downloaded file.

    Args:
        file_path: Path to the file to be saved
        default_filename: Default filename to suggest in the save dialog
        file_types: Tuple of allowed file types in format ('Description (*.ext)', ...)

    Returns:
        True if file was saved successfully, False if cancelled or error occurred
    """
    window = get_webview_window()
    if not window:
        return False

    # Use the filename from the path if not provided
    if default_filename is None:
        default_filename = os.path.basename(file_path)

    try:
        # Import FileDialog enum from webview
        import webview

        # Show save dialog - returns tuple of selected paths or None if cancelled
        result = window.create_file_dialog(
            dialog_type=webview.FileDialog.SAVE,
            save_filename=default_filename,
            file_types=file_types,
        )

        # If user cancelled, return False
        if not result:
            return False

        # Get the selected save path (first element of tuple)
        save_path = result[0]

        # Copy the file to the selected location
        shutil.copy2(file_path, save_path)

        return True
    except Exception as e:
        print(f"Error saving file in desktop mode: {e}")
        return False


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
    Enhanced send_file function that handles desktop mode file dialogs.

    This function wraps Flask's send_file to provide native save dialogs when
    running in desktop mode. In browser mode, it behaves exactly like send_file.

    When in desktop mode and as_attachment=True:
    - Opens a native system save dialog
    - User selects where to save the file
    - File is copied to the selected location
    - Returns a JSON response indicating success or cancellation

    Args:
        Same as Flask's send_file function

    Returns:
        Flask Response object
    """
    # If not in desktop mode or not an attachment, use standard send_file
    if not is_desktop_mode() or not as_attachment:
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

    # Desktop mode - show save dialog
    # Convert path_or_file to string path if needed
    if isinstance(path_or_file, str):
        file_path = path_or_file
    else:
        # If it's a file object, we need to get its name
        file_path = getattr(path_or_file, "name", None)
        if not file_path:
            # Can't handle file objects without a name in desktop mode
            # Fall back to standard send_file
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

    # Determine the default filename
    if download_name:
        default_filename = download_name
    else:
        default_filename = os.path.basename(file_path)

    # Determine file types filter based on file extension
    file_types = ()
    _, ext = os.path.splitext(default_filename)
    if ext:
        # Create a file type filter like "JSON Files (*.json)"
        ext_upper = ext[1:].upper()  # Remove the dot and uppercase
        file_types = (f"{ext_upper} Files (*{ext})",)

    # Show the save dialog and copy the file
    success = desktop_save_file(file_path, default_filename, file_types)

    # Return a response indicating success or cancellation
    # Use a simple HTML response with JavaScript to close or go back
    if success:
        return Response(
            """
            <html>
                <head><title>Download Complete</title></head>
                <body>
                    <script>
                        alert('File saved successfully!');
                        window.history.back();
                    </script>
                    <p>File saved successfully! <a href="javascript:history.back()">Go back</a></p>
                </body>
            </html>
            """,
            mimetype="text/html",
        )
    else:
        return Response(
            """
            <html>
                <head><title>Download Cancelled</title></head>
                <body>
                    <script>
                        window.history.back();
                    </script>
                    <p>Download cancelled. <a href="javascript:history.back()">Go back</a></p>
                </body>
            </html>
            """,
            mimetype="text/html",
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
