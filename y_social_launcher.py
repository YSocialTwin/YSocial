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
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None


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
            result = sock.connect_ex((host if host != '0.0.0.0' else 'localhost', int(port)))
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
    parser = ArgumentParser(description="YSocial - LLM-powered Social Media Twin")
    
    parser.add_argument(
        "-x", "--host", 
        default="localhost", 
        help="Host address to run the app on (default: localhost)"
    )
    parser.add_argument(
        "-y", "--port", 
        default="8080", 
        help="Port to run the app on (default: 8080)"
    )
    parser.add_argument(
        "-d", "--debug", 
        default=False, 
        action="store_true", 
        help="Enable debug mode"
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
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser on startup",
    )
    
    args = parser.parse_args()
    
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
            daemon=True
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
