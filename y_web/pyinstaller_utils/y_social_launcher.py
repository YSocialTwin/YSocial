"""
YSocial Launcher - Wrapper script for PyInstaller executable.

This script launches the YSocial application and automatically opens
a browser window when the server is ready.
"""

import datetime
import os
import sys
import tempfile
import threading
import time
import webbrowser
from argparse import ArgumentParser


def is_pyinstaller():
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def close_splash_screen():
    """
    Close the PyInstaller splash screen if it's active.

    This should be called after heavy imports are complete to hide the splash
    and show the main application.

    Note: On macOS builds, splash screen is not available (not supported by PyInstaller).
    This function will silently do nothing in that case.
    """
    # Only attempt splash screen on Windows where it's enabled
    # Splash screen is not built for macOS/Linux builds
    if sys.platform != "win32":
        return
    
    try:
        import pyi_splash

        # Check if splash is alive before trying to close
        # On some platforms, pyi_splash exists but isn't functional
        if hasattr(pyi_splash, "is_alive") and pyi_splash.is_alive():
            pyi_splash.close()
    except (ImportError, RuntimeError, AttributeError, Exception) as e:
        # Splash not available, already closed, or not supported - that's fine
        # This happens on macOS builds where splash isn't included
        pass


def get_log_file_paths():
    """
    Get the paths to log files.

    Returns:
        tuple: (stdout_log_path, stderr_log_path, log_dir)
    """
    log_dir = os.path.join(os.path.expanduser("~"), ".ysocial")

    # Check if log directory exists, otherwise use temp
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            log_dir = tempfile.gettempdir()

    stdout_log = os.path.join(log_dir, "ysocial.log")
    stderr_log = os.path.join(log_dir, "ysocial_error.log")

    return stdout_log, stderr_log, log_dir


def show_error_dialog(title, message):
    """
    Show an error dialog to the user on Windows.

    Args:
        title: Dialog title
        message: Error message to display
    """
    if not sys.platform.startswith("win"):
        return

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        # If GUI fails, at least the error is in the log file
        pass


# Suppress console output when running as PyInstaller executable
# This prevents the terminal window from showing when console=False in spec
# Skip redirection if we're being invoked as a subprocess (to avoid file locking issues on Windows)
is_subprocess = len(sys.argv) > 1 and sys.argv[1] in [
    "--run-client-subprocess",
    "--run-server-subprocess",
]

if is_pyinstaller() and not is_subprocess:
    # On Windows with console=False, redirect stdout/stderr to log file
    # This prevents Flask and other print statements from showing a console window
    # while still allowing diagnosis through the log file
    if sys.platform.startswith("win"):
        try:
            # Get user's home directory for log file
            log_dir = os.path.join(os.path.expanduser("~"), ".ysocial")

            # Create log directory if it doesn't exist
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception:
                # Fallback to temp directory if home directory is not writable
                log_dir = tempfile.gettempdir()

            # Create separate log files for stdout and stderr
            stdout_log_file = os.path.join(log_dir, "ysocial.log")
            stderr_log_file = os.path.join(log_dir, "ysocial_error.log")

            # Redirect stdout to log file to capture normal output (Flask logs, etc.)
            # Open in append mode with UTF-8 encoding and line buffering
            sys.stdout = open(stdout_log_file, "a", encoding="utf-8", buffering=1)

            # Redirect stderr to error log file to capture errors
            # Open in append mode with UTF-8 encoding and line buffering
            sys.stderr = open(stderr_log_file, "a", encoding="utf-8", buffering=1)

            # Write a startup marker to both logs
            timestamp = datetime.datetime.now()

            sys.stdout.write(f"\n{'='*60}\n")
            sys.stdout.write(f"YSocial started at {timestamp}\n")
            sys.stdout.write(f"{'='*60}\n")
            sys.stdout.flush()

            sys.stderr.write(f"\n{'='*60}\n")
            sys.stderr.write(f"YSocial started at {timestamp}\n")
            sys.stderr.write(f"{'='*60}\n")
            sys.stderr.flush()
        except Exception as e:
            # If redirection fails, try to show error dialog and continue anyway
            try:
                import tkinter as tk
                from tkinter import messagebox

                root = tk.Tk()
                root.withdraw()
                messagebox.showwarning(
                    "YSocial Warning",
                    f"Could not set up logging:\n{e}\n\nContinuing without log files.",
                )
            except Exception:
                pass
else:
    # When running from source (not frozen), keep normal output with line buffering
    # Force unbuffered output for better error messages
    (
        sys.stdout.reconfigure(line_buffering=True)
        if hasattr(sys.stdout, "reconfigure")
        else None
    )
    (
        sys.stderr.reconfigure(line_buffering=True)
        if hasattr(sys.stderr, "reconfigure")
        else None
    )


