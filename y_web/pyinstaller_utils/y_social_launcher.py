"""
YSocial Launcher - Wrapper script for PyInstaller executable.

This script launches the YSocial application and automatically opens
a browser window when the server is ready.
"""

import os
import sys
import threading
import time
import webbrowser
from argparse import ArgumentParser


def is_pyinstaller():
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


# Suppress console output when running as PyInstaller executable
# This prevents the terminal window from showing when console=False in spec
if is_pyinstaller():
    # On Windows with console=False, redirect stdout/stderr to suppress output
    # This prevents Flask and other print statements from showing a console window
    if sys.platform.startswith("win"):
        try:
            # Redirect to DEVNULL to completely suppress console output
            sys.stdout = open(os.devnull, "w")
            sys.stderr = open(os.devnull, "w")
        except Exception:
            # If redirection fails, continue anyway
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
                "\n⚠️  Warning: PyWebview is not installed. Falling back to browser mode.",
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
                    f"\n⚠️  Warning: GTK dependencies not available. Falling back to browser mode.",
                    file=sys.stderr,
                )
                print(
                    f"   This is expected on Linux PyInstaller builds.\n",
                    file=sys.stderr,
                )
                use_browser_fallback = True
            else:
                print(f"\n❌ Error importing y_social_desktop module:", file=sys.stderr)
                print(f"   {type(e).__name__}: {e}", file=sys.stderr)
                import traceback

                traceback.print_exc()
                sys.stderr.flush()
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
            except Exception as e:
                # Check if it's a GTK-related error
                error_msg = str(e).lower()
                if "gtk" in error_msg or "gi" in error_msg or "webview" in error_msg:
                    print(
                        f"\n⚠️  Warning: Desktop mode failed ({type(e).__name__}). Falling back to browser mode.",
                        file=sys.stderr,
                    )
                    print(
                        f"   This is expected on Linux PyInstaller builds without GTK.\n",
                        file=sys.stderr,
                    )
                    use_browser_fallback = True
                else:
                    print(f"\n❌ Error starting YSocial Desktop:", file=sys.stderr)
                    print(f"   {type(e).__name__}: {e}", file=sys.stderr)
                    import traceback

                    traceback.print_exc()
                    sys.stderr.flush()
                    sys.exit(1)
    
    # Browser mode - either explicitly requested or fallback from desktop mode
    if args.browser or use_browser_fallback:
        # Browser mode - traditional web browser
        # Import the actual application after parsing args (allows --help to work without dependencies)
        try:
            from y_social import start_app
        except Exception as e:
            print(f"\n❌ Error importing y_social module:", file=sys.stderr)
            print(f"   {type(e).__name__}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.stderr.flush()
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
            print(f"\n❌ Error starting YSocial:", file=sys.stderr)
            print(f"   {type(e).__name__}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.stderr.flush()
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Unexpected error in main:", file=sys.stderr)
        print(f"   {type(e).__name__}: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.stderr.flush()
        sys.exit(1)
