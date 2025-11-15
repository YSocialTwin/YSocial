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
        # For frozen builds, launch directly without splash screen
        # Splash screen causes issues with Hardened Runtime on signed macOS executables
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
