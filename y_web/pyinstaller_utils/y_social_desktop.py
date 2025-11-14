"""
YSocial Desktop Mode - Uses PyWebview for native desktop window experience.

This module provides a desktop application mode using PyWebview to display
the Flask application in a native window instead of a browser.
"""

import base64
import os
import sys
import threading
import time

import webview

# Global reference to the webview window for Flask app access
_webview_window = None


class DesktopAPI:
    """
    API class exposed to JavaScript in PyWebview.

    This allows JavaScript code in the webview to call Python functions,
    particularly for showing native file save dialogs.
    """

    def save_file_dialog(self, filename, base64_content, mime_type):
        """
        Show a native save file dialog and save the file.

        Args:
            filename: Default filename for the save dialog
            base64_content: Base64-encoded file content
            mime_type: MIME type of the file

        Returns:
            dict: {'success': True/False, 'path': saved_path or None, 'error': error message}
        """
        try:
            window = get_desktop_window()
            if not window:
                print("ERROR: Window not available")
                return {"success": False, "error": "Window not available", "path": None}

            # Show save file dialog
            # Note: On some platforms, if the user cancels the dialog,
            # it may return a tuple with an empty or invalid path like '\'
            result = window.create_file_dialog(
                dialog_type=webview.FileDialog.SAVE,
                save_filename=filename,
                directory="",  # Start in default directory
            )

            print(f"File dialog result: {result}")
            print(f"File dialog result type: {type(result)}")

            # Handle different return types from create_file_dialog
            # On macOS, it may return a string directly
            # On other platforms, it returns a tuple
            if not result:
                # User cancelled or empty result
                print("User cancelled file dialog (empty result)")
                return {"success": False, "error": "Cancelled", "path": None}

            # Extract the path from result
            if isinstance(result, str):
                # Result is a string directly (common on macOS)
                save_path = result
                print(f"Result is string: '{save_path}'")
            elif isinstance(result, (tuple, list)) and len(result) > 0:
                # Result is a tuple/list with path as first element
                save_path = result[0]
                print(f"Result is tuple/list, using first element: '{save_path}'")
            else:
                # Unexpected result format
                print(f"User cancelled or unexpected result format: {result}")
                return {"success": False, "error": "Cancelled", "path": None}

            print(f"Saving to: '{save_path}' (length: {len(save_path)})")

            # Validate the save path - check for invalid or empty paths
            if (
                not save_path
                or len(save_path) <= 1
                or save_path in ["\\", "/", ".", ".."]
            ):
                print(f"ERROR: Invalid or empty save path: '{save_path}'")
                # This likely means the dialog was cancelled or returned an invalid path
                return {"success": False, "error": "Cancelled", "path": None}

            # Check if the path is a directory instead of a file
            if os.path.isdir(save_path):
                print(f"ERROR: Path is a directory, not a file: '{save_path}'")
                return {
                    "success": False,
                    "error": "Selected path is a directory, not a file",
                    "path": None,
                }

            # Decode base64 content and save to file
            try:
                file_content = base64.b64decode(base64_content)
            except Exception as e:
                print(f"ERROR: Failed to decode base64 content: {e}")
                return {
                    "success": False,
                    "error": f"Failed to decode file content: {e}",
                    "path": None,
                }

            # Write the file
            try:
                # First check if parent directory exists
                parent_dir = os.path.dirname(save_path)
                if parent_dir and not os.path.exists(parent_dir):
                    print(f"ERROR: Parent directory does not exist: {parent_dir}")
                    return {
                        "success": False,
                        "error": f"Parent directory does not exist",
                        "path": None,
                    }

                # Try to open and write the file
                with open(save_path, "wb") as f:
                    f.write(file_content)
            except IsADirectoryError as e:
                print(f"ERROR: Path is a directory: {save_path}: {e}")
                return {
                    "success": False,
                    "error": f"Cannot save to directory: {save_path}",
                    "path": None,
                }
            except FileExistsError as e:
                print(f"ERROR: File already exists at {save_path}: {e}")
                return {
                    "success": False,
                    "error": f"File exists: {save_path}",
                    "path": None,
                }
            except PermissionError as e:
                print(f"ERROR: Permission denied: {save_path}: {e}")
                return {
                    "success": False,
                    "error": f"Permission denied: {save_path}",
                    "path": None,
                }
            except OSError as e:
                # OSError with errno 17 (EEXIST) can mean the path is a directory
                print(
                    f"ERROR: OS error writing file: {save_path}: {e} (errno: {e.errno})"
                )
                if e.errno == 17:  # EEXIST
                    return {
                        "success": False,
                        "error": f"Path exists and is a directory or has other conflict",
                        "path": None,
                    }
                return {"success": False, "error": f"OS error: {e}", "path": None}
            except Exception as e:
                print(f"ERROR: Failed to write file: {e}")
                return {
                    "success": False,
                    "error": f"Failed to write file: {e}",
                    "path": None,
                }

            print(f"File saved successfully to {save_path}")
            return {"success": True, "path": save_path, "error": None}

        except Exception as e:
            error_msg = str(e)
            print(f"ERROR saving file: {error_msg}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": error_msg, "path": None}


