"""
Test for Jupyter kernel installation behavior in different environments.

Verifies that kernel installation handles PyInstaller bundles correctly
and uses appropriate Python executables.
"""

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest


def test_ensure_kernel_in_frozen_mode_with_existing_kernel():
    """Test kernel installation when running from PyInstaller with existing kernel."""
    from y_web.utils.jupyter_utils import ensure_kernel_installed

    # Mock the frozen environment
    with patch("sys.frozen", True, create=True):
        with patch(
            "y_web.utils.jupyter_utils.get_python_executable",
            return_value="/usr/bin/python3",
        ):
            # Mock subprocess to simulate existing python3 kernel
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(
                {"kernelspecs": {"python3": {"spec": {"display_name": "Python 3"}}}}
            )

            with patch("subprocess.run", return_value=mock_result) as mock_run:
                result = ensure_kernel_installed()

                # Should return True (kernel found)
                assert result is True

                # Should have called jupyter kernelspec list
                assert mock_run.call_count >= 1
                first_call_args = mock_run.call_args_list[0][0][0]
                assert "jupyter" in first_call_args
                assert "kernelspec" in first_call_args


def test_ensure_kernel_in_frozen_mode_no_kernel():
    """Test kernel installation when running from PyInstaller without existing kernel."""
    from y_web.utils.jupyter_utils import ensure_kernel_installed

    # Mock the frozen environment
    with patch("sys.frozen", True, create=True):
        with patch(
            "y_web.utils.jupyter_utils.get_python_executable",
            return_value="/usr/bin/python3",
        ):
            call_count = 0

            def mock_subprocess_run(*args, **kwargs):
                nonlocal call_count
                call_count += 1

                mock_result = MagicMock()
                cmd = args[0] if args else []

                # First call: kernelspec list (no kernels)
                if call_count == 1 and "kernelspec" in cmd:
                    mock_result.returncode = 0
                    mock_result.stdout = json.dumps({"kernelspecs": {}})
                # Second call: pip install ipykernel
                elif "pip" in cmd and "install" in cmd:
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                # Third call: ipykernel install
                elif "ipykernel" in cmd and "install" in cmd:
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                else:
                    mock_result.returncode = 0
                    mock_result.stdout = ""

                return mock_result

            with patch("subprocess.run", side_effect=mock_subprocess_run) as mock_run:
                result = ensure_kernel_installed()

                # Should return True (kernel installed)
                assert result is True

                # Should have called subprocess multiple times
                assert mock_run.call_count >= 3


def test_ensure_kernel_in_frozen_mode_no_jupyter():
    """Test kernel installation when running from PyInstaller without jupyter."""
    from y_web.utils.jupyter_utils import ensure_kernel_installed

    # Mock the frozen environment
    with patch("sys.frozen", True, create=True):
        with patch(
            "y_web.utils.jupyter_utils.get_python_executable",
            return_value="/usr/bin/python3",
        ):
            # Mock subprocess to simulate jupyter not being available
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""

            with patch("subprocess.run", return_value=mock_result):
                result = ensure_kernel_installed()

                # Should return False (jupyter not available)
                assert result is False


def test_ensure_kernel_in_source_mode():
    """Test kernel installation when running from source."""
    from y_web.utils.jupyter_utils import ensure_kernel_installed

    # Mock non-frozen environment
    with patch("sys.frozen", False, create=True):
        with patch(
            "y_web.utils.jupyter_utils.get_python_executable",
            return_value=sys.executable,
        ):
            # Mock ipykernel import succeeds
            with patch("builtins.__import__"):
                # Mock subprocess to simulate existing custom kernel
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = json.dumps(
                    {
                        "kernelspecs": {
                            "python3_ysocial": {
                                "spec": {"display_name": "Python (python3_ysocial)"}
                            }
                        }
                    }
                )

                with patch("subprocess.run", return_value=mock_result) as mock_run:
                    result = ensure_kernel_installed()

                    # Should return True
                    assert result is True

                    # Should check for kernel
                    assert mock_run.call_count >= 1


def test_ensure_kernel_frozen_detection():
    """Test that PyInstaller frozen detection works correctly."""
    # Test with sys.frozen = True
    with patch("sys.frozen", True, create=True):
        is_frozen = getattr(sys, "frozen", False)
        assert is_frozen is True

    # Test with sys.frozen = False
    with patch("sys.frozen", False, create=True):
        is_frozen = getattr(sys, "frozen", False)
        assert is_frozen is False

    # Test when sys.frozen doesn't exist (default behavior)
    if hasattr(sys, "frozen"):
        delattr(sys, "frozen")
    is_frozen = getattr(sys, "frozen", False)
    assert is_frozen is False
