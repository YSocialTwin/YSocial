#!/usr/bin/env python
"""
YSocial Launcher Entry Point.

This script serves as the entry point for PyInstaller builds.
It delegates to the actual launcher in y_web.pyinstaller_utils.
"""

if __name__ == "__main__":
    from y_web.pyinstaller_utils.y_social_launcher import main

    main()
