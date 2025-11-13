"""
Desktop File Handler - Utility for handling file downloads in desktop mode.

This module provides utilities for handling file downloads when running in
PyInstaller desktop mode with PyWebview. It integrates with Flask's send_file
to provide native save dialogs instead of browser downloads.
"""

import base64
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


def desktop_download_file(
    file_path: str, default_filename: Optional[str] = None
) -> str:
    """
    Prepare file for download in desktop mode using JavaScript blob download.
    
    This function reads the file and returns an HTML page with JavaScript that
    triggers a browser download using a Blob. This approach works reliably in
    PyWebview without threading issues.
    
    Args:
        file_path: Path to the file to be downloaded
        default_filename: Filename to use for the download
        
    Returns:
        HTML string with embedded JavaScript that triggers the download
    """
    # Use the filename from the path if not provided
    if default_filename is None:
        default_filename = os.path.basename(file_path)
    
    try:
        # Read the file content
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Base64 encode the content for embedding in HTML
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        
        # Determine MIME type based on file extension
        _, ext = os.path.splitext(default_filename)
        mime_type = 'application/octet-stream'
        if ext.lower() == '.json':
            mime_type = 'application/json'
        elif ext.lower() == '.csv':
            mime_type = 'text/csv'
        elif ext.lower() == '.zip':
            mime_type = 'application/zip'
        elif ext.lower() == '.txt':
            mime_type = 'text/plain'
        
        # Create HTML with JavaScript that triggers download
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Downloading {default_filename}</title>
            <meta charset="utf-8">
        </head>
        <body>
            <p>Preparing download...</p>
            <script>
                (function() {{
                    try {{
                        // Decode base64 to binary
                        const base64Data = '{encoded_content}';
                        const binaryString = atob(base64Data);
                        const bytes = new Uint8Array(binaryString.length);
                        for (let i = 0; i < binaryString.length; i++) {{
                            bytes[i] = binaryString.charCodeAt(i);
                        }}
                        
                        // Create blob and download
                        const blob = new Blob([bytes], {{ type: '{mime_type}' }});
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = '{default_filename}';
                        document.body.appendChild(a);
                        a.click();
                        
                        // Clean up
                        setTimeout(function() {{
                            URL.revokeObjectURL(url);
                            document.body.removeChild(a);
                            // Go back after download starts
                            window.history.back();
                        }}, 100);
                    }} catch(e) {{
                        console.error('Download error:', e);
                        document.body.innerHTML = '<p>Error downloading file. <a href="javascript:history.back()">Go back</a></p>';
                    }}
                }})();
            </script>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        print(f"Error preparing file for download: {e}")
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Download Error</title></head>
        <body>
            <p>Error preparing download: {str(e)}</p>
            <p><a href="javascript:history.back()">Go back</a></p>
        </body>
        </html>
        """


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

    This function wraps Flask's send_file to provide JavaScript-based downloads
    when running in desktop mode. In browser mode, it behaves exactly like send_file.

    When in desktop mode and as_attachment=True:
    - Returns an HTML page with JavaScript that triggers a blob download
    - The browser/webview handles the save dialog naturally
    - Works reliably without threading issues

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

    # Desktop mode - use JavaScript blob download
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

    # Generate the HTML page with JavaScript download
    html_content = desktop_download_file(file_path, default_filename)
    
    return Response(html_content, mimetype="text/html")


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
