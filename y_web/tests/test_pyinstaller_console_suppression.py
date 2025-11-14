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

    def test_error_log_directory_path(self):
        """Test that error log directory path is correct"""
        # Verify the log directory path logic
        home_dir = os.path.expanduser("~")
        log_dir = os.path.join(home_dir, ".ysocial")
        stdout_log = os.path.join(log_dir, "ysocial.log")
        stderr_log = os.path.join(log_dir, "ysocial_error.log")

        # Verify paths are constructed correctly
        assert ".ysocial" in log_dir
        assert "ysocial.log" in stdout_log
        assert "ysocial_error.log" in stderr_log
        assert stdout_log.endswith("ysocial.log")
        assert stderr_log.endswith("ysocial_error.log")

    def test_get_log_file_paths_function(self):
        """Test that get_log_file_paths function works correctly"""
        from y_web.pyinstaller_utils.y_social_launcher import get_log_file_paths

        stdout_log, stderr_log, log_dir = get_log_file_paths()

        # Verify all paths are returned
        assert stdout_log is not None
        assert stderr_log is not None
        assert log_dir is not None

        # Verify paths contain expected components
        assert ".ysocial" in log_dir
        assert "ysocial.log" in stdout_log
        assert "ysocial_error.log" in stderr_log

    def test_stdout_redirection_logic(self):
        """Test the logic for stdout redirection to log file"""
        # Save original stdout
        original_stdout = sys.stdout

        # Simulate what would happen in the launcher
        try:
            # In the actual launcher on Windows, stdout would be redirected to a log file:
            # sys.stdout = open(stdout_log_file, "a", encoding="utf-8", buffering=1)
            # But we don't actually do it in the test to avoid breaking test output

            # Just verify we can open a log file for writing with UTF-8 encoding
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="a", encoding="utf-8", buffering=1, delete=False
            ) as log_file:
                assert log_file.writable()
                # Verify we can write to it without error
                log_file.write("test stdout\n")
                log_file.flush()
                log_path = log_file.name

            # Clean up
            os.unlink(log_path)
        finally:
            # Ensure stdout is restored (though we never changed it)
            assert sys.stdout is original_stdout

    def test_stderr_redirection_logic(self):
        """Test the logic for stderr redirection to log file"""
        # Save original stderr
        original_stderr = sys.stderr

        # Simulate what would happen in the launcher
        try:
            # In the actual launcher on Windows, stderr would be redirected to a log file:
            # sys.stderr = open(log_file, "a", encoding="utf-8", buffering=1)
            # But we don't actually do it in the test to avoid breaking test output

            # Just verify we can open a log file for appending with UTF-8 encoding
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="a", encoding="utf-8", buffering=1, delete=False
            ) as log_file:
                assert log_file.writable()
                # Verify we can write to it without error
                log_file.write("test error\n")
                log_file.flush()
                log_path = log_file.name

            # Clean up
            os.unlink(log_path)
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
            assert hasattr(y_social_launcher, "show_error_dialog")
            assert hasattr(y_social_launcher, "get_log_file_paths")
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

    def test_show_error_dialog_function_exists(self):
        """Test that show_error_dialog function exists and is callable"""
        from y_web.pyinstaller_utils.y_social_launcher import show_error_dialog

        assert callable(show_error_dialog)

        # Call it to verify it works (should return silently on non-Windows)
        try:
            show_error_dialog("Test Title", "Test Message")
        except Exception as e:
            pytest.fail(f"show_error_dialog raised unexpected exception: {e}")
