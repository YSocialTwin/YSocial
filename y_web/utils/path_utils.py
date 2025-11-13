"""
Path utilities for handling file paths in both development and PyInstaller environments.

This module provides utilities to get correct paths whether running from source
or from a PyInstaller bundle.
"""

import os
import sys


def get_base_path():
    """
    Get the base path of the application.

    When running from source, this returns the repository root.
    When running from PyInstaller bundle, this returns the _MEIPASS directory
    where PyInstaller extracts files.

    Returns:
        str: The base path of the application
    """
    if getattr(sys, "frozen", False):
        # Running in PyInstaller bundle
        # sys._MEIPASS is the temp folder where PyInstaller extracts files
        return sys._MEIPASS
    else:
        # Running from source
        # Get the repository root (two levels up from this file)
        return os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )


def get_data_schema_path():
    """
    Get the path to the data_schema directory.

    Returns:
        str: Path to data_schema directory
    """
    return os.path.join(get_base_path(), "data_schema")


def get_y_web_path():
    """
    Get the path to the y_web directory.

    Returns:
        str: Path to y_web directory
    """
    return os.path.join(get_base_path(), "y_web")


def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller.

    Args:
        relative_path: Relative path from the base directory

    Returns:
        str: Absolute path to the resource
    """
    return os.path.join(get_base_path(), relative_path)


def get_writable_path(relative_path=""):
    """
    Get absolute path to writable directory, works for dev and for PyInstaller.

    When running from source, this returns paths relative to the repository root.
    When running from PyInstaller bundle, this returns paths relative to a user-writable
    directory (Application Support on macOS, user's home directory on other platforms).

    Args:
        relative_path: Relative path from the writable base directory

    Returns:
        str: Absolute path to the writable location
    """
    if getattr(sys, "frozen", False):
        # Running in PyInstaller bundle - use user-writable directory
        # DMG-installed apps cannot write to /Applications or current working directory
        import platform
        from pathlib import Path
        
        if platform.system() == "Darwin":  # macOS
            # Use Application Support directory (standard for macOS apps)
            base = Path.home() / "Library" / "Application Support" / "YSocial"
        elif platform.system() == "Windows":
            # Use AppData directory (standard for Windows apps)
            base = Path.home() / "AppData" / "Local" / "YSocial"
        else:
            # Linux and others - use hidden directory in home
            base = Path.home() / ".ysocial"
        
        # Create base directory if it doesn't exist
        base.mkdir(parents=True, exist_ok=True)
        base = str(base)
    else:
        # Running from source - use repository root
        base = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

    if relative_path:
        return os.path.join(base, relative_path)
    return base
