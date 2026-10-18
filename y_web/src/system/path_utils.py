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
        # Get the repository root (three levels up from this file's location
        # y_web/src/system/path_utils.py → y_web/src/system/ → y_web/src/ → y_web/ → repo root)
        return os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def _default_home_dir():
    """Per-system default data folder of an installed (not source) YSocial."""
    import platform
    from pathlib import Path

    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "YSocial"
    if system == "Windows":
        return Path.home() / "AppData" / "Local" / "YSocial"
    return Path.home() / ".ysocial"


def _is_source_checkout(root):
    """True when ``root`` is a repository checkout (it holds pyproject.toml; the wheel does not)."""
    return os.path.isfile(os.path.join(root, "pyproject.toml")) and os.path.isdir(
        os.path.join(root, "y_web")
    )


def get_home_path():
    """
    Folder that holds every user's data: experiments, databases, logs, ``external/`` and the Python environment.

    Resolution order:

    1. ``YSOCIAL_HOME`` when set (any run mode).
    2. A PyInstaller bundle: the per-system default folder.
    3. A source checkout: the repository root (unchanged behaviour for developers).
    4. An installed package (wheel): the per-system default folder, never ``site-packages``.

    Returns:
        str: Absolute path of the data folder (created when it is not the checkout)
    """
    from pathlib import Path

    override = os.environ.get("YSOCIAL_HOME", "").strip()
    if override:
        base = Path(os.path.expanduser(override)).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return str(base)
    if getattr(sys, "frozen", False):
        base = _default_home_dir()
        base.mkdir(parents=True, exist_ok=True)
        return str(base)
    code_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    if _is_source_checkout(code_root):
        return code_root
    base = _default_home_dir()
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def get_writable_path(relative_path=""):
    """
    Get absolute path to the writable data folder (see :func:`get_home_path`).

    Args:
        relative_path: Relative path from the writable base directory

    Returns:
        str: Absolute path to the writable location
    """
    base = get_home_path()
    if relative_path:
        return os.path.join(base, relative_path)
    return base


def get_external_path(repo_name=""):
    """
    Folder of the external runtimes and plugins (``<data folder>/external``), or one repository inside it.

    Args:
        repo_name: Optional repository folder name (``YServer``, ``YClient``...)

    Returns:
        str: Absolute path
    """
    base = get_writable_path("external")
    return os.path.join(base, repo_name) if repo_name else base


def get_external_repo_dir(repo_name):
    """
    Directory of an external repository: the writable copy when it exists, else the bundled one.

    Args:
        repo_name: Repository folder name (``YServer``, ``YClient``...)

    Returns:
        str: Path of the writable copy, or of the bundled copy when only that exists
        (the writable path when neither exists, so callers fail with a clear path)
    """
    writable = get_external_path(repo_name)
    if os.path.isdir(writable):
        return writable
    bundled = os.path.join(get_base_path(), "external", repo_name)
    return bundled if os.path.isdir(bundled) else writable


def resolve_external_repo(base_path, repo_name):
    """
    Directory of an external repository seen from ``base_path``.

    ``<base_path>/external/<repo_name>`` when it exists (source checkout, bundle), otherwise the copy under
    the data folder (installed package, where ``base_path`` is ``site-packages`` and has no ``external``).
    """
    candidate = os.path.join(base_path, "external", repo_name)
    if os.path.isdir(candidate):
        return candidate
    return get_external_repo_dir(repo_name)
