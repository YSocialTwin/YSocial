#!/usr/bin/env python
"""
YSocial Launcher Entry Point.

This script serves as the entry point for PyInstaller builds.
For frozen executables, it shows a splash screen in a separate process before loading the main app.
For development, it directly launches the main application.
"""

if __name__ == "__main__":
    import os
    import subprocess
    import sys

    # Check if running as PyInstaller bundle
    is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

    splash_process = None

    if is_frozen:
        # For frozen builds, launch splash screen as subprocess before loading heavy dependencies
        try:
            # Get the path to the splash subprocess script
            if hasattr(sys, "_MEIPASS"):
                splash_script = os.path.join(
                    sys._MEIPASS, "y_web", "pyinstaller_utils", "splash_subprocess.py"
                )
            else:
                splash_script = os.path.join(
                    os.path.dirname(__file__),
                    "y_web",
                    "pyinstaller_utils",
                    "splash_subprocess.py",
                )

            # Launch splash screen as a separate process
            # This allows it to run independently while we load heavy dependencies
            if os.path.exists(splash_script):
                splash_process = subprocess.Popen(
                    [sys.executable, splash_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as e:
            # Splash screen is non-critical, continue without it
            print(f"Warning: Could not start splash screen: {e}", file=sys.stderr)

    # Now load the main application (with heavy dependencies)
    try:
        from y_web.pyinstaller_utils.y_social_launcher import main

        # Terminate splash screen after imports are complete
        if splash_process is not None:
            try:
                splash_process.terminate()
                splash_process.wait(timeout=2)
            except Exception:
                # Force kill if terminate doesn't work
                try:
                    splash_process.kill()
                except Exception:
                    pass

        # Run the main application
        main()
    except Exception as e:
        # Ensure splash screen is closed on error
        if splash_process is not None:
            try:
                splash_process.terminate()
                splash_process.wait(timeout=1)
            except Exception:
                try:
                    splash_process.kill()
                except Exception:
                    pass

        # Show error dialog if possible
        if is_frozen:
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
