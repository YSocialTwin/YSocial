"""
Tests for desktop file handler functionality.

This test suite validates the desktop mode file download feature,
ensuring that downloads work correctly in both desktop and browser modes.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from flask import Flask

from y_web.utils.desktop_file_handler import (
    desktop_download_file,
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


class TestDesktopDownloadFile(unittest.TestCase):
    """Test desktop_download_file function."""

    def setUp(self):
        """Set up test Flask app and temp file."""
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["DESKTOP_MODE"] = True
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

    def test_desktop_download_file_generates_html(self):
        """Test that desktop_download_file generates valid HTML."""
        result = desktop_download_file(self.temp_file.name, "test.json")
        
        self.assertIsInstance(result, str)
        self.assertIn("<!DOCTYPE html>", result)
        self.assertIn("test.json", result)
        self.assertIn("Blob", result)

    def test_desktop_download_file_with_custom_filename(self):
        """Test that desktop_download_file uses custom filename."""
        result = desktop_download_file(self.temp_file.name, "custom_name.json")
        
        self.assertIn("custom_name.json", result)

    def test_desktop_download_file_invalid_path(self):
        """Test that desktop_download_file handles invalid paths."""
        result = desktop_download_file("/nonexistent/file.json", "test.json")
        
        self.assertIn("Error", result)
        self.assertIn("Go back", result)

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

    @patch("y_web.utils.desktop_file_handler.desktop_download_file")
    def test_send_file_desktop_generates_html(self, mock_download):
        """Test that send_file_desktop generates HTML download page."""
        self.app.config["DESKTOP_MODE"] = True
        mock_download.return_value = "<html>Download page</html>"

        response = send_file_desktop(self.temp_file.name, as_attachment=True)

        mock_download.assert_called_once()
        self.assertIn(b"Download page", response.data)

    @patch("y_web.utils.desktop_file_handler.desktop_download_file")
    def test_send_file_desktop_with_download_name(self, mock_download):
        """Test that send_file_desktop uses download_name when provided."""
        self.app.config["DESKTOP_MODE"] = True
        mock_download.return_value = "<html>Download page</html>"

        response = send_file_desktop(
            self.temp_file.name, as_attachment=True, download_name="custom_name.json"
        )

        mock_download.assert_called_once()
        # Check that the custom filename was used
        call_args = mock_download.call_args
        self.assertEqual(call_args[0][1], "custom_name.json")


if __name__ == "__main__":
    unittest.main()
