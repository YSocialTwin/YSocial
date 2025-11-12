#!/usr/bin/env python
"""
YSocial Launcher Entry Point.

This script serves as the entry point for PyInstaller builds.
For frozen executables, it shows a fast splash screen before loading the main app.
For development, it directly launches the main application.
"""

if __name__ == "__main__":
    import sys

    # Check if running as PyInstaller bundle
    is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

    if is_frozen:
        # For frozen builds, show splash immediately before any heavy imports
        # Import only the lightweight modules needed for splash
        import threading
        import time

        # Import and show the fast splash screen
        from y_web.pyinstaller_utils.fast_splash import FastSplashScreen

        # Create and show splash immediately
        splash = FastSplashScreen()

        # Flag to track when imports are done
        imports_done = False

        # Import heavy modules in a background thread
        def do_imports():
            """Import the heavy modules in background."""
            global imports_done
            try:
                # Import the main launcher (heavy imports happen here)
                from y_web.pyinstaller_utils.y_social_launcher import main

                imports_done = True
            except Exception as e:
                imports_done = True
                raise e

        # Start import thread
        import_thread = threading.Thread(target=do_imports, daemon=True)
        import_thread.start()

        # Wait for import thread to complete with timeout
        # The splash will remain visible during this time
        # We don't update it to avoid conflicts with Hardened Runtime on signed executables
        import_thread.join(timeout=30)

        # Close splash
        try:
            splash.close()
        except Exception:
            pass

        # Now import and launch the main application on the MAIN thread
        # This is critical for PyWebview which requires the main thread
        try:
            from y_web.pyinstaller_utils.y_social_launcher import main

            main()
        except Exception as e:
            # Show error dialog if possible
            try:
                import tkinter as tk
                from tkinter import messagebox

                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "YSocial Error",
                    f"Error starting YSocial:\n\n{type(e).__name__}: {e}",
                )
            except Exception:
                pass
            raise e
    else:
        # For development, launch directly without splash
        from y_web.pyinstaller_utils.y_social_launcher import main

        main()
