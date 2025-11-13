"""
Tests for desktop file handler functionality.

This test suite validates the desktop mode file download dialog feature,
ensuring that downloads open system dialogs in desktop mode and work
normally in browser mode.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from flask import Flask

from y_web.utils.desktop_file_handler import (
    desktop_save_file,
    get_webview_window,
    is_desktop_mode,
    send_file_desktop,
)


class TestDesktopFileHandler(unittest.TestCase):
    """Test desktop file handler utility functions."""

    def setUp(self):
        """Set up test Flask app."""
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["DESKTOP_MODE"] = False
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        """Clean up test context."""
        self.ctx.pop()

    def test_is_desktop_mode_false(self):
        """Test that is_desktop_mode returns False in browser mode."""
        self.app.config["DESKTOP_MODE"] = False
        self.assertFalse(is_desktop_mode())

    def test_is_desktop_mode_true(self):
        """Test that is_desktop_mode returns True in desktop mode."""
        self.app.config["DESKTOP_MODE"] = True
        self.assertTrue(is_desktop_mode())

    def test_get_webview_window_none(self):
        """Test that get_webview_window returns None when not set."""
        self.app.config["WEBVIEW_WINDOW"] = None
        self.assertIsNone(get_webview_window())

    def test_get_webview_window_returns_window(self):
        """Test that get_webview_window returns window when set."""
        mock_window = MagicMock()
        self.app.config["WEBVIEW_WINDOW"] = mock_window
        self.assertEqual(get_webview_window(), mock_window)


class TestDesktopSaveFile(unittest.TestCase):
    """Test desktop_save_file function."""

    def setUp(self):
        """Set up test Flask app and temp file."""
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["DESKTOP_MODE"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Create a temporary file to "download"
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt"
        )
        self.temp_file.write("Test file content")
        self.temp_file.close()

    def tearDown(self):
        """Clean up test context and temp file."""
        try:
            os.unlink(self.temp_file.name)
        except FileNotFoundError:
            pass
        self.ctx.pop()

    def test_desktop_save_file_no_window(self):
        """Test that desktop_save_file returns False when no window."""
        self.app.config["WEBVIEW_WINDOW"] = None
        result = desktop_save_file(self.temp_file.name)
        self.assertFalse(result)

    @patch("y_web.utils.desktop_file_handler.shutil.copy2")
    def test_desktop_save_file_cancelled(self, mock_copy):
        """Test that desktop_save_file returns False when dialog is cancelled."""
        mock_window = MagicMock()
        # Simulate user cancelling the dialog (returns None)
        mock_window.create_file_dialog.return_value = None
        self.app.config["WEBVIEW_WINDOW"] = mock_window

        result = desktop_save_file(self.temp_file.name, "test.txt")

        self.assertFalse(result)
        mock_window.create_file_dialog.assert_called_once()
        mock_copy.assert_not_called()

    @patch("y_web.utils.desktop_file_handler.shutil.copy2")
    def test_desktop_save_file_success(self, mock_copy):
        """Test that desktop_save_file succeeds when user selects location."""
        mock_window = MagicMock()
        # Simulate user selecting a save location
        mock_window.create_file_dialog.return_value = ["/tmp/saved_file.txt"]
        self.app.config["WEBVIEW_WINDOW"] = mock_window

        result = desktop_save_file(self.temp_file.name, "test.txt")

        self.assertTrue(result)
        mock_window.create_file_dialog.assert_called_once()
        mock_copy.assert_called_once_with(self.temp_file.name, "/tmp/saved_file.txt")


class TestSendFileDesktop(unittest.TestCase):
    """Test send_file_desktop function."""

    def setUp(self):
        """Set up test Flask app."""
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Create a temporary file to "download"
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        )
        self.temp_file.write('{"test": "data"}')
        self.temp_file.close()

    def tearDown(self):
        """Clean up test context and temp file."""
        try:
            os.unlink(self.temp_file.name)
        except FileNotFoundError:
            pass
        self.ctx.pop()

    @patch("y_web.utils.desktop_file_handler.send_file")
    def test_send_file_desktop_browser_mode(self, mock_send_file):
        """Test that send_file_desktop uses standard send_file in browser mode."""
        self.app.config["DESKTOP_MODE"] = False
        mock_send_file.return_value = Mock()

        response = send_file_desktop(self.temp_file.name, as_attachment=True)

        mock_send_file.assert_called_once()
        self.assertIsNotNone(response)

    @patch("y_web.utils.desktop_file_handler.send_file")
    def test_send_file_desktop_not_attachment(self, mock_send_file):
        """Test that send_file_desktop uses standard send_file when not attachment."""
        self.app.config["DESKTOP_MODE"] = True
        mock_send_file.return_value = Mock()

        response = send_file_desktop(self.temp_file.name, as_attachment=False)

        mock_send_file.assert_called_once()
        self.assertIsNotNone(response)

    @patch("y_web.utils.desktop_file_handler.desktop_save_file")
    def test_send_file_desktop_success(self, mock_save):
        """Test that send_file_desktop shows success message on successful save."""
        self.app.config["DESKTOP_MODE"] = True
        mock_save.return_value = True

        response = send_file_desktop(self.temp_file.name, as_attachment=True)

        mock_save.assert_called_once()
        self.assertIn(b"File saved successfully", response.data)

    @patch("y_web.utils.desktop_file_handler.desktop_save_file")
    def test_send_file_desktop_cancelled(self, mock_save):
        """Test that send_file_desktop shows cancel message when user cancels."""
        self.app.config["DESKTOP_MODE"] = True
        mock_save.return_value = False

        response = send_file_desktop(self.temp_file.name, as_attachment=True)

        mock_save.assert_called_once()
        self.assertIn(b"Download cancelled", response.data)

    @patch("y_web.utils.desktop_file_handler.desktop_save_file")
    def test_send_file_desktop_with_download_name(self, mock_save):
        """Test that send_file_desktop uses download_name when provided."""
        self.app.config["DESKTOP_MODE"] = True
        mock_save.return_value = True

        response = send_file_desktop(
            self.temp_file.name, as_attachment=True, download_name="custom_name.json"
        )

        mock_save.assert_called_once()
        # Check that the custom filename was used
        call_args = mock_save.call_args
        self.assertEqual(call_args[0][1], "custom_name.json")


if __name__ == "__main__":
    unittest.main()