def wait_for_server_and_open_browser(host, port, max_wait=30):
    """
    Wait for the Flask server to start and then open the browser.

    Args:
        host: The host address where the server will run
        port: The port number where the server will run
        max_wait: Maximum time to wait for server (seconds)
    """
    import socket

    url = f"http://{host}:{port}"
    start_time = time.time()

    # Wait for the server to be ready
    while time.time() - start_time < max_wait:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(
                (host if host != "0.0.0.0" else "localhost", int(port))
            )
            sock.close()

            if result == 0:
                # Server is ready, wait a bit more to ensure it's fully initialized
                time.sleep(2)
                print(f"\n{'='*60}")
                print(f"🚀 YSocial is ready!")
                print(f"📱 Opening browser at: {url}")
                print(f"{'='*60}\n")
                webbrowser.open(url)
                return
        except Exception:
            pass

        time.sleep(0.5)

    print(f"Warning: Could not verify server startup. Please manually open {url}")


def main():
    """Main launcher function."""
    # Check if we're being invoked as a client runner subprocess
    # This happens when PyInstaller's bundled executable is called with client runner args
    if len(sys.argv) > 1 and sys.argv[1] == "--run-client-subprocess":
        # Remove the special flag and pass remaining args to client runner
        sys.argv.pop(1)
        # Import and run the client process runner
        from y_web.utils.y_client_process_runner import main as client_main

        client_main()
        return

    # Check if we're being invoked as a server runner subprocess
    # This happens when PyInstaller's bundled executable is called with server runner args
    if len(sys.argv) > 1 and sys.argv[1] == "--run-server-subprocess":
        # Remove the special flag and pass remaining args to server runner
        sys.argv.pop(1)
        # Import and run the server process
        from y_web.utils.y_server_process_runner import main as server_main

        server_main()
        return

    # Generate or load installation ID on first run
    if is_pyinstaller():
        try:
            from .installation_id import get_or_create_installation_id

            # This will create the ID on first run or load existing one
            installation_info = get_or_create_installation_id()
        except Exception as e:
            print(f"Warning: Could not initialize installation ID: {e}")

    parser = ArgumentParser(description="YSocial - LLM-powered Social Media Twin")

    parser.add_argument(
        "-x",
        "--host",
        default="localhost",
        help="Host address to run the app on (default: localhost)",
    )
    parser.add_argument(
        "-y", "--port", default="8080", help="Port to run the app on (default: 8080)"
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
        help="LLM backend to use: 'ollama', 'vllm', or custom URL (host:port). If not specified, LLM features will be disabled.",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Launch in browser mode instead of desktop mode (desktop is default)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser on startup (only applies to browser mode)",
    )
    parser.add_argument(
        "--window-width",
        type=int,
        default=0,  # 0 means fullscreen
        help="Desktop window width in pixels (default: 0 for fullscreen)",
    )
    parser.add_argument(
        "--window-height",
        type=int,
        default=0,  # 0 means fullscreen
        help="Desktop window height in pixels (default: 0 for fullscreen)",
    )

    args = parser.parse_args()

    # Notebooks are always disabled in PyInstaller mode
    # The bundled Python environment cannot be used as a Jupyter kernel
    notebook = False

    # Desktop mode is default unless --browser is specified
    use_browser_fallback = False

    if not args.browser:
        # Desktop mode - use PyWebview
        try:
            from .y_social_desktop import start_desktop_app
        except ImportError:
            print(
                "\nWarning: PyWebview is not installed. Falling back to browser mode.",
                file=sys.stderr,
            )
            print(
                "   For desktop mode, install pywebview: pip install pywebview\n",
                file=sys.stderr,
            )
            use_browser_fallback = True
        except Exception as e:
            # Check if it's a GTK-related error (common on Linux with PyInstaller)
            error_msg = str(e).lower()
            if "gtk" in error_msg or "gi" in error_msg:
                print(
                    f"\nWarning: GTK dependencies not available. Falling back to browser mode.",
                    file=sys.stderr,
                )
                print(
                    f"   This is expected on Linux PyInstaller builds.\n",
                    file=sys.stderr,
                )
                use_browser_fallback = True
            else:
                error_msg = f"{type(e).__name__}: {e}"
                print(f"\nError importing y_social_desktop module:", file=sys.stderr)
                print(f"   {error_msg}", file=sys.stderr)
                import traceback

                traceback.print_exc()
                sys.stderr.flush()

                # Show error dialog on Windows
                if sys.platform.startswith("win"):
                    stdout_log, stderr_log, log_dir = get_log_file_paths()
                    dialog_msg = f"Error importing desktop module:\n\n{error_msg}\n\n"
                    dialog_msg += f"Check the log files for details:\n"
                    dialog_msg += f"  • Errors: {stderr_log}\n"
                    dialog_msg += f"  • Output: {stdout_log}"
                    show_error_dialog("YSocial Desktop Import Error", dialog_msg)

                sys.exit(1)

        if not use_browser_fallback:
            try:
                start_desktop_app(
                    db_type=args.db,
                    debug=args.debug,
                    host=args.host,
                    port=args.port,
                    llm_backend=args.llm_backend,
                    notebook=notebook,
                    window_width=args.window_width,
                    window_height=args.window_height,
                )
                # If desktop mode succeeds, we're done
                sys.exit(0)
            except KeyboardInterrupt:
                print("\n\nShutting down YSocial Desktop...")
                sys.exit(0)
            except RuntimeError as e:
                # RuntimeError indicates incompatibility (e.g., GTK not available)
                error_msg = str(e).lower()
                print(
                    f"\nWarning: Desktop mode not compatible. Falling back to browser mode.",
                    file=sys.stderr,
                )
                print(f"   Reason: {e}", file=sys.stderr)
                if "gtk" in error_msg:
                    print(
                        f"   To use desktop mode on Linux, install GTK dependencies.\n",
                        file=sys.stderr,
                    )
                else:
                    print(f"", file=sys.stderr)
                use_browser_fallback = True
            except Exception as e:
                # Check if it's a GTK-related error
                error_msg = str(e).lower()
                if "gtk" in error_msg or "gi" in error_msg or "webview" in error_msg:
                    print(
                        f"\nWarning: Desktop mode failed ({type(e).__name__}). Falling back to browser mode.",
                        file=sys.stderr,
                    )
                    print(
                        f"   This is expected on Linux PyInstaller builds without GTK.\n",
                        file=sys.stderr,
                    )
                    use_browser_fallback = True
                else:
                    error_msg = f"{type(e).__name__}: {e}"
                    print(f"\nError starting YSocial Desktop:", file=sys.stderr)
                    print(f"   {error_msg}", file=sys.stderr)
                    import traceback

                    traceback.print_exc()
                    sys.stderr.flush()

                    # Show error dialog on Windows
                    if sys.platform.startswith("win"):
                        stdout_log, stderr_log, log_dir = get_log_file_paths()
                        dialog_msg = (
                            f"Error starting YSocial Desktop:\n\n{error_msg}\n\n"
                        )
                        dialog_msg += f"Check the log files for details:\n"
                        dialog_msg += f"  • Errors: {stderr_log}\n"
                        dialog_msg += f"  • Output: {stdout_log}"
                        show_error_dialog("YSocial Desktop Error", dialog_msg)

                    sys.exit(1)

    # Browser mode - either explicitly requested or fallback from desktop mode
    if args.browser or use_browser_fallback:
        # Browser mode - traditional web browser
        # Import the actual application after parsing args (allows --help to work without dependencies)
        try:
            from y_social import start_app

            # Close splash screen after heavy imports complete
            close_splash_screen()
        except Exception as e:
            # Close splash on import error
            close_splash_screen()
            error_msg = f"{type(e).__name__}: {e}"
            print(f"\nError importing y_social module:", file=sys.stderr)
            print(f"   {error_msg}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.stderr.flush()

            # Show error dialog on Windows
            if sys.platform.startswith("win"):
                stdout_log, stderr_log, log_dir = get_log_file_paths()
                dialog_msg = f"Error importing y_social module:\n\n{error_msg}\n\n"
                dialog_msg += f"Check the log files for details:\n"
                dialog_msg += f"  • Errors: {stderr_log}\n"
                dialog_msg += f"  • Output: {stdout_log}"
                show_error_dialog("YSocial Import Error", dialog_msg)

            sys.exit(1)

        # Start browser opener in background thread unless disabled
        if not args.no_browser:
            browser_thread = threading.Thread(
                target=wait_for_server_and_open_browser,
                args=(args.host, args.port),
                daemon=True,
            )
            browser_thread.start()

        # Start the application
        try:
            start_app(
                db_type=args.db,
                debug=args.debug,
                host=args.host,
                port=args.port,
                llm_backend=args.llm_backend,
                notebook=notebook,
            )
        except KeyboardInterrupt:
            print("\n\nShutting down YSocial...")
            sys.exit(0)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            print(f"\nError starting YSocial:", file=sys.stderr)
            print(f"   {error_msg}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.stderr.flush()

            # Show error dialog on Windows
            if sys.platform.startswith("win"):
                stdout_log, stderr_log, log_dir = get_log_file_paths()
                dialog_msg = f"Error starting YSocial:\n\n{error_msg}\n\n"
                dialog_msg += f"Check the log files for details:\n"
                dialog_msg += f"  • Errors: {stderr_log}\n"
                dialog_msg += f"  • Output: {stdout_log}"
                show_error_dialog("YSocial Startup Error", dialog_msg)

            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        print(f"\nUnexpected error in main:", file=sys.stderr)
        print(f"   {error_msg}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.stderr.flush()

        # Show error dialog on Windows PyInstaller build
        if is_pyinstaller() and sys.platform.startswith("win"):
            # Get log file paths
            stdout_log, stderr_log, log_dir = get_log_file_paths()

            dialog_msg = f"YSocial encountered an error:\n\n{error_msg}\n\n"
            dialog_msg += f"Check the log files for details:\n"
            dialog_msg += f"  • Errors: {stderr_log}\n"
            dialog_msg += f"  • Output: {stdout_log}"
            show_error_dialog("YSocial Error", dialog_msg)

        sys.exit(1)