def check_webview_compatibility():
    """
    Check if webview can be used on this system.

    This function attempts to detect if the required GUI backend is available
    before actually starting the webview. This helps provide better error messages
    for systems where GTK or other backends are not available.

    Returns:
        tuple: (is_compatible, error_message)
    """
    try:
        # Try to detect the GUI backend that will be used
        # On Linux, this will typically try to load GTK
        # This is a simple check - the real test is webview.start()

        # Check if we're on Linux and can import gi (GTK bindings)
        if sys.platform.startswith("linux"):
            try:
                import gi

                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk

                return (True, None)
            except (ImportError, ValueError) as e:
                return (False, f"GTK bindings not available: {e}")

        # On other platforms, assume compatibility
        return (True, None)

    except Exception as e:
        return (False, str(e))


def get_desktop_window():
    """
    Get the current desktop window instance.

    Returns:
        PyWebview Window instance or None
    """
    return _webview_window


def set_desktop_window(window):
    """
    Set the current desktop window instance.

    Args:
        window: PyWebview Window instance
    """
    global _webview_window
    _webview_window = window


def start_desktop_app(
    db_type="sqlite",
    debug=False,
    host="localhost",
    port=8080,
    llm_backend=None,
    notebook=False,
    window_title="YSocial - Social Media Digital Twin",
    window_width=0,  # 0 means fullscreen
    window_height=0,  # 0 means fullscreen
):
    """
    Start YSocial in desktop mode with PyWebview.

    Args:
        db_type: Database type ('sqlite' or 'postgresql')
        debug: Enable Flask debug mode
        host: Host address for Flask server
        port: Port for Flask server
        llm_backend: LLM backend to use
        notebook: Enable Jupyter notebook support
        window_title: Title for the desktop window
        window_width: Width of the desktop window (0 for fullscreen)
        window_height: Height of the desktop window (0 for fullscreen)

    Raises:
        RuntimeError: If webview backend is not compatible with the system
    """
    # Check webview compatibility before starting Flask
    is_compatible, error_msg = check_webview_compatibility()
    if not is_compatible:
        raise RuntimeError(f"Webview not compatible: {error_msg}")

    from y_social import start_app

    # Start Flask in a background thread
    def run_flask():
        """Run Flask server in a separate thread."""
        start_app(
            db_type=db_type,
            debug=debug,
            host=host,
            port=port,
            llm_backend=llm_backend,
            notebook=notebook,
            desktop_mode=True,  # Enable desktop mode
        )

    # Start Flask server in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Wait for Flask to be ready
    url = f"http://{host}:{port}"
    max_wait = 30
    start_time = time.time()
    server_ready = False

    import socket

    while time.time() - start_time < max_wait:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(
                (host if host != "0.0.0.0" else "localhost", int(port))
            )
            sock.close()

            if result == 0:
                # Server is ready
                time.sleep(1)  # Wait a bit more for full initialization
                server_ready = True
                break
        except Exception:
            pass

        time.sleep(0.5)

    if not server_ready:
        print(f"Warning: Could not verify Flask server startup within {max_wait}s")
        print("The desktop window will open anyway, but the app may not be ready.")

    # Create and start the desktop window
    print(f"\n{'='*60}")
    print(f"Starting YSocial in Desktop Mode")
    print(f"📱 Opening native window for: {url}")
    print(f"{'='*60}\n")

    # Determine if fullscreen mode should be used
    use_fullscreen = window_width == 0 or window_height == 0

    # If fullscreen, use default size initially
    if use_fullscreen:
        window_width = 1280
        window_height = 800

    # Create a PyWebview window with API
    api = DesktopAPI()
    window = webview.create_window(
        title=window_title,
        url=url,
        width=window_width,
        height=window_height,
        resizable=True,
        fullscreen=use_fullscreen,
        min_size=(800, 600),
        confirm_close=True,
        js_api=api,  # Expose API to JavaScript
    )

    # Store window reference globally for Flask app access
    set_desktop_window(window)

    # Start the webview - this blocks until the window is closed
    webview.start(debug=debug)

    print("\nYSocial desktop window closed. Exiting...")


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser(description="YSocial Desktop Mode")

    parser.add_argument(
        "-x",
        "--host",
        default="localhost",
        help="Host address for Flask server (default: localhost)",
    )
    parser.add_argument(
        "-y", "--port", default="8080", help="Port for Flask server (default: 8080)"
    )
    parser.add_argument(
        "-d", "--debug", default=False, action="store_true", help="Enable debug mode"
    )
    parser.add_argument(
        "-D",
        "--db",
        choices=["sqlite", "postgresql"],
        default="sqlite",
        help="Database type (default: sqlite)",
    )
    parser.add_argument(
        "-l",
        "--llm-backend",
        default=None,
        help="LLM backend to use: 'ollama', 'vllm', or custom URL (host:port)",
    )
    parser.add_argument(
        "-n",
        "--no_notebook",
        action="store_false",
        dest="notebook",
        help="Disable Jupyter Notebook server",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Window width in pixels (default: 1280)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=800,
        help="Window height in pixels (default: 800)",
    )

    args = parser.parse_args()

    try:
        start_desktop_app(
            db_type=args.db,
            debug=args.debug,
            host=args.host,
            port=args.port,
            llm_backend=args.llm_backend,
            notebook=args.notebook,
            window_width=args.width,
            window_height=args.height,
        )
    except KeyboardInterrupt:
        print("\n\nShutting down YSocial Desktop...")
    except Exception as e:
        print(f"\nError starting YSocial Desktop:")
        print(f"   {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
