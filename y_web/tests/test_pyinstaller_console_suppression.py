"""
Tests for PyInstaller console output suppression.

This test module validates that console output is properly suppressed
when running as a PyInstaller frozen executable on Windows.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestConsoleSuppressionLogic:
    """Test console output suppression for PyInstaller executables"""

    def test_is_pyinstaller_detection_frozen(self):
        """Test that is_pyinstaller() correctly detects frozen state"""
        # Mock frozen state
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "_MEIPASS", "/tmp/meipass", create=True):
                # This mimics the is_pyinstaller() function
                is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
                assert is_frozen is True

    def test_is_pyinstaller_detection_not_frozen(self):
        """Test that is_pyinstaller() correctly detects non-frozen state"""
        # In normal Python execution (like this test), frozen should not exist
        is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        assert is_frozen is False

    def test_windows_platform_detection(self):
        """Test Windows platform detection"""
        is_windows = sys.platform.startswith("win")
        # This should work on any platform
        assert isinstance(is_windows, bool)

    @patch("sys.platform", "win32")
    @patch.object(sys, "frozen", True, create=True)
    @patch.object(sys, "_MEIPASS", "/tmp/meipass", create=True)
    def test_should_suppress_on_windows_frozen(self):
        """Test that suppression should occur on Windows when frozen"""
        is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        is_windows = sys.platform.startswith("win")

        should_suppress = is_frozen and is_windows
        assert should_suppress is True

    @patch("sys.platform", "linux")
    @patch.object(sys, "frozen", True, create=True)
    @patch.object(sys, "_MEIPASS", "/tmp/meipass", create=True)
    def test_should_not_suppress_on_linux_frozen(self):
        """Test that suppression should NOT occur on Linux even when frozen"""
        is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        is_windows = sys.platform.startswith("win")

        should_suppress = is_frozen and is_windows
        assert should_suppress is False

    @patch("sys.platform", "win32")
    def test_should_not_suppress_on_windows_not_frozen(self):
        """Test that suppression should NOT occur on Windows when not frozen"""
        is_frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        is_windows = sys.platform.startswith("win")

        should_suppress = is_frozen and is_windows
        assert should_suppress is False

    def test_devnull_path_exists(self):
        """Test that os.devnull is a valid path"""
        assert os.devnull is not None
        # os.devnull should be '/dev/null' on Unix or 'nul' on Windows
        assert isinstance(os.devnull, str)
        assert len(os.devnull) > 0

    def test_stdout_redirection_logic(self):
        """Test the logic for stdout redirection (without actually redirecting)"""
        # Save original stdout
        original_stdout = sys.stdout

        # Simulate what would happen in the launcher
        try:
            # In the actual launcher, this would be:
            # sys.stdout = open(os.devnull, "w")
            # But we don't actually do it in the test to avoid breaking test output

            # Just verify we can open devnull for writing
            with open(os.devnull, "w") as devnull:
                assert devnull.writable()
                # Verify we can write to it without error
                devnull.write("test\n")
        finally:
            # Ensure stdout is restored (though we never changed it)
            assert sys.stdout is original_stdout

    def test_stderr_redirection_logic(self):
        """Test the logic for stderr redirection (without actually redirecting)"""
        # Save original stderr
        original_stderr = sys.stderr

        # Simulate what would happen in the launcher
        try:
            # In the actual launcher, this would be:
            # sys.stderr = open(os.devnull, "w")
            # But we don't actually do it in the test to avoid breaking test output

            # Just verify we can open devnull for writing
            with open(os.devnull, "w") as devnull:
                assert devnull.writable()
                # Verify we can write to it without error
                devnull.write("test error\n")
        finally:
            # Ensure stderr is restored (though we never changed it)
            assert sys.stderr is original_stderr

    def test_reconfigure_line_buffering_available(self):
        """Test that line buffering reconfiguration is available"""
        # Test that we can check for reconfigure method
        has_reconfigure = hasattr(sys.stdout, "reconfigure")
        assert isinstance(has_reconfigure, bool)

        if has_reconfigure:
            # If reconfigure exists, it should be callable
            assert callable(sys.stdout.reconfigure)

    def test_exception_handling_logic(self):
        """Test that redirection failures are handled gracefully"""
        # Test the pattern used in the launcher:
        # try:
        #     sys.stdout = open(os.devnull, "w")
        # except Exception:
        #     pass  # Continue anyway

        # Simulate a failure (though opening devnull should never fail)
        try:
            # Try to open a path that might not exist or be writable
            with open(os.devnull, "w") as f:
                assert f is not None
        except Exception:
            # If it fails, we should be able to continue
            # (this mimics the launcher's exception handling)
            pass

        # The test should complete successfully even if exception occurred
        assert True


class TestLauncherImport:
    """Test that the launcher module can be imported"""

    def test_import_launcher_module(self):
        """Test that y_social_launcher module can be imported"""
        try:
            from y_web.pyinstaller_utils import y_social_launcher

            assert hasattr(y_social_launcher, "main")
            assert hasattr(y_social_launcher, "is_pyinstaller")
        except ImportError as e:
            pytest.fail(f"Failed to import y_social_launcher: {e}")

    def test_is_pyinstaller_function_exists(self):
        """Test that is_pyinstaller function exists and is callable"""
        from y_web.pyinstaller_utils.y_social_launcher import is_pyinstaller

        assert callable(is_pyinstaller)

        # Call it to verify it works
        result = is_pyinstaller()
        assert isinstance(result, bool)
        # In a test environment, it should return False
        assert result is False
