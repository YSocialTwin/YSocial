"""
Tests for desktop file handler functionality.

This test suite validates the desktop mode file download feature.
The handler uses standard Flask send_file which PyWebview handles natively.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from flask import Flask

from y_web.utils.desktop_file_handler import (
    get_webview_window,
    is_desktop_mode,
    send_file_desktop,
)


class TestDesktopModeDetection(unittest.TestCase):
    """Test desktop mode detection functions."""

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


class TestSendFileDesktop(unittest.TestCase):
    """Test send_file_desktop function."""

    def setUp(self):
        """Set up test Flask app and temp file."""
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

    def test_send_file_desktop_returns_html_in_desktop_mode(self):
        """Test that send_file_desktop returns HTML download page in desktop mode."""
        self.app.config["DESKTOP_MODE"] = True

        response = send_file_desktop(self.temp_file.name, as_attachment=True)

        # In desktop mode with attachment, should return HTML response
        self.assertEqual(response.mimetype, "text/html")
        # HTML should contain the filename
        self.assertIn(
            os.path.basename(self.temp_file.name), response.get_data(as_text=True)
        )

    def test_send_file_desktop_with_download_name_in_html(self):
        """Test that send_file_desktop includes download_name in HTML response."""
        self.app.config["DESKTOP_MODE"] = True

        response = send_file_desktop(
            self.temp_file.name, as_attachment=True, download_name="custom_name.json"
        )

        # In desktop mode, should return HTML with custom filename
        self.assertEqual(response.mimetype, "text/html")
        html_content = response.get_data(as_text=True)
        self.assertIn("custom_name.json", html_content)

    @patch("y_web.utils.desktop_file_handler.send_file")
    def test_send_file_desktop_browser_mode(self, mock_send_file):
        """Test that send_file_desktop works in browser mode too."""
        self.app.config["DESKTOP_MODE"] = False
        mock_send_file.return_value = Mock()

        response = send_file_desktop(self.temp_file.name, as_attachment=True)

        # Should still call send_file
        mock_send_file.assert_called_once()


if __name__ == "__main__":
    unittest.main()
