"""
Desktop File Handler - Utility for handling file downloads in desktop mode.

This module provides utilities for handling file downloads when running in
PyInstaller desktop mode with PyWebview. It uses PyWebview's API to expose
download functionality to JavaScript, allowing proper file save dialogs.
"""

import base64
import os
import shutil
from functools import wraps
from typing import Optional

from flask import Response, current_app, jsonify, send_file


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

    In desktop mode with PyWebview, we return a special HTML page that uses
    PyWebview's file dialog API. In browser mode, it behaves like standard send_file.

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

    # Desktop mode with attachment - create download page
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

    # Read the file and encode it
    try:
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        
        # Determine MIME type
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
        
        # Create HTML that uses pywebview API to save the file
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Downloading {default_filename}</title>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                }}
                .container {{
                    text-align: center;
                    padding: 40px;
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .spinner {{
                    border: 4px solid #f3f3f3;
                    border-top: 4px solid #3498db;
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
                button {{
                    margin-top: 20px;
                    padding: 10px 20px;
                    font-size: 14px;
                    cursor: pointer;
                    background: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                }}
                button:hover {{
                    background: #2980b9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div id="status">
                    <div class="spinner"></div>
                    <p>Preparing download...</p>
                </div>
                <button onclick="goBack()" id="backBtn" style="display:none;">Go Back</button>
            </div>
            <script>
                function goBack() {{
                    window.history.back();
                }}
                
                function saveFile() {{
                    try {{
                        // Use pywebview API to show save dialog and save file
                        if (window.pywebview && window.pywebview.api) {{
                            window.pywebview.api.save_file_dialog(
                                '{default_filename}',
                                '{encoded_content}',
                                '{mime_type}'
                            ).then(function(result) {{
                                console.log('Save file dialog result:', result);
                                if (result && result.success === true) {{
                                    document.getElementById('status').innerHTML = 
                                        '<p style="color: green;">✓ File saved successfully!</p>';
                                    document.getElementById('backBtn').style.display = 'inline-block';
                                    setTimeout(goBack, 1500);
                                }} else if (result && result.error === 'Cancelled') {{
                                    document.getElementById('status').innerHTML = 
                                        '<p style="color: orange;">Download cancelled.</p>';
                                    document.getElementById('backBtn').style.display = 'inline-block';
                                }} else {{
                                    document.getElementById('status').innerHTML = 
                                        '<p style="color: red;">Error: ' + (result ? result.error : 'Unknown error') + '</p>';
                                    document.getElementById('backBtn').style.display = 'inline-block';
                                }}
                            }}).catch(function(error) {{
                                console.error('Download error:', error);
                                document.getElementById('status').innerHTML = 
                                    '<p style="color: red;">Error: ' + error + '</p>';
                                document.getElementById('backBtn').style.display = 'inline-block';
                            }});
                        }} else {{
                            // Fallback: trigger standard download
                            const base64Data = '{encoded_content}';
                            const binaryString = atob(base64Data);
                            const bytes = new Uint8Array(binaryString.length);
                            for (let i = 0; i < binaryString.length; i++) {{
                                bytes[i] = binaryString.charCodeAt(i);
                            }}
                            
                            const blob = new Blob([bytes], {{ type: '{mime_type}' }});
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = '{default_filename}';
                            document.body.appendChild(a);
                            a.click();
                            
                            setTimeout(function() {{
                                URL.revokeObjectURL(url);
                                document.body.removeChild(a);
                                document.getElementById('status').innerHTML = 
                                    '<p style="color: green;">✓ Download started!</p>';
                                document.getElementById('backBtn').style.display = 'inline-block';
                                setTimeout(goBack, 1500);
                            }}, 100);
                        }}
                    }} catch(e) {{
                        console.error('Download error:', e);
                        document.getElementById('status').innerHTML = 
                            '<p style="color: red;">Error: ' + e.message + '</p>';
                        document.getElementById('backBtn').style.display = 'inline-block';
                    }}
                }}
                
                // Start download when page loads
                window.addEventListener('load', function() {{
                    setTimeout(saveFile, 500);
                }});
            </script>
        </body>
        </html>
        """
        
        return Response(html, mimetype="text/html")
        
    except Exception as e:
        print(f"Error preparing download: {e}")
        return Response(
            f"""
            <!DOCTYPE html>
            <html>
            <head><title>Download Error</title></head>
            <body>
                <p>Error preparing download: {str(e)}</p>
                <p><a href="javascript:history.back()">Go back</a></p>
            </body>
            </html>
            """,
            mimetype="text/html"
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
