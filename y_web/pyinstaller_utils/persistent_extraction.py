"""
Persistent extraction directory management for PyInstaller.

This module provides functionality to determine the persistent cache directory
for PyInstaller extracted files. This is used by the spec file to configure
runtime_tmpdir, which tells PyInstaller's bootloader where to extract files.

When runtime_tmpdir is set, PyInstaller will:
1. Check if files already exist in that location
2. Skip extraction if they exist and are valid
3. Extract only when needed (first run or after updates)

This significantly speeds up application startup on subsequent runs.
"""

import os
import platform
from pathlib import Path


def get_persistent_extraction_dir():
    """
    Get the platform-specific directory for persistent PyInstaller extraction.
    
    This directory will be used as runtime_tmpdir in the PyInstaller spec file.
    PyInstaller will extract files here on first run and reuse them on subsequent runs.
    
    Returns:
        str: Path to the persistent extraction directory
    """
    system = platform.system()
    
    if system == "Windows":
        # Windows: Use Local AppData (writable, persistent location)
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        extraction_dir = base / "YSocial" / "Runtime"
    elif system == "Darwin":  # macOS
        # macOS: Use Application Support (standard for app data)
        extraction_dir = Path.home() / "Library" / "Application Support" / "YSocial" / "Runtime"
    else:  # Linux and others
        # Linux: Use ~/.local/share (XDG Base Directory specification)
        xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        extraction_dir = Path(xdg_data) / "ysocial" / "runtime"
    
    return str(extraction_dir)


def get_runtime_tmpdir_for_spec():
    """
    Get the runtime_tmpdir value to use in PyInstaller spec file.
    
    This function is called during the build process to determine where
    PyInstaller should extract files at runtime.
    
    Returns:
        str or None: Path to use as runtime_tmpdir, or None to use default temp directory
    """
    # Check if persistent extraction should be disabled via environment variable
    # This allows users/developers to opt-out if needed
    if os.environ.get("YSOCIAL_DISABLE_PERSISTENT_EXTRACTION", "").lower() in ("1", "true", "yes"):
        return None
    
    return get_persistent_extraction_dir()
