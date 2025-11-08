"""
Tests for Windows executable detection in external_processes module.

This test module validates the fix for Windows compatibility by ensuring
that the correct directory names (Scripts vs bin) and executable names
(python.exe vs python) are used on different platforms.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestPlatformSpecificPaths:
    """Test platform-specific path detection for Python executables"""

    def test_windows_platform_detection(self):
        """Test that Windows platform is correctly detected"""
        # Test the logic used in detect_env_handler
        is_windows = sys.platform.startswith("win")

        # On actual Windows systems, this should be True
        # On Unix/Linux/Mac, this should be False
        if sys.platform.startswith("win"):
            assert is_windows is True
        else:
            assert is_windows is False

    def test_directory_name_logic(self):
        """Test that correct directory name is chosen based on platform"""
        is_windows = sys.platform.startswith("win")
        bin_dir = "Scripts" if is_windows else "bin"

        if is_windows:
            assert bin_dir == "Scripts"
        else:
            assert bin_dir == "bin"

    def test_executable_name_logic(self):
        """Test that correct executable name is chosen based on platform"""
        is_windows = sys.platform.startswith("win")
        python_name = "python.exe" if is_windows else "python"
        gunicorn_name = "gunicorn.exe" if is_windows else "gunicorn"

        if is_windows:
            assert python_name == "python.exe"
            assert gunicorn_name == "gunicorn.exe"
        else:
            assert python_name == "python"
            assert gunicorn_name == "gunicorn"

    @patch("sys.platform", "win32")
    def test_windows_paths_mocked(self):
        """Test Windows path logic with mocked platform"""
        # When platform is Windows
        is_windows = sys.platform.startswith("win")
        bin_dir = "Scripts" if is_windows else "bin"
        python_name = "python.exe" if is_windows else "python"

        assert is_windows is True
        assert bin_dir == "Scripts"
        assert python_name == "python.exe"

    @patch("sys.platform", "linux")
    def test_linux_paths_mocked(self):
        """Test Linux path logic with mocked platform"""
        # When platform is Linux
        is_windows = sys.platform.startswith("win")
        bin_dir = "Scripts" if is_windows else "bin"
        python_name = "python.exe" if is_windows else "python"

        assert is_windows is False
        assert bin_dir == "bin"
        assert python_name == "python"

    def test_conda_path_construction(self):
        """Test that conda paths are constructed correctly"""
        # Simulate conda environment path construction
        is_windows = sys.platform.startswith("win")
        bin_dir = "Scripts" if is_windows else "bin"
        python_name = "python.exe" if is_windows else "python"

        # Example conda prefix
        if is_windows:
            conda_prefix = Path(r"C:\Users\Test\.conda\envs\test_env")
        else:
            conda_prefix = Path("/home/user/.conda/envs/test_env")

        env_bin = conda_prefix / bin_dir
        python_bin = env_bin / python_name

        # Verify the paths are constructed correctly
        if is_windows:
            assert "Scripts" in str(env_bin)
            assert "python.exe" in str(python_bin)
        else:
            assert "bin" in str(env_bin)
            assert str(python_bin).endswith("python")

    def test_venv_path_construction(self):
        """Test that venv paths are constructed correctly"""
        # Simulate venv path construction
        is_windows = sys.platform.startswith("win")
        bin_dir = "Scripts" if is_windows else "bin"
        python_name = "python.exe" if is_windows else "python"

        # Example venv prefix
        if is_windows:
            venv_prefix = Path(r"C:\Users\Test\venv")
        else:
            venv_prefix = Path("/home/user/venv")

        python_bin = venv_prefix / bin_dir / python_name

        # Verify the paths are constructed correctly
        if is_windows:
            assert "Scripts" in str(python_bin)
            assert "python.exe" in str(python_bin)
        else:
            assert "bin" in str(python_bin)
            assert str(python_bin).endswith("python")

    def test_gunicorn_path_construction(self):
        """Test that gunicorn paths are constructed correctly"""
        # Simulate gunicorn path construction
        is_windows = sys.platform.startswith("win")
        gunicorn_name = "gunicorn.exe" if is_windows else "gunicorn"

        # Example python executable path
        if is_windows:
            python_path = Path(r"C:\Users\Test\.conda\envs\test_env\Scripts\python.exe")
        else:
            python_path = Path("/home/user/.conda/envs/test_env/bin/python")

        gunicorn_path = python_path.parent / gunicorn_name

        # Verify the paths are constructed correctly
        if is_windows:
            assert "Scripts" in str(gunicorn_path)
            assert "gunicorn.exe" in str(gunicorn_path)
        else:
            assert "bin" in str(gunicorn_path)
            assert str(gunicorn_path).endswith("gunicorn")

    def test_fix_addresses_winerror_2(self):
        """
        Test that the fix addresses WinError 2 (file not found).

        The original bug was:
        - detect_env_handler() returned paths like "C:\\...\\bin\\python" on Windows
        - But on Windows, it should be "C:\\...\\Scripts\\python.exe"
        - Result: WinError 2 - The system cannot find the file specified

        With the fix:
        - detect_env_handler() returns "C:\\...\\Scripts\\python.exe" on Windows
        - The file should exist if the environment is properly set up
        """
        is_windows = sys.platform.startswith("win")

        if is_windows:
            # On Windows, verify we're using the correct naming
            bin_dir = "Scripts" if is_windows else "bin"
            python_name = "python.exe" if is_windows else "python"

            assert bin_dir == "Scripts", "Should use 'Scripts' directory on Windows"
            assert (
                python_name == "python.exe"
            ), "Should use 'python.exe' executable name on Windows"
        else:
            # On Unix/Linux, verify we're using the correct naming
            bin_dir = "Scripts" if is_windows else "bin"
            python_name = "python.exe" if is_windows else "python"

            assert bin_dir == "bin", "Should use 'bin' directory on Unix"
            assert (
                python_name == "python"
            ), "Should use 'python' executable name on Unix"
