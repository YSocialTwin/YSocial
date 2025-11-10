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

# Force unbuffered output for better error messages in PyInstaller
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


def is_pyinstaller():
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


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

    # Show splash screen if running as PyInstaller executable
    splash_thread = None
    splash_screen = None
    if is_pyinstaller():
        try:
            from splash_screen import YSocialSplashScreen

            splash_screen = YSocialSplashScreen()

            def show_splash():
                """Show splash screen in a separate thread."""
                try:
                    splash_screen.show(duration=5)
                except Exception as e:
                    print(f"Splash screen error: {e}")

            splash_thread = threading.Thread(target=show_splash, daemon=True)
            splash_thread.start()
            # Give splash screen time to appear
            time.sleep(0.5)
        except Exception as e:
            print(f"Could not show splash screen: {e}")
            splash_screen = None

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
        "-n",
        "--no_notebook",
        action="store_false",
        dest="notebook",
        help="Disable Jupyter Notebook server launch for experiments",
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
        default=1280,
        help="Desktop window width in pixels (default: 1280)",
    )
    parser.add_argument(
        "--window-height",
        type=int,
        default=800,
        help="Desktop window height in pixels (default: 800)",
    )

    args = parser.parse_args()

    # Update splash screen status if available
    if splash_screen:
        try:
            splash_screen.update_status("Loading application modules...")
        except Exception:
            pass

    # Desktop mode is default unless --browser is specified
    if not args.browser:
        # Desktop mode - use PyWebview
        if splash_screen:
            try:
                splash_screen.update_status("Initializing desktop mode...")
            except Exception:
                pass

        try:
            from y_social_desktop import start_desktop_app
        except ImportError:
            if splash_screen:
                try:
                    splash_screen.close()
                except Exception:
                    pass
            print(
                "\n❌ Error: PyWebview is not installed. Desktop mode requires pywebview.",
                file=sys.stderr,
            )
            print(
                "   Install it with: pip install pywebview",
                file=sys.stderr,
            )
            sys.exit(1)
        except Exception as e:
            if splash_screen:
                try:
                    splash_screen.close()
                except Exception:
                    pass
            print(f"\n❌ Error importing y_social_desktop module:", file=sys.stderr)
            print(f"   {type(e).__name__}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.stderr.flush()
            sys.exit(1)

        if splash_screen:
            try:
                splash_screen.update_status("Starting YSocial Desktop...")
            except Exception:
                pass

        try:
            # Close splash screen before showing desktop window
            if splash_screen:
                try:
                    # Give a moment to see the final status
                    time.sleep(1)
                    splash_screen.close()
                except Exception:
                    pass

            start_desktop_app(
                db_type=args.db,
                debug=args.debug,
                host=args.host,
                port=args.port,
                llm_backend=args.llm_backend,
                notebook=args.notebook,
                window_width=args.window_width,
                window_height=args.window_height,
            )
        except KeyboardInterrupt:
            print("\n\nShutting down YSocial Desktop...")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Error starting YSocial Desktop:", file=sys.stderr)
            print(f"   {type(e).__name__}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.stderr.flush()
            sys.exit(1)
    else:
        # Browser mode - traditional web browser
        if splash_screen:
            try:
                splash_screen.update_status("Initializing browser mode...")
            except Exception:
                pass

        # Import the actual application after parsing args (allows --help to work without dependencies)
        try:
            from y_social import start_app
        except Exception as e:
            if splash_screen:
                try:
                    splash_screen.close()
                except Exception:
                    pass
            print(f"\n❌ Error importing y_social module:", file=sys.stderr)
            print(f"   {type(e).__name__}: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.stderr.flush()
            sys.exit(1)

        if splash_screen:
            try:
                splash_screen.update_status("Starting Flask server...")
            except Exception:
                pass

        # Start browser opener in background thread unless disabled
        if not args.no_browser:
            browser_thread = threading.Thread(
                target=wait_for_server_and_open_browser,
                args=(args.host, args.port),
                daemon=True,
            )
            browser_thread.start()

        # Close splash screen before starting the app
        if splash_screen:
            try:
                time.sleep(1)
                splash_screen.close()
            except Exception:
                pass

        # Start the application
        try:
            start_app(
                db_type=args.db,
                debug=args.debug,
                host=args.host,
                port=args.port,
                llm_backend=args.llm_backend,
                notebook=args.notebook,
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
